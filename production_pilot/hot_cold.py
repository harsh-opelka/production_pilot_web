"""
hot_cold.py
-----------
Decides Hot vs Cold from the oil temperature instead of trusting the PLC:
the PLC reports Cold (1) even while the oil is still hot.

Applied in exactly ONE place — server.py's poll loop, right after the
active source is read and BEFORE transitions are compared and written to
history.db — so the tiles, the Next Action banner ("Switch to Auto" for
Hot), the top-bar KPIs and Statistics all see the same derived state.
The frontend never re-derives it.

Rule, for an ONLINE PLC whose raw state is Cold or Hot and whose current
oil temperature is readable:
    temp >= threshold                 -> Hot
    temp <  threshold - HYSTERESIS_C  -> Cold
    in between                        -> whatever it was on the last poll
                                         (Cold if there is no last poll)
No readable temperature -> the raw PLC state. Every other state (Error,
Heating, Waiting, Blocked, Baking) and offline PLCs are never touched.
"""

from __future__ import annotations

import math
from dataclasses import replace

from .models import MachineGroup, MachineState

#: Default Hot/Cold threshold in °C (Service-configurable, stored in
#: app_settings — see history.get_hot_cold_threshold_c).
DEFAULT_THRESHOLD_C = 50.0
MIN_THRESHOLD_C = 20.0
MAX_THRESHOLD_C = 150.0

#: Once Hot, a machine only goes back to Cold below threshold - this, so a
#: temperature hovering around the threshold doesn't flicker.
HYSTERESIS_C = 2.0

_IDLE_STATES = (MachineState.COLD, MachineState.HOT)


def validate_threshold(value) -> float:
    """The threshold as a float, or ValueError with a human-readable reason."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Threshold must be a number (°C)")
    if not MIN_THRESHOLD_C <= value <= MAX_THRESHOLD_C:
        raise ValueError(
            f"Threshold must be between {MIN_THRESHOLD_C:g} and {MAX_THRESHOLD_C:g} °C (got {value:g})"
        )
    return float(value)


def classify(
    raw_state: MachineState,
    temp_c: float | None,
    threshold_c: float,
    previous: MachineState | None = None,
) -> MachineState:
    """Pure rule (see module docstring). `previous` is this PLC's derived
    Hot/Cold from the last poll, or None."""
    if raw_state not in _IDLE_STATES or temp_c is None:
        return raw_state
    if temp_c >= threshold_c:
        return MachineState.HOT
    if temp_c < threshold_c - HYSTERESIS_C:
        return MachineState.COLD
    return previous if previous in _IDLE_STATES else MachineState.COLD


class HotColdRule:
    """Applies classify() to a whole poll, remembering each PLC's last
    derived Hot/Cold (by IP) for the hysteresis band."""

    def __init__(self) -> None:
        self._last: dict[str, MachineState] = {}

    def apply(self, groups: list[MachineGroup], threshold_c: float) -> list[MachineGroup]:
        """Returns copies of `groups` with the derived state. Copies, so the
        data sources keep their raw PLC state (the demo source's Demo
        Controls edit that raw state)."""
        result = []
        for group in groups:
            plcs = []
            for plc in group.plcs:
                derived = plc.state
                if plc.is_online and plc.state in _IDLE_STATES and plc.oil_temp_current is not None:
                    derived = classify(plc.state, plc.oil_temp_current, threshold_c, self._last.get(plc.ip))
                    self._last[plc.ip] = derived
                else:
                    # Hysteresis only bridges consecutive idle polls with a
                    # temperature; anything else starts fresh next time.
                    self._last.pop(plc.ip, None)
                plcs.append(replace(plc, state=derived))
            result.append(MachineGroup(name=group.name, type=group.type, plcs=plcs))
        return result
