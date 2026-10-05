"""
plc_config.py
-------------
Parsing and validation for plc_config.json's per-PLC entries — the one
place that knows the file's schema, shared by OpcUaSource, SimulatedSource,
stats.load_configured_plcs and server.py's /api/service/config.

Each machine's "plcs" array holds one entry per PLC:

    {"ip": "192.168.178.150", "unit_number": 3}

  - Array order is the default priority (index 0 = highest), exactly as
    before — priority.py never sees unit_number.
  - unit_number is the fixed machine number of the physical fryer, set by
    the technician in the Installation Wizard. It's what every screen,
    history row and export labels the PLC with, so re-ordering priority
    never renames a machine.

Backward compatible: an older config stores plain IP strings, which are
read as {"ip": <str>, "unit_number": <index + 1>} — the numbering that
config always implied. The wizard writes the new format on its next save.
"""

from __future__ import annotations

import json
from pathlib import Path


def normalize_plcs(raw_plcs: list) -> list[dict]:
    """A machine's raw "plcs" array (old or new format) as a list of
    {"ip", "unit_number"} dicts, in the same (priority) order. Doesn't
    validate unit_number — see unit_number_problem."""
    plcs = []
    for index, entry in enumerate(raw_plcs):
        if isinstance(entry, str):
            plcs.append({"ip": entry, "unit_number": index + 1})
        else:
            plcs.append({"ip": entry["ip"], "unit_number": entry.get("unit_number")})
    return plcs


def _is_positive_int(value) -> bool:
    # bool is an int subclass — True must not pass as machine number 1.
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def unit_number_problem(group_name: str, plcs: list[dict]) -> str | None:
    """A human-readable error if any machine number in this group is
    missing, not a positive whole number, or used twice; None if all
    fine. Machine numbers only need to be unique within their own group."""
    seen: set[int] = set()
    for plc in plcs:
        number = plc["unit_number"]
        if not _is_positive_int(number):
            return (
                f"Machine '{group_name}': machine number for {plc['ip']} must be "
                f"a whole number of 1 or more (got {number!r})"
            )
        if number in seen:
            return f"Machine '{group_name}': machine number {number} is used more than once"
        seen.add(number)
    return None


def read_config(config_path: Path) -> dict:
    """plc_config.json with every machine's "plcs" normalized to the new
    format, WITHOUT validating machine numbers — for the wizard's GET,
    which must still be able to show (and let a technician fix) a
    hand-edited config with a bad number. Raises on a missing/corrupt file."""
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for machine in data.get("machines", []):
        machine["plcs"] = normalize_plcs(machine.get("plcs", []))
    return data


def load_config(config_path: Path) -> dict:
    """read_config, plus validation — raises ValueError on a bad machine
    number. What the data sources and stats build from."""
    data = read_config(config_path)
    for machine in data.get("machines", []):
        problem = unit_number_problem(machine["name"], machine["plcs"])
        if problem:
            raise ValueError(problem)
    return data
