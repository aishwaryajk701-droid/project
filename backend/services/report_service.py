"""PDF report generation (reportlab, backend-only)."""

import io
from datetime import datetime, timezone
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

ACCENT = colors.HexColor("#10B981")
DARK = colors.HexColor("#0B130E")
MUTED = colors.HexColor("#6B7A70")
SEV_COLOR = {"critical": "#7F1D1D", "high": "#DC2626", "moderate": "#D97706", "low": "#CA8A04",
             "none": "#16A34A"}


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Title"], textColor=DARK, fontSize=20, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], textColor=ACCENT, fontSize=13, spaceBefore=10),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontSize=9, leading=12),
        "small": ParagraphStyle("small", parent=ss["BodyText"], fontSize=7, textColor=MUTED),
    }


def _table(rows: list, widths=None, header=True) -> Table:
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    style = [("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D3DCD6")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                                                    [colors.white, colors.HexColor("#F2F8F4")])]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


def build_report(analysis: Dict[str, Any], field: Dict[str, Any] | None, owner_email: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="AgriGaurd Analysis Report")
    S = _styles()
    story = []
    flood = analysis.get("flood") or {}

    story.append(Paragraph("AgriGaurd — Field Intelligence Report", S["h1"]))
    story.append(Paragraph(
        f"AI-Powered Satellite Agricultural Flood Monitoring, Land Suitability and Crop Intelligence Platform<br/>"
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} • Owner: {owner_email}"
        f"{' • <b>DEMO DATA — NOT LIVE SATELLITE DATA</b>' if analysis.get('demo') else ''}", S["body"]))

    sev = flood.get("severity", "none")
    story.append(Paragraph("1. Flood result", S["h2"]))
    story.append(_table([
        ["Status", str(flood.get("status"))],
        ["Severity", f"{sev} (thresholds: {flood.get('severity_thresholds')})"],
        ["Total water", f"{flood.get('total_water_pct')} % ({flood.get('total_water_ha')} ha)"],
        ["New water", f"{flood.get('new_water_pct')} % ({flood.get('new_water_ha')} ha)"],
        ["Agricultural flood", f"{flood.get('agricultural_flood_pct')} % ({flood.get('agricultural_flood_ha')} ha)"],
        ["Analytical confidence", f"{(flood.get('confidence') or {}).get('score')} / 100 ({(flood.get('confidence') or {}).get('label')})"],
        ["Field area", f"{analysis.get('area_ha')} ha"],
    ], widths=[120 * mm, 66 * mm]))

    story.append(Paragraph("2. Location & boundary", S["h2"]))
    story.append(_table([
        ["Field", (field or {}).get("name") or analysis.get("boundary", {}).get("name") or "—"],
        ["State / District / Village", f"{(field or {}).get('state') or '—'} / {(field or {}).get('district') or '—'} / {(field or {}).get('village') or '—'}"],
        ["Bounding box", ", ".join(f"{v:.5f}" for v in (analysis.get("bbox") or []))],
        ["Centroid", f"lat {analysis.get('centroid', {}).get('lat')}, lng {analysis.get('centroid', {}).get('lng')}"],
        ["Area", f"{analysis.get('area_ha')} ha"],
    ], widths=[60 * mm, 126 * mm]))

    if flood.get("evidence"):
        story.append(Paragraph("3. Evidence — why AgriGaurd detected this result", S["h2"]))
        rows = [["✓/⚠", "Finding"]]
        for c in (flood["evidence"].get("positive") or []):
            rows.append(["✓", c.get("text")])
        for c in (flood["evidence"].get("warnings") or []):
            rows.append(["⚠", c.get("text")])
        story.append(_table(rows, widths=[10 * mm, 176 * mm]))

    story.append(Paragraph("4. Data sources & transparency", S["h2"]))
    rows = [["Dataset", "Source / observation"]]
    for k, v in (analysis.get("sources") or {}).items():
        rows.append([k, str(v)])
    story.append(_table(rows, widths=[50 * mm, 136 * mm]))

    story.append(Paragraph("5. Water verification", S["h2"]))
    wv = analysis.get("water_verification") or {}
    rl = (wv.get("rivers_lakes") or {})
    bu = (wv.get("builtup") or {})
    story.append(_table([
        ["Detected water", f"{wv.get('detected_water_pct')} %"],
        ["Rivers/lakes note", rl.get("note", "—")],
        ["Built-up note", bu.get("note", "—")],
        ["Water classification", str((analysis.get("water_classification") or {}).get("classification"))],
    ], widths=[60 * mm, 126 * mm]))

    lc = analysis.get("landcover") or {}
    story.append(Paragraph("6. Land cover composition", S["h2"]))
    if lc.get("composition"):
        rows = [["Class", "%"]] + [[k, str(v)] for k, v in lc["composition"].items()]
        story.append(_table(rows, widths=[90 * mm, 50 * mm]))
    else:
        story.append(Paragraph("DATA UNAVAILABLE", S["body"]))

    story.append(Paragraph("7. Soil", S["h2"]))
    soil = analysis.get("soil") or {}
    if soil:
        props = soil.get("properties") or {}
        rows = [["Property", "Value", "Unit"]] + [
            [p.get("label"), str(p.get("value")), p.get("unit")] for p in props.values()]
        story.append(_table(rows, widths=[70 * mm, 30 * mm, 30 * mm]))
        story.append(Paragraph(f"Source: {soil.get('source')} — resolution {soil.get('resolution')}", S["small"]))
    else:
        story.append(Paragraph(f"DATA UNAVAILABLE ({analysis.get('soil_status')})", S["body"]))

    story.append(Paragraph("8. Terrain", S["h2"]))
    terrain = analysis.get("terrain") or {}
    if terrain:
        story.append(_table([
            ["Elevation (min/mean/max)", f"{terrain.get('elevation_min_m')} / {terrain.get('elevation_mean_m')} / {terrain.get('elevation_max_m')} m"],
            ["Median slope", f"{terrain.get('slope_median_pct')} %"],
            ["Low-lying area", f"{terrain.get('low_lying_pct')} %"],
            ["Terrain risk", terrain.get("terrain_risk")],
            ["Source", f"{terrain.get('source')} ({terrain.get('resolution')})"],
        ]))
    else:
        story.append(Paragraph("DATA UNAVAILABLE", S["body"]))

    story.append(Paragraph("9. Weather", S["h2"]))
    weather = analysis.get("weather") or {}
    if weather:
        recent = weather.get("recent") or {}
        story.append(_table([
            ["7-day rainfall", f"{recent.get('last_7_days_mm')} mm"],
            ["30-day rainfall", f"{recent.get('total_mm')} mm"],
            ["Rainfall evidence", (weather.get("verdict") or {}).get("statement", "—")],
            ["Source", "Open-Meteo"],
        ]))
    else:
        story.append(Paragraph("DATA UNAVAILABLE", S["body"]))

    story.append(Paragraph("10. Vegetation (NDVI / NDMI)", S["h2"]))
    ndvi, ndmi = analysis.get("ndvi"), analysis.get("ndmi")
    if ndvi or ndmi:
        story.append(_table([
            ["NDVI mean", f"{(ndvi or {}).get('mean')}"],
            ["NDMI mean", f"{(ndmi or {}).get('mean')}"],
            ["Note", analysis.get("optical_note") or "—"],
        ]))
    else:
        story.append(Paragraph(analysis.get("optical_note") or "DATA UNAVAILABLE", S["body"]))

    story.append(Paragraph("11. Land suitability", S["h2"]))
    ls = analysis.get("land_suitability") or {}
    rows = [["Factor", "Score", "Basis"]]
    for k, v in (ls.get("factors") or {}).items():
        rows.append([k, str(v.get("score")), str(v.get("basis"))])
    rows.append(["OVERALL", f"{ls.get('score')} ({ls.get('label')})", "weighted"])
    story.append(_table(rows, widths=[40 * mm, 25 * mm, 121 * mm]))

    story.append(Paragraph("12. Crop recommendations", S["h2"]))
    for c in ((analysis.get("crops") or {}).get("recommendations") or [])[:5]:
        story.append(Paragraph(f"<b>{c.get('crop')}</b> — suitability {c.get('score')}/100", S["body"]))
        if c.get("why"):
            story.append(Paragraph("Supporting: " + "; ".join(c["why"][:3]), S["small"]))
        if c.get("risks"):
            story.append(Paragraph("Risk: " + "; ".join(c["risks"][:2]), S["small"]))

    story.append(Paragraph("13. Data quality", S["h2"]))
    dq = analysis.get("data_quality") or {}
    story.append(Paragraph(f"Score {dq.get('score')}/100 — {dq.get('label')}. "
                           f"Missing sources: {', '.join(dq.get('missing_sources') or ['none'])}.", S["body"]))

    story.append(Paragraph("14. Limitations", S["h2"]))
    for lim in analysis.get("limitations") or []:
        story.append(Paragraph(f"• {lim}", S["body"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("This report is a remote-sensing based estimate for decision support. "
                           "It is not a government-certified flood assessment. Field verification is recommended.",
                           S["small"]))

    doc.build(story)
    return buf.getvalue()
