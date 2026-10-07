"""
new_cycle.py
-------------
"New Cycle" start sequence (Tim): when a new production cycle begins, the
machines of a group must not all be loaded straight after one another —
after each machine is started (enters Baking) the operator waits a
configurable delay before the next machine is asked for. Only the START
of a cycle is affected; mid-cycle the normal Next Action rules apply.

Per machine group, ONLINE machines only (offline ones are ignored, like
priority.py):
  - new_cycle -> True  when all online machines are Waiting
  - new_cycle -> False when all online machines are Baking (Almost
                       finished is Baking too): the cycle has started
  - new_cycle -> False (abort) when no online machine is Waiting or Baking
                       any more, so it can never get stuck
  - while True: every transition INTO Baking (first poll that sees it)
    (re)starts the delay; while it runs, the Next Action shows a "Wait
    m:ss" countdown instead of "Load Machine" (see priority.py).

Runtime state only — never persisted. A fresh NewCycleTracker (server
restart) starts with new_cycle False and recomputes from the next poll.
The clock is injectable (monotonic seconds) so tests can fake time.

Applied in ONE place: server.py's poll processing, after the Hot/Cold rule
and transition logging, on the same derived groups everything else sees.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable

from .models import MachineGroup, MachineState

#: Open question (Tim): does a Blocked machine count as "Waiting" for the
#: New Cycle condition? Default: no — Blocked is not Waiting.
BLOCKED_COUNTS_AS_WAITING = False

#: Service setting (app_settings.new_cycle_delay_seconds), in seconds.
DEFAULT_DELAY_SECONDS = 120
MIN_DELAY_SECONDS = 10
MAX_DELAY_SECONDS = 3600


def validate_delay(value) -> int:
    """The delay as whole seconds, or ValueError with a readable reason."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Delay must be a number of seconds")
    if value != int(value):
        raise ValueError("Delay must be a whole number of seconds")
    if not MIN_DELAY_SECONDS <= value <= MAX_DELAY_SECONDS:
        raise ValueError(
            f"Delay must be between {MIN_DELAY_SECONDS} and {MAX_DELAY_SECONDS} seconds (got {value:g})"
        )
    return int(value)


@dataclass
class CycleStatus:
    """What the rest of the app needs per group after a poll."""
    new_cycle: bool = False
    #: Whole seconds left of the running start delay (rounded up), or None
    #: when no delay is running (no machine started yet, delay expired, or
    #: no new cycle).
    wait_remaining_seconds: int | None = None


@dataclass
class _GroupState:
    new_cycle: bool = False
    last_start: float | None = None   # clock time the latest machine entered Baking
    delay: float = DEFAULT_DELAY_SECONDS  # the delay that applies to last_start (kept when the setting changes mid-countdown)
    previous: dict[str, MachineState] = field(default_factory=dict)  # ip -> state on the last poll


def _counts_as_waiting(state: MachineState) -> bool:
    return state == MachineState.WAITING or (BLOCKED_COUNTS_AS_WAITING and state == MachineState.BLOCKED)


class NewCycleTracker:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._groups: dict[str, _GroupState] = {}

    def update(self, groups: list[MachineGroup], delay_seconds: float) -> dict[str, CycleStatus]:
        """Feeds one poll's (derived) groups; returns {group name: CycleStatus}.
        `delay_seconds` applies to delays that START on this poll — a
        countdown already running keeps the value it started with."""
        now = self._clock()
        result: dict[str, CycleStatus] = {}
        for group in groups:
            g = self._groups.setdefault(group.name, _GroupState())
            online = [plc for plc in group.plcs if plc.is_online]

            if not g.new_cycle and online and all(_counts_as_waiting(p.state) for p in online):
                g.new_cycle = True
                g.last_start = None

            if g.new_cycle:
                started = [p for p in online
                           if p.state == MachineState.BAKING and g.previous.get(p.ip) != MachineState.BAKING]
                if started:
                    g.last_start = now
                    g.delay = delay_seconds
                if online and all(p.state == MachineState.BAKING for p in online):
                    g.new_cycle = False  # every machine started: cycle is running
                elif not any(_counts_as_waiting(p.state) or p.state == MachineState.BAKING for p in online):
                    g.new_cycle = False  # abort: nothing left to start or running
                if not g.new_cycle:
                    g.last_start = None

            g.previous = {p.ip: p.state for p in group.plcs if p.is_online}

            remaining = None
            if g.new_cycle and g.last_start is not None:
                left = g.delay - (now - g.last_start)
                if left > 0:
                    remaining = math.ceil(left)
            result[group.name] = CycleStatus(new_cycle=g.new_cycle, wait_remaining_seconds=remaining)
        return result
