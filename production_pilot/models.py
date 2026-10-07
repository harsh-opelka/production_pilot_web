from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class MachineState(Enum):
    """history.db stores these NAMES (state_transitions.new_state/old_state
    are TEXT), so a member must never be renamed without a migration —
    see history.migrate_state_mapping. Which raw PLC value maps to which
    member lives in opcua_source.PLC_STATE_MAP."""
    ERROR   = "Error"
    # Cold / Hot are PROXY states of STANDBY, derived from the oil
    # temperature (hot_cold.py) — the PLC never reports them itself.
    COLD    = "Cold"
    HOT     = "Hot"       # hot, but NOT in auto mode — needs switching to auto
    HEATING = "Heating"
    WAITING = "Waiting"   # empty and ready to load (called READY before state mapping v2)
    BLOCKED = "Blocked"   # waiting for another machine — nothing to do here
    BAKING  = "Baking"
    # Raw PLC state: NOT in auto mode. Only ever shown as itself when the
    # oil temperature is unreadable; otherwise hot_cold.py turns it into
    # COLD or HOT.
    STANDBY = "Standby"
    # The PLC sent a value outside PLC_STATE_MAP. Shown as "Unknown", but
    # deliberately NOT named UNKNOWN: that name is already taken in
    # state_transitions by history.UNKNOWN_MARKER (server-startup marker).
    UNRECOGNIZED = "Unknown"


# V1 (Qt) colour table — not read by the V2 web UI, whose single source
# of truth for state colours is frontend/src/app.css (--state-* tokens).
# Kept in step with those tokens so the two never disagree.
# OFFLINE is not a state (see PlcData.is_online); it's a connection
# condition that can co-occur with any of the states above, rendered via
# OFFLINE_STYLE instead of a state color.
STATE_COLORS: dict[MachineState, dict[str, str]] = {
    MachineState.ERROR:   {"bg": "#DC2626", "fg": "#FFFFFF"},  # Red
    MachineState.COLD:    {"bg": "#6B7280", "fg": "#FFFFFF"},  # Grey
    MachineState.HOT:     {"bg": "#FACC15", "fg": "#1C1C1C"},  # Yellow
    MachineState.HEATING: {"bg": "#F59E0B", "fg": "#1C1C1C"},  # Amber
    MachineState.WAITING: {"bg": "#05346C", "fg": "#FFFFFF"},  # Opelka blue — call to action
    MachineState.BLOCKED: {"bg": "#334E68", "fg": "#FFFFFF"},  # Slate, dashed border in the UI
    MachineState.BAKING:  {"bg": "#16A34A", "fg": "#FFFFFF"},  # Green — process running
    MachineState.STANDBY: {"bg": "#6B7280", "fg": "#FFFFFF"},  # Cold's grey, lighter border in the UI
    MachineState.UNRECOGNIZED: {"bg": "#6B7280", "fg": "#FFFFFF"},  # same as Standby
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
    recipe_name:       str | None = None   # current recipe/format name (OPC UA ::AsGlobalPV:gFormatVerwaltung.ActFormatName). None = unknown/empty — never fabricate a value here in real mode.
    oil_temp_current:  float | None = None # °C, OPC UA ::tempregl:ActOilTemp. None = not readable.
    oil_temp_target:   float | None = None # °C, OPC UA ::AsGlobalPV:gFormatSet.BackTemperatur. None = not readable.
    state_entered_at:  str | None = None   # ISO 8601 UTC timestamp of the most recent transition INTO the current state — set by server.py's poll loop (see _detect_and_log_transitions), regardless of whether history recording is on. Lets the frontend show a live elapsed-time timer without a server round-trip every second.

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
            "recipe_name": self.recipe_name,
            "oil_temp_current": self.oil_temp_current,
            "oil_temp_target": self.oil_temp_target,
            "state_entered_at": self.state_entered_at,
        }


@dataclass
class MachineGroup:
    """A machine made up of one or more PLCs (Standalone / DUO / TRIO / QUATTRO)."""
    name:  str
    type:  str                    # "STANDALONE" | "DUO" | "TRIO" | "QUATTRO"
    plcs:  list[PlcData] = field(default_factory=list)   # order here = default priority order
