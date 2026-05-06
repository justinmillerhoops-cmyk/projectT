"""
PDF export — generates a print-ready roster PDF from the composite view.

Layout:
  - Cover header: Villanova Track & Field, season, date
  - Composite ranked list split by gender
  - One section per event group (sprints, mid-d, etc.) with by-event rankings
  - Nationals bubble reference table in footer
"""
from datetime import date
from io import BytesIO
from typing import Optional

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_NOVA_NAVY = colors.HexColor("#003087")   # Villanova Navy
_NOVA_BABY_BLUE = colors.HexColor("#6CACE4")  # Villanova Baby Blue
_LIGHT_GRAY = colors.HexColor("#F5F5F5")

_EVENT_GROUPS = {
    "Sprints": ["60m", "100m", "200m", "400m"],
    "Mid-Distance": ["800m", "1500m", "mile"],
    "Distance": ["3000m", "5000m", "10000m", "3000sc"],
    "Hurdles": ["60h", "100h", "110h", "400h"],
    "Jumps": ["high_jump", "pole_vault", "long_jump", "triple_jump"],
    "Throws": ["shot_put", "weight_throw", "discus", "hammer", "javelin"],
    "Combined": ["heptathlon", "pentathlon", "decathlon"],
}


def _styles():
    ss = getSampleStyleSheet()
    title = ParagraphStyle(
        "Title",
        parent=ss["Title"],
        textColor=_NOVA_NAVY,
        fontSize=18,
        spaceAfter=4,
    )
    subtitle = ParagraphStyle(
        "Subtitle",
        parent=ss["Normal"],
        fontSize=10,
        textColor=colors.gray,
        spaceAfter=12,
    )
    section = ParagraphStyle(
        "Section",
        parent=ss["Heading2"],
        textColor=_NOVA_NAVY,
        fontSize=13,
        spaceBefore=16,
        spaceAfter=6,
    )
    return title, subtitle, section


def _header_table_style():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _NOVA_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_GRAY]),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),  # Name column left-aligned
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])


