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
  4. Hot / Blocked buckets, and the one-time READY -> WAITING history
     migration for state mapping v2 (idempotent, backed up, runs once).

Each scenario runs against its own throwaway sqlite file (history.DB_PATH
is repointed for the duration of this process) so none of this ever
touches the real history.db.
"""

from __future__ import annotations

import json
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


def _fresh_config() -> None:
    """Repoints stats.CONFIG_PATH at a throwaway plc_config.json containing
    only this module's test PLC — with_all_configured_machines (used by
    compute_seven_day_average) otherwise reads the real install's config, which
    would silently substitute whatever machines happen to be configured
    on this machine for the test's own PLC_IP."""
    tmp_dir = tempfile.mkdtemp(prefix="pp_test_stats_config_")
    config_path = Path(tmp_dir) / "plc_config_test.json"
    config_path.write_text(
        json.dumps({"machines": [{"name": GROUP_NAME, "plcs": [PLC_IP]}]}), encoding="utf-8"
    )
    stats.CONFIG_PATH = config_path


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
        # WAITING at 23:50 on day1 (10 min before day2's local midnight)...
        _insert(conn, timestamp=_ts(day2_start, minutes=-10), old_state="COLD", new_state="WAITING")
        # ...then BAKING at 08:00 on day2.
        _insert(conn, timestamp=_ts(day2_start, hours=8), old_state="WAITING", new_state="BAKING")
        conn.commit()

    m2 = _machine(stats.compute_daily_summary(DAY2))
    results.append(_check("day2 waiting_seconds == 8h (carried over from day1)", m2["waiting_seconds"], 8 * 3600))
    results.append(_check("day2 baking_seconds == 16h (08:00 -> day2 end)", m2["baking_seconds"], 16 * 3600))

    # day1's real 23:50 transition holds WAITING only to day1's own end (10
    # minutes) — it is NOT borrowed forward into day2's BAKING total.
    m1 = _machine(stats.compute_daily_summary(DAY1))
    results.append(_check("day1 waiting_seconds == 10min (unaffected by carry-over)", m1["waiting_seconds"], 10 * 60))
    results.append(_check("day1 baking_seconds == 0 (BAKING transition belongs to day2)", m1["baking_seconds"], 0))
    return results


