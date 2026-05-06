"""
Athlete profile — shown as a modal-style overlay when an athlete name is clicked.
Triggers Tier 2 scrape on first view, cached thereafter.
"""
from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..processing.wa_points import score as wa_score
from ..scraper.athlete import fetch_athlete
from ..scraper.lists import normalize_event


def _parse_date(date_str: str) -> Optional[datetime]:
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            pass
    return None


def _consistency_label(marks: list[float]) -> tuple[str, float]:
    if len(marks) < 2:
        return "insufficient data", 0.0
    import statistics
    sd = statistics.stdev(marks)
    label = "consistent" if sd < 0.5 else "variable"
    return label, round(sd, 3)


def render_athlete_profile(
    athlete_id: str,
    roster_lookup: dict,     # athlete_id → {name, year, gender, tfrrs_href}
    season: str,
    bubble_ref: dict,
):
    athlete = roster_lookup.get(str(athlete_id))
    if not athlete:
        st.error(f"Athlete {athlete_id} not found in roster.")
        return

    name = athlete.get("name", "")
    year = athlete.get("year", "")
    gender = athlete.get("gender", "M")
    tfrrs_href = athlete.get("tfrrs_href", "")

    st.markdown(f"### {name}")
    st.caption(f"{year} · {'Men' if gender == 'M' else 'Women'}")

    with st.spinner("Loading athlete data..."):
        data = fetch_athlete(athlete_id, tfrrs_href)

    if not data:
        st.warning("Could not load athlete data.")
        return

    season_bests = data.get("outdoor_bests" if season == "outdoor" else "indoor_bests", [])
    all_results = data.get("results", [])

    # Season bests summary
    if season_bests:
        st.subheader("Season Bests")
        bests_rows = []
        for b in season_bests:
            pts = wa_score(normalize_event(b.get("event_raw", "")), gender, b.get("mark", ""))
            bests_rows.append({
                "Event": b.get("event_raw", ""),
                "Mark": b.get("mark", ""),
                "WA Pts": pts or "",
            })
        st.dataframe(pd.DataFrame(bests_rows), use_container_width=True, hide_index=True)

        # vs Last Season comparison
        last_year = datetime.now().year - 1
        last_year_results = [
            r for r in all_results
            if _parse_date(r.get("meet_date", "")) is not None
            and _parse_date(r.get("meet_date", "")).year == last_year
        ]
        # Build best per event for last year
        last_year_bests: dict[str, dict] = {}
        for r in last_year_results:
            event_norm = normalize_event(r.get("event_raw", ""))
            mark_str = r.get("mark", "")
            if not event_norm or not mark_str:
                continue
            pts = wa_score(event_norm, gender, mark_str)
            if pts is None:
                continue
            existing = last_year_bests.get(event_norm)
            if existing is None or pts > existing["wa_points"]:
                last_year_bests[event_norm] = {"mark": mark_str, "wa_points": pts}

        # Build best per event for this season from season_bests
        this_year_bests: dict[str, dict] = {}
        for b in season_bests:
            event_norm = normalize_event(b.get("event_raw", ""))
            mark_str = b.get("mark", "")
            if not event_norm or not mark_str:
                continue
            pts = wa_score(event_norm, gender, mark_str)
            if pts is None:
                continue
            this_year_bests[event_norm] = {"mark": mark_str, "wa_points": pts}

        all_events = sorted(set(list(this_year_bests.keys()) + list(last_year_bests.keys())))
        if all_events and last_year_bests:
            st.subheader("vs Last Season")
            comparison_rows = []
            for event_norm in all_events:
                this = this_year_bests.get(event_norm)
                prev = last_year_bests.get(event_norm)
                comparison_rows.append({
                    "Event": event_norm,
                    "This Season": this["mark"] if this else "—",
                    "Last Season": prev["mark"] if prev else "—",
                })
            st.dataframe(pd.DataFrame(comparison_rows), use_container_width=True, hide_index=True)

    # Season progression chart
    if all_results:
        _render_progression_chart(all_results, gender, bubble_ref, season)

    # Meet-by-meet table
    st.subheader("Meet-by-Meet Results")
    if all_results:
        # Build full results rows first
        results_rows = []
        for r in all_results:
            event_norm = normalize_event(r.get("event_raw", ""))
            mark_str = r.get("mark", "")
            pts = wa_score(event_norm, gender, mark_str)
            results_rows.append({
                "Date": r.get("meet_date", ""),
                "Meet": r.get("meet", ""),
                "Event": r.get("event_raw", ""),
                "_event_norm": event_norm,
                "Mark": mark_str,
                "_wa_pts": pts or 0,
                "Wind": r.get("wind", ""),
                "Place": r.get("place", ""),
                "Round": r.get("round", ""),
                "WA Pts": pts or "",
            })

        results_df = pd.DataFrame(results_rows)

        # Controls: event filter + sort
        all_events = sorted(results_df["Event"].dropna().unique().tolist())
        ctrl1, ctrl2 = st.columns(2)
        with ctrl1:
            event_sel = st.selectbox(
                "Filter by event",
                ["All events"] + all_events,
                key="profile_event_filter",
            )
        with ctrl2:
            sort_sel = st.selectbox(
                "Sort by",
                ["Date (newest first)", "Date (oldest first)", "Best mark (WA Pts)"],
                key="profile_sort",
            )

        # Apply filter
        if event_sel != "All events":
            results_df = results_df[results_df["Event"] == event_sel]

        # Apply sort
        if sort_sel == "Date (newest first)":
            results_df = results_df.sort_values("Date", ascending=False)
        elif sort_sel == "Date (oldest first)":
            results_df = results_df.sort_values("Date", ascending=True)
        else:  # Best mark
            results_df = results_df.sort_values("_wa_pts", ascending=False)

        visible_cols = ["Date", "Meet", "Event", "Mark", "Wind", "Place", "Round", "WA Pts"]
        st.dataframe(results_df[visible_cols], use_container_width=True, hide_index=True)
    else:
        st.info("No meet results available.")

    # Consistency indicator
    _render_consistency(all_results, gender)


