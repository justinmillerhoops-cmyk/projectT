"""
Build the composite athlete DataFrame from roster + ranking list data.

Each row in the output DataFrame represents one athlete × one event.
The composite view collapses to one row per athlete (best event).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from .wa_points import mark_display, score
from .bubble import compute_bubble_gaps

logger = logging.getLogger(__name__)

# Column order for the full DataFrame
COLUMNS = [
    "athlete_id",
    "name",
    "year",
    "gender",
    "event",
    "season",
    "mark",
    "mark_display",
    "wa_points",
    "prev_mark",       # previous season's best mark string (same event), or None
    "wind",
    "wind_legal",
    "conf_rank",
    "regional_rank",
    "national_rank",
    "bubble_gap_mark",
    "bubble_gap_points",
    "last_updated",
]


def _wind_legal(wind: Optional[float]) -> Optional[bool]:
    if wind is None:
        return None
    return wind <= 2.0


def _best_mark_per_event(rows: list[dict], gender: str) -> dict[str, dict]:
    """
    From a flat list of list rows for one athlete, pick the season-best mark
    per event based on WA points (highest = best).
    Returns {event: {mark, wa_points, wind, ...}}
    """
    best: dict[str, dict] = {}
    for row in rows:
        # Skip rows from wrong-gender event sections (defensive: prevents
        # a men's section row from corrupting a women's athlete's marks if
        # the same ID ever appears in both sections).
        row_gender = row.get("gender")
        if row_gender and row_gender != gender:
            continue
        event = row.get("event", "")
        mark_str = row.get("mark", "")
        if not event or not mark_str:
            continue
        pts = score(event, gender, mark_str)
        if pts is None:
            continue
        existing = best.get(event)
        if existing is None or pts > existing["wa_points"]:
            wind_raw = row.get("wind")
            try:
                wind = float(wind_raw) if wind_raw else None
            except (ValueError, TypeError):
                wind = None
            best[event] = {
                "mark": mark_str,
                "wa_points": pts,
                "wind": wind,
            }
    return best


def build_dataframe(
    roster: list[dict],
    list_data: dict[str, list[dict]],  # list_key → rows
    season: str,
    bubble_ref: dict,
    prev_marks: dict = None,
) -> pd.DataFrame:
    """
    Build the full athlete × event DataFrame.

    Parameters
    ----------
    roster     : list of athlete dicts from roster scraper
    list_data  : dict of list_key → ranking rows (from fetch_all_lists)
    season     : "indoor" or "outdoor"
    bubble_ref : loaded bubble_reference.json dict
    """
    season_bubble = bubble_ref.get(season, {})

    # Key ranking lists by purpose
    if season == "outdoor":
        conf_key = "big_east_outdoor"
        regional_key = "ncaa_east_outdoor"
        national_key = "ncaa_national_outdoor"
    else:
        conf_key = "big_east_indoor"
        regional_key = None
        national_key = "ncaa_national_indoor"

    conf_rows = list_data.get(conf_key, [])
    regional_rows = list_data.get(regional_key, []) if regional_key else []
    national_rows = list_data.get(national_key, [])

    roster_ids = {str(a["athlete_id"]) for a in roster}

    # Build per-list lookups: athlete_id → {event → rank}
    # Filtered to roster athletes only — prevents accidental rank inheritance
    # from a non-Villanova athlete who shares an ID (shouldn't happen in TFRRS,
    # but makes intent explicit and adds a safety layer).
    def _build_rank_lookup(rows: list[dict]) -> dict[str, dict[str, int]]:
        lookup: dict[str, dict[str, int]] = {}
        for row in rows:
            aid = row.get("athlete_id")
            if not aid or aid not in roster_ids:
                continue
            event = row.get("event", "")
            rank = row.get("rank", 0)
            if aid not in lookup:
                lookup[aid] = {}
            # Keep best (lowest) rank per event
            if event not in lookup[aid] or rank < lookup[aid][event]:
                lookup[aid][event] = rank
        return lookup

    conf_ranks = _build_rank_lookup(conf_rows)
    regional_ranks = _build_rank_lookup(regional_rows)
    national_ranks = _build_rank_lookup(national_rows)

    # Build per-athlete mark lookup from all lists (union, prefer season best).
    # Filtered to roster athletes only — avoids storing thousands of non-Villanova
    # athlete rows in memory and prevents any cross-school ID collisions.
    all_rows_by_athlete: dict[str, list[dict]] = {}
    for rows in list_data.values():
        for row in rows:
            aid = row.get("athlete_id")
            if not aid or aid not in roster_ids:
                continue
            all_rows_by_athlete.setdefault(aid, []).append(row)

    now = datetime.now(timezone.utc)
    records: list[dict] = []

    for athlete in roster:
        aid = str(athlete["athlete_id"])
        gender = athlete.get("gender", "M")
        name = athlete.get("name", "")
        year = athlete.get("year", "")

        athlete_list_rows = all_rows_by_athlete.get(aid, [])
        best_by_event = _best_mark_per_event(athlete_list_rows, gender)

        if not best_by_event:
            # Athlete found on roster but not on any list — include with nulls
            records.append(
                {
                    "athlete_id": aid,
                    "name": name,
                    "year": year,
                    "gender": gender,
                    "event": None,
                    "season": season,
                    "mark": None,
                    "mark_display": None,
                    "wa_points": None,
                    "prev_mark": None,
                    "wind": None,
                    "wind_legal": None,
                    "conf_rank": None,
                    "regional_rank": None,
                    "national_rank": None,
                    "bubble_gap_mark": None,
                    "bubble_gap_points": None,
                    "last_updated": now,
                }
            )
            continue

        for event, perf in best_by_event.items():
            mark_str = perf["mark"]
            wa_pts = perf["wa_points"]
            wind = perf.get("wind")

            conf_r = conf_ranks.get(aid, {}).get(event)
            reg_r = regional_ranks.get(aid, {}).get(event)
            nat_r = national_ranks.get(aid, {}).get(event)

            # Bubble gap
            bubble_info = season_bubble.get(event)
            bubble_gap_mark: Optional[float] = None
            bubble_gap_pts: Optional[int] = None
            if bubble_info and mark_str:
                bubble_mark = bubble_info.get("bubble_mark")
                if bubble_mark is not None:
                    from ..scraper.bubble import _parse_mark_float, _is_time_event
                    perf_val = _parse_mark_float(mark_str, event)
                    if perf_val is not None:
                        if _is_time_event(event):
                            bubble_gap_mark = round(bubble_mark - perf_val, 4)
                        else:
                            bubble_gap_mark = round(perf_val - bubble_mark, 4)
                    bubble_pts = score(event, gender, str(bubble_mark))
                    if bubble_pts is not None and wa_pts is not None:
                        bubble_gap_pts = wa_pts - bubble_pts

            # Previous season mark — raw mark string for the same event.
            # Using the actual mark (not WA points) avoids coefficient-change noise
            # when WA updates their scoring tables between seasons.
            prev_mark_str: Optional[str] = None
            if prev_marks is not None:
                prev_mark_str = prev_marks.get(aid, {}).get(event) or None

            records.append(
                {
                    "athlete_id": aid,
                    "name": name,
                    "year": year,
                    "gender": gender,
                    "event": event,
                    "season": season,
                    "mark": mark_str,
                    "mark_display": mark_display(event, mark_str),
                    "wa_points": wa_pts,
                    "prev_mark": prev_mark_str,
                    "wind": wind,
                    "wind_legal": _wind_legal(wind),
                    "conf_rank": conf_r,
                    "regional_rank": reg_r,
                    "national_rank": nat_r,
                    "bubble_gap_mark": bubble_gap_mark,
                    "bubble_gap_points": bubble_gap_pts,
                    "last_updated": now,
                }
            )

    df = pd.DataFrame(records, columns=COLUMNS)
    logger.info("Built DataFrame: %d rows (%d athletes)", len(df), df["athlete_id"].nunique())
    return df


def composite_view(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse to one row per athlete: best WA points across all events.
    Keeps all rank columns (best rank per source).
    """
    if df.empty:
        return df

    def _agg(group: pd.DataFrame) -> pd.Series:
        # Pick the row with max WA points
        best_row = group.loc[group["wa_points"].fillna(0).idxmax()]
        result = best_row.copy()
        # Best rank (lowest non-null) across all events for each source
        for col in ("conf_rank", "regional_rank", "national_rank"):
            vals = group[col].dropna()
            result[col] = int(vals.min()) if not vals.empty else None
        # List events as comma-separated string
        events = group["event"].dropna().unique().tolist()
        result["events"] = ", ".join(sorted(events))
        return result

    comp = df.dropna(subset=["wa_points"]).groupby("athlete_id", group_keys=False).apply(_agg)
    comp = comp.reset_index(drop=True)
    comp.insert(0, "composite_rank", comp["wa_points"].rank(ascending=False, method="min").astype(int))
    return comp.sort_values("composite_rank")


def _sort_with_nulls_last(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Sort ascending by col, placing rows with null values at the bottom."""
    ranked = df[df[col].notna()].sort_values(col)
    unranked = df[df[col].isna()]
    return pd.concat([ranked, unranked], ignore_index=True)


def sort_by_conference(df: pd.DataFrame) -> pd.DataFrame:
    return _sort_with_nulls_last(df, "conf_rank")


def sort_by_regional(df: pd.DataFrame) -> pd.DataFrame:
    return _sort_with_nulls_last(df, "regional_rank")


def sort_by_national(df: pd.DataFrame) -> pd.DataFrame:
    return _sort_with_nulls_last(df, "national_rank")
