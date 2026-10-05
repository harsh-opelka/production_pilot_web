"""
exports.py
----------
Statistics-page exports (CSV / Excel / PDF) for one day's
with_all_configured_machines() summary — see server.py's
/api/stats/daily-summary/{csv,xlsx,pdf}.

All three formats are built from the same header/row lists (_table), so
they can never disagree about columns or values. Durations are written as
"1h 24m" strings rather than raw seconds/minutes so a manager can read the
export directly without converting units (same format as the on-screen
table — see frontend format.js formatHoursMinutes, which also floors to
whole minutes).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from fpdf import FPDF
from fpdf.fonts import FontFace

#: (header, machine-dict key) for every duration column, in table order.
#: untracked_seconds = UNKNOWN/SERVER_STOPPED marker spans, i.e. genuine
#: server-downtime gaps, not machine time (see stats.py module docstring).
_DURATION_COLUMNS = [
    ("Baking", "baking_seconds"),
    ("Ready", "ready_seconds"),
    ("Heating", "heating_seconds"),
    ("Error", "error_seconds"),
    ("Cold", "cold_seconds"),
    ("Offline", "offline_seconds"),
    ("No data (server offline)", "untracked_seconds"),
]

HEADERS = [
    "Machine Group",
    "Unit",
    *[header for header, _ in _DURATION_COLUMNS[:4]],
    "Error Count",
    *[header for header, _ in _DURATION_COLUMNS[4:]],
    "Productivity (%)",
]


def format_hm(seconds: float | int | None) -> str:
    """ "1h 24m" / "0h 8m" — whole minutes, floored."""
    total = max(0, round(seconds or 0))
    return f"{total // 3600}h {(total % 3600) // 60}m"


def _row(m: dict) -> list:
    durations = [format_hm(m[key]) for _, key in _DURATION_COLUMNS]
    return [
        m["group_name"],
        m["unit_number"],
        *durations[:4],
        m["error_count"],
        *durations[4:],
        f"{m['productivity_pct']:.1f}%",
    ]


def _table(summary: dict) -> list[list]:
    # Explicit group -> unit order, independent of what the caller passed
    # (Machine 1, 2, 3, ... within each group).
    machines = sorted(summary["machines"], key=lambda m: (m["group_name"], m["unit_number"]))
    return [_row(m) for m in machines]


def to_csv(summary: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEADERS)
    writer.writerows(_table(summary))
    return buf.getvalue()


def to_xlsx(summary: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = f"Statistics {summary['date']}"
    rows = _table(summary)
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)

    header_fill = PatternFill("solid", fgColor="05346C")  # OPELKA navy
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for col_index, header in enumerate(HEADERS, start=1):
        values = [str(header)] + [str(row[col_index - 1]) for row in rows]
        ws.column_dimensions[get_column_letter(col_index)].width = min(max(len(v) for v in values) + 2, 28)
        if col_index > 1:
            for cell in ws[get_column_letter(col_index)][1:]:
                cell.alignment = Alignment(horizontal="right")
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- PDF -------------------------------------------------------------------

_NAVY = (5, 52, 108)
_GREY = (100, 116, 139)
_LIGHT = (238, 242, 247)


def _latin1(text) -> str:
    # fpdf2's built-in core fonts are Latin-1 only; German umlauts are
    # fine, anything else degrades to "?" rather than raising.
    return str(text).encode("latin-1", "replace").decode("latin-1")


def to_pdf(summary: dict, totals: dict, target_pct: int | None, comparison: dict | None) -> bytes:
    """One-page A4-landscape daily report: title, date, KPI summary
    boxes, then the per-machine table. `totals` is stats.compute_totals()
    for the day; `comparison` is stats.compute_seven_day_average() (or
    None), shown as a "7-day avg" sub-line under each KPI."""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 10, "Production Statistics - Daily Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*_GREY)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    pdf.cell(0, 6, f"Date: {summary['date']}    |    Generated: {generated}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    avg = comparison["averages"] if comparison else None
    kpis = [
        (
            "Productivity",
            f"{totals['productivity_pct']:.1f}%",
            f"Target {target_pct}%" if target_pct is not None else "",
        ),
        ("Baking time", format_hm(totals["baking_seconds"]), f"7-day avg {format_hm(avg['baking_seconds'])}" if avg else ""),
        ("Error time", format_hm(totals["error_seconds"]), f"7-day avg {format_hm(avg['error_seconds'])}" if avg else ""),
        ("Error count", str(totals["error_count"]), f"7-day avg {avg['error_count']:.1f}" if avg else ""),
    ]
    gap = 4
    box_w = (pdf.epw - gap * (len(kpis) - 1)) / len(kpis)
    box_h = 22
    top = pdf.get_y()
    for i, (label, value, sub) in enumerate(kpis):
        x = pdf.l_margin + i * (box_w + gap)
        pdf.set_fill_color(*_LIGHT)
        pdf.rect(x, top, box_w, box_h, style="F")
        pdf.set_fill_color(*_NAVY)
        pdf.rect(x, top, 1.5, box_h, style="F")
        pdf.set_xy(x, top + 2)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_GREY)
        pdf.cell(box_w, 4, label.upper(), align="C")
        pdf.set_xy(x, top + 7)
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(box_w, 8, value, align="C")
        pdf.set_xy(x, top + 16)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*_GREY)
        pdf.cell(box_w, 4, sub, align="C")
    pdf.set_xy(pdf.l_margin, top + box_h + 6)

    rows = _table(summary)
    pdf.set_text_color(15, 23, 42)
    if not rows:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 8, "No data recorded for this date.")
        return bytes(pdf.output())

    pdf.set_font("Helvetica", "", 8)
    pdf.set_draw_color(203, 213, 225)
    pdf.set_fill_color(255, 255, 255)  # the KPI boxes left it navy
    col_widths = (34, 12, 20, 20, 20, 20, 16, 20, 20, 30, 22)
    with pdf.table(
        col_widths=col_widths,
        text_align=("LEFT", "CENTER", *(["RIGHT"] * (len(HEADERS) - 2))),
        headings_style=FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=_NAVY),
        line_height=5.5,
        cell_fill_color=_LIGHT,
        cell_fill_mode="ROWS",
    ) as table:
        table.row([_latin1(h) for h in HEADERS])
        for row in rows:
            table.row([_latin1(v) for v in row])

    return bytes(pdf.output())
