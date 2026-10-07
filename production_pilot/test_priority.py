"""
test_priority.py
-----------------
Plain-assert self-test for priority.select_next_action() — which machine
the Next Action banner and the NEXT badge point at. (The raw PLC value
mapping is tested in test_opcua_source.py.) No pytest needed:

    python -m production_pilot.test_priority
"""

from __future__ import annotations

from . import priority
from .models import MachineState, PlcData
from .priority import (
    ACTION_NOTHING_TO_DO,
    ACTION_ERROR,
    ACTION_LOAD,
    ACTION_NONE,
    ACTION_SWITCH_TO_AUTO,
    ACTION_UNLOAD_SOON,
    select_next_action,
)

ERROR   = MachineState.ERROR
COLD    = MachineState.COLD
HOT     = MachineState.HOT
HEATING = MachineState.HEATING
WAITING = MachineState.WAITING
BLOCKED = MachineState.BLOCKED
BAKING  = MachineState.BAKING
STANDBY = MachineState.STANDBY
UNKNOWN = MachineState.UNRECOGNIZED


def _check(label: str, actual, expected) -> bool:
    ok = actual == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")
    return ok


def machines(*specs) -> list[PlcData]:
    """Machines 1..n in saved order (= list order). Each spec is a state,
    or (state, remaining_seconds), or (state, remaining_seconds, is_online)."""
    plcs = []
    for index, spec in enumerate(specs):
        state, remaining, online = (spec, None, True) if isinstance(spec, MachineState) else (*spec, True)[:3]
        plcs.append(PlcData(ip=f"10.0.0.{index + 1}", name=f"M{index + 1}", state=state,
                            is_online=online, remaining_seconds=remaining,
                            default_priority=index, unit_number=index + 1))
    return plcs


def pick(plcs: list[PlcData], groups: str | None = None) -> tuple:
    """`groups` gives each machine's group as one letter, in order — e.g.
    "AAAA" = one QUATTRO, "AABB" = two DUOs. Default: every machine in its
    own group, so the group-Heating rule only shows up where a test asks."""
    letters = groups if groups is not None else [str(i) for i in range(len(plcs))]
    result = select_next_action(plcs, {plc.ip: letter for plc, letter in zip(plcs, letters)})
    return result["kind"], result["unit_number"]


ALMOST_DONE = (BAKING, 20)
BAKING_LONG = (BAKING, 600)


def test_select_next_action() -> list[bool]:
    print("--- select_next_action ---")
    results = []

    # The three examples from the spec (saved order 1, 2, 3, 4).
    results.append(_check("M1 almost finished, M3 Waiting -> 3: Load Machine",
                          pick(machines(ALMOST_DONE, HEATING, WAITING, BAKING_LONG)), (ACTION_LOAD, 3)))
    # Standby (shown as Cold, Hot or Standby) always beats Waiting, whatever the saved order.
    for shown in (COLD, HOT, STANDBY):
        results.append(_check(f"{shown.name} -> Switch to Auto",
                              pick(machines(BAKING_LONG, shown)), (ACTION_SWITCH_TO_AUTO, 2)))
        results.append(_check(f"{shown.name} beats a higher-ranked Waiting",
                              pick(machines(WAITING, HEATING, shown)), (ACTION_SWITCH_TO_AUTO, 3)))
        results.append(_check(f"Error beats a higher-ranked {shown.name}",
                              pick(machines(shown, ERROR)), (ACTION_ERROR, 2)))
    results.append(_check("Cold ranked above Hot -> the Cold one (same tier, saved order)",
                          pick(machines(BAKING_LONG, COLD, HOT)), (ACTION_SWITCH_TO_AUTO, 2)))
    results.append(_check("screen example: M1 Hot, M2 Heating, M3+M4 Waiting -> 1: Switch to Auto",
                          pick(machines(HOT, HEATING, WAITING, WAITING)), (ACTION_SWITCH_TO_AUTO, 1)))
    results.append(_check("M4 Hot, M1+M3 Waiting -> 4: Switch to Auto",
                          pick(machines(WAITING, HEATING, WAITING, HOT)), (ACTION_SWITCH_TO_AUTO, 4)))
    results.append(_check("M1 Hot, M3 Waiting -> 1: Switch to Auto",
                          pick(machines(HOT, HEATING, WAITING)), (ACTION_SWITCH_TO_AUTO, 1)))
    results.append(_check("Waiting ranked above Hot -> Hot still wins",
                          pick(machines(BAKING_LONG, WAITING, HOT)), (ACTION_SWITCH_TO_AUTO, 3)))
    results.append(_check("several Hot -> highest saved rank wins",
                          pick(machines(WAITING, HOT, BAKING_LONG, HOT)), (ACTION_SWITCH_TO_AUTO, 2)))
    results.append(_check("Waiting + Almost finished ranked higher -> Waiting wins",
                          pick(machines(ALMOST_DONE, WAITING)), (ACTION_LOAD, 2)))
    results.append(_check("Hot + Almost finished ranked higher -> Hot wins",
                          pick(machines(ALMOST_DONE, BAKING_LONG, HOT)), (ACTION_SWITCH_TO_AUTO, 3)))
    results.append(_check("Error still beats a higher-ranked Hot",
                          pick(machines(HOT, ERROR)), (ACTION_ERROR, 2)))
    results.append(_check("only M2 Hot -> 2: Switch to Auto",
                          pick(machines(BAKING_LONG, HOT, HEATING, BAKING_LONG)), (ACTION_SWITCH_TO_AUTO, 2)))

    results.append(_check("Error first, ahead of Waiting, Hot and Almost finished",
                          pick(machines(WAITING, HOT, ALMOST_DONE, ERROR)), (ACTION_ERROR, 4)))
    results.append(_check("Hot beats Almost finished, even ranked lower",
                          pick(machines(ALMOST_DONE, HOT)), (ACTION_SWITCH_TO_AUTO, 2)))
    results.append(_check("Almost finished only -> Unload Soon",
                          pick(machines(BAKING_LONG, ALMOST_DONE, HEATING)), (ACTION_UNLOAD_SOON, 2)))
    results.append(_check("same category -> higher saved rank wins",
                          pick(machines(BAKING_LONG, WAITING, WAITING)), (ACTION_LOAD, 2)))
    results.append(_check("two Almost finished -> saved order, NOT shortest remaining",
                          pick(machines((BAKING, 25), (BAKING, 5))), (ACTION_UNLOAD_SOON, 1)))

    results.append(_check("Blocked is never chosen",
                          pick(machines(BLOCKED, BLOCKED, HEATING)), (ACTION_NOTHING_TO_DO, None)))
    results.append(_check("Unknown is never chosen",
                          pick(machines(UNKNOWN, UNKNOWN, HEATING)), (ACTION_NOTHING_TO_DO, None)))
    results.append(_check("Unknown ranked first is skipped for a later Almost finished",
                          pick(machines(UNKNOWN, BLOCKED, ALMOST_DONE)), (ACTION_UNLOAD_SOON, 3)))
    results.append(_check("Blocked ranked first is skipped for a later Waiting",
                          pick(machines(BLOCKED, WAITING)), (ACTION_LOAD, 2)))
    results.append(_check("offline Error / Waiting / Hot / Standby are never chosen",
                          pick(machines((ERROR, None, False), (WAITING, None, False), (HOT, None, False),
                                        (STANDBY, None, False), HEATING)),
                          (ACTION_NOTHING_TO_DO, None)))
    results.append(_check("Baking with exactly 30 s left is not Almost finished",
                          pick(machines((BAKING, 30))), (ACTION_NOTHING_TO_DO, None)))

    results.append(_check("all online machines Baking -> smiley (offline ones ignored)",
                          pick(machines(BAKING_LONG, (BAKING, None), (STANDBY, None, False))),
                          (ACTION_NOTHING_TO_DO, None)))
    results.append(_check("Baking + Heating -> smiley (nothing to do right now)",
                          pick(machines(BAKING_LONG, HEATING)), (ACTION_NOTHING_TO_DO, None)))
    results.append(_check("everything offline -> none",
                          pick(machines((BAKING, 600, False))), (ACTION_NONE, None)))
    results.append(_check("no machines -> none", pick([]), (ACTION_NONE, None)))
    results.append(_check("result carries the chosen PLC's ip",
                          select_next_action(machines(BAKING_LONG, WAITING))["ip"], "10.0.0.2"))
    return results


