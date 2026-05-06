"""Tests for the athlete name/ID matching logic."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from villanova_tf.processing.matcher import match_roster_to_list, _normalize_name


class TestNormalizeName:
    def test_strips_punctuation(self):
        assert _normalize_name("O'Brien") == "o brien"

    def test_lowercases(self):
        assert _normalize_name("John DOE") == "john doe"

    def test_collapses_spaces(self):
        assert _normalize_name("  John   Doe  ") == "john doe"


class TestMatchRosterToList:
    def _make_roster_athlete(self, aid, name, gender="M"):
        return {"athlete_id": str(aid), "name": name, "gender": gender, "year": "Jr", "tfrrs_href": ""}

    def _make_list_row(self, aid, name, event="100m", gender="M"):
        return {"athlete_id": str(aid), "athlete_name": name, "event": event,
                "gender": gender, "mark": "10.50", "rank": 5}

    def test_exact_id_match(self):
        roster = [self._make_roster_athlete(123, "John Doe")]
        rows = [self._make_list_row(123, "Doe, John")]
        matched, unmatched = match_roster_to_list(roster, rows)
        assert len(matched) == 1
        assert matched[0]["match_method"] == "id"
        assert len(unmatched) == 0

    def test_fuzzy_name_match(self):
        # No athlete ID in list row
        roster = [self._make_roster_athlete(99, "Marcus Johnson")]
        rows = [{"athlete_id": None, "athlete_name": "Johnson, Marcus",
                 "event": "400m", "gender": "M", "mark": "46.00", "rank": 10}]
        matched, unmatched = match_roster_to_list(roster, rows, threshold=80)
        assert len(matched) >= 1
        assert matched[0]["match_method"] == "fuzzy"

    def test_unmatched_below_threshold(self):
        roster = [self._make_roster_athlete(1, "Completely Different Person")]
        rows = [self._make_list_row(999, "John Smith")]
        matched, unmatched = match_roster_to_list(roster, rows, threshold=85)
        assert len(unmatched) >= 1

    def test_gender_filter(self):
        roster = [self._make_roster_athlete(1, "Alex Kim", "M")]
        # Same ID but women's list row
        rows = [self._make_list_row(1, "Kim, Alex", gender="F")]
        matched, unmatched = match_roster_to_list(roster, rows)
        # Should not match across genders
        assert len(matched) == 0

    def test_no_list_rows(self):
        roster = [self._make_roster_athlete(1, "Solo Athlete")]
        matched, unmatched = match_roster_to_list(roster, [])
        assert len(unmatched) == 1

    def test_empty_roster(self):
        rows = [self._make_list_row(1, "Some Athlete")]
        matched, unmatched = match_roster_to_list([], rows)
        assert matched == []
        assert unmatched == []