def _fmt_bubble_gap(val) -> str:
    """Format bubble_gap_points as +53 / -12 / —."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        v = int(val)
    except (TypeError, ValueError):
        return "—"
    return f"+{v}" if v > 0 else str(v)


def _composite_table_data(comp_df: pd.DataFrame, season: str) -> list[list]:
    show_regional = season == "outdoor"
    headers = [
        "Rank", "Name", "Year", "Event(s)", "WA Pts", "Prev SB",
        "Bubble Δ", "Conf",
        "Reg" if show_regional else None, "Natl",
    ]
    headers = [h for h in headers if h]

    rows = [headers]
    for i, (_, row) in enumerate(comp_df.iterrows(), start=1):
        r = [
            str(i),
            row.get("name", ""),
            row.get("year", ""),
            row.get("events", row.get("event", "")),
            str(row.get("wa_points", "")),
            row.get("prev_mark") or "—",
            _fmt_bubble_gap(row.get("bubble_gap_points")),
            str(int(row["conf_rank"])) if pd.notna(row.get("conf_rank")) else "—",
        ]
        if show_regional:
            r.append(str(int(row["regional_rank"])) if pd.notna(row.get("regional_rank")) else "—")
        r.append(str(int(row["national_rank"])) if pd.notna(row.get("national_rank")) else "—")
        rows.append(r)
    return rows


def _event_section_data(df: pd.DataFrame, events: list[str], season: str) -> Optional[list[list]]:
    subset = df[df["event"].isin(events)].copy()
    if subset.empty:
        return None

    subset = subset.sort_values("wa_points", ascending=False)
    show_regional = season == "outdoor"
    headers = ["Rank", "Name", "Year", "Event", "Mark", "Prev SB", "WA Pts", "Conf", "Natl"]
    if show_regional:
        headers.insert(-1, "Reg")

    rows = [headers]
    for i, (_, row) in enumerate(subset.iterrows(), start=1):
        r = [
            str(i),
            row.get("name", ""),
            row.get("year", ""),
            row.get("event", ""),
            row.get("mark_display") or row.get("mark", ""),
            row.get("prev_mark") or "—",
            str(row.get("wa_points", "")),
            str(int(row["conf_rank"])) if pd.notna(row.get("conf_rank")) else "—",
        ]
        if show_regional:
            r.append(str(int(row["regional_rank"])) if pd.notna(row.get("regional_rank")) else "—")
        r.append(str(int(row["national_rank"])) if pd.notna(row.get("national_rank")) else "—")
        rows.append(r)
    return rows


def _bubble_footer_data(bubble_ref: dict, season: str) -> Optional[list[list]]:
    season_data = bubble_ref.get(season, {})
    if not season_data:
        return None

    rows = [["Event", "Bubble Mark", "Unit"]]
    for event, info in sorted(season_data.items()):
        rows.append([
            event,
            str(info.get("bubble_mark", "")),
            info.get("unit", ""),
        ])
    return rows


def _add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.gray)
    canvas.drawRightString(
        doc.pagesize[0] - 0.5 * inch,
        0.4 * inch,
        f"Page {doc.page}"
    )
    canvas.restoreState()


def generate_pdf(
    df: pd.DataFrame,
    comp_df: pd.DataFrame,
    season: str,
    bubble_ref: dict,
    school_name: str = "Villanova Track & Field",
    gender_filter: str = "Both",
) -> bytes:
    """
    Generate a PDF from the current composite and event views.
    Returns raw bytes suitable for st.download_button.

    Parameters
    ----------
    gender_filter : "Both" | "Men" | "Women"
        When "Men" or "Women", only that gender's data is included.
        When "Both", Men's sections appear first, then Women's.
    """
    from ..processing.composite import composite_view

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    title_style, subtitle_style, section_style = _styles()
    story = []

    # Cover header
    story.append(Paragraph(school_name, title_style))
    story.append(Paragraph(
        f"{season.capitalize()} Season  ·  Generated {date.today().strftime('%B %d, %Y')}",
        subtitle_style,
    ))
    story.append(HRFlowable(width="100%", color=_NOVA_NAVY, thickness=1.5, spaceAfter=12))

    # Determine which genders to render
    if gender_filter == "Men":
        gender_sections = [("M", "Men's")]
    elif gender_filter == "Women":
        gender_sections = [("F", "Women's")]
    else:
        gender_sections = [("M", "Men's"), ("F", "Women's")]

    # Composite column widths (Rank, Name, Yr, Event(s), WA Pts, Prev SB, Bubble Δ, [Reg,] Conf, Natl)
    if season == "outdoor":
        comp_col_widths = [0.38 * inch, 1.3 * inch, 0.45 * inch, 1.2 * inch,
                           0.55 * inch, 0.55 * inch, 0.55 * inch,
                           0.45 * inch, 0.45 * inch, 0.45 * inch]
    else:
        comp_col_widths = [0.38 * inch, 1.3 * inch, 0.45 * inch, 1.2 * inch,
                           0.55 * inch, 0.55 * inch, 0.55 * inch,
                           0.45 * inch, 0.45 * inch]

    for g_code, g_label in gender_sections:
        # --- Composite section ---
        g_comp = comp_df[comp_df["gender"] == g_code] if "gender" in comp_df.columns else comp_df
        g_df = df[df["gender"] == g_code] if "gender" in df.columns else df

        story.append(Paragraph(f"{g_label} Composite Ranking", section_style))
        comp_data = _composite_table_data(g_comp, season)
        if comp_data and len(comp_data) > 1:
            t = Table(comp_data, colWidths=comp_col_widths[:len(comp_data[0])])
            t.setStyle(_header_table_style())
            story.append(t)
        else:
            story.append(Paragraph(f"No {g_label.lower()} data available.", subtitle_style))

        # --- Per-event group sections ---
        for group_name, event_keys in _EVENT_GROUPS.items():
            section_data = _event_section_data(g_df, event_keys, season)
            if not section_data:
                continue
            story.append(PageBreak())
            story.append(Paragraph(f"{g_label} {group_name}", section_style))
            # Col widths: Rank, Name, Yr, Event, Mark, Prev SB, WA Pts, [Reg,] Conf, Natl
            if season == "outdoor":
                ev_col_widths = [0.35 * inch, 1.3 * inch, 0.45 * inch, 0.75 * inch,
                                 0.75 * inch, 0.55 * inch, 0.55 * inch,
                                 0.45 * inch, 0.45 * inch, 0.45 * inch]
            else:
                ev_col_widths = [0.35 * inch, 1.3 * inch, 0.45 * inch, 0.75 * inch,
                                 0.75 * inch, 0.55 * inch, 0.55 * inch,
                                 0.45 * inch, 0.45 * inch]
            t = Table(section_data, colWidths=ev_col_widths[:len(section_data[0])])
            t.setStyle(_header_table_style())
            story.append(t)

    # Bubble reference footer table
    bubble_data = _bubble_footer_data(bubble_ref, season)
    if bubble_data:
        story.append(PageBreak())
        story.append(Paragraph("Nationals Bubble Reference", section_style))
        story.append(Paragraph(
            "Historical average last-place qualifying mark (past 5 NCAA championship seasons).",
            subtitle_style,
        ))
        t = Table(bubble_data, colWidths=[2 * inch, 1.5 * inch, 1 * inch])
        t.setStyle(_header_table_style())
        story.append(t)

    doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
    return buf.getvalue()
