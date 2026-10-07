"""
server.py
---------
FastAPI backend for Produktionspilot V2. Serves the current machine
state over REST and WebSocket for the (future) web frontend.

Threading model — CRITICAL:
The `opcua` library is synchronous and blocking; a dead/unreachable PLC
can stall a read for seconds. It must never run on the asyncio event
loop or the whole server (every client, every request) freezes with it.
So OPC UA polling runs in its own background thread (same role V1's
QThread played, different mechanism), and writes the latest snapshot
into a module-level variable guarded by a threading.Lock. The asyncio
side (REST handlers, the WS broadcaster) only ever reads that shared
state — it never touches OpcUaSource directly.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import secrets
import socket
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from starlette.requests import ClientDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from production_pilot import (
    demo_video, exports, history, hot_cold, layout, new_cycle, plc_config, scan_plcs, service_config, state_colors,
    stats,
)
from production_pilot.demo_source import RECIPE_OPTIONS, SimulatedSource
from production_pilot.models import MachineGroup
from production_pilot.opcua_source import CONFIG_PATH, PLC_STATE_MAP, OpcUaSource
from production_pilot.serializers import build_state

POLL_INTERVAL_SECONDS = 0.5
HEARTBEAT_INTERVAL_SECONDS = 5.0
HOST = "0.0.0.0"
PORT = 8000

SESSION_TTL_SECONDS = 30 * 60
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 5 * 60

STATIC_DIR = Path(__file__).resolve().parent / "static"

_EMPTY_STATE = {
    "connected": False,
    "timestamp": None,
    "groups": [],
    "next_action": {"kind": "none", "ip": None, "unit_number": None},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Shared state — written only by _poll_loop() (background thread), read
# only through get_state() (asyncio side). The lock is the sole hand-off
# point between the two; neither side ever calls into the other's domain.
# ---------------------------------------------------------------------------

_state_lock = threading.Lock()
_state: dict = {**_EMPTY_STATE, "timestamp": _now_iso()}


def get_state() -> dict:
    with _state_lock:
        return _state


def _set_state(new_state: dict) -> None:
    global _state
    with _state_lock:
        _state = new_state


def _current_state_colors() -> dict:
    return state_colors.merge_with_defaults(history.get_saved_state_colors())


def _public_state() -> dict:
    """The state as sent to clients (REST + WS): plus colors_version, so an
    open dashboard re-fetches /api/state-colors when a technician changes
    them — no reload needed on the TV."""
    return {**get_state(), "colors_version": state_colors.colors_version(_current_state_colors())}


def _load_source() -> OpcUaSource | None:
    if not CONFIG_PATH.exists():
        print(f"[startup] No plc_config.json at {CONFIG_PATH} — starting unconfigured.")
        return None
    try:
        return OpcUaSource()
    except Exception as exc:
        print(f"[startup] Failed to load plc_config.json ({exc}) — starting unconfigured.")
        return None


# The running OpcUaSource, behind its own lock so the Service tab can
# swap it out after a config save (see _reload_source) without needing a
# server restart. Separate from _state_lock: this guards *which* source
# object the poll thread reads from, not the state it produces.
_source_lock = threading.Lock()
_source: OpcUaSource | None = None


def _get_source() -> OpcUaSource | None:
    with _source_lock:
        return _source


def _set_source(source: OpcUaSource | None) -> None:
    global _source
    with _source_lock:
        _source = source


def _reload_source() -> None:
    """Re-reads plc_config.json and swaps the live source in place — the
    next poll cycle picks it up. Called after a Service-tab config save."""
    _set_source(_load_source())


# The demo/simulated source, created lazily the first time Demo Mode is
# switched on (from either the data-source endpoint or the poll loop
# itself) and kept alive afterwards so a technician's control-panel edits
# survive switching back and forth to Real PLCs within the same server
# run. Separate lock from _source_lock: this guards a different object
# with a different lifecycle (created once, never swapped wholesale).
_demo_lock = threading.Lock()
_demo_source: SimulatedSource | None = None


def _ensure_demo_source() -> SimulatedSource:
    global _demo_source
    with _demo_lock:
        if _demo_source is None:
            _demo_source = SimulatedSource()
        return _demo_source


# ---------------------------------------------------------------------------
# History (KPI) logging — change detection only, no lock needed: this dict
# is only ever touched from the poll thread itself, never from a request
# handler. Kept up to date regardless of the recording toggle (see
# _detect_and_log_transitions) so turning recording back on later compares
# against real data instead of stale pre-toggle state.
# ---------------------------------------------------------------------------

_last_known: dict[str, tuple[str, str, bool]] = {}  # plc.ip -> (group_name, state.name, is_online)

# plc.ip -> ISO 8601 UTC timestamp the PLC's current state has been
# OBSERVED in, kept up to date regardless of the recording toggle (same
# reasoning as _last_known above) and sent to the frontend as
# state_entered_at (see PlcData.to_dict) for the live per-tile elapsed
# timer. Seeded at startup — see _hydrate_state_entered_at.
_state_entered_at: dict[str, str] = {}


def _hydrate_state_entered_at(server_started_at: str) -> None:
    """Called once at startup (see lifespan below), before the poll loop
    starts. Seeds each PLC's elapsed-timer anchor to the LATER of:

      (a) its most recent genuine state transition in history
          (history.get_latest_transition_per_plc, which excludes
          lifecycle markers), or
      (b) `server_started_at` — the instant this session began watching.

    (b) is what stops a restart from presenting server downtime as
    machine time: a server off overnight used to come back showing
    "Waiting 21:23:00" on every tile, because the last transition on
    record was from before the outage. What the timer can honestly
    claim is how long we've actually been observing the state, which
    after a restart is "since we came back up". A PLC with no history at
    all isn't seeded here and falls back to "now" the first time
    _detect_and_log_transitions below sees it — the same instant, give
    or take a poll cycle.

    Both values use history's fixed-width UTC format, so max() over the
    strings is a chronological max.

    Deliberately anchored to this process's own start instant rather
    than to the UNKNOWN marker row it writes: the two carry the same
    timestamp when recording is on, and this way the timer stays honest
    while recording is off, when no marker row exists at all."""
    for plc_ip, last_transition in history.get_latest_transition_per_plc().items():
        _state_entered_at[plc_ip] = max(last_transition, server_started_at)


def _marker_plcs() -> list[dict]:
    """group_name / plc_ip / unit_number for every PLC the ACTIVE data
    source knows about — the fleet a lifecycle marker has to cover.

    Mode-aware so downtime is excluded identically in demo and real
    mode: demo mirrors plc_config.json but falls back to its own default
    group when there's no config yet (see demo_source), so reading the
    config file alone would miss those PLCs entirely.

    Never touches OpcUaSource: its get_machines() does real blocking OPC
    UA reads and would stall startup/shutdown on an unreachable PLC.
    stats.load_configured_plcs() is a plain read of the same config the
    source is built from. SimulatedSource is pure in-memory, so calling
    it directly is safe."""
    if history.get_data_source_mode() == "demo":
        return [
            {"group_name": group.name, "plc_ip": plc.ip, "unit_number": plc.unit_number}
            for group in _ensure_demo_source().get_machines()
            for plc in group.plcs
        ]
    return stats.load_configured_plcs()


def _write_server_marker(new_state: str, timestamp: str) -> None:
    """Best-effort lifecycle marker for the whole fleet (see
    history.record_server_marker). A no-op while recording is off —
    there's no series to punch a hole in. Never raises: a DB problem
    must not stop the server starting, nor hold up its shutdown."""
    if not history.is_recording_enabled():
        return
    try:
        plcs = _marker_plcs()
        history.record_server_marker(new_state=new_state, timestamp=timestamp, plcs=plcs)
        print(f"[history] wrote {new_state} marker for {len(plcs)} PLC(s) at {timestamp}")
    except Exception as exc:
        print(f"[history] failed to write {new_state} marker: {exc}")


def _detect_and_log_transitions(groups: list[MachineGroup]) -> None:
    for group in groups:
        for plc in group.plcs:
            current = (group.name, plc.state.name, plc.is_online)
            previous = _last_known.get(plc.ip)

            if previous != current:
                # A genuine transition (previous is not None) always resets
                # the clock. The very first sighting of a PLC in this
                # process's lifetime (previous is None) only resets it if
                # nothing was hydrated from history for it — otherwise this
                # is just the poll loop catching up to a state that was
                # already known before the restart, and overwriting it here
                # would defeat the hydration above.
                if previous is not None or plc.ip not in _state_entered_at:
                    _state_entered_at[plc.ip] = _now_iso()

                if history.is_recording_enabled():
                    try:
                        history.record_transition(
                            group_name=group.name,
                            plc_ip=plc.ip,
                            unit_number=plc.unit_number,
                            old_state=previous[1] if previous else None,
                            new_state=plc.state.name,
                            was_online=plc.is_online,
                        )
                    except Exception as exc:
                        # A DB hiccup must never take the poll loop down with it.
                        print(f"[history] failed to record transition for {plc.ip}: {exc}")

                _last_known[plc.ip] = current

            plc.state_entered_at = _state_entered_at.get(plc.ip)


# Standby -> Cold / Hot from the oil temperature — applied to every poll HERE, before
# transition detection, so history and everything downstream share one
# derived state (see production_pilot/hot_cold.py). Poll thread only.
_hot_cold_rule = hot_cold.HotColdRule()


# New Cycle start sequence per group (see production_pilot/new_cycle.py) —
# runtime state only, recomputed from scratch after a restart. Poll thread only.
_new_cycle_tracker = new_cycle.NewCycleTracker()


def _process_poll(groups: list[MachineGroup]) -> tuple[list[MachineGroup], dict]:
    """One poll's raw source groups -> the derived groups everything else
    sees: Standby Cold/Hot rule first, then transition detection/history
    logging, then the New Cycle tracker (on the derived states). Returns
    (groups, {group name: new_cycle.CycleStatus})."""
    groups = _hot_cold_rule.apply(groups, history.get_hot_cold_threshold_c())
    _detect_and_log_transitions(groups)
    cycles = _new_cycle_tracker.update(groups, history.get_new_cycle_delay_seconds())
    return groups, cycles


def _poll_loop() -> None:
    """
    Runs forever in a daemon thread, one poll every POLL_INTERVAL_SECONDS
    — same cadence V1 used. Never lets an exception escape: a single bad
    cycle (or an unconfigured/unreachable install) must not kill the
    thread and freeze the state the API serves.

    Reads data_source_mode every cycle (a cheap in-memory cache read, see
    history.get_data_source_mode) and picks whichever source is currently
    active — this is the ONLY place that knows demo mode exists.
    Everything below it (priority, history logging, WS broadcast, KPI
    endpoints) just sees MachineGroup/PlcData and never special-cases it.
    """
    while True:
        source = _ensure_demo_source() if history.get_data_source_mode() == "demo" else _get_source()
        if source is None:
            _set_state({**_EMPTY_STATE, "timestamp": _now_iso()})
        else:
            try:
                groups, cycles = _process_poll(source.get_machines())
                connected = source.is_connected()
                _set_state(build_state(groups, connected, cycles))
            except Exception as exc:
                print(f"[poll] cycle failed: {exc}")
                _set_state({**_EMPTY_STATE, "timestamp": _now_iso()})
        time.sleep(POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# WebSocket broadcast — plain asyncio, single-threaded event loop, so no
# lock is needed around _clients: add/discard/list() have no `await`
# inside them, so they're atomic between coroutine switches.
# ---------------------------------------------------------------------------

_clients: set[WebSocket] = set()


async def _broadcast(message: dict) -> None:
    text = json.dumps(message)
    dead = []
    for ws in list(_clients):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


async def _broadcast_loop() -> None:
    """
    Polls the shared state at the same cadence it's produced, pushes a
    "state" message to every connected client whenever the actual data
    (groups/connected/colors_version) changes, and otherwise sends a lightweight
    "heartbeat" every HEARTBEAT_INTERVAL_SECONDS so clients can tell a
    silent connection from a dead one. Timestamp is excluded from the
    change check — it ticks every poll regardless, and shouldn't by
    itself trigger a broadcast.
    """
    last_content_key = None
    last_sent = 0.0
    while True:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        if not _clients:
            continue

        state = _public_state()
        content_key = json.dumps(
            {"connected": state["connected"], "groups": state["groups"], "colors_version": state["colors_version"]},
            sort_keys=True,
        )
        now = time.monotonic()

        if content_key != last_content_key:
            await _broadcast({"type": "state", **state})
            last_content_key = content_key
            last_sent = now
        elif now - last_sent >= HEARTBEAT_INTERVAL_SECONDS:
            await _broadcast({"type": "heartbeat", "timestamp": _now_iso()})
            last_sent = now


# ---------------------------------------------------------------------------
# Two-tier session auth (Management / Service). Tokens live only in
# memory — lost on restart, which is fine, a technician just logs in
# again. "service" is the stronger level: it can do everything
# "management" can, plus the wizard/config/scan/recording/history
# endpoints (see require_level below). The read-only dashboard endpoints
# above stay open to everyone (see module docstring on why a frontend-
# only password check isn't real protection).
# ---------------------------------------------------------------------------

_LEVEL_RANK = {"management": 1, "service": 2}

_sessions_lock = threading.Lock()
_sessions: dict[str, tuple[float, str]] = {}  # token -> (expiry (time.monotonic()), level)


def _create_session(level: str) -> str:
    token = secrets.token_urlsafe(32)
    with _sessions_lock:
        _sessions[token] = (time.monotonic() + SESSION_TTL_SECONDS, level)
    return token


def _touch_session(token: str) -> str | None:
    """Validates and slides the session's expiry forward. Returns the
    session's level, or None (without mutating anything) if the token is
    unknown or expired."""
    now = time.monotonic()
    with _sessions_lock:
        entry = _sessions.get(token)
        if entry is None:
            return None
        expiry, level = entry
        if expiry < now:
            _sessions.pop(token, None)
            return None
        _sessions[token] = (now + SESSION_TTL_SECONDS, level)
        return level


def _resolve_level(token: str | None) -> tuple[str, str]:
    """Raises 401 if `token` is falsy or unknown/expired. Returns
    (token, level) otherwise."""
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    level = _touch_session(token)
    if level is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token, level


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ")
    return None


async def _authenticate(authorization: str | None) -> tuple[str, str]:
    """Returns (token, level) for any valid session, regardless of
    level. Raises 401 if the header is missing/malformed or the token is
    unknown/expired."""
    return _resolve_level(_bearer_token(authorization))


def require_level(min_level: str):
    """
    Dependency factory: require_level("management") passes for both
    management and service tokens; require_level("service") passes only
    for service tokens (see _LEVEL_RANK — service outranks management).
    Usage: `_token: str = Depends(require_level("service"))`.
    """
    required_rank = _LEVEL_RANK[min_level]

    async def dependency(authorization: str | None = Header(default=None)) -> str:
        token, level = await _authenticate(authorization)
        if _LEVEL_RANK[level] < required_rank:
            raise HTTPException(status_code=403, detail="Insufficient access level")
        return token

    return dependency


def require_level_from_header_or_query(min_level: str):
    """
    Same as require_level, but also accepts the token via a `token`
    query parameter, falling back to it only when there's no Bearer
    header. Needed for the export downloads (CSV/XLSX/PDF), which the
    frontend reaches via a plain <a href> browser download so the page
    can rely on normal browser download handling — a plain link can't
    attach a custom Authorization header the way fetch() can.
    """
    required_rank = _LEVEL_RANK[min_level]

    async def dependency(authorization: str | None = Header(default=None), token: str | None = None) -> str:
        resolved_token, level = _resolve_level(_bearer_token(authorization) or token)
        if _LEVEL_RANK[level] < required_rank:
            raise HTTPException(status_code=403, detail="Insufficient access level")
        return resolved_token

    return dependency


# ---------------------------------------------------------------------------
# Login rate limiting — max LOGIN_RATE_LIMIT_MAX_ATTEMPTS failures per IP
# per LOGIN_RATE_LIMIT_WINDOW_SECONDS, to slow brute-forcing a 4-digit
# password. Keyed by client IP; stale timestamps just age out of the
# window on the next check, so nothing needs periodic cleanup.
# ---------------------------------------------------------------------------

_login_attempts_lock = threading.Lock()
_login_attempts: dict[str, list[float]] = {}


def _check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    with _login_attempts_lock:
        recent = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_RATE_LIMIT_WINDOW_SECONDS]
        _login_attempts[ip] = recent
        if len(recent) >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")


def _record_failed_login(ip: str) -> None:
    with _login_attempts_lock:
        _login_attempts.setdefault(ip, []).append(time.monotonic())


# ---------------------------------------------------------------------------
# Service endpoint request bodies
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    password: str


class ScanRequest(BaseModel):
    subnet: str
    port: int = scan_plcs.DEFAULT_PORT


class PlcIn(BaseModel):
    ip: str
    # Any, not int: a missing/non-numeric/bool machine number must reach
    # _validate_config's clear error message rather than pydantic's
    # generic 422 (or get silently coerced, e.g. "3" -> 3, True -> 1).
    unit_number: Any = None


class MachineIn(BaseModel):
    name: str
    type: str
    # Plain IP strings (the old format) are still accepted and numbered
    # by position — see plc_config.normalize_plcs.
    plcs: list[PlcIn | str]


class ConfigIn(BaseModel):
    machines: list[MachineIn]


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


class ManagementPasswordChangeIn(BaseModel):
    new_password: str
    confirm_password: str


class RecordingIn(BaseModel):
    enabled: bool


class HistoryClearIn(BaseModel):
    confirm: bool


class DataSourceIn(BaseModel):
    mode: str


class ProductivityTargetIn(BaseModel):
    target_pct: int


class NewCycleDelayIn(BaseModel):
    # Any, not int: a missing/non-numeric value must reach
    # new_cycle.validate_delay's clear message, not pydantic's 422.
    delay_seconds: Any = None


class HotColdThresholdIn(BaseModel):
    # Any, not float: a missing/non-numeric/bool value must reach
    # hot_cold.validate_threshold's clear message, not pydantic's 422.
    threshold_c: Any = None


class DemoSetStateIn(BaseModel):
    group_name: str
    ip: str
    state: str | None = None
    is_online: bool | None = None
    remaining_seconds: int | None = None
    oil_temp_current: float | None = None
    # None = not provided (leave unchanged); "" = explicitly clear it —
    # see SimulatedSource.set_plc_state's docstring.
    recipe: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    history.init_db()
    try:
        removed = demo_video.cleanup_orphans()  # interrupted uploads, superseded demo versions
        if removed:
            print(f"[demo] cleaned up {len(removed)} leftover file(s): {', '.join(removed)}")
    except OSError as exc:
        print(f"[demo] cleanup skipped: {exc}")

    # One instant shared by the startup marker and the elapsed-timer
    # anchors, so "when this session started observing" is a single
    # number rather than two that drift by however long startup takes.
    # Both must happen before the poll thread starts, or its first cycle
    # would log transitions ahead of the marker meant to precede them.
    started_at = _now_iso()
    history.set_server_started_at(started_at)
    _write_server_marker(history.UNKNOWN_MARKER, started_at)
    _hydrate_state_entered_at(started_at)

    _set_source(_load_source())
    poll_thread = threading.Thread(target=_poll_loop, daemon=True, name="opcua-poll")
    poll_thread.start()

    broadcast_task = asyncio.create_task(_broadcast_loop())
    try:
        yield
    finally:
        broadcast_task.cancel()
        # Closes the observed period, so the coming downtime is excluded
        # from tomorrow's totals rather than credited to each machine's
        # last-seen state. Best effort by nature — a hard power loss or
        # kill -9 never reaches this; the UNKNOWN marker the next startup
        # writes is the one that always lands.
        _write_server_marker(history.SERVER_STOPPED_MARKER, _now_iso())


app = FastAPI(title="Produktionspilot V2 API", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/machines")
def get_machines() -> dict:
    return _public_state()


@app.get("/api/stats/today-totals")
def stats_today_totals() -> dict:
    """Compact aggregate for the Dashboard top bar — same visibility level
    as /api/machines (no auth), unlike the rest of /api/stats/* below which
    is Management-only detail. See stats.compute_today_totals."""
    return stats.compute_today_totals()


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    try:
        await websocket.send_text(json.dumps({"type": "state", **_public_state()}))
        while True:
            # Frontend never needs to send anything; this just parks the
            # coroutine until the client disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[ws] client error: {exc}")
    finally:
        _clients.discard(websocket)


# ---------------------------------------------------------------------------
# Service endpoints — everything below except login and /api/auth/level
# requires a session token of at least the given level (see require_level
# above). Every endpoint here specifically requires "service".
# ---------------------------------------------------------------------------


@app.post("/api/service/login")
def service_login(body: LoginRequest, request: Request) -> dict:
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)
    level = service_config.verify_password(body.password)
    if level is None:
        _record_failed_login(ip)
        # Generic message — never hint at whether the password was close
        # or reveal anything about the stored credential.
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": _create_session(level), "level": level}


@app.get("/api/auth/level")
async def auth_level(authorization: str | None = Header(default=None)) -> dict:
    """Given a valid token (either level), returns its level. login()
    already returns the level directly, so the frontend's primary path
    doesn't need this — it exists for a client that only has a token in
    hand and needs to (re)confirm what it's authorized for. Accepts
    either level."""
    _token, level = await _authenticate(authorization)
    return {"level": level}


def _validate_subnet(subnet: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid subnet: {exc}")
    if network.version != 4:
        raise HTTPException(status_code=400, detail="Only IPv4 subnets are supported")
    if network.prefixlen < 16:
        raise HTTPException(status_code=400, detail="Subnet too large — use a /16 or smaller range")
    return network


def _run_full_scan(subnet: str, port: int) -> list[dict]:
    """
    Everything here is blocking — scan_subnet's own async port sweep is
    driven via a nested asyncio.run() inside this worker thread, and
    probe_opcua_server's opcua.Client.connect() is synchronous — so the
    whole scan runs off the main event loop via one run_in_executor call
    below (one thread for the entire scan, not one per host, so PLCs
    aren't hit with a burst of concurrent OPC UA handshake attempts).
    """
    open_ips = asyncio.run(scan_plcs.scan_subnet(subnet, port, scan_plcs.PORT_SCAN_TIMEOUT))
    return [scan_plcs.probe_opcua_server(ip, port, scan_plcs.DEFAULT_OPCUA_TIMEOUT) for ip in open_ips]


@app.post("/api/service/scan")
async def service_scan(body: ScanRequest, _token: str = Depends(require_level("service"))) -> dict:
    network = _validate_subnet(body.subnet)
    if not (1 <= body.port <= 65535):
        raise HTTPException(status_code=400, detail="Invalid port")

    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, _run_full_scan, str(network), body.port)

    devices = [
        {"ip": r["ip"], "port": r["port"], "server_name": r["server_name"]} for r in results if r["reachable"]
    ]
    return {"devices": devices}


@app.get("/api/service/config")
def service_get_config(_token: str = Depends(require_level("service"))) -> dict:
    # Always returned in the new {"ip", "unit_number"} format (an old
    # plain-IP config is numbered by position — see plc_config.py), so the
    # wizard edits the stored machine numbers rather than re-deriving them.
    if not CONFIG_PATH.exists():
        return {"machines": []}
    try:
        return plc_config.read_config(CONFIG_PATH)
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return {"machines": []}


_VALID_MACHINE_TYPES = {"STANDALONE", "DUO", "TRIO", "QUATTRO"}


def _normalized_machines(config: ConfigIn) -> list[dict]:
    return [
        {**m.model_dump(exclude={"plcs"}), "plcs": plc_config.normalize_plcs(m.model_dump()["plcs"])}
        for m in config.machines
    ]


def _validate_config(machines: list[dict]) -> None:
    seen_ips: set[str] = set()
    for machine in machines:
        if not machine["name"].strip():
            raise HTTPException(status_code=400, detail="Machine name must not be empty")
        if machine["type"] not in _VALID_MACHINE_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid machine type: {machine['type']}")
        if not machine["plcs"]:
            raise HTTPException(status_code=400, detail=f"Machine '{machine['name']}' has no PLCs")
        for plc in machine["plcs"]:
            ip = plc["ip"]
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid IP address: {ip}")
            if ip in seen_ips:
                raise HTTPException(status_code=400, detail=f"IP {ip} is assigned to more than one machine")
            seen_ips.add(ip)
        # Unique within this group only — two groups may both have a No. 1.
        problem = plc_config.unit_number_problem(machine["name"], machine["plcs"])
        if problem:
            raise HTTPException(status_code=400, detail=problem)


def _read_machines_or_empty() -> list[dict]:
    if not CONFIG_PATH.exists():
        return []
    try:
        return plc_config.read_config(CONFIG_PATH).get("machines", [])
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return []


@app.post("/api/service/config")
def service_save_config(body: ConfigIn, _token: str = Depends(require_level("service"))) -> dict:
    machines = _normalized_machines(body)
    _validate_config(machines)
    old_machines = _read_machines_or_empty()
    data = {"machines": machines}
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    # Renamed groups keep their floor position, deleted ones lose it —
    # see layout.reconcile_layout.
    saved_layout = history.get_floor_layout()
    if saved_layout is not None:
        history.set_floor_layout(layout.reconcile_layout(saved_layout, old_machines, machines))
    _reload_source()  # picks up the new config without a server restart
    return {"ok": True}


# ---------------------------------------------------------------------------
# Floor layout — where each machine group (and any TV icons) sits on the
# dashboard's tile view. Readable by everyone (the anonymous dashboard
# renders it), editable only at Service level. See production_pilot/layout.py.
# ---------------------------------------------------------------------------


def _known_group_names() -> set[str]:
    """Group names a layout may refer to: the configured groups, plus the
    demo source's (it falls back to its own default group when nothing is
    configured yet — see demo_source.py)."""
    names = {m["name"] for m in _read_machines_or_empty()}
    if history.get_data_source_mode() == "demo":
        names |= {group.name for group in _ensure_demo_source().get_machines()}
    return names


def _state_colors_payload() -> dict:
    colors = _current_state_colors()
    return {
        "colors": colors,
        "defaults": dict(state_colors.DEFAULT_STATE_COLORS),
        "version": state_colors.colors_version(colors),
    }


@app.get("/api/state-colors")
def get_state_colors() -> dict:
    """Readable without a session, like /api/layout — the anonymous
    dashboard (the TV) needs them. `defaults` lets the Service tab reset
    a colour without the frontend keeping its own copy."""
    return _state_colors_payload()


@app.put("/api/state-colors")
def put_state_colors(
    payload: Any = Body(...), _token: str = Depends(require_level("service"))
) -> dict:
    """Replaces the saved colours (keys left out fall back to their
    default). "Reset all" is a PUT of the defaults — same as the other
    settings, there is no DELETE."""
    try:
        colors = state_colors.validate_update(payload)
    except state_colors.StateColorsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    history.set_saved_state_colors(colors)  # broadcast to open dashboards via colors_version
    return _state_colors_payload()


@app.get("/api/layout")
def get_layout() -> dict:
    return history.get_floor_layout() or layout.EMPTY_LAYOUT


@app.put("/api/layout")
def put_layout(
    payload: Any = Body(...), _token: str = Depends(require_level("service"))
) -> dict:
    try:
        normalized = layout.validate_layout(payload, _known_group_names())
    except layout.LayoutError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    history.set_floor_layout(normalized)
    return normalized


@app.post("/api/service/password")
def service_change_password(body: PasswordChangeIn, _token: str = Depends(require_level("service"))) -> dict:
    # Only the Service password itself gates this — a Management-level
    # credential passed as current_password must not count as a match.
    if not service_config.verify_service_password(body.current_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if not body.new_password:
        raise HTTPException(status_code=400, detail="New password must not be empty")
    service_config.set_service_password(body.new_password)
    return {"ok": True}


@app.post("/api/service/password/management")
def service_change_management_password(
    body: ManagementPasswordChangeIn, _token: str = Depends(require_level("service"))
) -> dict:
    # No current-password check here on purpose: this is a Service-level
    # user resetting Management's password on its behalf (forgotten
    # password, rotation), not Management changing its own — see
    # service_config.set_management_password.
    if not body.new_password:
        raise HTTPException(status_code=400, detail="New password must not be empty")
    if body.new_password != body.confirm_password:
        raise HTTPException(status_code=400, detail="New password and confirmation do not match")
    service_config.set_management_password(body.new_password)
    return {"ok": True}


# ---------------------------------------------------------------------------
# History (KPI) logging controls. Data-capture only for now — no
# viewing/aggregation endpoints yet, just enable/disable, wipe, and enough
# of a summary to confirm rows are actually landing. All Service-level, so
# all four require a session same as the endpoints above.
# ---------------------------------------------------------------------------


@app.get("/api/service/recording-status")
def service_recording_status(_token: str = Depends(require_level("service"))) -> dict:
    return {"enabled": history.is_recording_enabled()}


def _write_recording_baseline() -> None:
    """Writes one row per currently-known PLC (old_state=None, new_state=
    its current state) the moment recording flips OFF->ON — treats
    "recording just started" as the first observed transition for every
    PLC, so a session has a real starting point immediately instead of
    waiting for a coincidental future state change. Reads the same
    snapshot the dashboard is currently showing (get_state()), not a
    fresh source read — "currently known" means what's on screen right
    now. Best-effort per row: a DB hiccup must not break the toggle
    itself (same reasoning as _detect_and_log_transitions)."""
    for group in get_state().get("groups", []):
        for plc in group.get("plcs", []):
            try:
                history.record_transition(
                    group_name=group["name"],
                    plc_ip=plc["ip"],
                    unit_number=plc["unit_number"],
                    old_state=None,
                    new_state=plc["state"],
                    was_online=plc["is_online"],
                )
            except Exception as exc:
                print(f"[history] failed to record baseline for {plc['ip']}: {exc}")


@app.post("/api/service/recording")
def service_set_recording(body: RecordingIn, request: Request, _token: str = Depends(require_level("service"))) -> dict:
    was_enabled = history.is_recording_enabled()
    history.set_recording_enabled(body.enabled)
    if body.enabled and not was_enabled:
        _write_recording_baseline()
    ip = request.client.host if request.client else "unknown"
    print(f"[history] recording {'enabled' if body.enabled else 'disabled'} by {ip} at {_now_iso()}")
    return {"enabled": body.enabled}


@app.post("/api/service/history/clear")
def service_clear_history(body: HistoryClearIn, request: Request, _token: str = Depends(require_level("service"))) -> dict:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Must pass confirm: true to clear history")
    deleted = history.clear_history()
    ip = request.client.host if request.client else "unknown"
    print(f"[history] history cleared ({deleted} row(s)) by {ip} at {_now_iso()}")
    return {"deleted_rows": deleted}


@app.get("/api/service/history/summary")
def service_history_summary(_token: str = Depends(require_level("service"))) -> dict:
    return history.get_summary()


# ---------------------------------------------------------------------------
# Demo data source — lets a technician switch the whole dashboard onto
# simulated data (for demos/training, or exercising the UI without real
# PLCs online) and drive it from a control panel. See _poll_loop above for
# the only place that reads data_source_mode / picks the active source;
# these endpoints just expose that switch and the simulated state behind
# it. All Service-level, same as the rest of this section.
# ---------------------------------------------------------------------------

_VALID_DATA_SOURCE_MODES = {"real", "demo"}
# Demo Controls set the RAW PLC state, so only states a PLC can actually
# report — Cold / Hot follow from Standby + the demo temperature
# (hot_cold.py), and Unknown is never a real PLC value.
_VALID_MACHINE_STATE_NAMES = {s.name for s in PLC_STATE_MAP.values()}


@app.get("/api/service/data-source")
def service_get_data_source(_token: str = Depends(require_level("service"))) -> dict:
    return {"mode": history.get_data_source_mode()}


@app.post("/api/service/data-source")
def service_set_data_source(body: DataSourceIn, _token: str = Depends(require_level("service"))) -> dict:
    if body.mode not in _VALID_DATA_SOURCE_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {body.mode}")
    if body.mode == "demo":
        # resync_clock() so a long stretch spent in Real PLCs mode (during
        # which nothing ticks the demo source) doesn't get misread as one
        # giant elapsed interval the moment demo mode is active again —
        # see SimulatedSource.resync_clock's docstring.
        _ensure_demo_source().resync_clock()
    history.set_data_source_mode(body.mode)
    return {"mode": body.mode}


@app.get("/api/service/productivity-target")
def service_get_productivity_target(_token: str = Depends(require_level("management"))) -> dict:
    """Management-readable (the Statistics page's KPI card needs it), but
    only Service can change it — see the POST endpoint below."""
    return {"target_pct": history.get_productivity_target_pct()}


@app.post("/api/service/productivity-target")
def service_set_productivity_target(
    body: ProductivityTargetIn, _token: str = Depends(require_level("service"))
) -> dict:
    if not 0 <= body.target_pct <= 100:
        raise HTTPException(status_code=400, detail="target_pct must be between 0 and 100")
    history.set_productivity_target_pct(body.target_pct)
    return {"target_pct": body.target_pct}


@app.get("/api/service/new-cycle-delay")
def service_get_new_cycle_delay() -> dict:
    """Readable by every level (no session needed, like the Hot/Cold
    threshold) — the poll loop itself reads the cached value directly."""
    return {
        "delay_seconds": history.get_new_cycle_delay_seconds(),
        "min_seconds": new_cycle.MIN_DELAY_SECONDS,
        "max_seconds": new_cycle.MAX_DELAY_SECONDS,
    }


@app.put("/api/service/new-cycle-delay")
def service_set_new_cycle_delay(
    body: NewCycleDelayIn, _token: str = Depends(require_level("service"))
) -> dict:
    """Applies to the next start delay; a countdown already running keeps
    the value it started with (see new_cycle.NewCycleTracker.update)."""
    try:
        delay_seconds = new_cycle.validate_delay(body.delay_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    history.set_new_cycle_delay_seconds(delay_seconds)
    return service_get_new_cycle_delay()


@app.get("/api/service/hot-cold-threshold")
def service_get_hot_cold_threshold() -> dict:
    """Readable by every level (no session needed, like /api/layout) —
    the poll loop itself reads the cached value directly."""
    return {"threshold_c": history.get_hot_cold_threshold_c()}


@app.put("/api/service/hot-cold-threshold")
def service_set_hot_cold_threshold(
    body: HotColdThresholdIn, _token: str = Depends(require_level("service"))
) -> dict:
    try:
        threshold_c = hot_cold.validate_threshold(body.threshold_c)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    history.set_hot_cold_threshold_c(threshold_c)  # picked up by the next poll
    return {"threshold_c": threshold_c}


def _demo_state_payload(source: SimulatedSource) -> dict:
    # Original config order (not calculated priority order, see
    # serializers.group_to_dict) — a control panel edits fixed physical
    # units, it shouldn't reshuffle rows as their simulated state changes.
    return {
        "groups": [
            {"name": group.name, "type": group.type, "plcs": [plc.to_dict() for plc in group.plcs]}
            for group in source.get_machines()
        ]
    }


@app.get("/api/service/demo/state")
def service_demo_state(_token: str = Depends(require_level("service"))) -> dict:
    return _demo_state_payload(_ensure_demo_source())


@app.post("/api/service/demo/set-state")
def service_demo_set_state(body: DemoSetStateIn, _token: str = Depends(require_level("service"))) -> dict:
    if history.get_data_source_mode() != "demo":
        raise HTTPException(status_code=400, detail="Switch to Demo Mode before editing simulated state")
    if body.state is not None and body.state not in _VALID_MACHINE_STATE_NAMES:
        raise HTTPException(status_code=400, detail=f"Invalid state: {body.state}")
    if body.recipe and body.recipe not in RECIPE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid recipe: {body.recipe}")
    if body.oil_temp_current is not None and not -50 <= body.oil_temp_current <= 400:
        raise HTTPException(status_code=400, detail="Demo oil temperature must be between -50 and 400 °C")

    source = _ensure_demo_source()
    try:
        source.set_plc_state(
            body.group_name,
            body.ip,
            state=body.state,
            is_online=body.is_online,
            remaining_seconds=body.remaining_seconds,
            recipe=body.recipe,
            oil_temp_current=body.oil_temp_current,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _demo_state_payload(source)


# ---------------------------------------------------------------------------
# Statistics screen — daily per-machine summaries aggregated from
# state_transitions (see production_pilot/stats.py for the actual
# computation). Available to Management level and above — read-only
# reporting, not a config/wizard concern like the endpoints above.
# ---------------------------------------------------------------------------


def _validate_date(date: str) -> None:
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date — expected YYYY-MM-DD")


_VALID_COMPARISON_BASES = {"avg_7d"}


@app.get("/api/stats/daily-summary")
def stats_daily_summary(
    date: str | None = None, compare: str | None = None, _token: str = Depends(require_level("management"))
) -> dict:
    date = date or stats.today_local()
    _validate_date(date)
    if compare is not None and compare not in _VALID_COMPARISON_BASES:
        raise HTTPException(status_code=400, detail="Invalid compare — expected avg_7d")
    # Left-joined against the currently configured PLC list so every
    # configured machine gets a row (00:00 / 0.0% if nothing's been
    # logged for it yet) instead of silently vanishing — see
    # with_all_configured_machines' docstring for why this isn't done
    # inside compute_daily_summary itself (range-summary/Trend needs the
    # un-joined, possibly-empty result to plot honest gaps).
    # boundary_mode="full_day": this is the Statistics page, which must
    # stay a trustworthy full-day report across routine server restarts —
    # unlike /api/stats/today-totals (see stats.compute_today_totals),
    # this never resets mid-day.
    summary = stats.with_all_configured_machines(stats.compute_daily_summary(date, boundary_mode="full_day"))
    totals = stats.compute_totals(summary["machines"])
    result = {**summary, "totals": totals}
    # Opt-in (the Dashboard's own call doesn't need it): the 7-day window
    # is seven extra full-day walks.
    if compare is not None:
        result["comparison"] = stats.compute_seven_day_average(date, totals)
    return result


@app.get("/api/stats/timeline")
def stats_timeline(date: str, _token: str = Depends(require_level("management"))) -> dict:
    _validate_date(date)
    return stats.compute_timeline(date)


@app.get("/api/stats/available-dates")
def stats_available_dates(_token: str = Depends(require_level("management"))) -> dict:
    return {"dates": history.get_available_dates()}


MAX_RANGE_DAYS = 90


@app.get("/api/stats/range-summary")
def stats_range_summary(start: str, end: str, _token: str = Depends(require_level("management"))) -> dict:
    _validate_date(start)
    _validate_date(end)
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start must be on or before end")
    if (end_date - start_date).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status_code=400, detail=f"Range too large — max {MAX_RANGE_DAYS} days")
    return stats.compute_range_summary(start, end)


def _export_summary(date: str | None) -> tuple[str, dict]:
    date = date or stats.today_local()
    _validate_date(date)
    # Same left-join (and full_day boundary — see stats_daily_summary
    # above) as the JSON endpoint, so every export matches what the
    # on-screen table shows for the same date.
    return date, stats.with_all_configured_machines(stats.compute_daily_summary(date, boundary_mode="full_day"))


def _download(content: str | bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/stats/daily-summary/csv")
def stats_daily_summary_csv(
    date: str | None = None, _token: str = Depends(require_level_from_header_or_query("management"))
) -> Response:
    date, summary = _export_summary(date)
    return _download(exports.to_csv(summary), "text/csv", f"daily-summary-{date}.csv")


@app.get("/api/stats/daily-summary/xlsx")
def stats_daily_summary_xlsx(
    date: str | None = None, _token: str = Depends(require_level_from_header_or_query("management"))
) -> Response:
    date, summary = _export_summary(date)
    return _download(
        exports.to_xlsx(summary),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        f"daily-summary-{date}.xlsx",
    )


@app.get("/api/stats/daily-summary/pdf")
def stats_daily_summary_pdf(
    date: str | None = None, _token: str = Depends(require_level_from_header_or_query("management"))
) -> Response:
    date, summary = _export_summary(date)
    totals = stats.compute_totals(summary["machines"])
    pdf = exports.to_pdf(
        summary,
        totals=totals,
        target_pct=history.get_productivity_target_pct(),
        comparison=stats.compute_seven_day_average(date, totals),
    )
    return _download(pdf, "application/pdf", f"daily-summary-{date}.pdf")


# ---------------------------------------------------------------------------
# Customer Demo Mode — one recorded demo video (see production_pilot/
# demo_video.py). Recording/deleting is Service-only. Playing follows the
# "Show Demo button for all users" setting: ON = anyone may stream it,
# OFF = Service only (token via header, or ?token= since a <video> can't
# send headers — same as the exports). Nothing here touches PLC state,
# history or statistics.
# ---------------------------------------------------------------------------


class DemoSettingsIn(BaseModel):
    show_for_all: bool


def _demo_status() -> dict:
    return {**demo_video.status(), "show_for_all": history.get_demo_button_for_all()}


@app.get("/api/demo/status")
def get_demo_status() -> dict:
    """Open to everyone: the dashboard needs it to decide whether to show
    the Demo button and which video version to load."""
    return _demo_status()


@app.get("/api/demo/video")
def get_demo_video(
    authorization: str | None = Header(default=None), token: str | None = None, which: str = "current"
):
    """Streams the demo (which=current, or which=previous: the last good
    version, the player's fallback). FileResponse opens the file per request
    and closes it when the response ends or the client disconnects; it
    answers Range requests with 206 (seeking) and sends ETag/Last-Modified.
    no-cache + the versioned URL (?v=) make a new recording show up at once."""
    if not history.get_demo_button_for_all():
        _token, level = _resolve_level(_bearer_token(authorization) or token)
        if _LEVEL_RANK[level] < _LEVEL_RANK["service"]:
            raise HTTPException(status_code=403, detail="Insufficient access level")
    path = demo_video.video_path(which)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="No demo recorded yet" if which == "current" else "No previous demo")
    return FileResponse(path, media_type="video/webm", headers={"Cache-Control": "no-cache"})


_DEMO_UPLOAD_TYPES = {"video/webm", "application/octet-stream"}


async def _drain(request: Request) -> None:
    """Reads and discards the rest of the body, so an error answer reaches the
    browser as a real HTTP response instead of a dropped connection
    ("Failed to fetch")."""
    try:
        async for _chunk in request.stream():
            pass
    except ClientDisconnect:
        pass


def _demo_error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status_code)


@app.post("/api/demo/video")
async def upload_demo_video(
    request: Request,
    duration_seconds: float | None = None,
    _token: str = Depends(require_level("service")),
):
    """Raw WebM body (no multipart), streamed chunk by chunk into a temp file
    (never held in memory); validation, the seek fix / ffmpeg remux and the
    pointer switch run in a worker thread (demo_video.store), so the event
    loop - state polling, WebSocket - is never blocked. Errors are JSON with
    a status code (413 too large, 415 wrong type, 422 invalid recording,
    500 unexpected); the current demo is never changed by a failed upload."""
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type not in _DEMO_UPLOAD_TYPES:
        await _drain(request)
        return _demo_error(415, f"Expected a WebM video (video/webm), got {content_type or 'no content type'}")
    try:
        duration = demo_video.validate_duration(duration_seconds)
    except demo_video.DemoVideoError as exc:
        await _drain(request)
        return _demo_error(422, str(exc))
    too_large = f"Recording larger than {demo_video.MAX_SIZE_BYTES // (1024 * 1024)} MB"
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > demo_video.MAX_SIZE_BYTES:
        await _drain(request)
        return _demo_error(413, too_large)

    upload = demo_video.new_upload_path()
    try:
        size = 0
        with upload.open("wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size <= demo_video.MAX_SIZE_BYTES:
                    await run_in_threadpool(f.write, chunk)
                # over the limit: keep reading (discarding) so the 413 below arrives
        if size > demo_video.MAX_SIZE_BYTES:
            return _demo_error(413, too_large)
        if size == 0:
            return _demo_error(422, "The recording is empty")
        try:
            await run_in_threadpool(demo_video.store, upload, duration)
        except demo_video.DemoVideoError as exc:
            return _demo_error(422, str(exc))
        except Exception as exc:  # disk full, permissions, ... - old demo untouched
            print(f"[demo] saving the recording failed: {type(exc).__name__}: {exc}")
            return _demo_error(500, f"Saving failed on the server: {type(exc).__name__}: {exc}")
        return _demo_status()
    except ClientDisconnect:
        # Browser tab closed / connection lost mid-upload: nothing to answer,
        # nothing stored - the current demo stays as it was.
        print("[demo] upload aborted by the client - previous demo kept")
        return Response(status_code=400)
    finally:
        upload.unlink(missing_ok=True)


@app.post("/api/demo/upload")
def start_demo_upload(_token: str = Depends(require_level("service"))):
    """Starts a chunked upload session (before recording): removes partial
    files of abandoned sessions and checks the free disk space (507 if too
    little). Returns {"session_id"}."""
    try:
        return {"session_id": demo_video.start_session()}
    except demo_video.DemoStorageError as exc:
        return _demo_error(507, str(exc))


@app.put("/api/demo/upload/{session_id}")
async def upload_demo_chunk(
    session_id: str, request: Request, offset: int, _token: str = Depends(require_level("service"))
):
    """One MediaRecorder chunk (raw body, a few MB), appended at `offset`."""
    try:
        data = await request.body()
    except ClientDisconnect:
        return Response(status_code=400)
    try:
        size = await run_in_threadpool(demo_video.append_chunk, session_id, offset, data)
    except demo_video.DemoStorageError as exc:
        return _demo_error(413, str(exc))
    except demo_video.DemoSessionError as exc:
        return _demo_error(409, str(exc))
    except OSError as exc:
        return _demo_error(500, f"Writing the chunk failed: {type(exc).__name__}: {exc}")
    return {"size": size}


@app.post("/api/demo/upload/{session_id}/finalize")
async def finalize_demo_upload(
    session_id: str, duration_seconds: float | None = None, _token: str = Depends(require_level("service"))
):
    """Stop: validate, ffmpeg remux (or the duration fix), atomic pointer
    switch, old versions deleted. On failure the uploaded file is kept so
    this can be retried ("Retry saving"); the current demo is untouched."""
    try:
        await run_in_threadpool(demo_video.finalize_session, session_id, duration_seconds)
    except demo_video.DemoSessionError as exc:
        return _demo_error(409, str(exc))
    except demo_video.DemoVideoError as exc:
        return _demo_error(422, str(exc))
    except Exception as exc:  # disk full, permissions, ... - old demo untouched
        print(f"[demo] saving the recording failed: {type(exc).__name__}: {exc}")
        return _demo_error(500, f"Saving failed on the server: {type(exc).__name__}: {exc}")
    return _demo_status()


@app.delete("/api/demo/video")
def delete_demo_video(_token: str = Depends(require_level("service"))) -> dict:
    demo_video.delete()
    return _demo_status()


@app.put("/api/service/demo-settings")
def put_demo_settings(body: DemoSettingsIn, _token: str = Depends(require_level("service"))) -> dict:
    history.set_demo_button_for_all(body.show_for_all)
    return _demo_status()


# Mounted last so it only catches what /api/* and /ws didn't already
# match — Starlette tries routes in registration order, and a mount at
# "/" registered first would shadow every route below it.
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    print(f"[startup] No {STATIC_DIR} — run `npm run build` in frontend/ to serve the dashboard.")


def _lan_ip() -> str:
    """
    Best-effort local IP for the startup banner. The UDP "connect" here
    never sends a packet — it only asks the OS to pick the local address
    it would route through, so this is safe to call even fully offline.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    lan_ip = _lan_ip()
    print("Produktionspilot V2 server starting:")
    print(f"  Local:   http://localhost:{PORT}/")
    print(f"  Network: http://{lan_ip}:{PORT}/")
    print(f"  WS:      ws://{lan_ip}:{PORT}/ws")
    uvicorn.run(app, host=HOST, port=PORT)
