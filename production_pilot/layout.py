"""
layout.py
---------
The dashboard's floor layout: where each machine group (and any TV icons)
sits on the screen, so the tile view mirrors the physical floor. Edited
from the Service page's floor layout editor, stored as JSON in
app_settings (see history.get_floor_layout / set_floor_layout), served by
GET/PUT /api/layout.

Shape (all positions are percentages of the 16:9 canvas, top-left corner
of the item):

    {
      "groups": {"<group name>": {"x": 4, "y": 6, "orientation": "horizontal"}},
      "tvs":    [{"x": 46, "y": 2}]
    }

A group with no entry falls back to the stacked layout on the dashboard,
so newly created groups never disappear. Pure functions only — no I/O.
"""

from __future__ import annotations

import math

ORIENTATIONS = ("horizontal", "vertical")
MAX_TVS = 10

EMPTY_LAYOUT: dict = {"groups": {}, "tvs": []}


class LayoutError(ValueError):
    """Raised by validate_layout with a human-readable reason."""


def _percent(value, what: str) -> float:
    # bool is an int subclass — True must not pass as 1 %.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise LayoutError(f"{what} must be a number")
    if not 0 <= value <= 100:
        raise LayoutError(f"{what} must be between 0 and 100 (got {value})")
    return float(value)


def _position(raw, what: str, extra_keys: frozenset = frozenset()) -> dict:
    if not isinstance(raw, dict):
        raise LayoutError(f"{what} must be an object")
    unknown = set(raw) - {"x", "y"} - extra_keys
    if unknown:
        raise LayoutError(f"{what} has unknown field(s): {', '.join(sorted(unknown))}")
    return {"x": _percent(raw.get("x"), f"{what}.x"), "y": _percent(raw.get("y"), f"{what}.y")}


def validate_layout(payload, group_names: set[str]) -> dict:
    """Returns a normalized copy of `payload`, or raises LayoutError.
    Rejects positions outside 0..100, unknown group names (anything not in
    `group_names`), bad orientations, unknown fields and more than MAX_TVS
    TVs."""
    if not isinstance(payload, dict):
        raise LayoutError("layout must be an object")
    unknown = set(payload) - {"groups", "tvs"}
    if unknown:
        raise LayoutError(f"layout has unknown field(s): {', '.join(sorted(unknown))}")

    raw_groups = payload.get("groups", {})
    if not isinstance(raw_groups, dict):
        raise LayoutError("groups must be an object keyed by group name")
    groups = {}
    for name, raw in raw_groups.items():
        if name not in group_names:
            raise LayoutError(f"unknown group: {name!r}")
        position = _position(raw, f"group {name!r}", frozenset({"orientation"}))
        orientation = raw.get("orientation", "horizontal")
        if orientation not in ORIENTATIONS:
            raise LayoutError(f"group {name!r}: orientation must be one of {', '.join(ORIENTATIONS)}")
        groups[name] = {**position, "orientation": orientation}

    raw_tvs = payload.get("tvs", [])
    if not isinstance(raw_tvs, list):
        raise LayoutError("tvs must be a list")
    if len(raw_tvs) > MAX_TVS:
        raise LayoutError(f"at most {MAX_TVS} TVs are allowed")
    tvs = [_position(raw, f"tv {index + 1}") for index, raw in enumerate(raw_tvs)]

    return {"groups": groups, "tvs": tvs}


def _ips(machine: dict) -> set[str]:
    return {plc if isinstance(plc, str) else plc["ip"] for plc in machine.get("plcs", [])}


def reconcile_layout(layout: dict, old_machines: list[dict], new_machines: list[dict]) -> dict:
    """Keeps a saved layout consistent with a freshly saved wizard config.
    The wizard posts the whole machine list, not individual operations, so
    renames are recognised by their PLCs:

      - a group whose name still exists keeps its entry;
      - a group name that's gone, whose old PLCs now (partly) belong to a
        new name that has no entry yet, moves its entry to that name
        (rename) — the new group sharing the most PLCs wins;
      - any other vanished name is dropped (delete).

    TVs are untouched. Returns a new dict; `layout` itself isn't modified."""
    new_names = {m["name"] for m in new_machines}
    old_ips_by_name = {m["name"]: _ips(m) for m in old_machines}
    new_ips_by_name = {m["name"]: _ips(m) for m in new_machines}

    groups = {name: entry for name, entry in layout.get("groups", {}).items() if name in new_names}
    for name, entry in layout.get("groups", {}).items():
        if name in new_names:
            continue
        old_ips = old_ips_by_name.get(name, set())
        candidates = [
            (len(old_ips & ips), new_name)
            for new_name, ips in new_ips_by_name.items()
            if new_name not in groups and old_ips & ips
        ]
        if candidates:
            _, renamed_to = max(candidates)
            groups[renamed_to] = entry

    return {"groups": groups, "tvs": list(layout.get("tvs", []))}