def test_group_heating_rule() -> list[bool]:
    print()
    print(f"--- Waiting blocked while its group is Heating (LOAD_BLOCKED_WHILE_GROUP_HEATING = "
          f"{priority.LOAD_BLOCKED_WHILE_GROUP_HEATING}) ---")
    results = [
        _check("1, 2, 3 Waiting + 4 Heating (one group) -> smiley",
               pick(machines(WAITING, WAITING, WAITING, HEATING), "AAAA"), (ACTION_NOTHING_TO_DO, None)),
        _check("... once 4 reaches Waiting -> 1: Load Machine",
               pick(machines(WAITING, WAITING, WAITING, WAITING), "AAAA"), (ACTION_LOAD, 1)),
        _check("3 almost finished, 1 + 2 Waiting, 4 Baking -> 1: Load Machine",
               pick(machines(WAITING, WAITING, ALMOST_DONE, BAKING_LONG), "AAAA"), (ACTION_LOAD, 1)),
        _check("1 Standby + 4 Heating -> 1: Switch to Auto",
               pick(machines(STANDBY, WAITING, WAITING, HEATING), "AAAA"), (ACTION_SWITCH_TO_AUTO, 1)),
        _check("Waiting blocked by group Heating -> Almost finished is next",
               pick(machines(WAITING, ALMOST_DONE, HEATING), "AAA"), (ACTION_UNLOAD_SOON, 2)),
        _check("Error still shown while the group is Heating",
               pick(machines(WAITING, ERROR, HEATING), "AAA"), (ACTION_ERROR, 2)),
        _check("Heating in ANOTHER group does not block -> 1: Load Machine",
               pick(machines(WAITING, WAITING, HEATING, HEATING), "AABB"), (ACTION_LOAD, 1)),
        _check("group A blocked, group B free -> first Waiting in B",
               pick(machines(WAITING, HEATING, BAKING_LONG, WAITING), "AABB"), (ACTION_LOAD, 4)),
        _check("offline Heating machine does not block",
               pick(machines(WAITING, (HEATING, None, False)), "AA"), (ACTION_LOAD, 1)),
        _check("no group map -> all PLCs count as one group",
               select_next_action(machines(WAITING, HEATING))["kind"], ACTION_NOTHING_TO_DO),
    ]
    priority.LOAD_BLOCKED_WHILE_GROUP_HEATING = False
    try:
        results.append(_check("rule switched off -> 1: Load Machine despite group Heating",
                              pick(machines(WAITING, WAITING, WAITING, HEATING), "AAAA"), (ACTION_LOAD, 1)))
    finally:
        priority.LOAD_BLOCKED_WHILE_GROUP_HEATING = True
    return results


def main() -> bool:
    results = test_select_next_action() + test_group_heating_rule()
    all_passed = all(results)
    print()
    print("ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
