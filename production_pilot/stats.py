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
from datetime import datetime, timedelta, timezone

from . import history

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
