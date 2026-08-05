"""
serializers.py
---------------
Builds the JSON-ready payload sent to the web frontend (REST + WS share
this shape). Lives outside models.py because ordering plcs within a
group requires priority.calculate_priority(), and priority.py already
imports models.py — putting the group-level serializer here avoids a
models <-> priority import cycle.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import MachineGroup
from .priority import calculate_priority


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def group_to_dict(group: MachineGroup) -> dict:
    """
    Serializes a group with its plcs in CALCULATED priority order (post
    calculate_priority()), so the frontend renders what it receives
    without re-sorting.
    """
    ordered = calculate_priority(group)
    return {
        "name": group.name,
        "type": group.type,
        "plcs": [plc.to_dict() for plc in ordered],
    }


def build_state(groups: list[MachineGroup], connected: bool) -> dict:
    return {
        "connected": connected,
        "timestamp": _now_iso(),
        "groups": [group_to_dict(g) for g in groups],
    }
