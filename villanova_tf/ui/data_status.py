"""
Tab 4 — Data Status.
Shows last refresh times, unmatched athletes, manual match UI, and scrape log.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from ..scraper.cache import get_cache

_MANUAL_MATCHES_PATH = Path(__file__).parent.parent / "data" / "manual_matches.json"


def load_manual_matches() -> list[dict]:
    """Load persisted manual athlete-to-list matches from disk."""
    if not _MANUAL_MATCHES_PATH.exists():
        return []
    try:
        with open(_MANUAL_MATCHES_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_manual_matches(overrides: list[dict]) -> None:
    """Persist manual matches to disk so they survive app restarts."""
    _MANUAL_MATCHES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_MANUAL_MATCHES_PATH, "w") as f:
        json.dump(overrides, f, indent=2)


def render_data_status(
    unmatched_athletes: list[dict],
    manual_overrides: list[dict],
    season: str,
    config: dict,
):
    cache = get_cache()
    list_ids = config.get("list_ids", {})

    st.subheader("Data Source Status")

    # Last refresh per list
    if season == "outdoor":
        keys = ["big_east_outdoor", "ncaa_east_outdoor", "ncaa_national_outdoor"]
    else:
        keys = ["big_east_indoor", "ncaa_national_indoor"]

    cols = st.columns(len(keys))
    for i, key in enumerate(keys):
        last = cache.get_last_refresh(key)
        if last:
            age_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600
            label = f"{age_h:.1f}h ago"
            color = "normal" if age_h < 24 else "inverse"
        else:
            label = "Never fetched"
            color = "off"
        cols[i].metric(key.replace("_", " ").title(), label)

    st.divider()

    # Unmatched athletes
    st.subheader("Unmatched Athletes")
    if not unmatched_athletes:
        st.success("All roster athletes matched to at least one ranking list.")
    else:
        st.warning(f"{len(unmatched_athletes)} athlete(s) not found on any ranking list.")
        for athlete in unmatched_athletes:
            with st.expander(f"{athlete['name']} (score={athlete.get('match_score', 0)})"):
                st.write(f"Best candidate: {athlete.get('best_candidate', '—')}")
                st.write(f"Athlete ID: {athlete.get('athlete_id', '—')}")

                # Manual match form
                with st.form(key=f"manual_match_{athlete['athlete_id']}"):
                    list_name = st.text_input("Matching name on list (exact):")
                    event = st.text_input("Event (e.g. 400m):")
                    mark = st.text_input("Season best mark:")
                    rank = st.number_input("Rank on list:", min_value=1, value=1)
                    submitted = st.form_submit_button("Save manual match")
                    if submitted and list_name:
                        override = {
                            "athlete_id": athlete["athlete_id"],
                            "list_athlete_name": list_name,
                            "event": event,
                            "mark": mark,
                            "rank": int(rank),
                        }
                        if "manual_overrides" not in st.session_state:
                            st.session_state["manual_overrides"] = []
                        # Replace existing entry for this athlete, then append
                        st.session_state["manual_overrides"] = [
                            o for o in st.session_state["manual_overrides"]
                            if str(o.get("athlete_id")) != str(athlete["athlete_id"])
                        ]
                        st.session_state["manual_overrides"].append(override)
                        save_manual_matches(st.session_state["manual_overrides"])
                        st.success(f"Manual match saved for {athlete['name']}")
                        st.rerun()

    st.divider()

    # Scrape log
    st.subheader("Recent Scrape Activity")
    log_entries = cache.get_recent_log(50)
    if log_entries:
        import pandas as pd
        log_df = pd.DataFrame(log_entries)
        log_df["ts"] = pd.to_datetime(log_df["ts"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(log_df, use_container_width=True, hide_index=True)
    else:
        st.info("No scrape activity recorded yet.")
