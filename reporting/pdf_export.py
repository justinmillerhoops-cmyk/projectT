from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def export_pdf_report(output_path: Path, team_scores: pd.DataFrame, rankings: pd.DataFrame, probability: pd.DataFrame, coverage: dict) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=letter)
    w, h = letter
    y = h - 40
    c.drawString(40, y, f"Villanova T&F Report - {datetime.utcnow().isoformat()} UTC")
    y -= 20
    c.drawString(40, y, f"Coverage: {coverage}")
    y -= 25

    def draw_df(title: str, df: pd.DataFrame, cols: list[str], max_rows: int = 15):
        nonlocal y
        c.drawString(40, y, title)
        y -= 14
        sample = df[cols].head(max_rows) if not df.empty else pd.DataFrame(columns=cols)
        for _, row in sample.iterrows():
            line = " | ".join(str(row[col]) for col in cols)
            c.drawString(40, y, line[:115])
            y -= 12
            if y < 60:
                c.showPage()
                y = h - 40

    draw_df("Projected Team Scores", team_scores, ["team", "points"])
    draw_df("Rankings Snapshot", rankings, ["event", "rank", "athlete_name", "team", "mark_raw"])
    draw_df("Probability Snapshot", probability, ["event", "athlete_name", "probability_percent", "bubble_delta"])

    c.save()
    return output_path
