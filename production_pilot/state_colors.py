"""
state_colors.py
----------------
The dashboard's machine-state colours, editable from the Service tab
(StateColorsCard.svelte, GET/PUT /api/state-colors). Pure Python, no I/O:
history.py stores the saved JSON in app_settings, server.py exposes it.

DEFAULT_STATE_COLORS is the ONE place the defaults live — the frontend
has no copy of its own; it gets them from GET /api/state-colors.

Keys are colour slots, not MachineState names: "near_completion" is the
"Almost finished" display override of BAKING, and "standby" is the grey
fallback shared by Standby-without-temperature and Unknown. Only the
background colour is stored; the frontend picks white or dark text from
its luminance.
"""

from __future__ import annotations

import hashlib
import json
import re

#: Slot -> default "#RRGGBB", in the order the Service tab lists them.
DEFAULT_STATE_COLORS: dict[str, str] = {
    "waiting": "#05346C",          # OPELKA navy
    "baking": "#16A34A",           # green
    "near_completion": "#9333EA",  # purple ("Almost finished")
    "heating": "#F59E0B",          # orange (the rising fill; the tile stays white)
    "hot": "#FACC15",              # yellow
    "cold": "#6B7280",             # grey
    "blocked": "#334E68",          # slate (always with a dashed border)
    "error": "#DC2626",            # red
    "standby": "#6B7280",          # grey fallback: Standby without temperature, Unknown
}

STATE_KEYS = tuple(DEFAULT_STATE_COLORS)

_HEX_RE = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


class StateColorsError(ValueError):
    """Invalid PUT payload — the message is shown to the technician."""


def normalize_hex(value) -> str:
    """'#RGB' or '#RRGGBB' (any case, surrounding spaces ignored) ->
    '#RRGGBB' uppercase. Raises StateColorsError otherwise."""
    if not isinstance(value, str) or not _HEX_RE.match(value.strip()):
        raise StateColorsError(f"{value!r} is not a hex colour (#RGB or #RRGGBB)")
    digits = value.strip()[1:]
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits.upper()


def merge_with_defaults(saved) -> dict[str, str]:
    """The colours to use: `saved` (the stored JSON, or None) on top of the
    defaults. Missing keys and invalid stored values fall back to the
    default; unknown keys are ignored."""
    colors = dict(DEFAULT_STATE_COLORS)
    if isinstance(saved, dict):
        for key in STATE_KEYS:
            if key in saved:
                try:
                    colors[key] = normalize_hex(saved[key])
                except StateColorsError:
                    pass
    return colors


def validate_update(payload) -> dict[str, str]:
    """A PUT body -> the normalized {key: '#RRGGBB'} to store. Must be an
    object of known keys only; keys left out fall back to their default.
    Raises StateColorsError naming the first bad key/value."""
    if not isinstance(payload, dict):
        raise StateColorsError("Expected an object of {state: '#RRGGBB'}")
    unknown = sorted(set(payload) - set(STATE_KEYS))
    if unknown:
        raise StateColorsError(f"Unknown state(s): {', '.join(map(str, unknown))}")
    result = {}
    for key, value in payload.items():
        try:
            result[key] = normalize_hex(value)
        except StateColorsError as exc:
            raise StateColorsError(f"{key}: {exc}") from None
    return result


def colors_version(colors: dict[str, str]) -> str:
    """Short, stable fingerprint of the effective colours. Sent with every
    state payload so an open dashboard (the TV) re-fetches the colours as
    soon as they change — and only then."""
    return hashlib.sha1(json.dumps(colors, sort_keys=True).encode()).hexdigest()[:12]