def test_downtime_excluded_within_a_day() -> list[bool]:
    print()
    print("--- server downtime within one day ---")
    _fresh_db()
    results = []
    start = history.local_day_start_utc(DAY2)

    with sqlite3.connect(history.DB_PATH) as conn:
        _insert(conn, timestamp=_ts(start, hours=8), old_state="COLD", new_state="WAITING")
        _insert(conn, timestamp=_ts(start, hours=10), old_state="WAITING", new_state="BAKING")
        # Server shut down at 11:00, back up at 15:00. The UNKNOWN marker
        # and the poll loop's first row share an instant (as they do in
        # practice, a poll cycle apart); insertion order breaks the tie.
        _insert(conn, timestamp=_ts(start, hours=11), old_state="BAKING",
                new_state=history.SERVER_STOPPED_MARKER, was_online=0)
        _insert(conn, timestamp=_ts(start, hours=15), old_state=history.SERVER_STOPPED_MARKER,
                new_state=history.UNKNOWN_MARKER, was_online=0)
        _insert(conn, timestamp=_ts(start, hours=15), old_state=None, new_state="WAITING")
        conn.commit()

    m = _machine(stats.compute_daily_summary(DAY2))
    # 08:00 -> 10:00, plus 15:00 -> end of day.
    results.append(_check("waiting_seconds == 11h (observed periods only)", m["waiting_seconds"], 11 * 3600))
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
        # WAITING at 18:00 on day1, server stopped five minutes later...
        _insert(conn, timestamp=_ts(day2_start, hours=-6), old_state="COLD", new_state="WAITING")
        _insert(conn, timestamp=_ts(day2_start, hours=-5, minutes=-55), old_state="WAITING",
                new_state=history.SERVER_STOPPED_MARKER, was_online=0)
        # ...and back up at 09:00 the next morning.
        _insert(conn, timestamp=_ts(day2_start, hours=9), old_state=history.SERVER_STOPPED_MARKER,
                new_state=history.UNKNOWN_MARKER, was_online=0)
        _insert(conn, timestamp=_ts(day2_start, hours=9), old_state=None, new_state="WAITING")
        conn.commit()

    m = _machine(stats.compute_daily_summary(DAY2))
    # Before the fix this read 24h: the overnight stretch carried into
    # day2 as WAITING, so the whole day was credited to it.
    results.append(_check("day2 waiting_seconds == 15h (09:00 -> end, not 24h)", m["waiting_seconds"], 15 * 3600))
    results.append(_check("day2 untracked_seconds == 9h (midnight -> 09:00)", m["untracked_seconds"], 9 * 3600))
    results.append(_check("day2 offline_seconds == 0", m["offline_seconds"], 0))

    # day1 keeps only the five minutes it actually observed WAITING.
    m1 = _machine(stats.compute_daily_summary(DAY1))
    results.append(_check("day1 waiting_seconds == 5min (18:00 -> 18:05)", m1["waiting_seconds"], 5 * 60))
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
        # WAITING at 08:00. Process is then hard-killed a few seconds
        # later with NO SERVER_STOPPED row (taskkill /F, PyCharm's Stop
        # button on Windows, a crash, power loss — see server.py's
        # lifespan shutdown handler docstring on why this is the
        # unreliable half of the pair). The only evidence anything
        # happened at all is the next startup's UNKNOWN marker at 10:00
        # (~2h later), whose old_state is WAITING -- the state that was
        # active when the process died, NOT a SERVER_STOPPED row.
        _insert(conn, timestamp=_ts(start, hours=8), old_state="COLD", new_state="WAITING")
        _insert(conn, timestamp=_ts(start, hours=10), old_state="WAITING",
                new_state=history.UNKNOWN_MARKER, was_online=0)
        _insert(conn, timestamp=_ts(start, hours=10), old_state=None, new_state="WAITING")
        conn.commit()

    m = _machine(stats.compute_daily_summary(DAY2))
    # Before this fix, the 08:00->10:00 segment was bucketed under its
    # OWN new_state (WAITING) all the way to the next row's start (the
    # UNKNOWN marker) -- so the entire 2h outage read as waiting_seconds,
    # and untracked_seconds only ever caught the UNKNOWN row's own
    # (near-instant) forward span. That's the exact bug report: Waiting
    # time inflated by real downtime, fixable only by clearing history.
    # waiting_seconds should be ONLY the genuine post-restart span
    # (10:00 -> day end, 14h) -- the pre-outage 08:00->10:00 span is
    # untrustworthy in full and must NOT also be folded into this total.
    results.append(_check("waiting_seconds == 14h (only the genuine post-restart span, 10:00 -> day end)",
                          m["waiting_seconds"], 14 * 3600))
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
        # Pre-restart: WAITING starting 40 minutes before the simulated
        # restart instant (today_start+01:00) -- this must be discarded
        # entirely, not folded into today's waiting_seconds.
        _insert(conn, timestamp=_ts(today_start, minutes=20), old_state="COLD", new_state="WAITING")
        # Post-restart, as the poll loop's own first cycles would log:
        # carried-over WAITING until the first real transition, then BAKING,
        # then COLD (left open so its duration depends on "now" and isn't
        # asserted here).
        _insert(conn, timestamp=_ts(today_start, hours=1, minutes=30), old_state="WAITING", new_state="BAKING")
        _insert(conn, timestamp=_ts(today_start, hours=2), old_state="BAKING", new_state="COLD")
        conn.commit()

    history.set_server_started_at(restart_at)
    m = _machine(stats.compute_daily_summary(today, boundary_mode="since_restart"))
    results.append(_check("since_restart: waiting_seconds == 30min (restart -> first post-restart transition only)",
                          m["waiting_seconds"], 30 * 60))
    results.append(_check("since_restart: baking_seconds == 30min (01:30 -> 02:00, unaffected once past the boundary)",
                          m["baking_seconds"], 30 * 60))

    # full_day mode must ignore the restart boundary even for today — the
    # whole point of the Statistics page's mode (see stats.py's docstring).
    # No carry-over exists before local midnight here, so the walk starts
    # at the pre-restart 00:20 row instead of sliding to 01:00.
    m_full = _machine(stats.compute_daily_summary(today, boundary_mode="full_day"))
    results.append(_check("full_day: waiting_seconds == 1h10m (00:20 pre-restart row -> 01:30, restart boundary ignored)",
                          m_full["waiting_seconds"], 70 * 60))
    results.append(_check("full_day: baking_seconds == 30min (unaffected either way)",
                          m_full["baking_seconds"], 30 * 60))

    # A past date must never be subject to the restart boundary in EITHER
    # mode, even if a (bogus, for this test) server_started_at instant
    # falls inside it.
    _fresh_db()
    day2_start = history.local_day_start_utc(DAY2)
    with sqlite3.connect(history.DB_PATH) as conn:
        _insert(conn, timestamp=_ts(day2_start, minutes=-10), old_state="COLD", new_state="WAITING")
        _insert(conn, timestamp=_ts(day2_start, hours=8), old_state="WAITING", new_state="BAKING")
        conn.commit()
    history.set_server_started_at(_ts(day2_start, hours=12))
    m2 = _machine(stats.compute_daily_summary(DAY2, boundary_mode="since_restart"))
    results.append(_check("past date waiting_seconds == 8h (restart boundary ignored for non-today dates)",
                          m2["waiting_seconds"], 8 * 3600))
    results.append(_check("past date baking_seconds == 16h (restart boundary ignored for non-today dates)",
                          m2["baking_seconds"], 16 * 3600))
    return results


