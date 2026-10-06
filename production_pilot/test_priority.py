"""
test_priority.py
-----------------
Plain-assert self-test for priority.select_next_action() — which machine
the Next Action banner and the NEXT badge point at — and for the state
mapping v2 integers. No pytest needed:

    python -m production_pilot.test_priority
"""

from __future__ import annotations

from .models import OPCUA_STATE_MAP, MachineState, PlcData
from .priority import (
    ACTION_ALL_BAKING,
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


def pick(plcs: list[PlcData]) -> tuple:
    result = select_next_action(plcs)
    return result["kind"], result["unit_number"]


ALMOST_DONE = (BAKING, 20)
BAKING_LONG = (BAKING, 600)


def test_state_mapping() -> list[bool]:
    print("--- state mapping v2 (::auto:external_machine_state) ---")
    expected = {0: "ERROR", 1: "COLD", 2: "HOT", 3: "HEATING", 4: "WAITING", 5: "BLOCKED", 6: "BAKING"}
    results = [_check("0..6 -> Error, Cold, Hot, Heating, Waiting, Blocked, Baking",
                      {k: v.name for k, v in OPCUA_STATE_MAP.items()}, expected)]
    results.append(_check("display names", [OPCUA_STATE_MAP[i].value for i in range(7)],
                          ["Error", "Cold", "Hot", "Heating", "Waiting", "Blocked", "Baking"]))
    results.append(_check("no READY member any more", "READY" in MachineState.__members__, False))
    results.append(_check("7 is not a valid state", OPCUA_STATE_MAP.get(7), None))
    return results


def test_select_next_action() -> list[bool]:
    print()
    print("--- select_next_action ---")
    results = []

    # The three examples from the spec (saved order 1, 2, 3, 4).
    results.append(_check("M1 almost finished, M3 Waiting -> 3: Load Machine",
                          pick(machines(ALMOST_DONE, HEATING, WAITING, COLD)), (ACTION_LOAD, 3)))
    # Waiting and Hot share one tier: saved order decides between them.
    results.append(_check("screen example: M1 Hot, M2 Heating, M3+M4 Waiting -> 1: Switch to Auto",
                          pick(machines(HOT, HEATING, WAITING, WAITING)), (ACTION_SWITCH_TO_AUTO, 1)))
    results.append(_check("Hot ranked above Waiting -> Switch to Auto",
                          pick(machines(BAKING_LONG, HOT, WAITING)), (ACTION_SWITCH_TO_AUTO, 2)))
    results.append(_check("Waiting ranked above Hot -> Load Machine",
                          pick(machines(BAKING_LONG, WAITING, HOT)), (ACTION_LOAD, 2)))
    results.append(_check("Hot + Almost finished ranked higher -> Hot wins",
                          pick(machines(ALMOST_DONE, BAKING_LONG, HOT)), (ACTION_SWITCH_TO_AUTO, 3)))
    results.append(_check("Error still beats a higher-ranked Hot",
                          pick(machines(HOT, ERROR)), (ACTION_ERROR, 2)))
    results.append(_check("only M2 Hot -> 2: Switch to Auto",
                          pick(machines(BAKING_LONG, HOT, HEATING, COLD)), (ACTION_SWITCH_TO_AUTO, 2)))

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
                          pick(machines(BLOCKED, BLOCKED, HEATING)), (ACTION_NONE, None)))
    results.append(_check("Blocked ranked first is skipped for a later Waiting",
                          pick(machines(BLOCKED, WAITING)), (ACTION_LOAD, 2)))
    results.append(_check("offline Error / Waiting / Hot are never chosen",
                          pick(machines((ERROR, None, False), (WAITING, None, False), (HOT, None, False), COLD)),
                          (ACTION_NONE, None)))
    results.append(_check("Baking with exactly 30 s left is not Almost finished",
                          pick(machines((BAKING, 30))), (ACTION_ALL_BAKING, None)))

    results.append(_check("all online machines Baking -> all_baking (offline ones ignored)",
                          pick(machines(BAKING_LONG, (BAKING, None), (COLD, None, False))),
                          (ACTION_ALL_BAKING, None)))
    results.append(_check("Baking + Heating -> none, not all_baking",
                          pick(machines(BAKING_LONG, HEATING)), (ACTION_NONE, None)))
    results.append(_check("everything offline -> none",
                          pick(machines((BAKING, 600, False))), (ACTION_NONE, None)))
    results.append(_check("no machines -> none", pick([]), (ACTION_NONE, None)))
    results.append(_check("result carries the chosen PLC's ip",
                          select_next_action(machines(COLD, WAITING))["ip"], "10.0.0.2"))
    return results


def main() -> bool:
    results = test_state_mapping() + test_select_next_action()
    all_passed = all(results)
    print()
    print("ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