def _render_progression_chart(results: list[dict], gender: str, bubble_ref: dict, season: str):
    st.subheader("Season Progression")

    # Group by event
    events: dict[str, list] = {}
    for r in results:
        event_norm = normalize_event(r.get("event_raw", ""))
        date = _parse_date(r.get("meet_date", ""))
        mark = r.get("mark", "")
        if not date or not mark or not event_norm:
            continue
        pts = wa_score(event_norm, gender, mark)
        if pts is None:
            continue
        events.setdefault(event_norm, []).append((date, mark, pts, r.get("meet", "")))

    if not events:
        return

    view_mode = st.radio("Y-axis", ["WA Points", "Mark"], horizontal=True, key="profile_yaxis")

    fig = go.Figure()
    season_bubble = bubble_ref.get(season, {})

    for event_key, entries in events.items():
        entries_sorted = sorted(entries, key=lambda x: x[0])
        dates = [e[0] for e in entries_sorted]
        vals = [e[2] if view_mode == "WA Points" else e[1] for e in entries_sorted]
        meets = [e[3] for e in entries_sorted]

        fig.add_trace(go.Scatter(
            x=dates, y=vals,
            mode="lines+markers",
            name=event_key,
            hovertemplate="%{customdata}<br>%{y}<extra></extra>",
            customdata=meets,
        ))

        # Season best reference line
        if view_mode == "WA Points":
            best_pts = max(e[2] for e in entries)
            fig.add_hline(y=best_pts, line_dash="dot",
                          annotation_text=f"{event_key} SB", annotation_position="right",
                          line_color="gray", opacity=0.5)

        # Bubble reference line
        bubble_info = season_bubble.get(event_key)
        if bubble_info and view_mode == "WA Points":
            bubble_pts = wa_score(event_key, gender, str(bubble_info.get("bubble_mark", 0)))
            if bubble_pts:
                fig.add_hline(y=bubble_pts, line_dash="dash", line_color="red",
                              annotation_text="Bubble", annotation_position="left",
                              opacity=0.7)

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title=view_mode,
        legend_title="Event",
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_consistency(results: list[dict], gender: str):
    if not results:
        return
    # Group times by event
    event_times: dict[str, list[float]] = {}
    for r in results:
        event_norm = normalize_event(r.get("event_raw", ""))
        mark = r.get("mark", "")
        pts = wa_score(event_norm, gender, mark)
        if pts:
            event_times.setdefault(event_norm, []).append(float(pts))

    if not event_times:
        return

    st.subheader("Consistency")
    cols = st.columns(min(len(event_times), 4))
    for i, (event_key, pts_list) in enumerate(event_times.items()):
        label, sd = _consistency_label(pts_list)
        cols[i % len(cols)].metric(
            event_key,
            label,
            help=f"Std dev of WA points: {sd}",
        )
