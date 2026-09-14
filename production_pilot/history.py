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
_DATA_SOURCE_KEY = "data_source_mode"
_DEFAULT_DATA_SOURCE_MODE = "real"
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Server-lifecycle markers, written into state_transitions.new_state.
# Deliberately NOT members of models.MachineState: they don't describe a
# machine's condition at all — they mark stretches of wall-clock time in
# which this server wasn't observing the machines. A period recorded
# under either of these is excluded from every duration total and from
# the productivity denominator (see stats.compute_daily_summary), rather
# than being credited to whatever state the PLC happened to be in when
# we last looked at it.
#
#   UNKNOWN        — written by the FastAPI startup handler before
#                    polling begins: "everything up to this instant
#                    happened without us watching". Always written, so
#                    it's the reliable of the two.
#   SERVER_STOPPED — written by the FastAPI shutdown handler. Best
#                    effort only: a hard power loss or kill -9 never
#                    gets there. See record_server_marker.
UNKNOWN_MARKER = "UNKNOWN"
SERVER_STOPPED_MARKER = "SERVER_STOPPED"
UNTRACKED_STATES = frozenset({UNKNOWN_MARKER, SERVER_STOPPED_MARKER})

_db_lock = threading.Lock()
_recording_enabled = False  # cache; authoritative value lives in app_settings
_data_source_mode = _DEFAULT_DATA_SOURCE_MODE  # cache; authoritative value lives in app_settings


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
    """Creates both tables if missing and seeds recording_enabled/
    data_source_mode to their defaults on a fresh install, so a first run
    just works. Also primes the in-memory caches from whatever's on disk
    (so a restart resumes whichever state the technician last set). Call
    once at startup."""
    global _recording_enabled, _data_source_mode
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
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            (_DATA_SOURCE_KEY, _DEFAULT_DATA_SOURCE_MODE),
        )
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (_RECORDING_KEY,)
        ).fetchone()
        _recording_enabled = row is not None and row["value"] == "true"
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (_DATA_SOURCE_KEY,)
        ).fetchone()
        _data_source_mode = row["value"] if row is not None else _DEFAULT_DATA_SOURCE_MODE


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


def get_data_source_mode() -> str:
    return _data_source_mode


def set_data_source_mode(mode: str) -> None:
    """Caller is expected to have already validated `mode` (see
    server.py's /api/service/data-source) — this always writes what
    it's given."""
    global _data_source_mode
    with _db_lock, _connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (_DATA_SOURCE_KEY, mode),
        )
    _data_source_mode = mode


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


def record_server_marker(*, new_state: str, timestamp: str, plcs: list[dict]) -> None:
    """Writes one lifecycle-marker row per PLC in `plcs` (dicts of
    group_name / plc_ip / unit_number — see server.py's _marker_plcs),
    all sharing the caller-supplied `timestamp` so the whole fleet's
    marker lands on a single instant. old_state is each PLC's own last
    recorded new_state (None if it has no history at all yet), so the
    log still reads as an ordinary transition out of whatever we last
    saw it in.

    was_online is always 0: across an untracked period we have no
    connection to anything, and recording otherwise would be a claim we
    can't back. The duration walk checks for an untracked new_state
    BEFORE it looks at was_online, so these rows don't land in
    offline_seconds either — they're their own category (see
    stats.compute_daily_summary).

    Caller is expected to have already checked is_recording_enabled() —
    this always writes when called."""
    if not plcs:
        return
    with _db_lock, _connection() as conn:
        last_states = {
            row["plc_ip"]: row["new_state"]
            for row in conn.execute(
                """
                SELECT plc_ip, new_state FROM state_transitions
                WHERE id IN (SELECT MAX(id) FROM state_transitions GROUP BY plc_ip)
                """
            ).fetchall()
        }
        conn.executemany(
            """
            INSERT INTO state_transitions
                (timestamp, group_name, plc_ip, unit_number, old_state, new_state, was_online)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            [
                (
                    timestamp,
                    plc["group_name"],
                    plc["plc_ip"],
                    plc["unit_number"],
                    last_states.get(plc["plc_ip"]),
                    new_state,
                )
                for plc in plcs
            ],
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


def get_last_transition_before(timestamp: str) -> dict[str, dict]:
    """plc_ip -> that PLC's most recent state_transitions row with
    timestamp STRICTLY BEFORE `timestamp` (an ISO UTC string) — the
    "carried-over state" a day's summary starts from when a PLC didn't
    transition at all on the requested day but was already in some state
    from a previous day (see stats.compute_daily_summary). A PLC with no
    rows before `timestamp` is simply absent from the returned dict.

    MAX(id) (rather than MAX(timestamp)) picks the latest-before-cutoff
    row per PLC — ids are insertion-ordered, which matches "most recent
    transition" without needing a tiebreak for any same-timestamp rows."""
    with _db_lock, _connection() as conn:
        rows = conn.execute(
            """
            SELECT plc_ip, timestamp, group_name, unit_number, new_state, was_online
            FROM state_transitions
            WHERE id IN (
                SELECT MAX(id) FROM state_transitions
                WHERE timestamp < ?
                GROUP BY plc_ip
            )
            """,
            (timestamp,),
        ).fetchall()
    return {row["plc_ip"]: dict(row) for row in rows}


def get_latest_transition_per_plc() -> dict[str, str]:
    """plc_ip -> timestamp of that PLC's most recent GENUINE state
    transition (across all history, regardless of the current recording
    toggle) — used to hydrate the live per-tile "time in state" timer on
    server startup (see server.py's _hydrate_state_entered_at). Empty
    dict if nothing has ever been recorded.

    Server-lifecycle marker rows (UNTRACKED_STATES) are excluded on
    purpose: they say when we stopped/started watching, not when a
    machine last changed state. _hydrate_state_entered_at combines this
    with the current session's startup instant itself, taking whichever
    is later — anchoring the timer to a marker row here as well would
    double-count the same startup instant from two directions."""
    placeholders = ", ".join("?" for _ in UNTRACKED_STATES)
    with _db_lock, _connection() as conn:
        rows = conn.execute(
            f"""
            SELECT plc_ip, MAX(timestamp) AS timestamp FROM state_transitions
            WHERE new_state NOT IN ({placeholders})
            GROUP BY plc_ip
            """,
            tuple(UNTRACKED_STATES),
        ).fetchall()
    return {row["plc_ip"]: row["timestamp"] for row in rows}


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
