"""
test_plc_config.py
-------------------
Plain-assert self-tests for plc_config.json's machine-number handling
(see plc_config.py). No pytest needed:

    python -m production_pilot.test_plc_config

Covers:
  1. An old-format config (plain IP strings) loads with
     unit_number = index + 1.
  2. A new-format config keeps the technician's custom machine numbers.
  3. Re-ordering priority changes default_priority but never unit_number.
  4. Missing / non-positive / duplicate machine numbers within a group
     are rejected; the same number in two different groups is fine.
  5. select_next_action() picks the same PLC for the same states,
     whatever the machine numbers are.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .demo_source import SimulatedSource
from .models import MachineState
from .opcua_source import OpcUaSource
from .plc_config import load_config, unit_number_problem
from .priority import select_next_action

IP_A = "192.168.178.150"
IP_B = "192.168.178.151"
IP_C = "192.168.178.152"
IP_D = "192.168.178.153"


def _check(label: str, actual, expected) -> bool:
    ok = actual == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")
    return ok


def _write_config(plcs: list) -> Path:
    path = Path(tempfile.mkdtemp(prefix="pp_test_plc_config_")) / "plc_config.json"
    path.write_text(
        json.dumps({"machines": [{"name": "Quattro", "type": "QUATTRO", "plcs": plcs}]}), encoding="utf-8"
    )
    return path


def _units_by_ip(source) -> dict[str, int]:
    # source._groups, not get_machines(): OpcUaSource.get_machines() would
    # attempt real OPC UA connections. Both sources build _groups on init.
    return {plc.ip: plc.unit_number for group in source._groups for plc in group.plcs}


def _priorities_by_ip(source) -> dict[str, int]:
    return {plc.ip: plc.default_priority for group in source._groups for plc in group.plcs}


def main() -> bool:
    results = []

    # --- 1. Old format -> index + 1 -------------------------------------
    old_path = _write_config([IP_A, IP_B, IP_C, IP_D])
    expected_old = {IP_A: 1, IP_B: 2, IP_C: 3, IP_D: 4}
    results.append(_check(
        "old format: load_config numbers plain IPs by position",
        [p["unit_number"] for p in load_config(old_path)["machines"][0]["plcs"]], [1, 2, 3, 4],
    ))
    results.append(_check("old format: OpcUaSource unit_number = index + 1",
                          _units_by_ip(OpcUaSource(old_path)), expected_old))
    results.append(_check("old format: SimulatedSource unit_number = index + 1",
                          _units_by_ip(SimulatedSource(old_path)), expected_old))

    # --- 2. New format keeps custom numbers -----------------------------
    custom = [
        {"ip": IP_A, "unit_number": 3},
        {"ip": IP_B, "unit_number": 1},
        {"ip": IP_C, "unit_number": 4},
        {"ip": IP_D, "unit_number": 2},
    ]
    new_path = _write_config(custom)
    expected_new = {IP_A: 3, IP_B: 1, IP_C: 4, IP_D: 2}
    results.append(_check("new format: OpcUaSource keeps custom numbers",
                          _units_by_ip(OpcUaSource(new_path)), expected_new))
    results.append(_check("new format: SimulatedSource keeps custom numbers",
                          _units_by_ip(SimulatedSource(new_path)), expected_new))

    # --- 3. Re-ordering priority doesn't renumber -----------------------
    reordered_path = _write_config(list(reversed(custom)))
    reordered = OpcUaSource(reordered_path)
    results.append(_check("reordered: unit_number unchanged per IP",
                          _units_by_ip(reordered), expected_new))
    results.append(_check("reordered: default_priority follows the new array order",
                          _priorities_by_ip(reordered), {IP_D: 0, IP_C: 1, IP_B: 2, IP_A: 3}))

    # --- 4. Validation --------------------------------------------------
    def plcs(*numbers):
        return [{"ip": f"10.0.0.{i}", "unit_number": n} for i, n in enumerate(numbers)]

    results.append(_check("valid: distinct positive numbers accepted",
                          unit_number_problem("G", plcs(3, 1, 4, 2)), None))
    duplicate = unit_number_problem("G", plcs(1, 2, 2))
    results.append(_check("duplicate number in a group rejected",
                          duplicate is not None and "used more than once" in duplicate, True))
    for label, bad in (("missing", None), ("zero", 0), ("negative", -1), ("non-integer", 1.5),
                       ("string", "3"), ("bool", True)):
        results.append(_check(f"{label} machine number rejected",
                              unit_number_problem("G", plcs(bad)) is not None, True))
    dup_path = _write_config([{"ip": IP_A, "unit_number": 1}, {"ip": IP_B, "unit_number": 1}])
    try:
        load_config(dup_path)
        raised = False
    except ValueError:
        raised = True
    results.append(_check("load_config raises on a duplicate number", raised, True))

    two_groups = Path(tempfile.mkdtemp(prefix="pp_test_plc_config_")) / "plc_config.json"
    two_groups.write_text(json.dumps({"machines": [
        {"name": "A", "type": "DUO", "plcs": [{"ip": IP_A, "unit_number": 1}, {"ip": IP_B, "unit_number": 2}]},
        {"name": "B", "type": "DUO", "plcs": [{"ip": IP_C, "unit_number": 1}, {"ip": IP_D, "unit_number": 2}]},
    ]}), encoding="utf-8")
    results.append(_check("same number in two different groups accepted",
                          _units_by_ip(OpcUaSource(two_groups)), {IP_A: 1, IP_B: 2, IP_C: 1, IP_D: 2}))

    # --- 5. Next Action pick unchanged -----------------------------------
    states = {
        IP_A: (MachineState.WAITING, None),
        IP_B: (MachineState.BAKING, 20),
        IP_C: (MachineState.ERROR, None),
        IP_D: (MachineState.HEATING, None),
    }

    def next_action_ip(path: Path, without: str | None = None) -> str | None:
        plcs = OpcUaSource(path)._groups[0].plcs
        for plc in plcs:
            plc.state, plc.remaining_seconds = states[plc.ip]
            plc.is_online = plc.ip != without
        return select_next_action(plcs)["ip"]

    results.append(_check("next action: same pick with or without custom numbers",
                          next_action_ip(new_path), next_action_ip(old_path)))
    results.append(_check("next action: ERROR first", next_action_ip(new_path), IP_C))
    results.append(_check("next action: WAITING once the ERROR machine is gone",
                          next_action_ip(new_path, without=IP_C), IP_A))

    all_passed = all(results)
    print()
    print("ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
