"""
opcua_source.py
----------------
Production MachineSource — reads real PLC state over OPC UA.

Each PLC is its own OPC UA server, so OpcUaSource keeps one Client
connection per configured IP (see _PlcConnection). Runs inside
MachineWorker's QThread poll loop (worker.py), so nothing here may
touch Qt widgets, and no read is allowed to block for long — a dead
PLC must not stall the other PLCs' reads or the poll loop itself.

Node IDs (confirmed identical on every connected PLC, Tim):
    state:           "::auto:external_machine_state"  -> int, see
                      models.OPCUA_STATE_MAP for the value mapping
    remaining time:  "::auto:ActRestzeitGes"           -> int seconds,
                      no scaling conversion needed
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from opcua import Client
except ImportError:
    print("Missing dependency. Install it with:\n  pip install opcua --break-system-packages")
    sys.exit(1)

from .models import MachineGroup, MachineState, OPCUA_STATE_MAP, PlcData

CONFIG_PATH = Path(__file__).resolve().parent / "plc_config.json"

DEFAULT_PORT = 4841   # Opelka's B&R PLCs — confirmed working
_CONNECT_TIMEOUT = 2.0  # seconds — short so a dead PLC can't stall the poll loop

_STATE_NODE_ID = "::auto:external_machine_state"
_REMAINING_TIME_NODE_ID = "::auto:ActRestzeitGes"

# B&R Automation Studio auto-exported OPC UA globals (the "::auto:" prefix)
# live in this namespace on Opelka's PLCs.
_NAMESPACE_INDEX = 6


def _node_id(identifier: str) -> str:
    return f"ns={_NAMESPACE_INDEX};s={identifier}"


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

    def read(self) -> tuple[MachineState, int | None] | None:
        """
        Returns (state, remaining_seconds) on success, or None if the PLC
        is unreachable, the connection fails, or the state node doesn't
        return a value in OPCUA_STATE_MAP. Never raises.
        """
        try:
            if self._client is None:
                self._connect()

            state_value = self._client.get_node(_node_id(_STATE_NODE_ID)).get_value()
            state = OPCUA_STATE_MAP.get(int(state_value))
            if state is None:
                raise ValueError(f"unrecognized machine state {state_value!r}")

            remaining_value = self._client.get_node(_node_id(_REMAINING_TIME_NODE_ID)).get_value()
            remaining_seconds = int(remaining_value) if remaining_value is not None else None

            return state, remaining_seconds
        except Exception:
            # Covers unreachable host, failed/expired session, and a
            # malformed state value alike — don't guess, just go offline
            # and let the next poll's lazy _connect() retry from scratch.
            self._drop()
            return None


# ---------------------------------------------------------------------------
# Production MachineSource
# ---------------------------------------------------------------------------

class OpcUaSource:
    """
    Drop-in replacement for SimulatedSource, backed by real PLCs.
    Built from plc_config.json (see wizard/install_wizard.py for the
    format) — one MachineGroup per configured machine, one _PlcConnection
    per PLC IP.
    """

    def __init__(self, config_path: Path | str = CONFIG_PATH):
        self._groups: list[MachineGroup] = []
        self._connections: dict[str, _PlcConnection] = {}
        self._online: dict[str, bool] = {}
        self._load_config(Path(config_path))

    def _load_config(self, config_path: Path) -> None:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        default_port = data.get("port", DEFAULT_PORT)

        for machine in data.get("machines", []):
            port = machine.get("port", default_port)
            plcs: list[PlcData] = []
            for index, ip in enumerate(machine.get("plcs", [])):
                # Order in the config's "plcs" array = saved default
                # priority, index 0 = highest (see install_wizard.py).
                # unit_number drives the on-screen "Fryer N" label, built
                # at render time (utils.format_unit_name) so it stays
                # translatable — name here is just an internal identity
                # label, never shown.
                plcs.append(PlcData(
                    ip=ip,
                    name=f"PLC {index + 1}",
                    state=MachineState.COLD,
                    is_online=False,
                    default_priority=index,
                    unit_number=index + 1,
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
                else:
                    plc.state, plc.remaining_seconds = result
                    plc.is_online = True
                self._online[plc.ip] = plc.is_online

        return list(self._groups)

    def is_connected(self) -> bool:
        return any(self._online.values())
