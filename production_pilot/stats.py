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
  - A row's duration runs from its own timestamp to the NEXT row's
    timestamp, for the same PLC.
  - was_online == 0 always counts as offline_seconds, regardless of
    new_state — a PLC's last-known state while offline isn't trustworthy
    (see opcua_source.py: state is left stale when a PLC drops offline).
  - The LAST row of the day per PLC has no "next row" within the day, so
    its end boundary is resolved as:
      1. the PLC's actual next transition, if it falls within the
         immediately following calendar day ("next day's first
         transition" per the spec) — this correctly captures a state
         that carried a few hours into the next day;
      2. otherwise, "now" if `date` is today (the state is still
         ongoing — don't silently drop it);
      3. otherwise (a past date with no nearby follow-up transition),
         cap at that day's own midnight-to-midnight boundary. This is
         deliberately NOT "extend to whatever the next transition ever
         is" — if a PLC didn't transition again for, say, 5 days, that
         entire gap must not get dumped into a single day's total.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

from . import history
from .opcua_source import CONFIG_PATH

_SECONDS_KEYS = (
    "baking_seconds",
    "ready_seconds",
    "heating_seconds",
    "error_seconds",
    "cold_seconds",
    "offline_seconds",
)

_CSV_HEADERS = [
    "Machine Group",
    "Unit",
    "IP",
    "Baking (min)",
    "Ready (min)",
    "Heating (min)",
    "Error (min)",
    "Cold (min)",
    "Offline (min)",
    "Productivity (%)",
]


def today_local() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _day_start(date: str) -> datetime:
    return datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def compute_daily_summary(date: str) -> dict:
    rows = history.get_daily_transitions(date)
    if not rows:
        return {"date": date, "machines": []}

    is_today = date == today_local()
    now = datetime.now(timezone.utc)
    day_end = _day_start(date) + timedelta(days=1)  # this day's own midnight-to-midnight cap
    next_day_end = day_end + timedelta(days=1)  # upper bound for "next day's first transition"

    by_plc: dict[str, list[dict]] = {}
    for row in rows:
        by_plc.setdefault(row["plc_ip"], []).append(row)

    machines = []
    for plc_ip, plc_rows in by_plc.items():
        totals = {key: 0.0 for key in _SECONDS_KEYS}

        for i, row in enumerate(plc_rows):
            start = _parse(row["timestamp"])

            if i + 1 < len(plc_rows):
                end = _parse(plc_rows[i + 1]["timestamp"])
            else:
                nxt = history.get_next_transition_after(plc_ip, row["timestamp"])
                nxt_time = _parse(nxt["timestamp"]) if nxt else None
                if nxt_time is not None and nxt_time < next_day_end:
                    end = nxt_time
                elif is_today:
                    end = now
                else:
                    end = day_end

            duration = max(0.0, (end - start).total_seconds())

            if not row["was_online"]:
                totals["offline_seconds"] += duration
            else:
                key = f"{row['new_state'].lower()}_seconds"
                if key in totals:
                    totals[key] += duration
                # else: unrecognized state name in old data — ignore
                # rather than crash; new_state always comes from
                # MachineState.name in normal operation.

        total_tracked = sum(totals.values())
        productivity_pct = round((totals["baking_seconds"] / total_tracked) * 100, 1) if total_tracked > 0 else 0.0

        last = plc_rows[-1]  # current identity as of the latest data that day
        machines.append(
            {
                "group_name": last["group_name"],
                "plc_ip": plc_ip,
                "unit_number": last["unit_number"],
                **{key: round(value) for key, value in totals.items()},
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
            "productivity_pct": 0.0,
        }

    baking = sum(m["baking_seconds"] for m in machines)
    waiting = sum(m["ready_seconds"] for m in machines)
    error = sum(m["error_seconds"] for m in machines)
    total_tracked = sum(sum(m[key] for key in _SECONDS_KEYS) for m in machines)
    productivity_pct = round((baking / total_tracked) * 100, 1) if total_tracked > 0 else 0.0

    return {
        "date": date,
        "has_data": True,
        "baking_seconds": baking,
        "waiting_seconds": waiting,
        "error_seconds": error,
        "productivity_pct": productivity_pct,
    }


_ZERO_TOTALS = {key: 0 for key in _SECONDS_KEYS}


def _load_configured_plcs() -> list[dict]:
    """Direct, read-only parse of plc_config.json — deliberately NOT via
    OpcUaSource (constructing/using that opens real OPC UA connections,
    which would make a stats-page request block on unreachable PLCs).
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
    configured = _load_configured_plcs()
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
                m["plc_ip"],
                round(m["baking_seconds"] / 60, 1),
                round(m["ready_seconds"] / 60, 1),
                round(m["heating_seconds"] / 60, 1),
                round(m["error_seconds"] / 60, 1),
                round(m["cold_seconds"] / 60, 1),
                round(m["offline_seconds"] / 60, 1),
                m["productivity_pct"],
            ]
        )
    return buf.getvalue()
