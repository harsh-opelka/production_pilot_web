"""
serializers.py
---------------
Builds the JSON-ready payload sent to the web frontend (REST + WS share
this shape). Lives outside models.py because it needs priority.py (the
near-completion flag and the Next Action pick), and priority.py already
imports models.py — putting the group-level serializer here avoids a
models <-> priority import cycle.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import MachineGroup
from .priority import is_near_completion, select_next_action


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _plc_to_dict(plc) -> dict:
    d = plc.to_dict()
    # Display-only "Fast fertig"/"Almost finished" override — see
    # priority.is_near_completion's docstring.
    d["near_completion"] = is_near_completion(plc)
    return d


def _saved_order(group: MachineGroup) -> list:
    return sorted(group.plcs, key=lambda p: p.default_priority)


def group_to_dict(group: MachineGroup) -> dict:
    """Serializes a group with its plcs in SAVED priority order. Tile
    placement is the frontend's job (machine number within a group) and
    never depends on live state, so tiles don't jump around."""
    return {
        "name": group.name,
        "type": group.type,
        "plcs": [_plc_to_dict(plc) for plc in _saved_order(group)],
    }


def build_state(groups: list[MachineGroup], connected: bool) -> dict:
    saved_order = [plc for group in groups for plc in _saved_order(group)]
    group_by_ip = {plc.ip: group.name for group in groups for plc in group.plcs}
    return {
        "connected": connected,
        "timestamp": _now_iso(),
        "groups": [group_to_dict(g) for g in groups],
        # Derived from `groups`, so the WS broadcaster's change check
        # (which only compares groups/connected) still covers it.
        "next_action": select_next_action(saved_order, group_by_ip),
    }
