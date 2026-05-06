"""Tests for composite ranking logic."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import pytest
from villanova_tf.processing.composite import (
    build_dataframe,
    composite_view,
    sort_by_conference,
    sort_by_national,
)


def _make_roster(ids_names_genders):
    return [
        {"athlete_id": str(aid), "name": name, "year": "Jr", "gender": gender, "tfrrs_href": ""}
        for aid, name, gender in ids_names_genders
    ]


def _make_list_data(rows):
    """rows is a list of (athlete_id, event, mark, gender, conf_rank, nat_rank)."""
    conf_rows, nat_rows = [], []
    for aid, event, mark, gender, conf_rank, nat_rank in rows:
        base = {
            "athlete_id": str(aid),
            "athlete_name": "Test",
            "event": event,
            "mark": mark,
            "gender": gender,
            "rank": conf_rank,
            "wind": None,
            "year": "Jr",
            "team": "Villanova",
            "meet": "Test Meet",
            "meet_date": "2026-04-01",
        }
        conf_rows.append({**base, "rank": conf_rank})
        nat_rows.append({**base, "rank": nat_rank})
    return {
        "big_east_outdoor": conf_rows,
        "ncaa_east_outdoor": [],
        "ncaa_national_outdoor": nat_rows,
    }


class TestBuildDataframe:
    def test_basic_build(self):
        roster = _make_roster([(1, "Alice Smith", "F"), (2, "Bob Jones", "M")])
        list_data = _make_list_data([
            (1, "100m", "11.50", "F", 3, 45),
            (2, "200m", "21.00", "M", 1, 10),
        ])
        df = build_dataframe(roster, list_data, "outdoor", {"outdoor": {}})
        assert len(df) >= 2
        assert "wa_points" in df.columns
        assert "conf_rank" in df.columns

    def test_athletes_not_on_list_included(self):
        roster = _make_roster([(1, "Alice Smith", "F"), (99, "Unknown Athlete", "M")])
        list_data = _make_list_data([(1, "100m", "11.50", "F", 3, 45)])
        df = build_dataframe(roster, list_data, "outdoor", {"outdoor": {}})
        # Both athletes should appear (unknown athlete gets null event row)
        assert df["athlete_id"].str.contains("99").any()

    def test_wa_points_populated(self):
        roster = _make_roster([(1, "Alice Smith", "F")])
        list_data = _make_list_data([(1, "100m", "11.50", "F", 3, 45)])
        df = build_dataframe(roster, list_data, "outdoor", {"outdoor": {}})
        pts_row = df[df["event"] == "100m"]
        assert not pts_row.empty
        assert pts_row.iloc[0]["wa_points"] > 0


class TestCompositeView:
    def _make_df(self):
        data = {
            "athlete_id": ["1", "1", "2"],
            "name": ["Alice", "Alice", "Bob"],
            "year": ["Jr", "Jr", "Sr"],
            "gender": ["F", "F", "M"],
            "event": ["100m", "200m", "400m"],
            "season": ["outdoor"] * 3,
            "mark": ["11.50", "23.50", "46.00"],
            "mark_display": ["11.50", "23.50", "46.00"],
            "wa_points": [900, 850, 950],
            "wind": [None, None, None],
            "wind_legal": [None, None, None],
            "conf_rank": [3, 5, 1],
            "regional_rank": [None, None, None],
            "national_rank": [50, 80, 20],
            "bubble_gap_mark": [None, None, None],
            "bubble_gap_points": [None, None, None],
            "last_updated": [None] * 3,
        }
        return pd.DataFrame(data)

    def test_one_row_per_athlete(self):
        df = self._make_df()
        comp = composite_view(df)
        assert len(comp) == 2  # Alice and Bob

    def test_best_wa_points_selected(self):
        df = self._make_df()
        comp = composite_view(df)
        alice_row = comp[comp["name"] == "Alice"].iloc[0]
        # Alice's best is 100m (900 pts) over 200m (850 pts)
        assert alice_row["wa_points"] == 900

    def test_composite_rank_ordering(self):
        df = self._make_df()
        comp = composite_view(df)
        ranks = comp.set_index("name")["composite_rank"].to_dict()
        # Bob (950) should rank 1, Alice (900) rank 2
        assert ranks["Bob"] < ranks["Alice"]

    def test_events_column_present(self):
        df = self._make_df()
        comp = composite_view(df)
        assert "events" in comp.columns


class TestSortFunctions:
    def _make_comp(self):
        data = {
            "athlete_id": ["1", "2", "3"],
            "name": ["A", "B", "C"],
            "composite_rank": [3, 1, 2],
            "conf_rank": [2.0, 1.0, 3.0],
            "regional_rank": [1.0, None, 2.0],
            "national_rank": [10.0, 5.0, 20.0],
            "wa_points": [900, 950, 800],
        }
        return pd.DataFrame(data)

    def test_sort_by_conference(self):
        comp = self._make_comp()
        sorted_df = sort_by_conference(comp)
        assert sorted_df.iloc[0]["conf_rank"] == 1.0

    def test_sort_by_national(self):
        comp = self._make_comp()
        sorted_df = sort_by_national(comp)
        assert sorted_df.iloc[0]["national_rank"] == 5.0
