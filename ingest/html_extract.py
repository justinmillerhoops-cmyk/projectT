from __future__ import annotations

from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup


def extract_tables_from_html(path: Path) -> list[pd.DataFrame]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tables = pd.read_html(html)
        return [t for t in tables if not t.empty]
    except ValueError:
        return []


def extract_event_blocks(path: Path) -> list[dict]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    blocks: list[dict] = []
    for header in soup.find_all(["h1", "h2", "h3", "h4"]):
        event = header.get_text(strip=True)
        table = header.find_next("table")
        if not table:
            continue
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if rows:
            blocks.append({"event": event, "rows": rows})
    return blocks
