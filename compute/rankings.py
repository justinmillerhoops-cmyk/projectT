from __future__ import annotations

import pandas as pd

from compute.marks import EVENT_CONFIG


def season_best(df: pd.DataFrame) -> pd.DataFrame:
    valid = df[df["mark_value"].notna()].copy()
    key = ["athlete_name", "team", "gender", "season", "event", "scope"]
    out = []
    for (ath, team, gender, season, event, scope), grp in valid.groupby(key, dropna=False):
        cfg = EVENT_CONFIG.get(event)
        if not cfg:
            continue
        idx = grp["mark_value"].idxmin() if cfg["direction"] == "lower_is_better" else grp["mark_value"].idxmax()
        out.append(valid.loc[idx])
    if not out:
        return pd.DataFrame(columns=df.columns)
    return pd.DataFrame(out).reset_index(drop=True)


def rank_by_event(sb: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for event, grp in sb.groupby("event"):
        cfg = EVENT_CONFIG.get(event)
        if not cfg:
            continue
        asc = cfg["direction"] == "lower_is_better"
        ranked = grp.sort_values("mark_value", ascending=asc).copy()
        ranked["rank"] = range(1, len(ranked) + 1)
        frames.append(ranked)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=list(sb.columns) + ["rank"])
