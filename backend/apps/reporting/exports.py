"""CSV / Excel / PDF exporters. Cells are neutralised against spreadsheet formula injection (a cell starting with = + - @ or a control
character would otherwise be executed by Excel when the file is opened)."""
import csv
import io
from datetime import date, datetime
from decimal import Decimal

MAX_EXPORT_ROWS = 20_000
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe(v):
    if isinstance(v, str) and v.startswith(_DANGEROUS):
        return "'" + v
    return v


def display(v, kind):
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return f"{v:.2f}"
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return safe(str(v)) if isinstance(v, str) else v


def to_csv(title, columns, rows, summary) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([c["label"] for c in columns])
    for r in rows:
        w.writerow([display(r.get(c["key"]), c["kind"]) for c in columns])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel reads UTF-8


def to_xlsx(title, columns, rows, summary) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append([c["label"] for c in columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        line = []
        for c in columns:
            v = r.get(c["key"])
            line.append(float(v) if isinstance(v, Decimal) else safe(v) if isinstance(v, str) else v)
        ws.append(line)
    for i, c in enumerate(columns, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = max(12, min(40, len(c["label"]) + 4))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_pdf(title, columns, rows, summary, subtitle="") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    st = getSampleStyleSheet()
    data = [[c["label"] for c in columns]] + [[str(display(r.get(c["key"]), c["kind"]))[:60] for c in columns] for r in rows]
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")), ("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                           ("ALIGN", (0, 1), (-1, -1), "LEFT"), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
    parts = [Paragraph(title, st["Title"]), Paragraph(subtitle, st["Normal"]), Spacer(1, 8), t]
    if summary:
        parts += [Spacer(1, 8), Paragraph(" · ".join(f"{k.replace('_', ' ')}: {display(v, 'text')}" for k, v in summary.items()), st["Normal"])]
    doc.build(parts)
    return out.getvalue()


CONTENT = {"csv": ("text/csv; charset=utf-8", to_csv), "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", to_xlsx), "pdf": ("application/pdf", to_pdf)}
