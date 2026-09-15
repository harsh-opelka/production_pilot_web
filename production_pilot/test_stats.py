"""
test_stats.py
--------------
Plain-assert self-tests for stats.compute_daily_summary(). No pytest
needed:

    python -m production_pilot.test_stats

Covers:
  1. Day-boundary carry-over — a PLC's state that started on a previous
     day and never transitioned again must still be credited for however
     long it held that day, not zero.
  2. Server-downtime exclusion — periods recorded under a lifecycle
     marker (SERVER_STOPPED / UNKNOWN, see history.UNTRACKED_STATES)
     count toward no state total, stay out of the productivity
     denominator, and are reported as untracked_seconds instead.
  3. Downtime carried across midnight — the originally reported bug:
     a server left off overnight must not hand the next day's summary a
     full day of whatever state each machine was last seen in.

Each scenario runs against its own throwaway sqlite file (history.DB_PATH
is repointed for the duration of this process) so none of this ever
touches the real history.db.
"""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from . import history, stats

PLC_IP = "192.168.178.200"
GROUP_NAME = "Test Group"
UNIT_NUMBER = 1

# Fixed past dates (relative to whatever "today" this process sees) so no
# walk resolves its open end via "now" — every day caps at its own
# midnight-to-midnight boundary, keeping expected durations exact
# regardless of when the test happens to run.
DAY2 = "2026-09-07"
DAY1 = (datetime.strptime(DAY2, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")


def _fresh_db() -> None:
    """Repoints history at an empty throwaway DB for the next scenario."""
    tmp_dir = tempfile.mkdtemp(prefix="pp_test_stats_")
    history.DB_PATH = Path(tmp_dir) / "history_test.db"
    history.init_db()


def _insert(conn: sqlite3.Connection, *, timestamp: str, old_state: str | None,
            new_state: str, was_online: int = 1) -> None:
    conn.execute(
        """
        INSERT INTO state_transitions
            (timestamp, group_name, plc_ip, unit_number, old_state, new_state, was_online)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (timestamp, GROUP_NAME, PLC_IP, UNIT_NUMBER, old_state, new_state, was_online),
    )


def _ts(base: datetime, **offset) -> str:
    return (base + timedelta(**offset)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _machine(summary: dict) -> dict:
    return next(m for m in summary["machines"] if m["plc_ip"] == PLC_IP)


def _check(label: str, actual, expected) -> bool:
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}")
    if not ok:
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")
    return ok


def test_day_boundary_carry_over() -> list[bool]:
    print("--- carry-over across midnight ---")
    _fresh_db()
    results = []
    day2_start = history.local_day_start_utc(DAY2)

    with sqlite3.connect(history.DB_PATH) as conn:
        # READY at 23:50 on day1 (10 min before day2's local midnight)...
        _insert(conn, timestamp=_ts(day2_start, minutes=-10), old_state="COLD", new_state="READY")
        # ...then BAKING at 08:00 on day2.
        _insert(conn, timestamp=_ts(day2_start, hours=8), old_state="READY", new_state="BAKING")
        conn.commit()

    m2 = _machine(stats.compute_daily_summary(DAY2))
    results.append(_check("day2 ready_seconds == 8h (carried over from day1)", m2["ready_seconds"], 8 * 3600))
    results.append(_check("day2 baking_seconds == 16h (08:00 -> day2 end)", m2["baking_seconds"], 16 * 3600))

    # day1's real 23:50 transition holds READY only to day1's own end (10
    # minutes) — it is NOT borrowed forward into day2's BAKING total.
    m1 = _machine(stats.compute_daily_summary(DAY1))
    results.append(_check("day1 ready_seconds == 10min (unaffected by carry-over)", m1["ready_seconds"], 10 * 60))
    results.append(_check("day1 baking_seconds == 0 (BAKING transition belongs to day2)", m1["baking_seconds"], 0))
    return results


def test_downtime_excluded_within_a_day() -> list[bool]:
    print()
    print("--- server downtime within one day ---")
    _fresh_db()
    results = []
    start = history.local_day_start_utc(DAY2)

    with sqlite3.connect(history.DB_PATH) as conn:
        _insert(conn, timestamp=_ts(start, hours=8), old_state="COLD", new_state="READY")
        _insert(conn, timestamp=_ts(start, hours=10), old_state="READY", new_state="BAKING")
        # Server shut down at 11:00, back up at 15:00. The UNKNOWN marker
        # and the poll loop's first row share an instant (as they do in
        # practice, a poll cycle apart); insertion order breaks the tie.
        _insert(conn, timestamp=_ts(start, hours=11), old_state="BAKING",
                new_state=history.SERVER_STOPPED_MARKER, was_online=0)
        _insert(conn, timestamp=_ts(start, hours=15), old_state=history.SERVER_STOPPED_MARKER,
                new_state=history.UNKNOWN_MARKER, was_online=0)
        _insert(conn, timestamp=_ts(start, hours=15), old_state=None, new_state="READY")
        conn.commit()

    m = _machine(stats.compute_daily_summary(DAY2))
    # 08:00 -> 10:00, plus 15:00 -> end of day.
    results.append(_check("ready_seconds == 11h (observed periods only)", m["ready_seconds"], 11 * 3600))
    results.append(_check("baking_seconds == 1h (10:00 -> 11:00)", m["baking_seconds"], 3600))
    results.append(_check("untracked_seconds == 4h (11:00 -> 15:00 downtime)", m["untracked_seconds"], 4 * 3600))
    # Marker rows carry was_online = 0, but "the server was down" is not
    # "the PLC was unreachable" and must not land in offline_seconds.
    results.append(_check("offline_seconds == 0 (markers are not offline)", m["offline_seconds"], 0))
    # 3600 baking / 43200 observed = 8.3%. Measured against wall-clock
    # time including the outage it would read 6.2% — the understated
    # number Management was previously being shown.
    results.append(_check("productivity_pct == 8.3 (observed time as denominator)", m["productivity_pct"], 8.3))
    return results


def test_downtime_carried_over_midnight() -> list[bool]:
    print()
    print("--- server off overnight (the reported bug) ---")
    _fresh_db()
    results = []
    day2_start = history.local_day_start_utc(DAY2)

    with sqlite3.connect(history.DB_PATH) as conn:
        # READY at 18:00 on day1, server stopped five minutes later...
        _insert(conn, timestamp=_ts(day2_start, hours=-6), old_state="COLD", new_state="READY")
        _insert(conn, timestamp=_ts(day2_start, hours=-5, minutes=-55), old_state="READY",
                new_state=history.SERVER_STOPPED_MARKER, was_online=0)
        # ...and back up at 09:00 the next morning.
        _insert(conn, timestamp=_ts(day2_start, hours=9), old_state=history.SERVER_STOPPED_MARKER,
                new_state=history.UNKNOWN_MARKER, was_online=0)
        _insert(conn, timestamp=_ts(day2_start, hours=9), old_state=None, new_state="READY")
        conn.commit()

    m = _machine(stats.compute_daily_summary(DAY2))
    # Before the fix this read 24h: the overnight stretch carried into
    # day2 as READY, so the whole day was credited to it.
    results.append(_check("day2 ready_seconds == 15h (09:00 -> end, not 24h)", m["ready_seconds"], 15 * 3600))
    results.append(_check("day2 untracked_seconds == 9h (midnight -> 09:00)", m["untracked_seconds"], 9 * 3600))
    results.append(_check("day2 offline_seconds == 0", m["offline_seconds"], 0))

    # day1 keeps only the five minutes it actually observed READY.
    m1 = _machine(stats.compute_daily_summary(DAY1))
    results.append(_check("day1 ready_seconds == 5min (18:00 -> 18:05)", m1["ready_seconds"], 5 * 60))
    results.append(_check("day1 untracked_seconds == 5h55m (18:05 -> midnight)",
                          m1["untracked_seconds"], 5 * 3600 + 55 * 60))
    return results


def test_ungraceful_shutdown_no_server_stopped_row() -> list[bool]:
    print()
    print("--- ungraceful shutdown (hard kill / crash: no SERVER_STOPPED row) ---")
    _fresh_db()
    results = []
    start = history.local_day_start_utc(DAY2)

    with sqlite3.connect(history.DB_PATH) as conn:
        # READY at 08:00. Process is then hard-killed a few seconds
        # later with NO SERVER_STOPPED row (taskkill /F, PyCharm's Stop
        # button on Windows, a crash, power loss — see server.py's
        # lifespan shutdown handler docstring on why this is the
        # unreliable half of the pair). The only evidence anything
        # happened at all is the next startup's UNKNOWN marker at 10:00
        # (~2h later), whose old_state is READY -- the state that was
        # active when the process died, NOT a SERVER_STOPPED row.
        _insert(conn, timestamp=_ts(start, hours=8), old_state="COLD", new_state="READY")
        _insert(conn, timestamp=_ts(start, hours=10), old_state="READY",
                new_state=history.UNKNOWN_MARKER, was_online=0)
        _insert(conn, timestamp=_ts(start, hours=10), old_state=None, new_state="READY")
        conn.commit()

    m = _machine(stats.compute_daily_summary(DAY2))
    # Before this fix, the 08:00->10:00 segment was bucketed under its
    # OWN new_state (READY) all the way to the next row's start (the
    # UNKNOWN marker) -- so the entire 2h outage read as ready_seconds,
    # and untracked_seconds only ever caught the UNKNOWN row's own
    # (near-instant) forward span. That's the exact bug report: Waiting
    # time inflated by real downtime, fixable only by clearing history.
    # ready_seconds should be ONLY the genuine post-restart span
    # (10:00 -> day end, 14h) -- the pre-outage 08:00->10:00 span is
    # untrustworthy in full and must NOT also be folded into this total.
    results.append(_check("ready_seconds == 14h (only the genuine post-restart span, 10:00 -> day end)",
                          m["ready_seconds"], 14 * 3600))
    results.append(_check("untracked_seconds == 2h (08:00 -> 10:00, the whole unobserved span, not just the marker instant)",
                          m["untracked_seconds"], 2 * 3600))
    return results


def test_today_restart_boundary() -> list[bool]:
    print()
    print("--- today's restart boundary (server_started_at) ---")
    _fresh_db()
    results = []
    today = stats.today_local()
    today_start = history.local_day_start_utc(today)
    restart_at = _ts(today_start, hours=1)

    with sqlite3.connect(history.DB_PATH) as conn:
        # Pre-restart: READY starting 40 minutes before the simulated
        # restart instant (today_start+01:00) -- this must be discarded
        # entirely, not folded into today's ready_seconds.
        _insert(conn, timestamp=_ts(today_start, minutes=20), old_state="COLD", new_state="READY")
        # Post-restart, as the poll loop's own first cycles would log:
        # carried-over READY until the first real transition, then BAKING,
        # then COLD (left open so its duration depends on "now" and isn't
        # asserted here).
        _insert(conn, timestamp=_ts(today_start, hours=1, minutes=30), old_state="READY", new_state="BAKING")
        _insert(conn, timestamp=_ts(today_start, hours=2), old_state="BAKING", new_state="COLD")
        conn.commit()

    history.set_server_started_at(restart_at)
    m = _machine(stats.compute_daily_summary(today))
    results.append(_check("ready_seconds == 30min (restart -> first post-restart transition only)",
                          m["ready_seconds"], 30 * 60))
    results.append(_check("baking_seconds == 30min (01:30 -> 02:00, unaffected once past the boundary)",
                          m["baking_seconds"], 30 * 60))

    # A past date must never be subject to the restart boundary, even if
    # a (bogus, for this test) server_started_at instant falls inside it.
    _fresh_db()
    day2_start = history.local_day_start_utc(DAY2)
    with sqlite3.connect(history.DB_PATH) as conn:
        _insert(conn, timestamp=_ts(day2_start, minutes=-10), old_state="COLD", new_state="READY")
        _insert(conn, timestamp=_ts(day2_start, hours=8), old_state="READY", new_state="BAKING")
        conn.commit()
    history.set_server_started_at(_ts(day2_start, hours=12))
    m2 = _machine(stats.compute_daily_summary(DAY2))
    results.append(_check("past date ready_seconds == 8h (restart boundary ignored for non-today dates)",
                          m2["ready_seconds"], 8 * 3600))
    results.append(_check("past date baking_seconds == 16h (restart boundary ignored for non-today dates)",
                          m2["baking_seconds"], 16 * 3600))
    return results


def main() -> bool:
    results = []
    for scenario in (
        test_day_boundary_carry_over,
        test_downtime_excluded_within_a_day,
        test_downtime_carried_over_midnight,
        test_ungraceful_shutdown_no_server_stopped_row,
        test_today_restart_boundary,
    ):
        results.extend(scenario())

    all_passed = all(results)
    print()
    print("ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
