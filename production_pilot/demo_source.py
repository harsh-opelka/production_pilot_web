"""
demo_source.py
----------------
SimulatedSource — a MachineSource with the same interface as
OpcUaSource (get_machines(), is_connected()), backed by in-memory state
a technician edits from the Service page instead of real OPC UA reads.

Everything downstream (priority calculation, history logging, WS
broadcast, KPI endpoints) only ever sees the MachineGroup/PlcData
structures both sources produce — server.py's poll loop is the single
place that picks which source is active (see _poll_loop), so nothing
here needs to be, or should be, source-aware.

On init, mirrors the actual installed configuration (plc_config.json —
same group names/types/IPs/priority order/machine numbers OpcUaSource
would build) so
demo data looks like the real site. Falls back to one default demo
group when there's no config yet (e.g. before the Installation Wizard
has run), so Demo Mode always has something to show.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from .models import MachineGroup, MachineState, PlcData
from .opcua_source import CONFIG_PATH
from .plc_config import load_config

#: Fixed recipe choices offered by the Demo Controls panel (see
#: server.py's DemoSetStateIn / /api/service/demo/set-state, which
#: validates against this same list). Real PLCs report their own recipe
#: (see opcua_source.py) — this only ever populates PlcData.recipe_name
#: while data_source_mode is "demo".
RECIPE_OPTIONS = ("Quarkballs", "Berliners", "Donuts", "Apfelschnenken")

# Demo-only oil temperatures (°C) — invented here so the tile's
# "current / target" line has something to show in Demo Mode. Never used
# by OpcUaSource; real mode shows only what the PLC reports.
_DEMO_TARGET_TEMP = 180.0
_DEMO_COLD_TEMP = 22.0
_DEMO_HEAT_RATE = 3.0   # °C per second while HEATING
_DEMO_COOL_RATE = 0.5   # °C per second while COLD

_DEFAULT_GROUP_NAME = "Demo Station"
_DEFAULT_GROUP_TYPE = "QUATTRO"
_DEFAULT_UNIT_COUNT = 4
# RFC 5737 TEST-NET-1 — guaranteed non-routable, so a default demo IP can
# never collide with (or be mistaken for) a real PLC address.
_DEFAULT_IP_PREFIX = "192.0.2."


def _default_plc(index: int, ip: str, unit_number: int | None = None) -> PlcData:
    """index = priority position; unit_number = the configured machine
    number (see plc_config.py), defaulting to index + 1 for the built-in
    demo group, which has no config to take it from."""
    return PlcData(
        ip=ip,
        name=f"PLC {index + 1}",
        state=MachineState.WAITING,
        is_online=True,
        default_priority=index,
        unit_number=unit_number if unit_number is not None else index + 1,
        oil_temp_current=_DEMO_TARGET_TEMP,
        oil_temp_target=_DEMO_TARGET_TEMP,
    )


class SimulatedSource:
    """
    Drop-in replacement for OpcUaSource. Holds its groups/PLCs in memory
    for the lifetime of the process — set_plc_state() is the only way
    their state changes; there is no polling of anything real here.
    """

    def __init__(self, config_path: Path | str = CONFIG_PATH):
        self._groups: list[MachineGroup] = []
        self._lock = threading.Lock()
        self._last_tick = time.monotonic()
        # Fractional leftover seconds not yet applied to a BAKING PLC's
        # remaining_seconds, keyed by ip — without this, repeatedly
        # rounding each ~0.5s poll interval straight to an int would drift
        # (e.g. a countdown could stall or run fast) instead of tracking
        # real elapsed wall-clock time exactly. See _tick.
        self._carry: dict[str, float] = {}
        self._load(Path(config_path))

    def _load(self, config_path: Path) -> None:
        if config_path.exists():
            try:
                self._load_from_config(config_path)
                if self._groups:
                    return
            except Exception as exc:
                print(f"[demo] failed to load {config_path} ({exc}) — using default demo group.")
        self._load_default()

    def _load_from_config(self, config_path: Path) -> None:
        data = load_config(config_path)

        groups: list[MachineGroup] = []
        for machine in data.get("machines", []):
            plcs = [
                _default_plc(index, entry["ip"], entry["unit_number"])
                for index, entry in enumerate(machine["plcs"])
            ]
            groups.append(MachineGroup(name=machine["name"], type=machine["type"], plcs=plcs))
        self._groups = groups

    def _load_default(self) -> None:
        self._groups = [
            MachineGroup(
                name=_DEFAULT_GROUP_NAME,
                type=_DEFAULT_GROUP_TYPE,
                plcs=[
                    _default_plc(i, f"{_DEFAULT_IP_PREFIX}{10 + i}")
                    for i in range(_DEFAULT_UNIT_COUNT)
                ],
            )
        ]

    def get_machines(self) -> list[MachineGroup]:
        with self._lock:
            self._tick()
            return list(self._groups)

    def is_connected(self) -> bool:
        return True

    def resync_clock(self) -> None:
        """Resets the tick baseline to now, WITHOUT touching any PLC's
        remaining_seconds. Called by server.py whenever demo mode is
        (re)activated (see the /api/service/data-source switch) so a long
        stretch spent in Real PLCs mode — during which nothing here ever
        calls get_machines(), so _last_tick goes stale — doesn't get
        misread as one giant elapsed interval and slam every BAKING PLC's
        countdown straight to 0 the next time it's actually ticked."""
        with self._lock:
            self._last_tick = time.monotonic()

    def _tick(self) -> None:
        """Decrements every BAKING PLC's remaining_seconds by the actual
        wall-clock time elapsed since the last call (never a fixed 0.5s
        assumption — polling isn't perfectly metronomic), floored at 0.
        Reaching 0 (including via a tester manually setting it to 0 from
        the demo panel) auto-advances the PLC straight to WAITING — a real
        PLC's own state naturally moves on once the bake finishes, so a
        simulated one shouldn't sit frozen at "Almost finished" forever
        either. Caller holds _lock."""
        now = time.monotonic()
        elapsed = now - self._last_tick
        self._last_tick = now
        if elapsed <= 0:
            return

        for group in self._groups:
            for plc in group.plcs:
                self._tick_temperature(plc, elapsed)
                if plc.state != MachineState.BAKING or plc.remaining_seconds is None:
                    continue
                whole, fraction = divmod(self._carry.get(plc.ip, 0.0) + elapsed, 1.0)
                self._carry[plc.ip] = fraction
                if whole:
                    plc.remaining_seconds = max(0, plc.remaining_seconds - int(whole))
                if plc.remaining_seconds == 0:
                    plc.state = MachineState.WAITING
                    plc.remaining_seconds = None
                    self._carry.pop(plc.ip, None)

    @staticmethod
    def _tick_temperature(plc: PlcData, elapsed: float) -> None:
        """Demo-only oil temperature: cools towards room temperature while
        COLD (0.5 °C/s, so a Cold-reported machine visibly goes from Hot to
        Cold across the threshold — see hot_cold.py), climbs to the target
        while HEATING, and otherwise holds its value — so a temperature set
        from Demo Controls sticks instead of snapping back."""
        current = plc.oil_temp_current if plc.oil_temp_current is not None else _DEMO_COLD_TEMP
        target = _DEMO_TARGET_TEMP
        if plc.state == MachineState.COLD:
            current = max(_DEMO_COLD_TEMP, current - _DEMO_COOL_RATE * elapsed)
        elif plc.state == MachineState.HEATING:
            current = min(target, current + _DEMO_HEAT_RATE * elapsed)
        plc.oil_temp_current = round(current, 1)
        plc.oil_temp_target = target

    def _find(self, group_name: str, ip: str) -> PlcData | None:
        for group in self._groups:
            if group.name != group_name:
                continue
            for plc in group.plcs:
                if plc.ip == ip:
                    return plc
        return None

    def set_plc_state(
        self,
        group_name: str,
        ip: str,
        *,
        state: str | None = None,
        is_online: bool | None = None,
        remaining_seconds: int | None = None,
        recipe: str | None = None,
        oil_temp_current: float | None = None,
    ) -> None:
        """Updates only the fields passed (None = leave unchanged) on the
        given PLC. Raises KeyError if group_name/ip doesn't match any
        currently simulated PLC.

        recipe is the one field that needs to be explicitly CLEARABLE
        (the demo panel's recipe dropdown has a blank "None" option) —
        None still means "not provided" like every other parameter here,
        but an empty string means "clear it", so it round-trips to
        PlcData.recipe_name's own None-means-unset convention rather than
        getting stuck on a stale recipe name forever."""
        with self._lock:
            plc = self._find(group_name, ip)
            if plc is None:
                raise KeyError(f"No PLC {ip!r} in group {group_name!r}")

            if state is not None:
                plc.state = MachineState[state]
            if is_online is not None:
                plc.is_online = is_online
            if remaining_seconds is not None:
                plc.remaining_seconds = remaining_seconds
                # A tester just set an exact value — any leftover fractional
                # carry from before must not immediately eat into it on the
                # next tick (see _tick).
                self._carry.pop(ip, None)
            if recipe is not None:
                plc.recipe_name = recipe or None
            if oil_temp_current is not None:
                plc.oil_temp_current = float(oil_temp_current)
