from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class MachineState(Enum):
    COLD    = "Cold"
    HEATING = "Heating"
    READY   = "Ready"
    BAKING  = "Baking"
    ERROR   = "Error"


# Colors used by the UI — defined once here so both views stay in sync.
# OFFLINE is not a state (see PlcData.is_online); it's a connection
# condition that can co-occur with any of the states above, rendered via
# OFFLINE_STYLE instead of a state color.
STATE_COLORS: dict[MachineState, dict[str, str]] = {
    MachineState.COLD:    {"bg": "#6B7280", "fg": "#FFFFFF"},  # Grey
    MachineState.HEATING: {"bg": "#F59E0B", "fg": "#1C1C1C"},  # Amber
    MachineState.READY:   {"bg": "#1D4ED8", "fg": "#FFFFFF"},  # Blue  — call to action
    MachineState.BAKING:  {"bg": "#16A34A", "fg": "#FFFFFF"},  # Green — process running
    MachineState.ERROR:   {"bg": "#DC2626", "fg": "#FFFFFF"},  # Red
}

# Describes the visual treatment for an offline PLC: a neutral dark grey
# box (deliberately NOT one of STATE_COLORS — the last-known state is not
# shown while offline, since we don't actually know it's still true),
# dimmed further and dashed-outlined so it's unmistakably distinct from
# the solid-grey Cold state.
OFFLINE_STYLE: dict[str, object] = {
    "opacity": 0.5,
    "border_style": "dashed",
    "border_color": "#94A3B8",
    "background_color": "#374151",
    "text_color": "#E5E7EB",
}


# Maps the integer value of the "::auto:external_machine_state" OPC UA
# node (confirmed by Tim, identical on every PLC) to MachineState.
OPCUA_STATE_MAP: dict[int, MachineState] = {
    0: MachineState.ERROR,
    1: MachineState.COLD,
    2: MachineState.HEATING,
    3: MachineState.READY,
    4: MachineState.BAKING,
}


@dataclass
class PlcData:
    """A single physical PLC unit within a MachineGroup."""
    ip:                str
    name:              str   # internal identity label (debugging/tests) — NOT the on-screen unit name, see unit_number
    state:             MachineState
    is_online:         bool
    remaining_seconds: int | None = None   # only meaningful when BAKING
    default_priority:  int = 0             # index in saved install-time order, 0 = highest
    unit_number:       int = 0             # 1-based position within the machine; display layer builds a translated "{unit word} {n}" label from this (see utils.format_unit_name), so switching language updates it live
    recipe:            str | None = None   # current recipe/product name — plumbing only for now; no OPC UA node for this exists yet (pending a node ID from Tim), so this is always None until something actually sets it. Never fabricate a value here.

    def to_dict(self) -> dict:
        """
        JSON-ready dict for the web frontend. Deliberately excludes
        `name` (internal-only, never shown) and sends raw
        remaining_seconds/state-name rather than pre-formatted or
        colored values — the frontend owns localisation and styling.

        `ip` is included for Service-level consumers (the Installation
        Wizard) that still need it — the Dashboard views simply choose
        not to render it (see FryerTile.svelte / MachineListRow.svelte).
        """
        return {
            "ip": self.ip,
            "unit_number": self.unit_number,
            "state": self.state.name,
            "is_online": self.is_online,
            "remaining_seconds": self.remaining_seconds,
            "default_priority": self.default_priority,
            "recipe": self.recipe,
        }


@dataclass
class MachineGroup:
    """A machine made up of one or more PLCs (Standalone / DUO / TRIO / QUATTRO)."""
    name:  str
    type:  str                    # "STANDALONE" | "DUO" | "TRIO" | "QUATTRO"
    plcs:  list[PlcData] = field(default_factory=list)   # order here = default priority order
