import pandas as pd

from compute.probability import event_cutlines
from compute.scoring import projected_team_scoring


def test_cutline_extraction():
    rows = []
    for i in range(10):
        rows.append(
            {
                "season": "indoor",
                "gender": "M",
                "year": 2025,
                "event": "800m",
                "mark_value": 110.0 + i,
            }
        )
    df = pd.DataFrame(rows)
    cut = event_cutlines(df)
    assert len(cut) == 1
    assert cut.iloc[0]["cutline"] == 117.0


def test_entry_limits_scoring_logic():
    rows = []
    for i in range(7):
        rows.append({"event": "800m", "team": "A", "athlete_name": f"A{i}", "mark_value": 110 + i, "mark_raw": str(110 + i)})
    for i in range(7):
        rows.append({"event": "800m", "team": "B", "athlete_name": f"B{i}", "mark_value": 111 + i, "mark_raw": str(111 + i)})
    ranked = pd.DataFrame(rows)
    totals, event_scores, _ = projected_team_scoring(ranked)
    assert event_scores[event_scores["team"] == "A"].shape[0] <= 4
    assert event_scores.shape[0] <= 8
    assert totals["points"].sum() == 39
