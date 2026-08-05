"""
priority.py
-----------
Dynamic priority ordering for the PLCs within a MachineGroup. Pure
Python, no Qt, no I/O — calculate_priority() just reorders and returns a
list; it never mutates PlcData.default_priority, which stays fixed as
the saved install-time order.

tier() and sort_key() are public so other code (main_window.py's next-
action logic) can rank PLCs using the exact same precedence without
duplicating it.
"""

from __future__ import annotations

from .models import MachineGroup, MachineState, PlcData

NEAR_COMPLETION_THRESHOLD_SECONDS = 30


def tier(plc: PlcData) -> int:
    # Offline machines sink to the bottom regardless of their last-known
    # state — this check must come before any state-based tier so an
    # offline ERROR (say) doesn't get mistaken for an active tier-1 alarm.
    if not plc.is_online:
        return 5
    if plc.state == MachineState.COLD:
        return 5
    if plc.state == MachineState.ERROR:
        return 1
    if (plc.state == MachineState.BAKING
            and plc.remaining_seconds is not None
            and plc.remaining_seconds < NEAR_COMPLETION_THRESHOLD_SECONDS):
        return 2
    if plc.state == MachineState.HEATING:
        return 4
    # READY, or BAKING with remaining_seconds >= NEAR_COMPLETION_THRESHOLD_SECONDS,
    # or BAKING with remaining_seconds is None — the "Default Priority group".
    return 3


def sort_key(plc: PlcData) -> tuple[int, int, int]:
    t = tier(plc)
    if t == 2:
        # Shortest remaining time first, default_priority as tie-break.
        return (t, plc.remaining_seconds, plc.default_priority)
    return (t, plc.default_priority, 0)


def calculate_priority(group: MachineGroup) -> list[PlcData]:
    """
    Returns plcs from group.plcs re-ordered according to the dynamic
    priority rules. Does not mutate default_priority — that stays fixed,
    representing the saved install-time order. Only the returned list
    order changes.
    """
    plcs = group.plcs

    # Step 1 shortcut: everyone online and READY -> default order, done.
    if all(p.is_online and p.state == MachineState.READY for p in plcs):
        return sorted(plcs, key=lambda p: p.default_priority)

    return sorted(plcs, key=sort_key)
