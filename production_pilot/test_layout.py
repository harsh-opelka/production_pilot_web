"""
test_layout.py
---------------
Plain-assert self-test for layout.validate_layout() and
layout.reconcile_layout(). No pytest needed:

    python -m production_pilot.test_layout
"""

from __future__ import annotations

from .layout import LayoutError, reconcile_layout, validate_layout

GROUPS = {"Quattro", "Trio"}


def _check(label: str, actual, expected) -> bool:
    ok = actual == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")
    return ok


def _rejected(payload) -> bool:
    try:
        validate_layout(payload, GROUPS)
    except LayoutError:
        return True
    return False


def test_validate() -> list[bool]:
    print("--- validate_layout ---")
    results = []
    valid = {
        "groups": {
            "Quattro": {"x": 2, "y": 4, "orientation": "horizontal"},
            "Trio": {"x": 60.5, "y": 0, "orientation": "vertical"},
        },
        "tvs": [{"x": 46, "y": 100}],
    }
    results.append(_check("valid layout accepted and normalized", validate_layout(valid, GROUPS), {
        "groups": {
            "Quattro": {"x": 2.0, "y": 4.0, "orientation": "horizontal"},
            "Trio": {"x": 60.5, "y": 0.0, "orientation": "vertical"},
        },
        "tvs": [{"x": 46.0, "y": 100.0}],
    }))
    results.append(_check("empty layout (= reset to default) accepted",
                          validate_layout({"groups": {}, "tvs": []}, GROUPS), {"groups": {}, "tvs": []}))
    results.append(_check("orientation defaults to horizontal",
                          validate_layout({"groups": {"Trio": {"x": 1, "y": 1}}}, GROUPS)["groups"]["Trio"]["orientation"],
                          "horizontal"))

    for label, payload in (
        ("x above 100", {"groups": {"Quattro": {"x": 100.5, "y": 0}}}),
        ("y below 0", {"groups": {"Quattro": {"x": 0, "y": -1}}}),
        ("TV out of range", {"tvs": [{"x": 50, "y": 101}]}),
        ("unknown group", {"groups": {"Duo": {"x": 0, "y": 0}}}),
        ("bad orientation", {"groups": {"Trio": {"x": 0, "y": 0, "orientation": "diagonal"}}}),
        ("missing coordinate", {"groups": {"Trio": {"x": 0}}}),
        ("non-numeric coordinate", {"tvs": [{"x": "10", "y": 0}]}),
        ("bool coordinate", {"tvs": [{"x": True, "y": 0}]}),
        ("NaN coordinate", {"tvs": [{"x": float("nan"), "y": 0}]}),
        ("unknown top-level field", {"groups": {}, "colour": "red"}),
        ("unknown item field", {"tvs": [{"x": 1, "y": 1, "w": 3}]}),
        ("too many TVs", {"tvs": [{"x": 1, "y": 1}] * 11}),
        ("not an object", ["Quattro"]),
    ):
        results.append(_check(f"rejected: {label}", _rejected(payload), True))
    return results


def test_reconcile() -> list[bool]:
    print()
    print("--- reconcile_layout (wizard rename / delete / create) ---")
    results = []
    old = [
        {"name": "Quattro", "plcs": [{"ip": "10.0.0.1"}, {"ip": "10.0.0.2"}]},
        {"name": "Trio", "plcs": ["10.0.1.1", "10.0.1.2"]},  # old plain-IP format
    ]
    saved = {
        "groups": {
            "Quattro": {"x": 2, "y": 2, "orientation": "horizontal"},
            "Trio": {"x": 60, "y": 2, "orientation": "vertical"},
        },
        "tvs": [{"x": 46, "y": 4}],
    }

    renamed = [{"name": "Quattro Left", "plcs": old[0]["plcs"]}, old[1]]
    results.append(_check("rename moves the entry to the new name", reconcile_layout(saved, old, renamed), {
        "groups": {
            "Quattro Left": {"x": 2, "y": 2, "orientation": "horizontal"},
            "Trio": {"x": 60, "y": 2, "orientation": "vertical"},
        },
        "tvs": [{"x": 46, "y": 4}],
    }))

    deleted = [old[1]]
    results.append(_check("delete removes the entry, TVs kept", reconcile_layout(saved, old, deleted), {
        "groups": {"Trio": {"x": 60, "y": 2, "orientation": "vertical"}},
        "tvs": [{"x": 46, "y": 4}],
    }))

    added = [*old, {"name": "Duo", "plcs": [{"ip": "10.0.2.1"}]}]
    results.append(_check("new group gets no entry (falls back to stacked)",
                          sorted(reconcile_layout(saved, old, added)["groups"]), ["Quattro", "Trio"]))

    replaced = [{"name": "Other", "plcs": [{"ip": "10.9.9.9"}]}, old[1]]
    results.append(_check("vanished name with no shared PLCs is dropped, not reassigned",
                          sorted(reconcile_layout(saved, old, replaced)["groups"]), ["Trio"]))

    results.append(_check("input layout not modified", sorted(saved["groups"]), ["Quattro", "Trio"]))
    return results


def main() -> bool:
    results = test_validate() + test_reconcile()
    all_passed = all(results)
    print()
    print("ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
