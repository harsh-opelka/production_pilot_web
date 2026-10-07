"""
test_hot_cold.py
-----------------
Plain-assert self-test for hot_cold.py (Standby -> Cold / Hot from the
oil temperature) and for its place in server.py's poll processing. No pytest
needed — run from the project root:

    python -m production_pilot.test_hot_cold
"""

from __future__ import annotations

import contextlib
import io
import sqlite3
import tempfile
from pathlib import Path

from . import history
from .hot_cold import HYSTERESIS_C, HotColdRule, classify, validate_threshold
from .models import MachineGroup, MachineState, PlcData

ERROR, COLD, HOT, HEATING = MachineState.ERROR, MachineState.COLD, MachineState.HOT, MachineState.HEATING
WAITING, BLOCKED, BAKING = MachineState.WAITING, MachineState.BLOCKED, MachineState.BAKING
STANDBY, UNRECOGNIZED = MachineState.STANDBY, MachineState.UNRECOGNIZED
THRESHOLD = 50.0
IP = "192.0.2.77"


def _check(label: str, actual, expected) -> bool:
    ok = actual == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")
    return ok


def _groups(state: MachineState, temp: float | None, online: bool = True) -> list[MachineGroup]:
    plc = PlcData(ip=IP, name="M1", state=state, is_online=online, unit_number=1,
                  oil_temp_current=temp, oil_temp_target=180.0)
    return [MachineGroup(name="G", type="STANDALONE", plcs=[plc])]


def _derived(rule: HotColdRule, state: MachineState, temp: float | None, online: bool = True) -> MachineState:
    return rule.apply(_groups(state, temp, online), THRESHOLD)[0].plcs[0].state


def test_rule() -> list[bool]:
    print("--- Standby -> Cold / Hot rule ---")
    results = [
        _check("Standby at 30 °C -> Cold", classify(STANDBY, 30.0, THRESHOLD), COLD),
        _check("Standby at 60 °C -> Hot", classify(STANDBY, 60.0, THRESHOLD), HOT),
        _check("Standby, temp None -> Standby (no guessing)", classify(STANDBY, None, THRESHOLD), STANDBY),
        _check("exactly at the threshold -> Hot", classify(STANDBY, 50.0, THRESHOLD), HOT),
        _check("in the band with no history -> Cold", classify(STANDBY, 49.0, THRESHOLD), COLD),
        _check("hysteresis constant is 2 °C", HYSTERESIS_C, 2.0),
    ]
    for state in (HEATING, BAKING, ERROR, WAITING, BLOCKED, UNRECOGNIZED):
        results.append(_check(f"{state.name} at 20 °C unchanged", classify(state, 20.0, THRESHOLD), state))
        results.append(_check(f"{state.name} at 180 °C unchanged", classify(state, 180.0, THRESHOLD), state))
        results.append(_check(f"{state.name}, temp None unchanged", classify(state, None, THRESHOLD), state))

    rule = HotColdRule()
    results.append(_check("offline PLC never touched", _derived(rule, STANDBY, 80.0, online=False), STANDBY))
    results.append(_check("rule: Standby at 30 °C -> Cold", _derived(rule, STANDBY, 30.0), COLD))
    results.append(_check("rule: Standby, temp None -> Standby", _derived(rule, STANDBY, None), STANDBY))
    raw = _groups(STANDBY, 80.0)
    rule.apply(raw, THRESHOLD)
    results.append(_check("source's own PlcData keeps the raw PLC state", raw[0].plcs[0].state, STANDBY))
    return results


def test_hysteresis() -> list[bool]:
    print()
    print("--- hysteresis (threshold 50 °C) ---")
    rule = HotColdRule()
    steps = [(30.0, COLD), (50.0, HOT), (49.0, HOT), (48.0, HOT), (47.9, COLD), (49.0, COLD), (50.0, HOT)]
    results = []
    for temp, expected in steps:
        results.append(_check(f"Standby at {temp} °C -> {expected.name}", _derived(rule, STANDBY, temp), expected))

    rule = HotColdRule()
    _derived(rule, STANDBY, 55.0)
    _derived(rule, HEATING, 49.0)  # leaves Standby: memory cleared
    results.append(_check("after leaving Standby, the band starts fresh (Cold)", _derived(rule, STANDBY, 49.0), COLD))
    rule = HotColdRule()
    _derived(rule, STANDBY, 55.0)
    _derived(rule, STANDBY, None)  # temperature unreadable: memory cleared
    results.append(_check("after an unreadable temperature, the band starts fresh (Cold)",
                          _derived(rule, STANDBY, 49.0), COLD))
    return results


def test_threshold_validation() -> list[bool]:
    print()
    print("--- threshold validation (20..150 °C) ---")
    results = [
        _check("50 accepted", validate_threshold(50), 50.0),
        _check("20 accepted (lower bound)", validate_threshold(20), 20.0),
        _check("150 accepted (upper bound)", validate_threshold(150.0), 150.0),
        _check("62.5 accepted", validate_threshold(62.5), 62.5),
    ]
    for label, bad in (("too low", 19.9), ("too high", 150.5), ("not a number", "50"), ("missing", None),
                       ("bool", True), ("NaN", float("nan"))):
        try:
            validate_threshold(bad)
            rejected = False
        except ValueError:
            rejected = True
        results.append(_check(f"rejected: {label}", rejected, True))
    return results


def test_recorded_once() -> list[bool]:
    print()
    print("--- derived Hot/Cold change recorded once (server poll processing) ---")
    import server  # project root is on sys.path when run with -m from the root

    history.DB_PATH = Path(tempfile.mkdtemp(prefix="pp_test_hot_cold_")) / "history.db"
    with contextlib.redirect_stdout(io.StringIO()):
        history.init_db()
    history.set_recording_enabled(True)
    history.set_hot_cold_threshold_c(THRESHOLD)
    server._last_known.clear()
    server._state_entered_at.clear()
    server._hot_cold_rule = HotColdRule()

    # The PLC keeps reporting Standby the whole time; only the oil cools.
    for temp in (80.0, 79.0, 60.0, 49.0, 48.0, 47.0, 46.0, 45.0):
        server._process_poll(_groups(STANDBY, temp))

    with sqlite3.connect(history.DB_PATH) as conn:
        rows = conn.execute(
            "SELECT old_state, new_state FROM state_transitions WHERE plc_ip = ? ORDER BY id", (IP,)
        ).fetchall()
    return [_check("8 polls -> 2 rows: first sighting as HOT, then HOT -> COLD once",
                   rows, [(None, "HOT"), ("HOT", "COLD")])]


def main() -> bool:
    results = test_rule() + test_hysteresis() + test_threshold_validation() + test_recorded_once()
    all_passed = all(results)
    print()
    print("ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
