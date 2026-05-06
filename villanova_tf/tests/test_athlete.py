"""
Tests for athlete detail page HTML parsing.
Uses mocked HTML matching the TFRRS athlete page structure.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from bs4 import BeautifulSoup
from villanova_tf.scraper.athlete import _parse_bests_table, _parse_meet_tables


# ---------------------------------------------------------------------------
# HTML fixture helpers
# ---------------------------------------------------------------------------

def _bests_table_html(rows: list[list[tuple[str, str]]], css_class: str = "indoor_bests") -> str:
    """
    Build a bests table HTML string.
    rows: list of rows, each row is a list of (event, mark) tuples.
    """
    row_html = ""
    for row in rows:
        cells = "".join(f"<td>{e}</td><td>{m}</td>" for e, m in row)
        row_html += f"<tr>{cells}</tr>"
    return f'<table class="table {css_class}"><tbody>{row_html}</tbody></table>'


def _meet_table_html(
    meet_name: str = "Big East Championships",
    meet_href: str = "/results/12345/meet.html",
    meet_date: str = "Apr 26, 2026",
    results: list[dict] | None = None,
) -> str:
    if results is None:
        results = [{"event": "100m", "mark": "10.50", "wind": None, "place": "1st (F)"}]
    rows_html = ""
    for r in results:
        wind_span = f'<span style="font-style:italic">({r["wind"]})</span>' if r.get("wind") else ""
        place_td = f'<td class="panel-heading-text">{r.get("place", "")}</td>'
        rows_html += f"""
        <tr>
            <td class="panel-heading-text">{r["event"]}</td>
            <td class="panel-heading-normal-text">
                <a href="/results/12345/67890/result.html">{r["mark"]}</a>
                {wind_span}
            </td>
            {place_td}
        </tr>"""
    return f"""
    <table class="table table-hover >">
        <thead>
            <tr>
                <th class="panel-heading-text" colspan="100%">
                    <a href="{meet_href}">{meet_name}</a>
                    <span>{meet_date}</span>
                </th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>"""


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# _parse_bests_table
# ---------------------------------------------------------------------------

class TestParseBestsTable:
    def test_basic_event_mark_pair(self):
        html = _bests_table_html([[("5000m", "13:28.43")]])
        table = _soup(html).find("table")
        bests = _parse_bests_table(table)
        assert len(bests) == 1
        assert bests[0]["event_raw"] == "5000m"
        assert bests[0]["mark"] == "13:28.43"
        assert bests[0]["wind"] is None

    def test_multiple_pairs_in_one_row(self):
        html = _bests_table_html([[("5000m", "13:28.43"), ("Mile", "4:01.23")]])
        table = _soup(html).find("table")
        bests = _parse_bests_table(table)
        assert len(bests) == 2
        events = [b["event_raw"] for b in bests]
        assert "5000m" in events
        assert "Mile" in events

    def test_wind_extracted_from_mark(self):
        html = _bests_table_html([[("100m", "10.48 (1.2)")]])
        table = _soup(html).find("table")
        bests = _parse_bests_table(table)
        assert bests[0]["wind"] == pytest.approx(1.2)
        assert bests[0]["mark"] == "10.48"

    def test_negative_wind(self):
        html = _bests_table_html([[("100m", "10.55 (-0.4)")]])
        table = _soup(html).find("table")
        bests = _parse_bests_table(table)
        assert bests[0]["wind"] == pytest.approx(-0.4)

    def test_no_wind_in_mark(self):
        html = _bests_table_html([[("Shot Put", "18.45m")]])
        table = _soup(html).find("table")
        bests = _parse_bests_table(table)
        assert bests[0]["wind"] is None
        assert bests[0]["mark"] == "18.45m"

    def test_multiple_rows(self):
        html = _bests_table_html([
            [("100m", "10.48"), ("200m", "20.95")],
            [("400m", "46.50")],
        ])
        table = _soup(html).find("table")
        bests = _parse_bests_table(table)
        assert len(bests) == 3

    def test_empty_table(self):
        html = '<table class="table indoor_bests"><tbody></tbody></table>'
        table = _soup(html).find("table")
        assert _parse_bests_table(table) == []

    def test_none_input(self):
        assert _parse_bests_table(None) == []

    def test_empty_event_cell_skipped(self):
        html = _bests_table_html([[("", "10.50"), ("100m", "10.48")]])
        table = _soup(html).find("table")
        bests = _parse_bests_table(table)
        # empty event + mark pair is skipped; valid pair kept
        assert len(bests) == 1
        assert bests[0]["event_raw"] == "100m"


# ---------------------------------------------------------------------------
# _parse_meet_tables
# ---------------------------------------------------------------------------

class TestParseMeetTables:
    def test_basic_result(self):
        html = _meet_table_html(results=[{"event": "100m", "mark": "10.50", "wind": None, "place": "1st (F)"}])
        results = _parse_meet_tables(_soup(html))
        assert len(results) == 1
        r = results[0]
        assert r["meet"] == "Big East Championships"
        assert r["event_raw"] == "100m"
        assert r["mark"] == "10.50"
        assert r["place"] == "1"
        assert r["round"] == "F"

    def test_meet_name_and_date_extracted(self):
        html = _meet_table_html(meet_name="Penn Relays", meet_date="Apr 24, 2026")
        results = _parse_meet_tables(_soup(html))
        assert results[0]["meet"] == "Penn Relays"
        assert results[0]["meet_date"] == "2026-04-24"

    def test_invalid_date_stored_raw(self):
        html = _meet_table_html(meet_date="Unknown Date")
        results = _parse_meet_tables(_soup(html))
        assert results[0]["meet_date"] == "Unknown Date"

    def test_wind_in_span_extracted(self):
        html = _meet_table_html(results=[{"event": "200m", "mark": "20.95", "wind": "1.5", "place": "2nd (F)"}])
        results = _parse_meet_tables(_soup(html))
        assert results[0]["wind"] == pytest.approx(1.5)

    def test_no_wind_is_none(self):
        html = _meet_table_html(results=[{"event": "Shot Put", "mark": "18.45m", "wind": None, "place": "1st (F)"}])
        results = _parse_meet_tables(_soup(html))
        assert results[0]["wind"] is None

    def test_multiple_results_per_meet(self):
        html = _meet_table_html(results=[
            {"event": "100m", "mark": "10.50", "wind": None, "place": "3rd (H)"},
            {"event": "100m", "mark": "10.48", "wind": "1.2", "place": "1st (F)"},
        ])
        results = _parse_meet_tables(_soup(html))
        assert len(results) == 2

    def test_table_without_header_skipped(self):
        html = """
        <table class="table table-hover >">
            <thead><tr><th>No panel-heading-text class here</th></tr></thead>
            <tbody><tr><td>100m</td><td>10.50</td></tr></tbody>
        </table>"""
        results = _parse_meet_tables(_soup(html))
        assert results == []

    def test_multiple_meets(self):
        html = (
            _meet_table_html(meet_name="Meet A", results=[{"event": "100m", "mark": "10.55", "wind": None, "place": ""}])
            + _meet_table_html(meet_name="Meet B", results=[{"event": "200m", "mark": "21.10", "wind": None, "place": ""}])
        )
        results = _parse_meet_tables(_soup(html))
        assert len(results) == 2
        meets = [r["meet"] for r in results]
        assert "Meet A" in meets
        assert "Meet B" in meets

    def test_row_with_fewer_than_two_cells_skipped(self):
        html = """
        <table class="table table-hover >">
            <thead>
                <tr><th class="panel-heading-text"><a href="/results/1/meet.html">Test Meet</a><span>Jan 1, 2026</span></th></tr>
            </thead>
            <tbody>
                <tr><td>only one cell</td></tr>
                <tr><td>100m</td><td>10.50</td></tr>
            </tbody>
        </table>"""
        results = _parse_meet_tables(_soup(html))
        assert len(results) == 1
        assert results[0]["event_raw"] == "100m"

    def test_no_tables_returns_empty(self):
        results = _parse_meet_tables(_soup("<html><body><p>nothing</p></body></html>"))
        assert results == []
