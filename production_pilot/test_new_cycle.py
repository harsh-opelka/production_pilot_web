"""
test_new_cycle.py
------------------
Plain-assert self-test for the New Cycle start sequence (new_cycle.py)
and how it drives the Next Action (priority.py / serializers.py), with a
fake clock. No pytest needed — run from the project root:

    python -m production_pilot.test_new_cycle
"""

from __future__ import annotations

from . import new_cycle
from .models import MachineGroup, MachineState, PlcData
from .new_cycle import NewCycleTracker, validate_delay
from .serializers import build_state

WAITING, BAKING, HEATING = MachineState.WAITING, MachineState.BAKING, MachineState.HEATING
STANDBY, COLD, HOT = MachineState.STANDBY, MachineState.COLD, MachineState.HOT
ERROR, BLOCKED = MachineState.ERROR, MachineState.BLOCKED
DELAY = 120
OFF = "offline"


def _check(label: str, actual, expected) -> bool:
    ok = actual == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")
    return ok


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Site:
    """One QUATTRO ("Q", machines 1-4 in saved order) plus a helper to poll
    the tracker and build the state payload exactly like server.py."""

    def __init__(self, *states, group: str = "Q") -> None:
        self.clock = FakeClock()
        self.tracker = NewCycleTracker(self.clock)
        self.group = group
        self.plcs = [
            PlcData(ip=f"10.0.0.{i + 1}", name=f"M{i + 1}", state=WAITING, is_online=True,
                    default_priority=i, unit_number=i + 1)
            for i in range(len(states))
        ]
        self.set(*states)

    def set(self, *states) -> None:
        for plc, state in zip(self.plcs, states):
            if state is None:
                continue
            plc.is_online = state != OFF
            if state != OFF:
                plc.state = state[0] if isinstance(state, tuple) else state
                plc.remaining_seconds = state[1] if isinstance(state, tuple) else (600 if state == BAKING else None)

    def poll(self, *states, after: float = 0.5, delay: int = DELAY) -> dict:
        self.clock.now += after
        if states:
            self.set(*states)
        groups = [MachineGroup(name=self.group, type="QUATTRO", plcs=self.plcs)]
        self.cycles = self.tracker.update(groups, delay)
        return build_state(groups, True, self.cycles)

    @property
    def new_cycle(self) -> bool:
        return self.cycles[self.group].new_cycle


def na(state: dict) -> tuple:
    a = state["next_action"]
    if a["kind"] == "wait":
        return "wait", a["wait_remaining_seconds"], a["next_unit_number"], a["ip"]
    return a["kind"], a["unit_number"]


ALMOST = (BAKING, 20)


def test_flag() -> list[bool]:
    print("--- new_cycle flag ---")
    r = []
    s = Site(WAITING, WAITING, WAITING, WAITING)
    s.poll()
    r.append(_check("all online Waiting -> new_cycle TRUE", s.new_cycle, True))

    for odd in (STANDBY, HEATING, COLD, BLOCKED):
        s = Site(WAITING, WAITING, WAITING, odd)
        s.poll()
        r.append(_check(f"one {odd.name} -> stays FALSE", s.new_cycle, False))

    s = Site(WAITING, WAITING, WAITING, WAITING)
    s.poll()
    s.poll(BAKING, BAKING, BAKING, ALMOST)
    r.append(_check("all online Baking (incl. Almost finished) -> FALSE", s.new_cycle, False))

    s = Site(WAITING, WAITING, WAITING, OFF)
    s.poll()
    r.append(_check("offline ignored: 3 Waiting + 1 offline -> TRUE", s.new_cycle, True))
    s.poll(BAKING, BAKING, BAKING, OFF)
    r.append(_check("offline ignored: 3 Baking + 1 offline -> FALSE", s.new_cycle, False))
    s = Site(OFF, OFF, OFF, OFF)
    s.poll()
    r.append(_check("nothing online -> FALSE", s.new_cycle, False))

    s = Site(WAITING, WAITING, WAITING, WAITING)
    s.poll()
    s.poll(BAKING, WAITING, WAITING, WAITING)
    s.poll(STANDBY, HEATING, ERROR, BLOCKED)
    r.append(_check("abort: nothing Waiting or Baking any more -> FALSE", s.new_cycle, False))
    s.poll(BAKING, HEATING, ERROR, BLOCKED)
    r.append(_check("after abort, Baking alone does not re-arm it", s.new_cycle, False))
    s.poll(WAITING, WAITING, WAITING, WAITING)
    r.append(_check("all Waiting again -> TRUE again (next cycle)", s.new_cycle, True))

    r.append(_check("open question default: Blocked is NOT Waiting", new_cycle.BLOCKED_COUNTS_AS_WAITING, False))
    return r


