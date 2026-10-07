"""
opcua_source.py
----------------
Production MachineSource — reads real PLC state over OPC UA.

Each PLC is its own OPC UA server, so OpcUaSource keeps one Client
connection per configured IP (see _PlcConnection). Runs inside
MachineWorker's QThread poll loop (worker.py), so nothing here may
touch Qt widgets, and no read is allowed to block for long — a dead
PLC must not stall the other PLCs' reads or the poll loop itself.

Node IDs (confirmed identical on every connected PLC, Tim), all in
namespace _NAMESPACE_INDEX as string node ids:
    state:           "::auto:external_machine_state"  -> int 0..5, see
                      PLC_STATE_MAP below for the value mapping
    remaining time:  "::auto:ActRestzeitGes"           -> int seconds,
                      no scaling conversion needed
  Optional (a failed read never takes the PLC offline — see _OPTIONAL_NODES):
    current oil temp: "::tempregl:ActOilTemp"                      -> float °C
    target oil temp:  "::AsGlobalPV:gFormatSet.BackTemperatur"     -> number °C
    recipe name:      "::AsGlobalPV:gFormatVerwaltung.ActFormatName" -> string
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from opcua import Client
except ImportError:
    print("Missing dependency. Install it with:\n  pip install opcua --break-system-packages")
    sys.exit(1)

from .models import MachineGroup, MachineState, PlcData
from .plc_config import load_config

CONFIG_PATH = Path(__file__).resolve().parent / "plc_config.json"

DEFAULT_PORT = 4841   # Opelka's B&R PLCs — confirmed working
_CONNECT_TIMEOUT = 2.0  # seconds — short so a dead PLC can't stall the poll loop

_STATE_NODE_ID = "::auto:external_machine_state"
_REMAINING_TIME_NODE_ID = "::auto:ActRestzeitGes"
_OIL_TEMP_CURRENT_NODE_ID = "::tempregl:ActOilTemp"
_OIL_TEMP_TARGET_NODE_ID = "::AsGlobalPV:gFormatSet.BackTemperatur"
_RECIPE_NAME_NODE_ID = "::AsGlobalPV:gFormatVerwaltung.ActFormatName"

# Raw value of _STATE_NODE_ID -> MachineState. The ONE place that knows
# the PLC's numbers (state mapping v3, Tim) — everything else, including
# history.db (which stores MachineState NAMES), only sees MachineState.
# Cold/Hot are not PLC values any more: hot_cold.py derives them from
# STANDBY + oil temperature.
PLC_STATE_MAP: dict[int, MachineState] = {
    0: MachineState.ERROR,
    1: MachineState.STANDBY,   # NOT in auto mode
    2: MachineState.HEATING,
    3: MachineState.WAITING,
    4: MachineState.BLOCKED,   # waiting for another machine
    5: MachineState.BAKING,
}

# Raw values already warned about — one warning per distinct value for the
# lifetime of the process, not one per poll.
_warned_state_values: set = set()


def state_from_plc_value(value) -> MachineState:
    """PLC_STATE_MAP lookup. Anything else (an int outside the map, a
    negative, a non-integer, None) is MachineState.UNRECOGNIZED — never an
    exception, so an unexpected value can't take the PLC offline."""
    if isinstance(value, int) and not isinstance(value, bool) and value in PLC_STATE_MAP:
        return PLC_STATE_MAP[value]
    key = repr(value)
    if key not in _warned_state_values:
        _warned_state_values.add(key)
        print(f"[opcua] unrecognized machine state value {key} — showing it as Unknown")
    return MachineState.UNRECOGNIZED


# B&R Automation Studio auto-exported OPC UA globals (the "::auto:" prefix)
# live in this namespace on Opelka's PLCs.
_NAMESPACE_INDEX = 6


def _node_id(identifier: str) -> str:
    return f"ns={_NAMESPACE_INDEX};s={identifier}"


