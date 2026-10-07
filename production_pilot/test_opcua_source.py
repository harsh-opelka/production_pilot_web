"""
test_opcua_source.py
---------------------
Plain-assert self-test for OpcUaSource: the raw state value mapping
(PLC_STATE_MAP) including unexpected values, and the
optional nodes (current/target oil temperature, recipe name) — a failed
or empty read must come back as None without taking the PLC offline or
breaking the state read. Uses a fake OPC UA client — no PLC needed:

    python -m production_pilot.test_opcua_source
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path

from .models import MachineState
from .opcua_source import (
    _OIL_TEMP_CURRENT_NODE_ID,
    _OIL_TEMP_TARGET_NODE_ID,
    _RECIPE_NAME_NODE_ID,
    _REMAINING_TIME_NODE_ID,
    _STATE_NODE_ID,
    PLC_STATE_MAP,
    OpcUaSource,
    _node_id,
)

IP = "192.0.2.50"


class _FakeNode:
    def __init__(self, value):
        self._value = value

    def get_value(self):
        if isinstance(self._value, Exception):
            raise self._value
        return self._value


class _FakeClient:
    """Answers get_node() from a {node identifier: value-or-exception}
    dict; an identifier that's missing raises like an unknown node would."""

    def __init__(self, values: dict):
        self._values = values

    def get_node(self, node_id: str) -> _FakeNode:
        for identifier, value in self._values.items():
            if node_id == _node_id(identifier):
                return _FakeNode(value)
        return _FakeNode(RuntimeError(f"BadNodeIdUnknown: {node_id}"))

    def disconnect(self) -> None:
        pass


def _source_with(values: dict) -> OpcUaSource:
    path = Path(tempfile.mkdtemp(prefix="pp_test_opcua_")) / "plc_config.json"
    path.write_text(json.dumps({"machines": [{"name": "G", "type": "STANDALONE", "plcs": [IP]}]}),
                    encoding="utf-8")
    source = OpcUaSource(path)
    # Pre-set client: read() skips _connect(), so nothing touches the network.
    source._connections[IP]._client = _FakeClient(values)
    return source


def _poll(source: OpcUaSource, polls: int = 1) -> tuple:
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        for _ in range(polls):
            plc = source.get_machines()[0].plcs[0]
    return plc, log.getvalue()


def _check(label: str, actual, expected) -> bool:
    ok = actual == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")
    return ok


def main() -> bool:
    results = []

    print("--- state mapping (::auto:external_machine_state) ---")
    results.append(_check("0, 1, 3, 4, 5, 6 -> Error, Standby, Heating, Waiting, Blocked, Baking (no 2)",
                          {k: v.name for k, v in PLC_STATE_MAP.items()},
                          {0: "ERROR", 1: "STANDBY", 3: "HEATING", 4: "WAITING", 5: "BLOCKED", 6: "BAKING"}))
    results.append(_check("Cold / Hot are not PLC values any more",
                          {MachineState.COLD, MachineState.HOT} & set(PLC_STATE_MAP.values()), set()))
    for raw, expected in PLC_STATE_MAP.items():
        plc, _ = _poll(_source_with({_STATE_NODE_ID: raw, _REMAINING_TIME_NODE_ID: None}))
        results.append(_check(f"raw {raw} reads as {expected.name}, online",
                              (plc.state, plc.is_online), (expected, True)))

    # Unrecognized values: ignored, last valid state kept, never offline.
    source = _source_with({_STATE_NODE_ID: 4, _REMAINING_TIME_NODE_ID: None, _OIL_TEMP_CURRENT_NODE_ID: 80.0})
    _poll(source)
    values = source._connections[IP]._client._values
    for raw in (2, 7):
        values[_STATE_NODE_ID] = raw
        plc, log = _poll(source, polls=3)
        results.append(_check(f"Waiting, then raw {raw} -> still Waiting, online, temperature still read",
                              (plc.state, plc.is_online, plc.oil_temp_current), (MachineState.WAITING, True, 80.0)))
        results.append(_check(f"raw {raw}: exactly one warning over 3 polls",
                              log.count("unrecognized machine state"), 1))
    values[_STATE_NODE_ID] = 6
    plc, _ = _poll(source)
    results.append(_check("next valid value applies again (6 -> Baking)", plc.state, MachineState.BAKING))
    values[_STATE_NODE_ID] = 2
    plc, log = _poll(source)
    results.append(_check("raw 2 again: Baking kept, no second warning",
                          (plc.state, log.count("unrecognized")), (MachineState.BAKING, 0)))

    for raw in (2, 7, -1, 2.5, "3", None, True):
        source = _source_with({_STATE_NODE_ID: raw, _REMAINING_TIME_NODE_ID: None, _OIL_TEMP_CURRENT_NODE_ID: 80.0})
        plc, _ = _poll(source, polls=3)
        results.append(_check(f"raw {raw!r} with no valid state yet -> Unknown, still online",
                              (plc.state, plc.is_online, plc.oil_temp_current, plc.state.value),
                              (MachineState.UNRECOGNIZED, True, 80.0, "Unknown")))
    print()

    required = {_STATE_NODE_ID: 6, _REMAINING_TIME_NODE_ID: 120}

    plc, _ = _poll(_source_with({
        **required,
        _OIL_TEMP_CURRENT_NODE_ID: 29.4,
        _OIL_TEMP_TARGET_NODE_ID: 20,
        _RECIPE_NAME_NODE_ID: "Spritzkuchen",
    }))
    results.append(_check("all nodes readable: values come through",
                          (plc.is_online, plc.state, plc.remaining_seconds,
                           plc.oil_temp_current, plc.oil_temp_target, plc.recipe_name),
                          (True, MachineState.BAKING, 120, 29.4, 20.0, "Spritzkuchen")))

    source = _source_with(required)  # all three optional nodes missing
    plc, log = _poll(source, polls=3)
    results.append(_check("optional nodes missing: PLC stays online with its state",
                          (plc.is_online, plc.state, plc.remaining_seconds), (True, MachineState.BAKING, 120)))
    results.append(_check("optional nodes missing: values are None",
                          (plc.oil_temp_current, plc.oil_temp_target, plc.recipe_name), (None, None, None)))
    results.append(_check("optional nodes missing: one warning per node, not per poll (3 polls)",
                          log.count("unreadable"), 3))
    results.append(_check("source still reports connected", source.is_connected(), True))

    plc, _ = _poll(_source_with({
        **required,
        _OIL_TEMP_CURRENT_NODE_ID: None,
        _OIL_TEMP_TARGET_NODE_ID: float("nan"),
        _RECIPE_NAME_NODE_ID: "  \x00\x00",
    }))
    results.append(_check("None / NaN / blank recipe -> None, never invented",
                          (plc.is_online, plc.oil_temp_current, plc.oil_temp_target, plc.recipe_name),
                          (True, None, None, None)))

    plc, _ = _poll(_source_with({**required, _OIL_TEMP_CURRENT_NODE_ID: "not a number",
                                 _RECIPE_NAME_NODE_ID: b"Berliner\x00\x00"}))
    results.append(_check("unconvertible temp -> None; padded bytes recipe is cleaned",
                          (plc.is_online, plc.oil_temp_current, plc.recipe_name), (True, None, "Berliner")))


    source = _source_with({_STATE_NODE_ID: RuntimeError("connection lost"), _OIL_TEMP_CURRENT_NODE_ID: 29.4})
    plc, _ = _poll(source)
    results.append(_check("required state node failing still takes the PLC offline",
                          (plc.is_online, plc.oil_temp_current), (False, None)))

    all_passed = all(results)
    print()
    print("ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
