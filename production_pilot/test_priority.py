"""
test_priority.py
-----------------
Plain-assert self-test for priority.calculate_priority() against the
spec's worked examples. No pytest needed:

    python -m production_pilot.test_priority
"""

from __future__ import annotations

from .models import MachineGroup, MachineState, PlcData
from .priority import calculate_priority

COLD    = MachineState.COLD
HEATING = MachineState.HEATING
READY   = MachineState.READY
BAKING  = MachineState.BAKING
ERROR   = MachineState.ERROR


def _names(plcs: list[PlcData]) -> list[str]:
    return [p.name for p in plcs]


def _run_case(label: str, group: MachineGroup, expected: list[str]) -> bool:
    result = _names(calculate_priority(group))
    ok = result == expected
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}")
    if not ok:
        print(f"         expected: {expected}")
        print(f"         actual:   {result}")
    return ok


def main() -> bool:
    results = []

    # --- Test case A --------------------------------------------------
    group_a = MachineGroup(
        name="Trio Test", type="TRIO",
        plcs=[
            PlcData(ip="192.168.178.152", name="PLC152", state=READY,
                    is_online=True, default_priority=0),
            PlcData(ip="192.168.178.150", name="PLC150", state=HEATING,
                    is_online=True, default_priority=1),
            PlcData(ip="192.168.178.151", name="PLC151", state=READY,
                    is_online=True, default_priority=2),
        ],
    )
    results.append(_run_case(
        "Test case A — one HEATING among two READY",
        group_a, ["PLC152", "PLC151", "PLC150"],
    ))

    # --- Test case B --------------------------------------------------
    group_b = MachineGroup(
        name="Trio Test", type="TRIO",
        plcs=[
            PlcData(ip="192.168.178.152", name="PLC152", state=READY,
                    is_online=True, default_priority=0),
            PlcData(ip="192.168.178.150", name="PLC150", state=ERROR,
                    is_online=True, default_priority=1),
            PlcData(ip="192.168.178.151", name="PLC151", state=BAKING,
                    is_online=True, remaining_seconds=20, default_priority=2),
        ],
    )
    results.append(_run_case(
        "Test case B — ERROR beats near-done BAKING beats READY",
        group_b, ["PLC150", "PLC151", "PLC152"],
    ))

    # --- Test case C --------------------------------------------------
    group_c = MachineGroup(
        name="Trio Test 2", type="TRIO",
        plcs=[
            PlcData(ip="192.168.178.152", name="PLC152", state=READY,
                    is_online=True, default_priority=0),
            PlcData(ip="192.168.178.150", name="PLC150", state=READY,
                    is_online=True, default_priority=1),
            PlcData(ip="192.168.178.151", name="PLC151", state=READY,
                    is_online=True, default_priority=2),
        ],
    )
    results.append(_run_case(
        "Test case C — all READY/online -> Step 1 shortcut, default order",
        group_c, ["PLC152", "PLC150", "PLC151"],
    ))

    # --- Test case D --------------------------------------------------
    group_d = MachineGroup(
        name="Duo Test", type="DUO",
        plcs=[
            PlcData(ip="192.168.178.160", name="PLCa", state=COLD,
                    is_online=True, default_priority=0),
            PlcData(ip="192.168.178.161", name="PLCb", state=READY,
                    is_online=False, default_priority=1),
        ],
    )
    results.append(_run_case(
        "Test case D — COLD and offline both sink to tier 5",
        group_d, ["PLCa", "PLCb"],
    ))

    # --- Test case E --------------------------------------------------
    group_e = MachineGroup(
        name="Trio Test 3", type="TRIO",
        plcs=[
            PlcData(ip="192.168.178.152", name="PLC152", state=READY,
                    is_online=True, default_priority=0),
            PlcData(ip="192.168.178.150", name="PLC150", state=ERROR,
                    is_online=True, default_priority=1),
            PlcData(ip="192.168.178.151", name="PLC151", state=BAKING,
                    is_online=True, remaining_seconds=180, default_priority=2),
        ],
    )
    results.append(_run_case(
        "Test case E — BAKING with 180s remaining is NOT near-done "
        "under the 30s threshold, falls into the default priority tier",
        group_e, ["PLC150", "PLC152", "PLC151"],
    ))

    all_passed = all(results)
    print()
    print("ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
