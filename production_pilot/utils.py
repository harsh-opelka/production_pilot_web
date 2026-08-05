"""
utils.py
--------
Small formatting helpers that need i18n but must stay import-safe from
models.py (i18n.py already imports from models.py, so models.py can't
import i18n.py back without a cycle — hence this separate module).
"""

from __future__ import annotations

from .i18n import tm


def format_remaining(seconds: int) -> str:
    """
    Format remaining seconds for display in the current language, e.g.
    "3 mins 45 secs" (EN) / "3 Min. 45 Sek." (DE).
    """
    seconds = max(0, seconds)
    minutes, secs = divmod(seconds, 60)
    return tm.t("remaining_time_format").format(mins=minutes, secs=secs)


def format_unit_name(unit_number: int) -> str:
    """
    Format a PLC's on-screen unit label in the current language, e.g.
    "Fryer 2" (EN) / "Fritteuse 2" (DE), built from PlcData.unit_number.
    """
    return f"{tm.t('unit_fryer')} {unit_number}"
