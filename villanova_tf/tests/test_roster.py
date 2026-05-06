"""
Tests for roster HTML parsing.
Uses mocked HTML matching the TFRRS team page tablesaw table structure.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from villanova_tf.scraper.roster import _parse_roster_html, _parse_year


# ---------------------------------------------------------------------------
# HTML fixture helpers
# ---------------------------------------------------------------------------

def _athlete_row(athlete_id: str, name: str = "Last, First", year: str = "SR-4") -> str:
    return f"""
    <tr>
        <td><a href="/athletes/{athlete_id}/PA_college_m_Villanova/First_Last.html">{name}</a></td>
        <td>{year}</td>
    </tr>"""


def _roster_page(athletes: list[str], include_event_table: bool = True) -> str:
    event_table = """
    <table class="tablesaw table-striped">
        <thead><tr><th>Event</th><th>Mark</th></tr></thead>
        <tbody><tr><td>100m</td><td>10.45</td></tr></tbody>
    </table>""" if include_event_table else ""

    roster_rows = "\n".join(athletes)
    return f"""
    <html><body>
    {event_table}
    <table class="tablesaw table-striped table-hover">
        <thead><tr><th>Name</th><th>Year</th></tr></thead>
        <tbody>{roster_rows}</tbody>
    </table>
    </body></html>"""


# ---------------------------------------------------------------------------
# _parse_year
# ---------------------------------------------------------------------------

class TestParseYear:
    def test_sr(self):
        assert _parse_year("SR-4") == "Sr"

    def test_jr(self):
        assert _parse_year("JR-3") == "Jr"

    def test_so(self):
        assert _parse_year("SO-2") == "So"

    def test_fr(self):
        assert _parse_year("FR-1") == "Fr"

    def test_lowercase_prefix(self):
        assert _parse_year("sr-4") == "Sr"

    def test_unknown_passthrough(self):
        # Returns original string unchanged when prefix not in mapping
        assert _parse_year("GR-5") == "GR-5"

    def test_no_dash(self):
        assert _parse_year("SR") == "Sr"


# ---------------------------------------------------------------------------
# _parse_roster_html
# ---------------------------------------------------------------------------

class TestParseRosterHtml:
    def test_basic_athlete_extracted(self):
        html = _roster_page([_athlete_row("8232893", "Langon, Marco", "JR-3")])
        athletes = _parse_roster_html(html, "M")
        assert len(athletes) == 1
        a = athletes[0]
        assert a["athlete_id"] == "8232893"
        assert a["name"] == "Marco Langon"
        assert a["year"] == "Jr"
        assert a["gender"] == "M"

    def test_name_last_first_inverted(self):
        html = _roster_page([_athlete_row("11111", "Smith, Alice")])
        athletes = _parse_roster_html(html, "F")
        assert athletes[0]["name"] == "Alice Smith"

    def test_name_raw_preserved(self):
        html = _roster_page([_athlete_row("11111", "O'Brien, Patrick")])
        athletes = _parse_roster_html(html, "M")
        assert athletes[0]["name_raw"] == "O'Brien, Patrick"

    def test_single_name_no_comma(self):
        html = _roster_page([_athlete_row("11111", "Mononym")])
        athletes = _parse_roster_html(html, "M")
        assert athletes[0]["name"] == "Mononym"

    def test_gender_stored_from_parameter(self):
        html = _roster_page([_athlete_row("22222", "Jones, Mary")])
        athletes = _parse_roster_html(html, "F")
        assert athletes[0]["gender"] == "F"

    def test_href_stored(self):
        html = _roster_page([_athlete_row("33333", "Doe, Jane")])
        athletes = _parse_roster_html(html, "F")
        assert "/athletes/33333/" in athletes[0]["tfrrs_href"]

    def test_name_year_table_preferred_over_event_table(self):
        # Event table has no athlete IDs → should use the NAME/YEAR table
        html = _roster_page([
            _athlete_row("44444", "Carter, James", "SR-4"),
            _athlete_row("55555", "Lee, Sarah", "FR-1"),
        ])
        athletes = _parse_roster_html(html, "M")
        # Should only include athletes from the NAME/YEAR table, not the event table row
        assert len(athletes) == 2

    def test_deduplication_same_id(self):
        html = _roster_page([
            _athlete_row("66666", "King, Chris", "JR-3"),
            _athlete_row("66666", "King, Chris", "JR-3"),  # duplicate
        ])
        athletes = _parse_roster_html(html, "M")
        assert len(athletes) == 1

    def test_no_tablesaw_table_returns_empty(self):
        html = "<html><body><p>No tables here</p></body></html>"
        athletes = _parse_roster_html(html, "M")
        assert athletes == []

    def test_row_without_athlete_link_skipped(self):
        html = _roster_page([
            "<tr><td>No link</td><td>SR-4</td></tr>",
            _athlete_row("77777", "Valid, Athlete"),
        ])
        athletes = _parse_roster_html(html, "M")
        assert len(athletes) == 1
        assert athletes[0]["athlete_id"] == "77777"

    def test_multiple_athletes_all_returned(self):
        rows = [_athlete_row(str(10000 + i), f"Athlete{i}, First") for i in range(10)]
        html = _roster_page(rows)
        athletes = _parse_roster_html(html, "M")
        assert len(athletes) == 10
