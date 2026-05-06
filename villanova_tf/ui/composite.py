"""
Tab 2 — Composite / chopping order view.
Single ranked list across all athletes, sortable by WA composite, conference,
regional (outdoor only), or national rank.
"""
import pandas as pd
import streamlit as st

from ..processing.composite import (
    composite_view,
    sort_by_conference,
    sort_by_national,
    sort_by_regional,
)


def render_composite(df: pd.DataFrame, season: str, gender_filter: str, event_filter: list[str]):
    """Render Tab 2 content."""
    if df.empty:
        st.info("No data loaded.")
        return

    filtered = df.copy()

    if event_filter:
        filtered = filtered[filtered["event"].isin(event_filter)]

    if gender_filter != "Both":
        g = "M" if gender_filter == "Men" else "F"
        filtered = filtered[filtered["gender"] == g]

    comp = composite_view(filtered)

    if comp.empty:
        st.info("No ranked athletes match the selected filters.")
        return

    show_regional = season == "outdoor"

    # Sort mode buttons
    n_cols = 4 if show_regional else 3
    cols = st.columns(n_cols)
    sort_labels = ["WA Composite", "Conference", "National"]
    if show_regional:
        sort_labels.insert(2, "Regional")

    if "comp_sort" not in st.session_state:
        st.session_state["comp_sort"] = "WA Composite"

    for i, label in enumerate(sort_labels):
        disabled = not show_regional and label == "Regional"
        if cols[i].button(
            label,
            type="primary" if st.session_state["comp_sort"] == label else "secondary",
            disabled=disabled,
            use_container_width=True,
            key=f"sort_btn_{label}",
        ):
            st.session_state["comp_sort"] = label

    # Apply sort
    sort_mode = st.session_state["comp_sort"]
    rank_col = {
        "Conference": "conf_rank",
        "Regional": "regional_rank",
        "National": "national_rank",
    }.get(sort_mode)

    if sort_mode == "Conference":
        sorted_df = sort_by_conference(comp)
    elif sort_mode == "Regional" and show_regional:
        sorted_df = sort_by_regional(comp)
    elif sort_mode == "National":
        sorted_df = sort_by_national(comp)
    else:
        sorted_df = comp.sort_values("composite_rank")

    # Show how many athletes appear at bottom with no rank in the selected column
    if rank_col:
        n_unranked = int(sorted_df[rank_col].isna().sum())
        n_total = len(sorted_df)
        if n_unranked > 0:
            st.caption(
                f"Showing all {n_total} athletes — "
                f"{n_total - n_unranked} ranked by {sort_mode}, "
                f"{n_unranked} unranked shown at bottom."
            )

    # Build display rows
    display_rows = []
    n_profile = 0
    for i, (_, row) in enumerate(sorted_df.iterrows(), start=1):
        # Profile-only: has WA points but no rank on any list
        has_rank = (
            pd.notna(row.get("conf_rank"))
            or pd.notna(row.get("regional_rank"))
            or pd.notna(row.get("national_rank"))
        )
        has_pts = pd.notna(row.get("wa_points"))
        profile_only = has_pts and not has_rank
        if profile_only:
            n_profile += 1
        name = row.get("name", "") + (" †" if profile_only else "")

        d = {
            "Rank": i,
            "Name": name,
            "Year": row.get("year", ""),
            "Event(s)": row.get("events", row.get("event", "")),
            "SB": row.get("mark_display") or row.get("mark", ""),
            "WA Pts": row.get("wa_points", ""),
            "Prev SB": row.get("prev_mark") or "—",
            "Conf Rank": row.get("conf_rank", ""),
        }
        if show_regional:
            d["Regional Rank"] = row.get("regional_rank", "")
        d["Natl Rank"] = row.get("national_rank", "")
        d["_athlete_id"] = row.get("athlete_id", "")
        display_rows.append(d)

    display_df = pd.DataFrame(display_rows)
    visible_cols = [c for c in display_df.columns if not c.startswith("_")]
    st.dataframe(display_df[visible_cols], use_container_width=True, hide_index=True)

    if n_profile > 0:
        st.caption(
            "† Mark sourced from TFRRS athlete profile — ranked outside the "
            "list cutoff (~top 50 per event). Exact list position unavailable."
        )

    # Athlete profile selector + PDF export in same row
    st.divider()
    sel_col, pdf_col = st.columns([3, 1])

    with sel_col:
        name_to_id = {
            row["Name"]: row["_athlete_id"]
            for _, row in display_df.iterrows()
        }
        names = ["— select to view profile —"] + list(name_to_id.keys())
        chosen = st.selectbox("View athlete profile", names, key="comp_profile_select")
        if chosen != "— select to view profile —":
            st.session_state["selected_athlete_id"] = name_to_id[chosen]
            st.session_state["show_profile"] = True

    with pdf_col:
        if st.button("Export PDF", type="secondary", use_container_width=True):
            st.session_state["trigger_pdf"] = True
