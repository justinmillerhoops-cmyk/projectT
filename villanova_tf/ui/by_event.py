"""
Tab 1 — By Event view.
Shows all Villanova athletes in selected event(s) with ranking columns.
"""
import pandas as pd
import streamlit as st


def _wind_badge(wind, legal):
    if wind is None:
        return ""
    if legal is True:
        return f"✓ {wind:+.1f}"
    if legal is False:
        return f"⚠ {wind:+.1f}"
    return ""


def render_by_event(df: pd.DataFrame, season: str, event_filter: list[str], gender_filter: str):
    """Render Tab 1 content."""
    if df.empty:
        st.info("No data loaded. Use the refresh button in the sidebar.")
        return

    filtered = df.copy()

    if event_filter:
        filtered = filtered[filtered["event"].isin(event_filter)]

    if gender_filter != "Both":
        g = "M" if gender_filter == "Men" else "F"
        filtered = filtered[filtered["gender"] == g]

    if filtered.empty:
        st.info("No athletes match the selected filters.")
        return

    show_regional = season == "outdoor"

    display_rows = []
    for _, row in filtered.iterrows():
        # Athlete is "profile-only" if they have a mark but no rank on any list
        has_rank = (
            pd.notna(row.get("conf_rank"))
            or pd.notna(row.get("regional_rank"))
            or pd.notna(row.get("national_rank"))
        )
        has_mark = pd.notna(row.get("wa_points"))
        profile_only = has_mark and not has_rank
        name = row["name"] + (" †" if profile_only else "")

        display_row = {
            "Name": name,
            "Year": row.get("year", ""),
            "Event": row.get("event", ""),
            "Mark": row.get("mark_display") or row.get("mark", ""),
            "Prev SB": row.get("prev_mark") or "—",
            "Wind": _wind_badge(row.get("wind"), row.get("wind_legal")),
            "WA Pts": row.get("wa_points", ""),
            "Conf Rank": row.get("conf_rank", ""),
        }
        if show_regional:
            display_row["Regional Rank"] = row.get("regional_rank", "")
        display_row["Natl Rank"] = row.get("national_rank", "")
        display_row["_athlete_id"] = row["athlete_id"]
        display_rows.append(display_row)

    display_df = pd.DataFrame(display_rows)

    # Count profile-only athletes for footnote
    n_profile = sum(
        1 for r in display_rows
        if r["Name"].endswith(" †")
    )

    ctrl_col1, ctrl_col2 = st.columns([2, 3])

    with ctrl_col1:
        sort_options = ["WA Pts", "Conf Rank", "Natl Rank", "Name"]
        if show_regional:
            sort_options.insert(2, "Regional Rank")
        sort_col = st.selectbox("Sort by", sort_options, key="by_event_sort")

    with ctrl_col2:
        # Athlete profile selector
        name_to_id = {
            row["Name"]: row["_athlete_id"]
            for _, row in display_df.iterrows()
        }
        names = ["— select to view profile —"] + sorted(name_to_id.keys())
        chosen = st.selectbox("View athlete profile", names, key="by_event_profile_select")
        if chosen != "— select to view profile —":
            st.session_state["selected_athlete_id"] = name_to_id[chosen]
            st.session_state["show_profile"] = True

    if sort_col in display_df.columns:
        asc = sort_col in ("Conf Rank", "Regional Rank", "Natl Rank", "Name")
        display_df = display_df.sort_values(sort_col, ascending=asc, na_position="last")

    visible_cols = [c for c in display_df.columns if not c.startswith("_")]
    st.dataframe(display_df[visible_cols], use_container_width=True, hide_index=True)

    if n_profile > 0:
        st.caption(
            "† Mark sourced from athlete's TFRRS profile page — ranked outside the "
            "TFRRS list cutoff (~top 50 per event). Exact list position unavailable."
        )
