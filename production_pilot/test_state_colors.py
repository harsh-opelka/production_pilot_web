"""
test_state_colors.py
---------------------
Plain-assert self-test for the Service-configurable state colours:
state_colors.py (hex validation, defaults, merging) and the
GET/PUT /api/state-colors endpoints (levels, validation, colors_version
in the state payload). No pytest needed — run from the project root:

    python -m production_pilot.test_state_colors
"""

from __future__ import annotations

import contextlib
import io
import tempfile
from pathlib import Path

from . import history
from .state_colors import (
    DEFAULT_STATE_COLORS,
    StateColorsError,
    colors_version,
    merge_with_defaults,
    normalize_hex,
    validate_update,
)


def _check(label: str, actual, expected) -> bool:
    ok = actual == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")
    return ok


def _raises(fn, *args) -> bool:
    try:
        fn(*args)
    except StateColorsError:
        return True
    return False


def test_hex() -> list[bool]:
    print("--- hex validation / normalization ---")
    results = [
        _check("#rgb -> #RRGGBB uppercase", normalize_hex("#0af"), "#00AAFF"),
        _check("#rrggbb lowercase -> uppercase", normalize_hex("#05346c"), "#05346C"),
        _check("surrounding spaces ignored", normalize_hex("  #FACC15 "), "#FACC15"),
    ]
    for bad in ("05346C", "#12", "#12345", "#1234567", "#GGGGGG", "", None, 123, "red"):
        results.append(_check(f"rejected: {bad!r}", _raises(normalize_hex, bad), True))
    return results


def test_merge() -> list[bool]:
    print()
    print("--- defaults / merge ---")
    return [
        _check("nothing saved -> defaults", merge_with_defaults(None), DEFAULT_STATE_COLORS),
        _check("9 slots, Standby/Unknown included",
               list(DEFAULT_STATE_COLORS),
               ["waiting", "baking", "near_completion", "heating", "hot", "cold", "blocked", "error", "standby"]),
        _check("partial saved JSON merges with defaults",
               merge_with_defaults({"hot": "#ff0"}), {**DEFAULT_STATE_COLORS, "hot": "#FFFF00"}),
        _check("unknown and invalid stored keys ignored",
               merge_with_defaults({"purple_thing": "#000000", "error": "nope"}), DEFAULT_STATE_COLORS),
        _check("version changes with the colours",
               colors_version(DEFAULT_STATE_COLORS) != colors_version({**DEFAULT_STATE_COLORS, "hot": "#FFFF00"}),
               True),
        _check("version is stable", colors_version(dict(DEFAULT_STATE_COLORS)), colors_version(DEFAULT_STATE_COLORS)),
        _check("validate_update normalizes", validate_update({"cold": "#abc"}), {"cold": "#AABBCC"}),
        _check("validate_update rejects unknown state", _raises(validate_update, {"COLD": "#000000"}), True),
        _check("validate_update rejects invalid hex", _raises(validate_update, {"cold": "#12"}), True),
        _check("validate_update rejects a non-object", _raises(validate_update, ["#000000"]), True),
    ]


def test_endpoints() -> list[bool]:
    print()
    print("--- GET / PUT /api/state-colors ---")
    from fastapi.testclient import TestClient

    import server  # project root is on sys.path when run with -m from the root

    history.DB_PATH = Path(tempfile.mkdtemp(prefix="pp_test_colors_")) / "history.db"
    with contextlib.redirect_stdout(io.StringIO()):
        history.init_db()
    client = TestClient(server.app)  # no `with`: lifespan (poll thread) not started
    service = {"Authorization": f"Bearer {server._create_session('service')}"}
    management = {"Authorization": f"Bearer {server._create_session('management')}"}

    results = []
    for label, headers in (("no session", {}), ("management", management), ("service", service)):
        res = client.get("/api/state-colors", headers=headers)
        results.append(_check(f"GET works for {label}", (res.status_code, res.json()["colors"]),
                              (200, DEFAULT_STATE_COLORS)))
    body = client.get("/api/state-colors").json()
    results.append(_check("GET includes the defaults", body["defaults"], DEFAULT_STATE_COLORS))

    results.append(_check("PUT without session -> 401",
                          client.put("/api/state-colors", json={"hot": "#FFFF00"}).status_code, 401))
    results.append(_check("PUT as management -> 403",
                          client.put("/api/state-colors", json={"hot": "#FFFF00"}, headers=management).status_code,
                          403))
    res = client.put("/api/state-colors", json={"bogus": "#FFFF00"}, headers=service)
    results.append(_check("PUT unknown state -> 400 with a clear error",
                          (res.status_code, "bogus" in res.json()["detail"]), (400, True)))
    res = client.put("/api/state-colors", json={"hot": "yellow"}, headers=service)
    results.append(_check("PUT invalid hex -> 400 naming the state",
                          (res.status_code, res.json()["detail"].startswith("hot:")), (400, True)))
    results.append(_check("rejected PUTs saved nothing", history.get_saved_state_colors(), None))

    version_before = client.get("/api/machines").json()["colors_version"]
    res = client.put("/api/state-colors", json={"hot": "#ff0", "error": "#B91C1C"}, headers=service)
    results.append(_check("PUT as service -> 200, normalized, merged with defaults",
                          (res.status_code, res.json()["colors"]),
                          (200, {**DEFAULT_STATE_COLORS, "hot": "#FFFF00", "error": "#B91C1C"})))
    results.append(_check("saved as one JSON value in app_settings",
                          history.get_saved_state_colors(), {"hot": "#FFFF00", "error": "#B91C1C"}))
    results.append(_check("GET for everyone returns the saved colours",
                          client.get("/api/state-colors").json()["colors"]["hot"], "#FFFF00"))
    results.append(_check("state payload's colors_version changed (TV re-fetches)",
                          client.get("/api/machines").json()["colors_version"] != version_before, True))

    with contextlib.redirect_stdout(io.StringIO()):
        history.init_db()  # restart: cache primed from the DB
    results.append(_check("survives a restart", history.get_saved_state_colors()["hot"], "#FFFF00"))

    res = client.put("/api/state-colors", json=body["defaults"], headers=service)
    results.append(_check("reset = PUT of the defaults",
                          (res.json()["colors"], client.get("/api/machines").json()["colors_version"]),
                          (DEFAULT_STATE_COLORS, version_before)))
    return results


def main() -> bool:
    results = test_hex() + test_merge() + test_endpoints()
    all_passed = all(results)
    print()
    print("ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
