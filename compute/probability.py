from __future__ import annotations

import statistics

import pandas as pd

from compute.marks import EVENT_CONFIG


def event_cutlines(confmeet_df: pd.DataFrame, years: int = 5) -> pd.DataFrame:
    if confmeet_df.empty:
        return pd.DataFrame(columns=["season", "gender", "year", "event", "cutline"])
    out = []
    for (season, gender, year, event), grp in confmeet_df.groupby(["season", "gender", "year", "event"]):
        cfg = EVENT_CONFIG.get(event)
        if not cfg:
            continue
        g = grp[grp["mark_value"].notna()].copy()
        if g.empty:
            continue
        asc = cfg["direction"] == "lower_is_better"
        g = g.sort_values("mark_value", ascending=asc)
        if len(g) < 8:
            continue
        out.append({"season": season, "gender": gender, "year": int(year), "event": event, "cutline": float(g.iloc[7]["mark_value"])})
    cut = pd.DataFrame(out)
    if cut.empty:
        return cut
    return cut.sort_values("year", ascending=False).groupby(["season", "gender", "event"]).head(years)


def score_probability(current_sb: pd.DataFrame, cutlines: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, perf in current_sb.iterrows():
        c = cutlines[
            (cutlines["season"] == perf["season"])
            & (cutlines["gender"] == perf["gender"])
            & (cutlines["event"] == perf["event"])
        ]
        if c.empty or pd.isna(perf["mark_value"]):
            continue
        cfg = EVENT_CONFIG.get(perf["event"])
        if not cfg:
            continue
        comp = (c["cutline"] >= perf["mark_value"]) if cfg["direction"] == "lower_is_better" else (c["cutline"] <= perf["mark_value"])
        prob = float(comp.sum()) / float(len(c)) * 100.0
        band = "High" if prob >= 70 else ("Medium" if prob >= 40 else "Low")
        med = statistics.median(c["cutline"].tolist())
        bubble_delta = perf["mark_value"] - med
        rows.append(
            {
                "athlete_name": perf["athlete_name"],
                "team": perf["team"],
                "gender": perf["gender"],
                "season": perf["season"],
                "event": perf["event"],
                "mark_raw": perf["mark_raw"],
                "mark_value": perf["mark_value"],
                "probability_percent": round(prob, 1),
                "band": band,
                "bubble_delta": round(bubble_delta, 3),
                "years_used": len(c),
            }
        )
    return pd.DataFrame(rows)
