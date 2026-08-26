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

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from production_pilot import history, scan_plcs, service_config, stats
from production_pilot.models import MachineGroup
from production_pilot.opcua_source import CONFIG_PATH, OpcUaSource
from production_pilot.serializers import build_state

POLL_INTERVAL_SECONDS = 0.5
HEARTBEAT_INTERVAL_SECONDS = 5.0
HOST = "0.0.0.0"
PORT = 8000

SESSION_TTL_SECONDS = 30 * 60
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 5 * 60

STATIC_DIR = Path(__file__).resolve().parent / "static"

_EMPTY_STATE = {"connected": False, "timestamp": None, "groups": []}


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


# ---------------------------------------------------------------------------
# History (KPI) logging — change detection only, no lock needed: this dict
# is only ever touched from the poll thread itself, never from a request
# handler. Kept up to date regardless of the recording toggle (see
# _detect_and_log_transitions) so turning recording back on later compares
# against real data instead of stale pre-toggle state.
# ---------------------------------------------------------------------------

_last_known: dict[str, tuple[str, str, bool]] = {}  # plc.ip -> (group_name, state.name, is_online)


def _detect_and_log_transitions(groups: list[MachineGroup]) -> None:
    for group in groups:
        for plc in group.plcs:
            current = (group.name, plc.state.name, plc.is_online)
            previous = _last_known.get(plc.ip)
            if previous == current:
                continue

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


def _poll_loop() -> None:
    """
    Runs forever in a daemon thread, one poll every POLL_INTERVAL_SECONDS
    — same cadence V1 used. Never lets an exception escape: a single bad
    cycle (or an unconfigured/unreachable install) must not kill the
    thread and freeze the state the API serves.
    """
    while True:
        source = _get_source()
        if source is None:
            _set_state({**_EMPTY_STATE, "timestamp": _now_iso()})
        else:
            try:
                groups = source.get_machines()
                connected = source.is_connected()
                _detect_and_log_transitions(groups)
                _set_state(build_state(groups, connected))
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
    (groups/connected) changes, and otherwise sends a lightweight
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

        state = get_state()
        content_key = json.dumps(
            {"connected": state["connected"], "groups": state["groups"]},
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
    header. Needed for exactly one endpoint: the CSV export, which the
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


class MachineIn(BaseModel):
    name: str
    type: str
    plcs: list[str]


class ConfigIn(BaseModel):
    machines: list[MachineIn]


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


class RecordingIn(BaseModel):
    enabled: bool


class HistoryClearIn(BaseModel):
    confirm: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    history.init_db()
    _set_source(_load_source())
    poll_thread = threading.Thread(target=_poll_loop, daemon=True, name="opcua-poll")
    poll_thread.start()

    broadcast_task = asyncio.create_task(_broadcast_loop())
    try:
        yield
    finally:
        broadcast_task.cancel()


app = FastAPI(title="Produktionspilot V2 API", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/machines")
def get_machines() -> dict:
    return get_state()


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    try:
        await websocket.send_text(json.dumps({"type": "state", **get_state()}))
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
    if not CONFIG_PATH.exists():
        return {"machines": []}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"machines": []}


_VALID_MACHINE_TYPES = {"STANDALONE", "DUO", "TRIO", "QUATTRO"}


def _validate_config(config: ConfigIn) -> None:
    seen_ips: set[str] = set()
    for machine in config.machines:
        if not machine.name.strip():
            raise HTTPException(status_code=400, detail="Machine name must not be empty")
        if machine.type not in _VALID_MACHINE_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid machine type: {machine.type}")
        if not machine.plcs:
            raise HTTPException(status_code=400, detail=f"Machine '{machine.name}' has no PLCs")
        for ip in machine.plcs:
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid IP address: {ip}")
            if ip in seen_ips:
                raise HTTPException(status_code=400, detail=f"IP {ip} is assigned to more than one machine")
            seen_ips.add(ip)


@app.post("/api/service/config")
def service_save_config(body: ConfigIn, _token: str = Depends(require_level("service"))) -> dict:
    _validate_config(body)
    data = {"machines": [m.model_dump() for m in body.machines]}
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    _reload_source()  # picks up the new config without a server restart
    return {"ok": True}


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


# ---------------------------------------------------------------------------
# History (KPI) logging controls. Data-capture only for now — no
# viewing/aggregation endpoints yet, just enable/disable, wipe, and enough
# of a summary to confirm rows are actually landing. All Service-level, so
# all four require a session same as the endpoints above.
# ---------------------------------------------------------------------------


@app.get("/api/service/recording-status")
def service_recording_status(_token: str = Depends(require_level("service"))) -> dict:
    return {"enabled": history.is_recording_enabled()}


@app.post("/api/service/recording")
def service_set_recording(body: RecordingIn, request: Request, _token: str = Depends(require_level("service"))) -> dict:
    history.set_recording_enabled(body.enabled)
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


@app.get("/api/stats/daily-summary")
def stats_daily_summary(date: str | None = None, _token: str = Depends(require_level("management"))) -> dict:
    date = date or stats.today_local()
    _validate_date(date)
    return stats.compute_daily_summary(date)


@app.get("/api/stats/available-dates")
def stats_available_dates(_token: str = Depends(require_level("management"))) -> dict:
    return {"dates": history.get_available_dates()}


@app.get("/api/stats/daily-summary/csv")
def stats_daily_summary_csv(
    date: str | None = None, _token: str = Depends(require_level_from_header_or_query("management"))
) -> Response:
    date = date or stats.today_local()
    _validate_date(date)
    csv_text = stats.to_csv(stats.compute_daily_summary(date))
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="daily-summary-{date}.csv"'},
    )


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