def test_sequence() -> list[bool]:
    print()
    print("--- start sequence (delay 120 s, fake clock) ---")
    r = []
    s = Site(WAITING, WAITING, WAITING, WAITING)
    r.append(_check("new cycle, nothing started -> 1: Load Machine (no delay yet)", na(s.poll()), ("load", 1)))

    st = s.poll(BAKING, None, None, None)
    r.append(_check("machine 1 enters Baking -> Wait 2:00, next is 2, no NEXT badge (ip None)",
                    na(st), ("wait", 120, 2, None)))
    r.append(_check("group payload carries new_cycle + wait_remaining_seconds",
                    (st["groups"][0]["new_cycle"], st["groups"][0]["wait_remaining_seconds"]), (True, 120)))
    r.append(_check("26 s later -> Wait 1:34", na(s.poll(after=26)), ("wait", 94, 2, None)))
    r.append(_check("delay over (120 s after the start) -> 2: Load Machine",
                    na(s.poll(after=94)), ("load", 2)))

    s.poll(after=30)  # the banner asked for machine 2 for a while ...
    st = s.poll(None, BAKING, None, None, after=0.5)
    r.append(_check("machine 2 starts -> delay restarts from ITS start (Wait 2:00), next is 3",
                    na(st), ("wait", 120, 3, None)))
    r.append(_check("119.5 s after machine 2 started -> still Wait 0:01", na(s.poll(after=119.5)), ("wait", 1, 3, None)))
    r.append(_check("120 s after -> 3: Load Machine", na(s.poll(after=0.5)), ("load", 3)))

    s.poll(None, None, BAKING, None)
    st = s.poll(None, None, None, BAKING, after=200)
    r.append(_check("last machine starts -> all Baking -> new_cycle FALSE, normal rules (smiley)",
                    (s.new_cycle, na(st)), (False, ("nothing_to_do", None))))
    return r


def test_other_machine_and_precedence() -> list[bool]:
    print()
    print("--- operator starts another machine / precedence ---")
    r = []
    s = Site(WAITING, WAITING, WAITING, WAITING)
    s.poll()
    s.poll(BAKING, None, None, None)
    s.poll(after=130)  # delay over -> asks for 2
    st = s.poll(None, None, BAKING, None, after=5)  # ... but 3 is started instead
    r.append(_check("different machine started -> delay restarts, next = highest priority still Waiting (2)",
                    na(st), ("wait", 120, 2, None)))
    st = s.poll(None, BAKING, None, None, after=10)  # starts 2 during the delay
    r.append(_check("start during the delay -> delay restarts again, next is 4", na(st), ("wait", 120, 4, None)))

    s = Site(WAITING, WAITING, WAITING, WAITING)
    s.poll()
    s.poll(BAKING, None, None, None)
    r.append(_check("Error beats Wait", na(s.poll(None, None, ERROR, None, after=5)), ("error", 3)))
    for shown in (STANDBY, COLD, HOT):
        r.append(_check(f"Switch to Auto ({shown.name}) beats Wait",
                        na(s.poll(None, None, shown, None, after=1)), ("switch_to_auto", 3)))
    s.poll(ALMOST, None, WAITING, None, after=1)
    r.append(_check("Wait beats Unload Soon", na(s.poll(after=1))[0], "wait"))

    # Mid-cycle (new_cycle never armed): normal Load Machine, no delay.
    s = Site(BAKING, BAKING, WAITING, BAKING)
    s.poll()
    st = s.poll(None, None, WAITING, WAITING)  # 4 finished baking
    r.append(_check("new_cycle FALSE mid-cycle -> normal 3: Load Machine, no delay",
                    (s.new_cycle, na(st)), (False, ("load", 3))))
    st = s.poll(None, None, BAKING, None)
    r.append(_check("... and starting 3 mid-cycle -> straight to 4: Load Machine", na(st), ("load", 4)))

    # LOAD_BLOCKED_WHILE_GROUP_HEATING also holds back the Wait countdown.
    s = Site(WAITING, WAITING, WAITING, WAITING)
    s.poll()
    s.poll(BAKING, None, None, None)
    r.append(_check("group Heating during the delay -> no Wait (Waiting tier blocked), smiley",
                    na(s.poll(None, None, None, HEATING, after=1)), ("nothing_to_do", None)))

    # Two groups: a loadable machine in another group beats the countdown.
    a = Site(WAITING, WAITING, group="A")
    b_plcs = [PlcData(ip="10.0.1.1", name="B1", state=BAKING, is_online=True, remaining_seconds=600,
                      default_priority=0, unit_number=1)]
    groups = [MachineGroup("A", "DUO", a.plcs), MachineGroup("B", "STANDALONE", b_plcs)]
    a.tracker.update(groups, DELAY)
    a.plcs[0].state = BAKING
    a.clock.now += 1
    b_plcs[0].state = WAITING
    cycles = a.tracker.update(groups, DELAY)
    st = build_state(groups, True, cycles)
    r.append(_check("group A in its delay, group B has a Waiting machine -> load B's machine first",
                    (st["next_action"]["kind"], st["next_action"]["ip"]), ("load", "10.0.1.1")))
    return r