def test_error_count() -> list[bool]:
    print()
    print("--- error_count (transitions into ERROR) ---")
    _fresh_db()
    results = []
    start = history.local_day_start_utc(DAY2)

    with sqlite3.connect(history.DB_PATH) as conn:
        _insert(conn, timestamp=_ts(start, hours=1), old_state="COLD", new_state="WAITING")
        _insert(conn, timestamp=_ts(start, hours=2), old_state="WAITING", new_state="ERROR")
        _insert(conn, timestamp=_ts(start, hours=3), old_state="ERROR", new_state="WAITING")
        _insert(conn, timestamp=_ts(start, hours=4), old_state="WAITING", new_state="ERROR")
        _insert(conn, timestamp=_ts(start, hours=5), old_state="ERROR", new_state="BAKING")
        conn.commit()

    m = _machine(stats.compute_daily_summary(DAY2))
    results.append(_check("error_count == 2 (two transitions into ERROR)", m["error_count"], 2))

    # A carried-over ERROR anchor (from before the day started) is not a
    # transition that happened WITHIN this day, so it must not be counted.
    _fresh_db()
    day2_start = history.local_day_start_utc(DAY2)
    with sqlite3.connect(history.DB_PATH) as conn:
        _insert(conn, timestamp=_ts(day2_start, hours=-5), old_state="WAITING", new_state="ERROR")
        _insert(conn, timestamp=_ts(day2_start, hours=8), old_state="ERROR", new_state="WAITING")
        conn.commit()
    m2 = _machine(stats.compute_daily_summary(DAY2))
    results.append(_check("error_count == 0 (carried-over ERROR anchor isn't a within-day transition)",
                          m2["error_count"], 0))
    return results


def test_compute_totals() -> list[bool]:
    print()
    print("--- compute_totals (across-machine aggregation) ---")
    results = []

    machines = [
        {"baking_seconds": 3600, "waiting_seconds": 3600, "heating_seconds": 0, "hot_seconds": 0,
         "blocked_seconds": 0, "error_seconds": 0, "cold_seconds": 0, "offline_seconds": 0, "error_count": 1},
        {"baking_seconds": 1800, "waiting_seconds": 0, "heating_seconds": 1800, "hot_seconds": 0,
         "blocked_seconds": 0, "error_seconds": 3600, "cold_seconds": 0, "offline_seconds": 0, "error_count": 2},
    ]
    totals = stats.compute_totals(machines)
    results.append(_check("baking_seconds == 5400 (summed across machines)", totals["baking_seconds"], 5400))
    results.append(_check("error_count == 3 (summed across machines)", totals["error_count"], 3))
    # tracked = (3600+3600) + (1800+1800+3600) = 14400; baking = 5400 -> 37.5%
    results.append(_check("productivity_pct == 37.5 (weighted by tracked time, not averaged per-machine)",
                          totals["productivity_pct"], 37.5))

    empty_totals = stats.compute_totals([])
    results.append(_check("compute_totals([]) baking_seconds == 0", empty_totals["baking_seconds"], 0))
    results.append(_check("compute_totals([]) productivity_pct == 0.0", empty_totals["productivity_pct"], 0.0))
    return results