def _to_temperature(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _to_recipe_name(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    # PLC strings are often fixed-length buffers padded with NULs.
    text = str(value).replace("\x00", "").strip()
    return text or None


# PlcReading field -> (node identifier, converter). Read after the required
# state/remaining-time nodes; each one is independent and optional — see
# _PlcConnection._read_optional.
_OPTIONAL_NODES = {
    "oil_temp_current": (_OIL_TEMP_CURRENT_NODE_ID, _to_temperature),
    "oil_temp_target": (_OIL_TEMP_TARGET_NODE_ID, _to_temperature),
    "recipe_name": (_RECIPE_NAME_NODE_ID, _to_recipe_name),
}


@dataclass
class PlcReading:
    state: MachineState
    remaining_seconds: int | None
    oil_temp_current: float | None = None
    oil_temp_target: float | None = None
    recipe_name: str | None = None


# ---------------------------------------------------------------------------
# One OPC UA client connection to a single PLC
# ---------------------------------------------------------------------------

class _PlcConnection:
    """
    Owns the Client for one PLC IP. Connects lazily and reconnects
    automatically: any read failure drops the client so the next
    read() call attempts a fresh connect — no separate reconnect logic
    needed, and a currently-dead PLC never blocks longer than
    _CONNECT_TIMEOUT per poll.
    """

    def __init__(self, ip: str, port: int):
        self._ip = ip
        self._port = port
        self._client: Client | None = None
        # Optional node identifiers whose current failure streak has
        # already been logged — one warning per streak, not one per poll.
        self._warned: set[str] = set()

    def _connect(self) -> None:
        client = Client(f"opc.tcp://{self._ip}:{self._port}", timeout=_CONNECT_TIMEOUT)
        client.connect()
        self._client = client

    def _drop(self) -> None:
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

    def _read_optional(self, identifier: str, convert):
        """One optional node: its converted value, or None on any failure
        (missing node, bad value, ...). Never raises and never drops the
        connection — the required reads already proved the PLC is up."""
        try:
            value = convert(self._client.get_node(_node_id(identifier)).get_value())
        except Exception as exc:
            if identifier not in self._warned:
                self._warned.add(identifier)
                print(f"[opcua] {self._ip}: optional node {identifier!r} unreadable ({exc}) — showing it as blank")
            return None
        if identifier in self._warned:
            self._warned.discard(identifier)
            print(f"[opcua] {self._ip}: optional node {identifier!r} readable again")
        return value

    def read(self) -> PlcReading | None:
        """
        Returns a PlcReading on success, or None if the PLC is
        unreachable or the connection fails. Never raises. An unexpected
        state VALUE is not a failure: it reads as UNRECOGNIZED (see
        state_from_plc_value) and the PLC stays online. Only the state
        and remaining-time reads decide online/offline; the optional
        nodes (temperatures, recipe) just come back as None when they
        can't be read.
        """
        try:
            if self._client is None:
                self._connect()

            state = state_from_plc_value(self._client.get_node(_node_id(_STATE_NODE_ID)).get_value())

            remaining_value = self._client.get_node(_node_id(_REMAINING_TIME_NODE_ID)).get_value()
            remaining_seconds = int(remaining_value) if remaining_value is not None else None
        except Exception:
            # Covers unreachable host and failed/expired session alike —
            # don't guess, just go offline
            # and let the next poll's lazy _connect() retry from scratch.
            self._drop()
            return None

        optional = {
            field: self._read_optional(identifier, convert)
            for field, (identifier, convert) in _OPTIONAL_NODES.items()
        }
        return PlcReading(state=state, remaining_seconds=remaining_seconds, **optional)


# ---------------------------------------------------------------------------
# Production MachineSource
# ---------------------------------------------------------------------------

class OpcUaSource:
    """
    Drop-in replacement for SimulatedSource, backed by real PLCs.
    Built from plc_config.json (see plc_config.py for the format) — one
    MachineGroup per configured machine, one _PlcConnection
    per PLC IP.
    """

    def __init__(self, config_path: Path | str = CONFIG_PATH):
        self._groups: list[MachineGroup] = []
        self._connections: dict[str, _PlcConnection] = {}
        self._online: dict[str, bool] = {}
        self._load_config(Path(config_path))

    def _load_config(self, config_path: Path) -> None:
        data = load_config(config_path)

        default_port = data.get("port", DEFAULT_PORT)

        for machine in data.get("machines", []):
            port = machine.get("port", default_port)
            plcs: list[PlcData] = []
            for index, entry in enumerate(machine["plcs"]):
                ip = entry["ip"]
                # Order in the config's "plcs" array = saved default
                # priority, index 0 = highest. unit_number is the
                # technician-set machine number (see plc_config.py) —
                # independent of that order — and drives the on-screen
                # label, built at render time (utils.format_unit_name) so
                # it stays translatable. name here is just an internal
                # identity label, never shown.
                plcs.append(PlcData(
                    ip=ip,
                    name=f"PLC {index + 1}",
                    state=MachineState.STANDBY,
                    is_online=False,
                    default_priority=index,
                    unit_number=entry["unit_number"],
                ))
                self._connections[ip] = _PlcConnection(ip, port)
                self._online[ip] = False
            self._groups.append(MachineGroup(
                name=machine["name"], type=machine["type"], plcs=plcs,
            ))

    def get_machines(self) -> list[MachineGroup]:
        for group in self._groups:
            for plc in group.plcs:
                try:
                    result = self._connections[plc.ip].read()
                except Exception:
                    # Belt-and-braces: _PlcConnection.read() already
                    # swallows its own errors, but one PLC's bookkeeping
                    # must never take the rest of the poll down with it.
                    result = None

                if result is None:
                    plc.is_online = False
                    plc.remaining_seconds = None
                    # Last-known values aren't trustworthy while offline —
                    # show blanks rather than stale numbers.
                    plc.oil_temp_current = None
                    plc.oil_temp_target = None
                    plc.recipe_name = None
                else:
                    plc.state = result.state
                    plc.remaining_seconds = result.remaining_seconds
                    plc.oil_temp_current = result.oil_temp_current
                    plc.oil_temp_target = result.oil_temp_target
                    plc.recipe_name = result.recipe_name
                    plc.is_online = True
                self._online[plc.ip] = plc.is_online

        return list(self._groups)

    def is_connected(self) -> bool:
        return any(self._online.values())
