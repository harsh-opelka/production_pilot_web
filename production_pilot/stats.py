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
    This is what lets a PLC that, say, has been READY since three days
    ago and never transitioned again show the full day as ready_seconds
    instead of zero.
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

import csv
import io
import json
from datetime import datetime, timedelta, timezone

from . import history
from .opcua_source import CONFIG_PATH

# The observed-time buckets. Everything in here is summed to form the
# productivity denominator, so UNTRACKED_KEY is deliberately NOT a member
# — see compute_daily_summary.
_SECONDS_KEYS = (
    "baking_seconds",
    "ready_seconds",
    "heating_seconds",
    "error_seconds",
    "cold_seconds",
    "offline_seconds",
)

#: Wall-clock time this server wasn't observing the machines (see
#: history.UNTRACKED_STATES). Reported alongside the buckets above, never
#: mixed into them.
_UNTRACKED_KEY = "untracked_seconds"

_CSV_HEADERS = [
    "Machine Group",
    "Unit",
    "Baking (min)",
    "Ready (min)",
    "Heating (min)",
    "Error (min)",
    "Cold (min)",
    "Offline (min)",
    "Untracked (min)",
    "Productivity (%)",
]


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


def compute_daily_summary(date: str) -> dict:
    rows = history.get_daily_transitions(date)
    day_start = _day_start(date)
    day_end = day_start + timedelta(days=1)  # this day's own midnight-to-midnight cap

    # Per-PLC state as of exactly 00:00:00 on `date`, carried over from
    # before the day started — a synthetic anchor, not a real row (see
    # get_last_transition_before). Lets a PLC that had zero transitions
    # on this day but was already in some state still get credited for
    # however long it sat in that state.
    carry_over = history.get_last_transition_before(day_start.strftime("%Y-%m-%dT%H:%M:%SZ"))

    by_plc: dict[str, list[dict]] = {}
    for row in rows:
        by_plc.setdefault(row["plc_ip"], []).append(row)

    if not by_plc and not carry_over:
        return {"date": date, "machines": []}

    is_today = date == today_local()
    now = datetime.now(timezone.utc)

    machines = []
    for plc_ip in set(by_plc) | set(carry_over):
        plc_rows = by_plc.get(plc_ip, [])
        anchor = carry_over.get(plc_ip)
        totals = {key: 0.0 for key in _SECONDS_KEYS}
        untracked = 0.0

        segments = []
        if anchor is not None:
            segments.append({**anchor, "start": day_start})
        segments.extend({**row, "start": _parse(row["timestamp"])} for row in plc_rows)

        for i, seg in enumerate(segments):
            start = seg["start"]

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
        total_tracked = sum(totals.values())
        productivity_pct = round((totals["baking_seconds"] / total_tracked) * 100, 1) if total_tracked > 0 else 0.0

        last = segments[-1]  # current identity as of the latest data that day
        machines.append(
            {
                "group_name": last["group_name"],
                "plc_ip": plc_ip,
                "unit_number": last["unit_number"],
                **{key: round(value) for key, value in totals.items()},
                _UNTRACKED_KEY: round(untracked),
                "productivity_pct": productivity_pct,
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
    so the frontend can show a placeholder instead of a false "0h 0m"."""
    date = today_local()
    summary = compute_daily_summary(date)
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
    waiting = sum(m["ready_seconds"] for m in machines)
    error = sum(m["error_seconds"] for m in machines)
    untracked = sum(m[_UNTRACKED_KEY] for m in machines)
    # _SECONDS_KEYS excludes _UNTRACKED_KEY, so server-downtime periods
    # are out of this denominator the same way they are per-machine.
    total_tracked = sum(sum(m[key] for key in _SECONDS_KEYS) for m in machines)
    productivity_pct = round((baking / total_tracked) * 100, 1) if total_tracked > 0 else 0.0

    return {
        "date": date,
        "has_data": True,
        "baking_seconds": baking,
        "waiting_seconds": waiting,
        "error_seconds": error,
        "untracked_seconds": untracked,
        "productivity_pct": productivity_pct,
    }


_ZERO_TOTALS = {**{key: 0 for key in _SECONDS_KEYS}, _UNTRACKED_KEY: 0}


def load_configured_plcs() -> list[dict]:
    """Direct, read-only parse of plc_config.json — deliberately NOT via
    OpcUaSource (constructing/using that opens real OPC UA connections,
    which would make a stats-page request — or server startup, see
    server.py _marker_plcs — block on unreachable PLCs).
    Mirrors OpcUaSource._load_config's unit_number convention (1-based
    index within each machine's plcs array) so labels line up with the
    live dashboard. Returns [] if unconfigured or the file is missing/
    corrupt — a fresh install just shows an empty table, not an error."""
    if not CONFIG_PATH.exists():
        return []
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    plcs = []
    for machine in data.get("machines", []):
        for index, ip in enumerate(machine.get("plcs", [])):
            plcs.append({"group_name": machine["name"], "plc_ip": ip, "unit_number": index + 1})
    return plcs


def with_all_configured_machines(summary: dict) -> dict:
    """
    Left-joins a compute_daily_summary() result against the CURRENTLY
    configured PLC list, so every configured machine gets a row — an
    all-zero one (00:00 everywhere, 0.0% productivity) if it has no
    state_transitions rows for that date yet, instead of silently not
    appearing. group_name/unit_number are taken from the current config
    for every row (not from historical transition data), so a
    zero-default row and a real-data row for the same PLC never disagree
    about its current name/position.

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
    it just walks whatever range it's given."""
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()

    days = []
    current = start_date
    while current <= end_date:
        days.append(compute_daily_summary(current.strftime("%Y-%m-%d")))
        current += timedelta(days=1)

    return {"start": start, "end": end, "days": days}


def to_csv(summary: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_CSV_HEADERS)
    for m in summary["machines"]:
        writer.writerow(
            [
                m["group_name"],
                m["unit_number"],
                round(m["baking_seconds"] / 60, 1),
                round(m["ready_seconds"] / 60, 1),
                round(m["heating_seconds"] / 60, 1),
                round(m["error_seconds"] / 60, 1),
                round(m["cold_seconds"] / 60, 1),
                round(m["offline_seconds"] / 60, 1),
                round(m[_UNTRACKED_KEY] / 60, 1),
                m["productivity_pct"],
            ]
        )
    return buf.getvalue()
