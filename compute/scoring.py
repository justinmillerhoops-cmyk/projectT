from __future__ import annotations

import pandas as pd

from compute.marks import EVENT_CONFIG

POINTS = [10, 8, 6, 5, 4, 3, 2, 1]


def apply_entry_limits(ranked: pd.DataFrame) -> pd.DataFrame:
    kept = []
    for event, grp in ranked.groupby("event"):
        cfg = EVENT_CONFIG.get(event, {})
        type_ = cfg.get("type", "track")
        per_team = 1 if type_ == "relay" else 4
        for team, tgrp in grp.groupby("team"):
            asc = cfg.get("direction") == "lower_is_better"
            tgrp = tgrp.sort_values("mark_value", ascending=asc).head(per_team)
            kept.append(tgrp)
    if not kept:
        return ranked.iloc[0:0]
    return pd.concat(kept, ignore_index=True)


def projected_team_scoring(ranked: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    limited = apply_entry_limits(ranked)
    score_rows = []
    who_scores = []
    for event, grp in limited.groupby("event"):
        cfg = EVENT_CONFIG.get(event)
        if not cfg:
            continue
        asc = cfg["direction"] == "lower_is_better"
        r = grp.sort_values("mark_value", ascending=asc).head(8).copy()
        r["event_place"] = range(1, len(r) + 1)
        r["points"] = [POINTS[i] for i in range(len(r))]
        score_rows.append(r[["event", "team", "athlete_name", "event_place", "points", "mark_raw", "mark_value"]])
        who_scores.append(r[["team", "athlete_name", "event", "points"]])

    scored = pd.concat(score_rows, ignore_index=True) if score_rows else pd.DataFrame(columns=["event", "team", "athlete_name", "event_place", "points"])
    team_totals = scored.groupby("team", as_index=False)["points"].sum().sort_values("points", ascending=False)
    return team_totals, scored, pd.concat(who_scores, ignore_index=True) if who_scores else pd.DataFrame(columns=["team", "athlete_name", "event", "points"])
