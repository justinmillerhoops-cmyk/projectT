"""
Tests for ranking list HTML parsing.
Uses mocked HTML matching the real TFRRS div-based performance-list layout.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from villanova_tf.scraper.lists import _parse_event_sections, normalize_event, _parse_athlete_id


# ---------------------------------------------------------------------------
# HTML fixture helpers
# ---------------------------------------------------------------------------

def _row_html(
    rank: int = 1,
    athlete_id: str = "12345",
    name: str = "Last, First",
    year: str = "SR-4",
    team: str = "Villanova",
    mark: str = "10.50",
    meet: str = "Big East Championships",
    date: str = "Apr 26, 2026",
    wind: str | None = None,
) -> str:
    wind_div = f'<div class="col-narrow" data-label="Wind">{wind}</div>' if wind is not None else ""
    return f"""
    <div class="performance-list-row">
        <div class="col-place">{rank}</div>
        <div class="col-athlete">
            <a href="/athletes/{athlete_id}/PA_college_m_Villanova/First_Last.html">{name}</a>
        </div>
        <div class="col-narrow" data-label="Year">{year}</div>
        <div class="col-team">{team}</div>
        <div class="col-narrow" data-label="Time">{mark}</div>
        <div class="col-meet">{meet}</div>
        <div class="col-narrow" data-label="Meet Date">{date}</div>
        {wind_div}
    </div>"""


def _section_html(event_name: str, rows: list[str]) -> str:
    body = "\n".join(rows)
    return f"""
    <div class="custom-table-title"><h3>{event_name}</h3></div>
    <div class="performance-list">
        <div class="performance-list-body">
            {body}
        </div>
    </div>"""


def _page(sections: list[str]) -> str:
    return "<html><body>" + "".join(sections) + "</body></html>"


# ---------------------------------------------------------------------------
# normalize_event
# ---------------------------------------------------------------------------

class TestNormalizeEvent:
    def test_lowercase_canonical(self):
        assert normalize_event("100 Meters") == "100m"

    def test_already_normalized(self):
        assert normalize_event("100m") == "100m"

    def test_strips_women_suffix(self):
        assert normalize_event("100 Meters (Women)") == "100m"

    def test_strips_men_suffix(self):
        assert normalize_event("High Jump (Men)") == "high_jump"

    def test_comma_thousands(self):
        assert normalize_event("5,000 Meters") == "5000m"

    def test_steeplechase(self):
        assert normalize_event("3000 Meter Steeplechase") == "3000sc"

    def test_unknown_passthrough(self):
        result = normalize_event("4x400 Relay")
        assert result == "4x400 relay"

    def test_leading_trailing_whitespace(self):
        assert normalize_event("  200 Meters  ") == "200m"


# ---------------------------------------------------------------------------
# _parse_athlete_id
# ---------------------------------------------------------------------------

class TestParseAthleteId:
    def test_standard_href(self):
        assert _parse_athlete_id("/athletes/8232893/PA_college_m_Villanova/Marco_Langon.html") == "8232893"

    def test_none_href(self):
        assert _parse_athlete_id(None) is None

    def test_empty_href(self):
        assert _parse_athlete_id("") is None

    def test_no_match(self):
        assert _parse_athlete_id("/teams/some_team.html") is None


# ---------------------------------------------------------------------------
# _parse_event_sections
# ---------------------------------------------------------------------------

class TestParseEventSections:
    def test_basic_row_extraction(self):
        html = _page([_section_html("100 Meters", [_row_html(
            rank=1, athlete_id="99001", name="Smith, Alice",
            mark="11.20", wind="+1.2",
        )])])
        rows = _parse_event_sections(html)
        assert len(rows) == 1
        r = rows[0]
        assert r["rank"] == 1
        assert r["athlete_id"] == "99001"
        assert r["athlete_name"] == "Smith, Alice"
        assert r["mark"] == "11.20"
        assert r["event"] == "100m"
        assert r["wind"] == "+1.2"

    def test_women_gender_inference(self):
        html = _page([_section_html("100 Meters (Women)", [_row_html()])])
        rows = _parse_event_sections(html)
        assert rows[0]["gender"] == "F"

    def test_men_gender_inference(self):
        html = _page([_section_html("100 Meters (Men)", [_row_html()])])
        rows = _parse_event_sections(html)
        assert rows[0]["gender"] == "M"

    def test_no_gender_tag_defaults_to_men(self):
        html = _page([_section_html("100 Meters", [_row_html()])])
        rows = _parse_event_sections(html)
        assert rows[0]["gender"] == "M"

    def test_multiple_events(self):
        html = _page([
            _section_html("100 Meters (Women)", [_row_html(mark="11.20")]),
            _section_html("400 Meters (Women)", [_row_html(mark="52.30"), _row_html(rank=2, athlete_id="22222", mark="53.10")]),
        ])
        rows = _parse_event_sections(html)
        assert len(rows) == 3
        events = [r["event"] for r in rows]
        assert events.count("100m") == 1
        assert events.count("400m") == 2

    def test_no_wind_field_is_none(self):
        html = _page([_section_html("200 Meters", [_row_html(wind=None)])])
        rows = _parse_event_sections(html)
        assert rows[0]["wind"] is None

    def test_row_without_athlete_link_skipped(self):
        no_link_row = """
        <div class="performance-list-row">
            <div class="col-place">1</div>
            <div class="col-athlete">No link here</div>
            <div class="col-narrow" data-label="Time">10.50</div>
        </div>"""
        html = _page([_section_html("100 Meters", [no_link_row])])
        rows = _parse_event_sections(html)
        assert rows == []

    def test_malformed_rank_defaults_to_zero(self):
        bad_rank_row = _row_html(rank=0).replace(
            '<div class="col-place">0</div>',
            '<div class="col-place">—</div>',
        )
        html = _page([_section_html("100 Meters", [bad_rank_row])])
        rows = _parse_event_sections(html)
        assert rows[0]["rank"] == 0

    def test_nm_mark_stored_as_string(self):
        html = _page([_section_html("Shot Put", [_row_html(mark="NM")])])
        rows = _parse_event_sections(html)
        assert rows[0]["mark"] == "NM"

    def test_empty_html_returns_empty(self):
        rows = _parse_event_sections("<html><body></body></html>")
        assert rows == []

    def test_list_key_attached_by_caller(self):
        # _parse_event_sections itself doesn't set list_key; fetch_list does.
        html = _page([_section_html("100 Meters", [_row_html()])])
        rows = _parse_event_sections(html)
        assert "list_key" not in rows[0]

    def test_team_field_extracted(self):
        html = _page([_section_html("400 Meters", [_row_html(team="Georgetown")])])
        rows = _parse_event_sections(html)
        assert rows[0]["team"] == "Georgetown"

    def test_meet_and_date_extracted(self):
        html = _page([_section_html("800 Meters", [_row_html(
            meet="Penn Relays", date="Apr 24, 2026"
        )])])
        rows = _parse_event_sections(html)
        assert rows[0]["meet"] == "Penn Relays"
        assert rows[0]["meet_date"] == "Apr 24, 2026"

    def test_field_event_normalized(self):
        html = _page([_section_html("High Jump (Men)", [_row_html(mark="2.10m")])])
        rows = _parse_event_sections(html)
        assert rows[0]["event"] == "high_jump"

    def test_multiple_athletes_all_extracted(self):
        rows_html = [
            _row_html(rank=i + 1, athlete_id=str(10000 + i), mark="11.00")
            for i in range(5)
        ]
        html = _page([_section_html("100 Meters (Women)", rows_html)])
        rows = _parse_event_sections(html)
        assert len(rows) == 5
        ids = [r["athlete_id"] for r in rows]
        assert len(set(ids)) == 5
