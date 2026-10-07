"""
priority.py
-----------
Next Action selection — which single machine the dashboard's Next Action
banner (and the NEXT badge on its tile) points at. Pure Python, no I/O:
select_next_action() only reads the PlcData it's given.

Tile ORDER is no longer decided here: tiles stay put (floor layout, then
machine number within a group — see the frontend), and only the banner
and the NEXT badge move. The old calculate_priority()/tier()/sort_key()
reordering was removed for that reason.
"""

from __future__ import annotations

from .models import MachineState, PlcData

NEAR_COMPLETION_THRESHOLD_SECONDS = 30

# Next Action kinds, highest precedence first. The frontend maps each one
# to its translated "<no>: ..." text and banner colour (nextAction.js).
ACTION_ERROR = "error"                  # "<no>: Check Error"
ACTION_SWITCH_TO_AUTO = "switch_to_auto"  # "<no>: Switch to Auto" (HOT)
ACTION_LOAD = "load"                    # "<no>: Load Machine"   (WAITING)
ACTION_UNLOAD_SOON = "unload_soon"      # "<no>: Unload Soon"    (Almost finished)
# Nothing actionable:
ACTION_ALL_BAKING = "all_baking"        # every online machine is Baking -> smiley
ACTION_NONE = "none"                    # anything else (heating, cold, blocked, offline...)


def is_near_completion(plc: PlcData) -> bool:
    """True for a BAKING PLC with less than NEAR_COMPLETION_THRESHOLD_SECONDS
    remaining — the "Fast fertig" / "Almost finished" display override (see
    serializers._plc_to_dict, which sends this as the `near_completion`
    flag). Display-only: MachineState stays BAKING."""
    return (
        plc.is_online
        and plc.state == MachineState.BAKING
        and plc.remaining_seconds is not None
        and plc.remaining_seconds < NEAR_COMPLETION_THRESHOLD_SECONDS
    )


def _action_kind(plc: PlcData) -> str | None:
    """The actionable category of one PLC, or None if there's nothing to
    do at it right now (Blocked, Baking >= threshold, Heating, Cold, Offline)."""
    if not plc.is_online:
        return None
    if plc.state == MachineState.ERROR:
        return ACTION_ERROR
    if plc.state == MachineState.HOT:
        return ACTION_SWITCH_TO_AUTO
    if plc.state == MachineState.WAITING:
        return ACTION_LOAD
    if is_near_completion(plc):
        return ACTION_UNLOAD_SOON
    return None


# Tiers, highest first. Within a tier, saved order decides.
_TIERS = (
    (ACTION_ERROR,),
    (ACTION_SWITCH_TO_AUTO,),
    (ACTION_LOAD,),
    (ACTION_UNLOAD_SOON,),
)


def select_next_action(plcs: list[PlcData]) -> dict:
    """
    `plcs` must be in saved priority order: groups in plc_config.json
    order, each group's PLCs in their saved order (default_priority).

    Tier precedence beats saved order: Error ("Check Error"), then Hot
    ("Switch to Auto"), then Waiting ("Load Machine"), then Almost
    finished ("Unload Soon"). Within a tier, the PLC earliest in `plcs`
    wins — so a Hot machine beats every Waiting machine, even one ranked
    higher in the saved order, and of several Hot machines the
    highest-ranked one is next.

    Returns {"kind", "ip", "unit_number"}. When nothing is actionable,
    kind is ACTION_ALL_BAKING if there is at least one online machine and
    every online machine is Baking, otherwise ACTION_NONE; ip and
    unit_number are None in both cases.
    """
    kinds = [(plc, _action_kind(plc)) for plc in plcs]
    for tier in _TIERS:
        for plc, kind in kinds:
            if kind in tier:
                return {"kind": kind, "ip": plc.ip, "unit_number": plc.unit_number}

    online = [plc for plc in plcs if plc.is_online]
    if online and all(plc.state == MachineState.BAKING for plc in online):
        return {"kind": ACTION_ALL_BAKING, "ip": None, "unit_number": None}
    return {"kind": ACTION_NONE, "ip": None, "unit_number": None}