def test_compute_seven_day_average() -> list[bool]:
    print()
    print("--- compute_seven_day_average (KPI 'vs 7-day avg' baseline) ---")
    _fresh_db()
    _fresh_config()
    results = []

    day0 = (datetime.strptime(DAY1, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    day2_start = history.local_day_start_utc(DAY2)
    day1_start = history.local_day_start_utc(DAY1)
    day0_start = history.local_day_start_utc(day0)

    with sqlite3.connect(history.DB_PATH) as conn:
        # DAY0: 4h baking, 2 errors totalling 1h.
        _insert(conn, timestamp=_ts(day0_start, hours=1), old_state="COLD", new_state="ERROR")
        _insert(conn, timestamp=_ts(day0_start, hours=1, minutes=30), old_state="ERROR", new_state="BAKING")
        _insert(conn, timestamp=_ts(day0_start, hours=5, minutes=30), old_state="BAKING", new_state="ERROR")
        _insert(conn, timestamp=_ts(day0_start, hours=6), old_state="ERROR", new_state="WAITING")
        # DAY1: baked for 2h, no errors.
        _insert(conn, timestamp=_ts(day1_start, hours=1), old_state="COLD", new_state="BAKING")
        _insert(conn, timestamp=_ts(day1_start, hours=3), old_state="BAKING", new_state="WAITING")
        # DAY2 (current date): baked for 1h, one error.
        _insert(conn, timestamp=_ts(day2_start, hours=1), old_state="COLD", new_state="BAKING")
        _insert(conn, timestamp=_ts(day2_start, hours=2), old_state="BAKING", new_state="ERROR")
        _insert(conn, timestamp=_ts(day2_start, hours=2, minutes=30), old_state="ERROR", new_state="WAITING")
        conn.commit()

    day2_summary = stats.with_all_configured_machines(stats.compute_daily_summary(DAY2, boundary_mode="full_day"))
    day2_totals = stats.compute_totals(day2_summary["machines"])
    results.append(_check("day2 baking_seconds == 1h", day2_totals["baking_seconds"], 3600))
    results.append(_check("day2 error_count == 1", day2_totals["error_count"], 1))

    comparison = stats.compute_seven_day_average(DAY2, day2_totals)
    results.append(_check("comparison is not None (window has data)", comparison is not None, True))
    results.append(_check("window is DAY2-7 .. DAY1 (selected date excluded)",
                          (comparison["window_start"], comparison["window_end"]),
                          ((datetime.strptime(DAY2, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d"), DAY1)))
    # The five days before DAY0 have no rows at all -> skipped, not
    # averaged in as zeros.
    results.append(_check("days_with_data == 2 (empty days skipped)", comparison["days_with_data"], 2))
    results.append(_check("averages.baking_seconds == 3h ((4h + 2h) / 2)",
                          comparison["averages"]["baking_seconds"], 10800))
    results.append(_check("averages.error_count == 1.0 ((2 + 0) / 2)", comparison["averages"]["error_count"], 1.0))
    results.append(_check("deltas.baking_seconds == -2h (current minus average)",
                          comparison["deltas"]["baking_seconds"], -7200))
    results.append(_check("deltas.error_seconds == 0 (30min vs avg (1h + 0) / 2)",
                          comparison["deltas"]["error_seconds"], 0))
    results.append(_check("deltas.error_count == 0.0 (1 vs avg 1.0)", comparison["deltas"]["error_count"], 0.0))

    # Nothing recorded in the 7 days before DAY0 -> None, not a fake
    # all-zero average.
    day0_totals = stats.compute_totals(
        stats.with_all_configured_machines(stats.compute_daily_summary(day0, boundary_mode="full_day"))["machines"]
    )
    results.append(_check("returns None when no day in the window has data",
                          stats.compute_seven_day_average(day0, day0_totals), None))
    return results


def test_compute_timeline() -> list[bool]:
    print()
    print("--- compute_timeline (per-PLC state spans) ---")
    _fresh_db()
    results = []
    start = history.local_day_start_utc(DAY2)
    day_end = start + timedelta(days=1)

    with sqlite3.connect(history.DB_PATH) as conn:
        # WAITING carried in from before DAY2 (no row on DAY2 itself for the
        # first stretch) -> COLD at 08:00 -> server downtime with no
        # SERVER_STOPPED row (hard kill) -> UNKNOWN marker at 12:00 ->
        # WAITING again at 12:05, open for the rest of the day.
        _insert(conn, timestamp=_ts(start, hours=-2), old_state="COLD", new_state="WAITING")
        _insert(conn, timestamp=_ts(start, hours=8), old_state="WAITING", new_state="COLD")
        _insert(conn, timestamp=_ts(start, hours=12), old_state="COLD",
                new_state=history.UNKNOWN_MARKER, was_online=0)
        _insert(conn, timestamp=_ts(start, hours=12, minutes=5), old_state=None, new_state="WAITING")
        conn.commit()

    timeline = stats.compute_timeline(DAY2)
    m = next(x for x in timeline["machines"] if x["plc_ip"] == PLC_IP)
    spans = m["spans"]

    results.append(_check("4 spans (carried WAITING, poisoned-COLD as NO_DATA, marker as NO_DATA, final WAITING)",
                          len(spans), 4))
    results.append(_check("span 0 is WAITING, day_start -> 08:00 (carried over, a real trustworthy span)",
                          (spans[0]["state"], spans[0]["start"], spans[0]["end"]),
                          ("WAITING", start.strftime("%Y-%m-%dT%H:%M:%SZ"), _ts(start, hours=8))))
    # The 08:00 COLD row's OWN new_state is a real state, but its next row
    # is the UNKNOWN marker with no SERVER_STOPPED row ever written (hard
    # kill) — so per the poisoned-by-unknown rule (see module docstring)
    # this whole span is untrustworthy and must read as NO_DATA, not COLD.
    results.append(_check("span 1 is NO_DATA (COLD poisoned by the following UNKNOWN, not a real COLD span)",
                          (spans[1]["state"], spans[1]["start"], spans[1]["end"], spans[1]["is_online"]),
                          ("NO_DATA", _ts(start, hours=8), _ts(start, hours=12), False)))
    results.append(_check("span 2 is NO_DATA (the UNKNOWN marker's own brief span)",
                          (spans[2]["state"], spans[2]["start"], spans[2]["end"], spans[2]["is_online"]),
                          ("NO_DATA", _ts(start, hours=12), _ts(start, hours=12, minutes=5), False)))
    results.append(_check("span 3 is WAITING, 12:05 -> day_end (DAY2 isn't today, so it caps at midnight, not 'now')",
                          (spans[3]["state"], spans[3]["start"], spans[3]["end"]),
                          ("WAITING", _ts(start, hours=12, minutes=5), day_end.strftime("%Y-%m-%dT%H:%M:%SZ"))))
    return results


def test_hot_and_blocked() -> list[bool]:
    print()
    print("--- Hot / Blocked durations (state mapping v2) ---")
    _fresh_db()
    results = []
    start = history.local_day_start_utc(DAY2)

    with sqlite3.connect(history.DB_PATH) as conn:
        _insert(conn, timestamp=_ts(start, hours=6), old_state=None, new_state="COLD")
        _insert(conn, timestamp=_ts(start, hours=7), old_state="COLD", new_state="HOT")
        _insert(conn, timestamp=_ts(start, hours=9), old_state="HOT", new_state="BLOCKED")
        _insert(conn, timestamp=_ts(start, hours=12), old_state="BLOCKED", new_state="BAKING")
        _insert(conn, timestamp=_ts(start, hours=18), old_state="BAKING", new_state="COLD")
        conn.commit()

    m = _machine(stats.compute_daily_summary(DAY2))
    results.append(_check("hot_seconds == 2h (07:00 -> 09:00)", m["hot_seconds"], 2 * 3600))
    results.append(_check("blocked_seconds == 3h (09:00 -> 12:00)", m["blocked_seconds"], 3 * 3600))
    # Hot and Blocked count as observed time like Cold/Heating:
    # 6h baking over 06:00 -> 24:00 = 18h observed.
    results.append(_check("productivity_pct == 33.3 (Hot/Blocked in the denominator)",
                          m["productivity_pct"], 33.3))
    results.append(_check("productivity_pct() is the shared formula",
                          stats.productivity_pct(6 * 3600, 18 * 3600), 33.3))
    return results


def _legacy_db_with_rows(rows: list[tuple[str | None, str]]) -> None:
    """A throwaway DB as written BEFORE state mapping v2: tables exist,
    rows use the old READY name, no state_mapping_version flag yet."""
    _fresh_db()
    with sqlite3.connect(history.DB_PATH) as conn:
        conn.execute("DELETE FROM app_settings WHERE key = 'state_mapping_version'")
        for i, (old_state, new_state) in enumerate(rows):
            _insert(conn, timestamp=_ts(datetime(2026, 9, 1), minutes=i), old_state=old_state, new_state=new_state)
        conn.commit()


def _states_in_db() -> list[tuple]:
    with sqlite3.connect(history.DB_PATH) as conn:
        return conn.execute("SELECT old_state, new_state FROM state_transitions ORDER BY id").fetchall()


def test_state_mapping_migration() -> list[bool]:
    print()
    print("--- history migration to state mapping v2 (READY -> WAITING) ---")
    results = []
    legacy = [(None, "COLD"), ("COLD", "HEATING"), ("HEATING", "READY"), ("READY", "BAKING"),
              ("BAKING", "READY"), ("READY", "ERROR"), ("ERROR", history.UNKNOWN_MARKER)]
    _legacy_db_with_rows(legacy)

    changed = history.migrate_state_mapping()
    results.append(_check("4 rows changed (any row with READY in old_state or new_state)", changed, 4))
    results.append(_check("READY renamed to WAITING in both columns, everything else untouched",
                          _states_in_db(),
                          [(None, "COLD"), ("COLD", "HEATING"), ("HEATING", "WAITING"), ("WAITING", "BAKING"),
                           ("BAKING", "WAITING"), ("WAITING", "ERROR"), ("ERROR", history.UNKNOWN_MARKER)]))
    backup = history.DB_PATH.with_name(history.DB_PATH.name + ".bak-before-state-v2")
    results.append(_check("backup written before migrating", backup.exists(), True))
    with sqlite3.connect(backup) as conn:
        backed_up = conn.execute("SELECT old_state, new_state FROM state_transitions ORDER BY id").fetchall()
    results.append(_check("backup holds the original (pre-migration) rows", backed_up, legacy))

    # Runs once: a second call (and a re-init, which calls it too) is a no-op,
    # even if a stray READY row shows up afterwards.
    with sqlite3.connect(history.DB_PATH) as conn:
        _insert(conn, timestamp="2026-09-02T00:00:00Z", old_state=None, new_state="READY")
        conn.commit()
    results.append(_check("second run returns None (flag set)", history.migrate_state_mapping(), None))
    history.init_db()
    results.append(_check("init_db() doesn't re-run it", _states_in_db()[-1], (None, "READY")))

    _fresh_db()
    results.append(_check("fresh install: nothing to migrate, flag already set",
                          history.migrate_state_mapping(), None))
    return results


def main() -> bool:
    results = []
    for scenario in (
        test_day_boundary_carry_over,
        test_downtime_excluded_within_a_day,
        test_downtime_carried_over_midnight,
        test_ungraceful_shutdown_no_server_stopped_row,
        test_today_restart_boundary,
        test_error_count,
        test_compute_totals,
        test_compute_seven_day_average,
        test_compute_timeline,
        test_hot_and_blocked,
        test_state_mapping_migration,
    ):
        results.extend(scenario())

    all_passed = all(results)
    print()
    print("ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
