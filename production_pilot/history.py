"""
history.py
-----------
Local SQLite-backed KPI history logger. Off by default; a Service-level
toggle (see server.py's /api/service/recording endpoints) controls
whether PLC state transitions actually get written. Data-capture only
for now — no viewing/aggregation screens yet, just the raw event log.

Every (group, state, online) change is logged as its own row in
state_transitions rather than a pre-aggregated duration, so any future
KPI calculation (uptime %, cycle counts, time-in-state, ...) can be
derived from the raw log without re-instrumenting the poller.

Thread safety: this module is called from both the background OPC UA
poll thread and FastAPI's sync-endpoint threadpool. sqlite3 connections
aren't safe to share across threads, so every call opens its own
short-lived connection; _db_lock serializes access — SQLite only ever
allows one writer at a time anyway, so this doesn't add real contention.
`is_recording_enabled()` is the exception: it reads an in-memory cache
(kept in sync by init_db()/set_recording_enabled()) rather than hitting
the DB, since it's checked on every ~0.5s poll cycle.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "history.db"

_RECORDING_KEY = "recording_enabled"
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_db_lock = threading.Lock()
_recording_enabled = False  # cache; authoritative value lives in app_settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)


def local_day_start_utc(date: str) -> datetime:
    """The UTC instant of local midnight at the start of `date` (a
    YYYY-MM-DD string interpreted in the server's own local timezone).

    state_transitions timestamps are always stored in UTC (_now_iso()),
    while "today"/a picked calendar date is inherently a LOCAL concept —
    e.g. a transition at 01:00 CEST is stored as 23:00 UTC the previous
    day. Matching rows by a naive substring of the UTC timestamp against
    a local date string silently drops (or misfiles into the wrong day)
    anything within the local/UTC offset window around local midnight.
    Callers use this to compute the actual UTC range a local calendar
    day covers, instead of comparing date strings directly.

    `datetime.astimezone()` on a naive datetime presumes it already
    represents system-local time and just attaches the correct tzinfo
    (including DST) for that instant — exactly what's needed here."""
    local_midnight = datetime.strptime(date, "%Y-%m-%d").astimezone()
    return local_midnight.astimezone(timezone.utc)


@contextmanager
def _connection():
    """sqlite3.Connection's own context-manager protocol only handles
    commit/rollback, not closing — without an explicit close() a
    long-running server would leak a file handle per call."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Creates both tables if missing and seeds recording_enabled to
    "false" on a fresh install, so a first run just works. Also primes
    the in-memory recording-flag cache from whatever's on disk (so a
    restart resumes whichever state the technician last set). Call once
    at startup."""
    global _recording_enabled
    with _db_lock, _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS state_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                group_name TEXT NOT NULL,
                plc_ip TEXT NOT NULL,
                unit_number INTEGER NOT NULL,
                old_state TEXT,
                new_state TEXT NOT NULL,
                was_online INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            (_RECORDING_KEY, "false"),
        )
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (_RECORDING_KEY,)
        ).fetchone()
        _recording_enabled = row is not None and row["value"] == "true"


def is_recording_enabled() -> bool:
    return _recording_enabled


def set_recording_enabled(enabled: bool) -> None:
    global _recording_enabled
    with _db_lock, _connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (_RECORDING_KEY, "true" if enabled else "false"),
        )
    _recording_enabled = enabled


def record_transition(
    *,
    group_name: str,
    plc_ip: str,
    unit_number: int,
    old_state: str | None,
    new_state: str,
    was_online: bool,
) -> None:
    """Inserts one row. Caller is expected to have already checked
    is_recording_enabled() — this always writes when called."""
    with _db_lock, _connection() as conn:
        conn.execute(
            """
            INSERT INTO state_transitions
                (timestamp, group_name, plc_ip, unit_number, old_state, new_state, was_online)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (_now_iso(), group_name, plc_ip, unit_number, old_state, new_state, int(was_online)),
        )


def clear_history() -> int:
    """Deletes all rows from state_transitions (schema stays; the
    recording_enabled setting is untouched — clearing history and
    toggling recording are independent actions). Returns the count of
    rows removed."""
    with _db_lock, _connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM state_transitions").fetchone()[0]
        conn.execute("DELETE FROM state_transitions")
    return count


def get_available_dates() -> list[str]:
    """Sorted list of distinct UTC calendar dates (YYYY-MM-DD, taken from
    the stored timestamp's date portion) that have any rows — lets the
    frontend's date picker restrict to dates that actually have data."""
    with _db_lock, _connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT substr(timestamp, 1, 10) AS date FROM state_transitions ORDER BY date"
        ).fetchall()
    return [row["date"] for row in rows]


def get_daily_transitions(date: str) -> list[dict]:
    """All rows falling within the LOCAL calendar day `date` (YYYY-MM-DD,
    server-local timezone — see local_day_start_utc), ordered per-PLC by
    timestamp — the walk order stats.compute_daily_summary() needs.

    Matches against the actual UTC instant range the local day covers,
    not a naive substring of the (UTC) stored timestamp — see
    local_day_start_utc's docstring for why that would misfile rows near
    local midnight."""
    start = local_day_start_utc(date)
    end = start + timedelta(days=1)
    with _db_lock, _connection() as conn:
        rows = conn.execute(
            """
            SELECT id, timestamp, group_name, plc_ip, unit_number, old_state, new_state, was_online
            FROM state_transitions
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY plc_ip, timestamp, id
            """,
            (start.strftime(_TIMESTAMP_FORMAT), end.strftime(_TIMESTAMP_FORMAT)),
        ).fetchall()
    return [dict(row) for row in rows]


def get_next_transition_after(plc_ip: str, timestamp: str) -> dict | None:
    """The chronologically next row for this PLC after `timestamp` — used
    to close out a day's last transition when it carries into a
    following day (see stats.compute_daily_summary)."""
    with _db_lock, _connection() as conn:
        row = conn.execute(
            """
            SELECT timestamp FROM state_transitions
            WHERE plc_ip = ? AND timestamp > ?
            ORDER BY timestamp ASC, id ASC
            LIMIT 1
            """,
            (plc_ip, timestamp),
        ).fetchone()
    return dict(row) if row else None


def get_summary() -> dict:
    with _db_lock, _connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total, MIN(timestamp) AS earliest, MAX(timestamp) AS latest
            FROM state_transitions
            """
        ).fetchone()
    return {
        "total_rows": row["total"],
        "earliest_timestamp": row["earliest"],
        "latest_timestamp": row["latest"],
        "recording_enabled": is_recording_enabled(),
    }
