"""
stats.py
--------
Aggregates history.py's raw state_transitions event log into per-day,
per-machine summaries for the Statistics screen. Kept separate from
history.py (which only owns raw storage/access) since this is
presentation-layer computation, not storage.

Deliberately computed in Python after fetching a day's rows, not as one
big SQL query — the per-PLC duration walk (this transition's timestamp
to the next one) is much easier to get right and debug this way, and a
day's row count is small enough (recording is a deliberate on/off
toggle, not always-on telemetry) that this costs nothing in practice.

Duration-walk rules (see compute_daily_summary):
  - Each PLC's walk starts either at its first real transition of the
    day, or — if it has a transition from BEFORE the day that carried
    into it untouched — at 00:00:00 local with that carried-over state
    as a synthetic starting point (see history.get_last_transition_before).
    This is what lets a PLC that, say, has been WAITING since three days
    ago and never transitioned again show the full day as waiting_seconds
    instead of zero.
  - compute_daily_summary takes a `boundary_mode` of "since_restart" or
    "full_day":
      - "since_restart": TODAY ONLY, the "00:00:00 local" start boundary
        itself slides forward to this process's own startup instant
        whenever that's later than local midnight (see
        history.get_server_started_at) — every restart makes today's
        totals start accumulating fresh from the moment the server came
        back up, rather than from midnight or from whatever had already
        accumulated pre-restart. This is what the shop-floor top-bar KPI
        (compute_today_totals) uses, so it resets on every restart.
      - "full_day": the boundary always stays at plain local midnight,
        even for today — a restart never resets these totals. This is
        what the Statistics page (compute_daily_summary's other callers)
        uses, so a manager's daily report is trustworthy across routine
        reboots.
    Any date strictly before today always keeps the plain
    midnight-to-midnight boundary regardless of boundary_mode — a closed
    historical day is never touched by either mode.
  - A segment's duration runs from its own start to the NEXT segment's
    start, for the same PLC.
  - was_online == 0 always counts as offline_seconds, regardless of
    new_state — a PLC's last-known state while offline isn't trustworthy
    (see opcua_source.py: state is left stale when a PLC drops offline).
  - A segment whose state is one of history.UNTRACKED_STATES
    (SERVER_STOPPED / UNKNOWN) is time this server was NOT observing the
    machines — server down, or the stretch before this session started
    watching. It counts toward neither any *_seconds total nor the
    productivity denominator; it's reported separately as
    untracked_seconds so the gap is auditable instead of silently
    dropped. Without this, a server left off overnight would credit the
    whole outage to whatever state each PLC was last seen in.
  - A segment whose NEXT row is an UNKNOWN marker is ALSO excluded as
    untracked, even though the segment's own state is a real one. A
    graceful shutdown writes SERVER_STOPPED before the next startup's
    UNKNOWN, closing the real segment off at that known instant — that
    case is already handled by the rule above and is unaffected here.
    But SERVER_STOPPED is only best-effort (a hard kill, crash, or power
    loss never reaches it — see server.py's lifespan shutdown handler),
    so a segment can run straight into an UNKNOWN marker with no
    SERVER_STOPPED ever recorded for it. Nothing then pins down when
    within that segment the server actually stopped observing, so
    trusting its own state for the full span would silently hand the
    entire outage to whatever state was active when the process died —
    this was a real, reproduced bug (inflated daily Waiting time that
    persisted across a restart, fixable only by clearing all history).
    UNKNOWN's own docstring is "we don't know what happened before this
    point in this session" — this rule is what actually makes that true
    even when its SERVER_STOPPED counterpart never fired.
  - The LAST segment of the day per PLC has no "next segment" within the
    day, so its end boundary is resolved as:
      1. "now" if `date` is today and no further transition has happened
         yet (the state is still ongoing — don't silently drop it);
      2. otherwise, that day's own midnight-to-midnight boundary. A
         transition that carries past this day's end simply becomes the
         following day's carried-over starting anchor (see rule above) —
         it is NOT also borrowed forward into this day's own total, or
         a state spanning a day boundary would get double-counted on
         both sides of it.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import history
from .opcua_source import CONFIG_PATH
from .plc_config import load_config

# The observed-time buckets, one per displayed MachineState (named
# f"{state.name.lower()}_seconds") plus offline. UNRECOGNIZED (an
# unexpected PLC value) has no bucket, so that time is left out of every
# column and of the denominator. Everything in here is
# summed to form the productivity denominator, so UNTRACKED_KEY is
# deliberately NOT a member — see compute_daily_summary and
# productivity_pct.
_SECONDS_KEYS = (
    "baking_seconds",
    "waiting_seconds",
    "heating_seconds",
    "hot_seconds",
    "blocked_seconds",
    "error_seconds",
    "cold_seconds",
    # Standby with an unreadable oil temperature — normally Standby shows
    # up as cold_seconds / hot_seconds instead (see hot_cold.py).
    "standby_seconds",
    "offline_seconds",
)

#: Wall-clock time this server wasn't observing the machines (see
#: history.UNTRACKED_STATES). Reported alongside the buckets above, never
#: mixed into them.
_UNTRACKED_KEY = "untracked_seconds"


def productivity_pct(baking_seconds: float, tracked_seconds: float) -> float:
    """THE productivity formula, shared by every caller: baking time over
    all observed time (the sum of _SECONDS_KEYS — so Cold, Hot, Standby,
    Blocked, Heating, Waiting, Error and Offline all count as available
    time for now; still to be decided whether Cold/Hot/Standby/Blocked
    should). 0.0 when nothing was observed."""
    return round((baking_seconds / tracked_seconds) * 100, 1) if tracked_seconds > 0 else 0.0


def today_local() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _day_start(date: str) -> datetime:
    """The UTC instant of local midnight starting `date` — see
    history.local_day_start_utc for why this must be local-day-aware
    rather than treating `date` as literally UTC midnight (state
    transitions are UTC-stamped, but "today"/a picked date is a local
    calendar concept)."""
    return history.local_day_start_utc(date)


def _gather_daily_rows(date: str, boundary_mode: str) -> tuple[datetime, datetime, bool, dict[str, list[dict]], dict[str, dict]]:
    """Shared setup for compute_daily_summary and compute_timeline: resolves
    the day's start boundary (per boundary_mode — see module docstring),
    fetches this day's rows trimmed to it, and the carry-over anchor per
    PLC. Returns (day_start, day_end, is_today, by_plc, carry_over)."""
    if boundary_mode not in ("since_restart", "full_day"):
        raise ValueError(f"invalid boundary_mode: {boundary_mode!r}")

    is_today = date == today_local()
    day_start = _day_start(date)
    day_end = day_start + timedelta(days=1)  # this day's own midnight-to-midnight cap

    # TODAY ONLY, and only in "since_restart" mode: the day's own effective
    # start slides forward to this process's own startup instant, if
    # that's later than local midnight — every restart makes "today" start
    # accumulating fresh from that moment instead of from 00:00:00 (see
    # history.get_server_started_at's docstring). "full_day" mode never
    # applies this, even for today — that's what keeps the Statistics
    # page's daily report intact across a routine restart. Any date
    # strictly before today always keeps the plain midnight boundary
    # computed above — a closed historical day is never touched by this,
    # regardless of boundary_mode or of when the server happens to restart.
    if is_today and boundary_mode == "since_restart":
        started_at = history.get_server_started_at()
        if started_at is not None:
            day_start = max(day_start, _parse(started_at))
    day_start_str = day_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Rows are fetched for the full calendar day (get_daily_transitions is
    # unaware of the restart boundary), then trimmed to day_start — a
    # no-op for any non-today date, since day_start there is still exactly
    # local midnight.
    rows = [row for row in history.get_daily_transitions(date) if row["timestamp"] >= day_start_str]

    # Per-PLC state as of exactly `day_start` (local midnight, or — today,
    # post-restart — this session's startup instant), carried over from
    # before that instant — a synthetic anchor, not a real row (see
    # get_last_transition_before). Lets a PLC that had zero transitions
    # since `day_start` but was already in some state still get credited
    # for however long it sat in that state.
    carry_over = history.get_last_transition_before(day_start_str)

    by_plc: dict[str, list[dict]] = {}
    for row in rows:
        by_plc.setdefault(row["plc_ip"], []).append(row)

    return day_start, day_end, is_today, by_plc, carry_over


def _plc_segments(plc_ip: str, by_plc: dict[str, list[dict]], carry_over: dict[str, dict], day_start: datetime) -> list[dict]:
    """The carry-over anchor (if any) plus this PLC's real rows for the
    day, each with a resolved 'start' datetime — the raw segment list both
    compute_daily_summary and compute_timeline walk (see module
    docstring's duration-walk rules)."""
    plc_rows = by_plc.get(plc_ip, [])
    anchor = carry_over.get(plc_ip)
    segments = []
    if anchor is not None:
        segments.append({**anchor, "start": day_start})
    segments.extend({**row, "start": _parse(row["timestamp"])} for row in plc_rows)
    return segments


def _resolve_span_end(
    segments: list[dict], i: int, day_end: datetime, is_today: bool, now: datetime
) -> tuple[datetime, bool]:
    """Resolves segment i's end instant, and whether it's poisoned by a
    following UNKNOWN marker — see module docstring's duration-walk rules
    for both. Shared by compute_daily_summary (duration totals) and
    compute_timeline (span boundaries)."""
    if i + 1 < len(segments):
        end = segments[i + 1]["start"]
        # UNKNOWN means "we don't know what happened before this
        # instant this session" — see history.py's docstring. The
        # matching SERVER_STOPPED row (written on a graceful
        # shutdown) is what would normally close off the segment
        # right before it at a KNOWN clean boundary; without one,
        # nothing pins down when within this segment the server
        # actually stopped observing. SERVER_STOPPED is only
        # best-effort (never fires on a hard kill / crash / power
        # loss — see server.py's _write_server_marker), so a
        # segment can end at UNKNOWN with no SERVER_STOPPED ever
        # having been written for it at all. Trusting seg's own
        # new_state in that case would silently hand the entire
        # unobserved gap to whatever state was active when the
        # process died — exactly the inflated-Waiting-time bug
        # this fixes. Only UNKNOWN retroactively poisons its
        # predecessor this way; SERVER_STOPPED itself is always
        # already caught by the UNTRACKED_STATES check below, so
        # a segment that ends there (a clean shutdown) keeps its
        # real, fully-trusted duration.
        poisoned_by_unknown = segments[i + 1]["new_state"] == history.UNKNOWN_MARKER
    elif is_today:
        end = now
        poisoned_by_unknown = False
    else:
        end = day_end
        poisoned_by_unknown = False
    return end, poisoned_by_unknown


def compute_daily_summary(date: str, boundary_mode: str = "full_day") -> dict:
    """boundary_mode is "since_restart" (top-bar KPI — see
    compute_today_totals) or "full_day" (Statistics page — see this
    module's docstring). Only affects TODAY's start boundary; any other
    date always uses the plain midnight boundary regardless."""
    day_start, day_end, is_today, by_plc, carry_over = _gather_daily_rows(date, boundary_mode)

    if not by_plc and not carry_over:
        return {"date": date, "machines": []}

    now = datetime.now(timezone.utc)
    unit_numbers = _configured_unit_numbers()

    machines = []
    for plc_ip in set(by_plc) | set(carry_over):
        plc_rows = by_plc.get(plc_ip, [])
        segments = _plc_segments(plc_ip, by_plc, carry_over, day_start)
        totals = {key: 0.0 for key in _SECONDS_KEYS}
        untracked = 0.0

        for i, seg in enumerate(segments):
            start = seg["start"]
            end, poisoned_by_unknown = _resolve_span_end(segments, i, day_end, is_today, now)
            duration = max(0.0, (end - start).total_seconds())

            # Checked BEFORE was_online: a marker row carries
            # was_online = 0 (we had no connection to anything), but
            # "the server wasn't running" is not the same fact as "the
            # PLC was unreachable" and must not land in offline_seconds.
            if seg["new_state"] in history.UNTRACKED_STATES or poisoned_by_unknown:
                untracked += duration
            elif not seg["was_online"]:
                totals["offline_seconds"] += duration
            else:
                key = f"{seg['new_state'].lower()}_seconds"
                if key in totals:
                    totals[key] += duration
                # else: unrecognized state name in old data — ignore
                # rather than crash; new_state always comes from
                # MachineState.name in normal operation.

        # Denominator is observed time only (untracked is excluded from
        # `totals` by construction), so productivity is baking over the
        # time we were actually watching — not over wall-clock time that
        # happens to include an outage.
        machine_productivity = productivity_pct(totals["baking_seconds"], sum(totals.values()))

        # Counts genuine transitions INTO ERROR within the period — i.e.
        # real rows only (plc_rows, already trimmed to day_start), not the
        # synthetic carry-over anchor (that transition happened before the
        # period started, so counting it here would attribute an error
        # that occurred on some earlier day to this one). UNKNOWN/
        # SERVER_STOPPED markers never have new_state == "ERROR" so they're
        # excluded automatically, matching the task's requirement.
        error_count = sum(1 for row in plc_rows if row["new_state"] == "ERROR")

        last = segments[-1]  # current identity as of the latest data that day
        machines.append(
            {
                "group_name": last["group_name"],
                "plc_ip": plc_ip,
                "unit_number": unit_numbers.get(plc_ip, last["unit_number"]),
                **{key: round(value) for key, value in totals.items()},
                _UNTRACKED_KEY: round(untracked),
                "productivity_pct": machine_productivity,
                "error_count": error_count,
            }
        )

    machines.sort(key=lambda m: (m["group_name"], m["unit_number"]))
    return {"date": date, "machines": machines}


def compute_timeline(date: str) -> dict:
    """Per-PLC ordered state spans across `date` (00:00-24:00 local, or
    00:00-now for today) — for the Statistics page's Timeline view. Same
    day-boundary/carry-forward/UNKNOWN-poisoning rules as
    compute_daily_summary (see module docstring), but returns the spans
    themselves rather than aggregated durations. Always boundary_mode=
    "full_day" — like the rest of the Statistics page, a routine restart
    must not truncate today's timeline.

    Untracked spans (UNTRACKED_STATES, or a real span poisoned by a
    following UNKNOWN — see module docstring) are represented explicitly
    as state "NO_DATA" rather than omitted, so a manager can see exactly
    when this server wasn't observing the machines instead of a
    fabricated gap-free timeline."""
    day_start, day_end, is_today, by_plc, carry_over = _gather_daily_rows(date, boundary_mode="full_day")
    now = datetime.now(timezone.utc)
    unit_numbers = _configured_unit_numbers()

    machines = []
    for plc_ip in set(by_plc) | set(carry_over):
        segments = _plc_segments(plc_ip, by_plc, carry_over, day_start)
        spans = []
        for i, seg in enumerate(segments):
            start = seg["start"]
            end, poisoned_by_unknown = _resolve_span_end(segments, i, day_end, is_today, now)
            is_untracked = seg["new_state"] in history.UNTRACKED_STATES or poisoned_by_unknown
            spans.append(
                {
                    "state": "NO_DATA" if is_untracked else seg["new_state"],
                    "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "is_online": False if is_untracked else bool(seg["was_online"]),
                }
            )

        last = segments[-1]
        machines.append(
            {
                "group_name": last["group_name"],
                "plc_ip": plc_ip,
                "unit_number": unit_numbers.get(plc_ip, last["unit_number"]),
                "spans": spans,
            }
        )

    machines.sort(key=lambda m: (m["group_name"], m["unit_number"]))
    return {"date": date, "machines": machines}


def compute_today_totals() -> dict:
    """Dashboard-top-bar aggregate: sums compute_daily_summary's per-machine
    rows for today across ALL machines into one glanceable total, instead of
    per-machine rows (that's the Statistics screen's job). Same underlying
    computation as /api/stats/daily-summary — just summed differently.

    has_data mirrors compute_daily_summary's own "no rows at all" signal
    (recording off, or nothing logged yet today) rather than re-deriving it,
    so the frontend can show a placeholder instead of a false "0h 0m".

    Uses boundary_mode="since_restart" — this is the shop-floor top-bar
    KPI, which is deliberately meant to reset on every server restart
    (unlike the Statistics page's "full_day" totals — see this module's
    docstring)."""
    date = today_local()
    summary = compute_daily_summary(date, boundary_mode="since_restart")
    machines = summary["machines"]
    if not machines:
        return {
            "date": date,
            "has_data": False,
            "baking_seconds": 0,
            "waiting_seconds": 0,
            "error_seconds": 0,
            "untracked_seconds": 0,
            "productivity_pct": 0.0,
        }

    baking = sum(m["baking_seconds"] for m in machines)
    waiting = sum(m["waiting_seconds"] for m in machines)
    error = sum(m["error_seconds"] for m in machines)
    untracked = sum(m[_UNTRACKED_KEY] for m in machines)
    # _SECONDS_KEYS excludes _UNTRACKED_KEY, so server-downtime periods
    # are out of this denominator the same way they are per-machine.
    total_tracked = sum(sum(m[key] for key in _SECONDS_KEYS) for m in machines)

    return {
        "date": date,
        "has_data": True,
        "baking_seconds": baking,
        "waiting_seconds": waiting,
        "error_seconds": error,
        "untracked_seconds": untracked,
        "productivity_pct": productivity_pct(baking, total_tracked),
    }


_TOTALS_FIELDS = ("baking_seconds", "waiting_seconds", "error_seconds", "cold_seconds", "offline_seconds")


def compute_totals(machines: list[dict]) -> dict:
    """Aggregates a compute_daily_summary()-shaped machines list (after
    with_all_configured_machines, typically) into one across-all-machines
    totals object — the shape /api/stats/daily-summary's top-level
    "totals" field uses, and what "comparison.averages" is averaged
    from (see compute_seven_day_average). productivity_pct is the weighted total (baking
    over all machines' tracked time), matching compute_today_totals — NOT
    an average of the per-machine percentages, which would misweight a
    lightly-observed machine the same as a heavily-observed one."""
    if not machines:
        return {**{key: 0 for key in _TOTALS_FIELDS}, "error_count": 0, "productivity_pct": 0.0}

    totals = {key: sum(m[key] for m in machines) for key in _TOTALS_FIELDS}
    error_count = sum(m["error_count"] for m in machines)
    # _SECONDS_KEYS (not _TOTALS_FIELDS) is the full observed-time set —
    # includes heating/hot/blocked, which _TOTALS_FIELDS deliberately omits
    # from the reported totals shape but which still count as tracked
    # time for the denominator, exactly as in compute_today_totals.
    total_tracked = sum(sum(m[key] for key in _SECONDS_KEYS) for m in machines)

    return {
        **totals,
        "error_count": error_count,
        "productivity_pct": productivity_pct(totals["baking_seconds"], total_tracked),
    }


#: How many days BEFORE the selected date form the KPI cards' baseline
#: (see compute_seven_day_average).
AVERAGE_WINDOW_DAYS = 7

_DELTA_FIELDS = ("baking_seconds", "error_seconds", "error_count", "productivity_pct")


def compute_seven_day_average(date: str, current_totals: dict) -> dict | None:
    """The "vs 7-day average" baseline for /api/stats/daily-summary's
    "comparison" field: across-all-machines totals averaged over the
    AVERAGE_WINDOW_DAYS days immediately BEFORE `date` (date-7 .. date-1;
    `date` itself is excluded so today never pulls its own baseline
    toward itself), plus current-minus-average deltas. `current_totals`
    is the caller's already-computed compute_totals() for `date`.

    Window days are closed past days, so each uses boundary_mode=
    "full_day" (plain midnight-to-midnight) — the selected date's own
    totals keep whatever boundary the caller used.

    Only days with recorded data count toward the average — checked
    against the RAW compute_daily_summary result (genuinely empty
    machines list), not the configured-machines-left-joined one. A day
    the recorder was off is "unknown", not "zero"; averaging it in as
    zero would make every normal day look like an improvement. Returns
    None (not a zeroed-out dict) when NO day in the window has data, so
    the frontend shows "no comparison data" instead of a misleading delta.

    The Productivity card is compared against the configured target on
    the frontend instead (see KpiRow.svelte); the averaged
    productivity_pct (mean of the daily weighted percentages) is still
    returned here for completeness."""
    selected = datetime.strptime(date, "%Y-%m-%d").date()
    window_start = selected - timedelta(days=AVERAGE_WINDOW_DAYS)
    window_end = selected - timedelta(days=1)

    day_totals = []
    current = window_start
    while current <= window_end:
        raw = compute_daily_summary(current.strftime("%Y-%m-%d"), boundary_mode="full_day")
        if raw["machines"]:
            day_totals.append(compute_totals(with_all_configured_machines(raw)["machines"]))
        current += timedelta(days=1)

    if not day_totals:
        return None

    n = len(day_totals)
    averages = {key: round(sum(t[key] for t in day_totals) / n, 1) for key in _DELTA_FIELDS}
    deltas = {key: round(current_totals[key] - averages[key], 1) for key in _DELTA_FIELDS}

    return {
        "basis": "avg_7d",
        "window_start": window_start.strftime("%Y-%m-%d"),
        "window_end": window_end.strftime("%Y-%m-%d"),
        "days_with_data": n,
        "averages": averages,
        "deltas": deltas,
    }


_ZERO_TOTALS = {**{key: 0 for key in _SECONDS_KEYS}, _UNTRACKED_KEY: 0, "error_count": 0}


def load_configured_plcs() -> list[dict]:
    """Direct, read-only parse of plc_config.json — deliberately NOT via
    OpcUaSource (constructing/using that opens real OPC UA connections,
    which would make a stats-page request — or server startup, see
    server.py _marker_plcs — block on unreachable PLCs).
    unit_number is the configured machine number (see plc_config.py),
    same value OpcUaSource uses, so labels line up with the live
    dashboard. Returns [] if unconfigured or the file is missing/
    corrupt — a fresh install just shows an empty table, not an error."""
    if not CONFIG_PATH.exists():
        return []
    try:
        data = load_config(CONFIG_PATH)
    except (json.JSONDecodeError, OSError, KeyError, ValueError):
        return []

    plcs = []
    for machine in data.get("machines", []):
        for entry in machine["plcs"]:
            plcs.append({"group_name": machine["name"], "plc_ip": entry["ip"], "unit_number": entry["unit_number"]})
    return plcs


def _configured_unit_numbers() -> dict[str, int]:
    """plc_ip -> machine number from the CURRENT config. History rows keep
    whatever unit_number was stored when they were written (never
    rewritten), so anything displayed looks the number up here by IP and
    only falls back to the row's own value for an IP no longer configured."""
    return {plc["plc_ip"]: plc["unit_number"] for plc in load_configured_plcs()}


def with_all_configured_machines(summary: dict) -> dict:
    """
    Left-joins a compute_daily_summary() result against the CURRENTLY
    configured PLC list, so every configured machine gets a row — an
    all-zero one (00:00 everywhere, 0.0% productivity) if it has no
    state_transitions rows for that date yet, instead of silently not
    appearing. group_name/unit_number are taken from the current config
    for every row (not from historical transition data), so a
    zero-default row and a real-data row for the same PLC never disagree
    about its current name/machine number.

    Deliberately NOT folded into compute_daily_summary itself:
    compute_range_summary (and the Trend charts) rely on a day's
    machines list being genuinely EMPTY to mean "no data recorded that
    day" so it can plot an honest gap rather than a false zero — see
    compute_range_summary's docstring. Only the single-day
    /api/stats/daily-summary (+ its CSV export) applies this; the range
    endpoint calls compute_daily_summary directly and keeps its original
    behaviour.

    If nothing is configured at all (a fresh/unconfigured install),
    returns an empty machines list — the frontend's "No data recorded"
    empty state is reserved for that case, not for "configured but
    nothing logged yet".
    """
    configured = load_configured_plcs()
    if not configured:
        return {"date": summary["date"], "machines": []}

    by_ip = {m["plc_ip"]: m for m in summary["machines"]}
    machines = []
    for plc in configured:
        existing = by_ip.get(plc["plc_ip"])
        base = existing if existing is not None else {**_ZERO_TOTALS, "productivity_pct": 0.0}
        machines.append({**base, "group_name": plc["group_name"], "plc_ip": plc["plc_ip"], "unit_number": plc["unit_number"]})

    machines.sort(key=lambda m: (m["group_name"], m["unit_number"]))
    return {"date": summary["date"], "machines": machines}


def compute_range_summary(start: str, end: str) -> dict:
    """One compute_daily_summary() call per day in [start, end] (inclusive)
    — the exact same per-day computation as the single-date endpoint, not
    a separate implementation. Callers (server.py) are responsible for
    validating start <= end and the 90-day range cap before calling this;
    it just walks whatever range it's given.

    Always uses boundary_mode="full_day" (the Trend charts this feeds are
    Statistics-page reporting, same as the single-date endpoint — see this
    module's docstring)."""
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()

    days = []
    current = start_date
    while current <= end_date:
        days.append(compute_daily_summary(current.strftime("%Y-%m-%d"), boundary_mode="full_day"))
        current += timedelta(days=1)

    return {"start": start, "end": end, "days": days}

