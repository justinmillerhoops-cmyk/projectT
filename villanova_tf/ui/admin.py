"""
Admin sidebar panel — roster management and manual data operations.
"""
import json
from pathlib import Path

import streamlit as st

_OVERRIDES_PATH = Path(__file__).parent.parent / "data" / "roster_overrides.json"


def _load_overrides() -> dict:
    if _OVERRIDES_PATH.exists():
        with open(_OVERRIDES_PATH) as f:
            return json.load(f)
    return {"add": [], "remove": []}


def _save_overrides(data: dict) -> None:
    with open(_OVERRIDES_PATH, "w") as f:
        json.dump(data, f, indent=2)


def render_admin_sidebar(roster: list[dict]):
    with st.sidebar.expander("Admin", expanded=False):
        st.markdown("**Add Athlete**")
        with st.form("add_athlete_form"):
            name = st.text_input("Full name")
            year = st.selectbox("Year", ["Fr", "So", "Jr", "Sr"])
            gender = st.radio("Gender", ["M", "F"], horizontal=True)
            events = st.text_input("Events (comma-separated, e.g. 400m, 200m)")
            tfrrs_id = st.text_input("TFRRS athlete ID (if known)")
            submitted = st.form_submit_button("Add")
            if submitted and name:
                overrides = _load_overrides()
                entry = {
                    "name": name,
                    "year": year,
                    "gender": gender,
                    "events": [e.strip() for e in events.split(",") if e.strip()],
                }
                if tfrrs_id:
                    entry["athlete_id"] = tfrrs_id
                overrides["add"].append(entry)
                _save_overrides(overrides)
                st.success(f"Added {name}")
                st.rerun()

        st.divider()
        st.markdown("**Current Roster**")
        overrides = _load_overrides()
        removed_ids = set(str(x) for x in overrides.get("remove", []))

        for athlete in roster:
            aid = str(athlete.get("athlete_id", ""))
            is_removed = aid in removed_ids
            col1, col2 = st.columns([4, 1])
            label = f"~~{athlete['name']}~~" if is_removed else athlete["name"]
            col1.markdown(f"{label} ({athlete.get('year', '')})")
            if not is_removed:
                if col2.button("✕", key=f"remove_{aid}"):
                    overrides = _load_overrides()
                    if aid not in [str(x) for x in overrides["remove"]]:
                        overrides["remove"].append(aid)
                    _save_overrides(overrides)
                    st.rerun()
            else:
                if col2.button("↩", key=f"restore_{aid}"):
                    overrides = _load_overrides()
                    overrides["remove"] = [x for x in overrides["remove"] if str(x) != aid]
                    _save_overrides(overrides)
                    st.rerun()

        st.divider()
        st.markdown("**Bubble Reference**")
        if st.button("Rebuild bubble reference", use_container_width=True):
            st.session_state["trigger_bubble_rebuild"] = True
            st.info("Bubble rebuild queued — this may take several minutes.")