def test_restart_and_setting() -> list[bool]:
    print()
    print("--- restart / delay setting ---")
    r = []
    s = Site(BAKING, WAITING, WAITING, WAITING)
    s.poll()
    r.append(_check("restart mid start-sequence (not all Waiting) -> FALSE, normal Load Machine",
                    (s.new_cycle, na(s.poll())), (False, ("load", 2))))
    s = Site(WAITING, WAITING, WAITING, WAITING)
    s.poll()
    r.append(_check("restart with all Waiting -> TRUE again", s.new_cycle, True))

    s.poll(BAKING, None, None, None, delay=10)
    r.append(_check("short delay for demo/testing (10 s)", na(s.poll(after=4, delay=10)), ("wait", 6, 2, None)))
    r.append(_check("setting changed mid-countdown -> running countdown keeps its value",
                    na(s.poll(after=1, delay=600)), ("wait", 5, 2, None)))
    st = s.poll(None, BAKING, None, None, after=10, delay=600)
    r.append(_check("... the new value applies to the next delay", na(st), ("wait", 600, 3, None)))

    r.append(_check("default delay 120 s", new_cycle.DEFAULT_DELAY_SECONDS, 120))
    r.append(_check("10 and 3600 accepted", (validate_delay(10), validate_delay(3600)), (10, 3600)))
    for bad in (9, 3601, 0, -5, 12.5, "120", None, True, float("nan")):
        try:
            validate_delay(bad)
            rejected = False
        except ValueError:
            rejected = True
        r.append(_check(f"rejected: {bad!r}", rejected, True))
    return r


def test_endpoint() -> list[bool]:
    print()
    print("--- GET / PUT /api/service/new-cycle-delay ---")
    import contextlib
    import io
    import tempfile
    from pathlib import Path

    from fastapi.testclient import TestClient

    import server
    from . import history

    history.DB_PATH = Path(tempfile.mkdtemp(prefix="pp_test_new_cycle_")) / "history.db"
    with contextlib.redirect_stdout(io.StringIO()):
        history.init_db()
    client = TestClient(server.app)
    service = {"Authorization": f"Bearer {server._create_session('service')}"}
    management = {"Authorization": f"Bearer {server._create_session('management')}"}
    url = "/api/service/new-cycle-delay"
    r = [
        _check("GET without session -> default 120", client.get(url).json()["delay_seconds"], 120),
        _check("PUT as management -> 403", client.put(url, json={"delay_seconds": 60}, headers=management).status_code, 403),
    ]
    res = client.put(url, json={"delay_seconds": 5}, headers=service)
    r.append(_check("PUT 5 -> 400 with a clear message",
                    (res.status_code, "between 10 and 3600" in res.json()["detail"]), (400, True)))
    r.append(_check("PUT 3601 -> 400", client.put(url, json={"delay_seconds": 3601}, headers=service).status_code, 400))
    res = client.put(url, json={"delay_seconds": 10}, headers=service)
    r.append(_check("PUT 10 as service -> saved, used by the poll loop",
                    (res.status_code, history.get_new_cycle_delay_seconds()), (200, 10)))
    with contextlib.redirect_stdout(io.StringIO()):
        history.init_db()
    r.append(_check("survives a restart", history.get_new_cycle_delay_seconds(), 10))
    return r


def main() -> bool:
    results = test_flag() + test_sequence() + test_other_machine_and_precedence() + test_restart_and_setting() + test_endpoint()
    all_passed = all(results)
    print()
    print("ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
