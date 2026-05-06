"""
Villanova Track & Field Ranking Tool
Streamlit entry point.
"""
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the tfrrs-tool directory is on sys.path so that
# `villanova_tf` resolves as a package (required for relative imports).
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent / "data" / "scrape.log"),
    ],
)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Villanova T&F Rankings",
    page_icon="🦶",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Villanova brand colors: Navy #003087, Baby Blue #6CACE4
st.markdown("""
<style>
    /* Primary buttons → navy */
    div.stButton > button[kind="primary"] {
        background-color: #003087 !important;
        border-color: #003087 !important;
        color: white !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #6CACE4 !important;
        border-color: #6CACE4 !important;
    }
    /* Secondary buttons → baby blue outline */
    div.stButton > button[kind="secondary"] {
        border-color: #6CACE4 !important;
        color: #003087 !important;
    }
    div.stButton > button[kind="secondary"]:hover {
        background-color: #6CACE4 !important;
        color: white !important;
    }
    /* Sidebar header */
    [data-testid="stSidebar"] h2 {
        color: #003087;
    }
    /* Tab active indicator */
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #003087 !important;
        border-bottom-color: #003087 !important;
    }
    /* Dataframe header row */
    [data-testid="stDataFrame"] th {
        background-color: #003087 !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------

@st.cache_resource
def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


config = load_config()

# ---------------------------------------------------------------------------
# Imports after config (avoid circular issues)
# ---------------------------------------------------------------------------
from villanova_tf.scraper.roster import get_roster
from villanova_tf.scraper.lists import fetch_all_lists
from villanova_tf.scraper.athlete import roster_profile_rows, build_prev_marks_from_profiles
from villanova_tf.scraper.bubble import load_bubble_reference, build_bubble_reference, save_bubble_reference
from villanova_tf.processing.composite import build_dataframe, composite_view
from villanova_tf.processing.matcher import match_roster_to_list, apply_manual_overrides
from villanova_tf.ui.by_event import render_by_event
from villanova_tf.ui.composite import render_composite
from villanova_tf.ui.athlete_profile import render_athlete_profile
from villanova_tf.ui.data_status import render_data_status, load_manual_matches
from villanova_tf.ui.admin import render_admin_sidebar
from villanova_tf.ui.pdf_export import generate_pdf

# Seed manual_overrides from disk on first run of each session
if "manual_overrides" not in st.session_state:
    st.session_state["manual_overrides"] = load_manual_matches()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## Villanova T&F Rankings")

    # Season toggle
    season_col1, season_col2 = st.columns(2)
    if "season" not in st.session_state:
        st.session_state["season"] = config.get("season", "outdoor")

    if season_col1.button(
        "Indoor",
        type="primary" if st.session_state["season"] == "indoor" else "secondary",
        use_container_width=True,
    ):
        st.session_state["season"] = "indoor"
        st.session_state.pop("cached_df", None)
        st.rerun()

    if season_col2.button(
        "Outdoor",
        type="primary" if st.session_state["season"] == "outdoor" else "secondary",
        use_container_width=True,
    ):
        st.session_state["season"] = "outdoor"
        st.session_state.pop("cached_df", None)
        st.rerun()

    season = st.session_state["season"]
    st.divider()

    # Event group filter
    event_groups = config.get("event_groups", {})
    all_group_names = list(event_groups.keys())
    selected_groups = st.multiselect(
        "Event groups",
        all_group_names,
        default=[],
        placeholder="All events",
    )
    # Resolve selected group names to event keys
    if selected_groups:
        event_filter = []
        for g in selected_groups:
            event_filter.extend(event_groups.get(g, []))
    else:
        event_filter = []

    # Gender filter
    gender_filter = st.radio("Gender", ["Both", "Men", "Women"], horizontal=True)

    st.divider()

    # Refresh controls
    from villanova_tf.scraper.cache import get_cache
    cache = get_cache()
    _limit = config.get("ranking_list_limit", 100)
    _base_key = "big_east_outdoor" if season == "outdoor" else "big_east_indoor"
    last_refresh = cache.get_last_refresh(f"{_base_key}_top{_limit}")
    if last_refresh:
        age_h = (datetime.now(timezone.utc) - last_refresh).total_seconds() / 3600
        st.caption(f"Last refresh: {age_h:.1f}h ago")
    else:
        st.caption("No data loaded yet")

    if st.button("Refresh Data", use_container_width=True, type="primary"):
        st.session_state.pop("cached_df", None)
        st.session_state.pop("roster", None)
        st.session_state["force_refresh"] = True
        st.rerun()


# ---------------------------------------------------------------------------
# Data loading with auto-refresh if stale
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner="Loading roster...")
def cached_roster() -> list[dict]:
    return get_roster()


def load_data(season: str, force: bool = False) -> tuple:
    """Load and build the full DataFrame. Cached in session state."""
    roster = cached_roster()

    ttl_hours = config.get("cache", {}).get("ranking_list_ttl_hours", 24)

    # Auto-refresh if stale (check cache key that incorporates the limit)
    cache = get_cache()
    limit = config.get("ranking_list_limit", 100)
    base_list_key = "big_east_outdoor" if season == "outdoor" else "big_east_indoor"
    list_cache_key = f"{base_list_key}_top{limit}"
    last = cache.get_last_refresh(list_cache_key)
    stale = not last or (datetime.now(timezone.utc) - last).total_seconds() / 3600 > ttl_hours

    if force or stale:
        with st.spinner("Fetching ranking lists..."):
            list_data = fetch_all_lists(config, season)
    else:
        list_data = fetch_all_lists(config, season)  # served from cache

    # Match roster → lists
    all_rows = [r for rows in list_data.values() for r in rows]
    threshold = config.get("matching", {}).get("fuzzy_score_threshold", 85)
    matched, unmatched = match_roster_to_list(roster, all_rows, threshold=threshold)

    # Apply manual overrides from session state
    manual_overrides = st.session_state.get("manual_overrides", [])
    matched, unmatched = apply_manual_overrides(matched, unmatched, manual_overrides)

    # Supplement list data with direct athlete profile fetches for any Villanova
    # athletes not found in the top-N per-event TFRRS ranking list cutoff.
    athletes_in_lists = {r["athlete_id"] for rows in list_data.values() for r in rows}
    roster_ids_in_lists = {str(a["athlete_id"]) for a in roster} & athletes_in_lists
    with st.spinner("Loading profiles for athletes outside ranking list cutoffs..."):
        profile_rows = roster_profile_rows(roster, season, roster_ids_in_lists)
    if profile_rows:
        list_data[f"profile_{season}"] = profile_rows

    # Build previous-season mark lookup from athlete profile career results.
    # Profiles are already fetched for uncovered athletes above; this fetches
    # the rest too (cached in SQLite after first run — subsequent loads instant).
    with st.spinner("Building year-over-year comparison..."):
        try:
            prev_marks = build_prev_marks_from_profiles(roster, season)
        except Exception as exc:
            logger.warning("Could not build prev-season marks: %s", exc)
            prev_marks = None

    # Build DataFrame — use all ranking list rows directly (matcher is for status reporting)
    bubble_ref = load_bubble_reference()
    df = build_dataframe(roster, list_data, season, bubble_ref, prev_marks=prev_marks)

    return df, roster, unmatched, bubble_ref


def _data_freshness_caption(season: str) -> str:
    """Return a short freshness string for the current season's lists."""
    cache = get_cache()
    ttl_hours = config.get("cache", {}).get("ranking_list_ttl_hours", 24)
    limit = config.get("ranking_list_limit", 100)
    base_keys = (
        ["big_east_outdoor", "ncaa_east_outdoor", "ncaa_national_outdoor"]
        if season == "outdoor"
        else ["big_east_indoor", "ncaa_national_indoor"]
    )
    # Cache keys include the limit suffix
    keys = [f"{k}_top{limit}" for k in base_keys]
    ages = []
    for key in keys:
        last = cache.get_last_refresh(key)
        if last:
            ages.append((datetime.now(timezone.utc) - last).total_seconds() / 3600)
    if not ages:
        return "⚠️ No data loaded"
    max_age = max(ages)
    if max_age > ttl_hours:
        return f"⚠️ Data stale ({max_age:.0f}h old — refresh recommended)"
    return f"✓ Data fresh ({max_age:.1f}h old)"


force_refresh = st.session_state.pop("force_refresh", False)

with st.spinner("Loading data..."):
    try:
        df, roster, unmatched_athletes, bubble_ref = load_data(season, force=force_refresh)
    except Exception as e:
        st.error(f"Error loading data: {e}")
        logger.exception("Data load error")
        df, roster, unmatched_athletes, bubble_ref = None, [], [], {}

# Roster lookup for athlete profile
roster_lookup = {str(a["athlete_id"]): a for a in roster}

# ---------------------------------------------------------------------------
# Admin sidebar
# ---------------------------------------------------------------------------
render_admin_sidebar(roster)

# Handle bubble rebuild trigger
if st.session_state.pop("trigger_bubble_rebuild", False):
    with st.spinner("Rebuilding bubble reference (this may take a few minutes)..."):
        try:
            ref = build_bubble_reference(config)
            save_bubble_reference(ref)
            st.sidebar.success("Bubble reference rebuilt.")
        except Exception as e:
            st.sidebar.error(f"Rebuild failed: {e}")

# ---------------------------------------------------------------------------
# Athlete profile overlay
# ---------------------------------------------------------------------------
if st.session_state.get("show_profile") and st.session_state.get("selected_athlete_id"):
    athlete_id = str(st.session_state["selected_athlete_id"])
    with st.expander(f"Athlete Profile — {roster_lookup.get(athlete_id, {}).get('name', athlete_id)}", expanded=True):
        col_close, _ = st.columns([1, 8])
        if col_close.button("✕ Close"):
            st.session_state.pop("show_profile", None)
            st.session_state.pop("selected_athlete_id", None)
            st.rerun()
        render_athlete_profile(athlete_id, roster_lookup, season, bubble_ref)

# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["By Event", "Composite / Chop Order", "Athlete Lookup", "Data Status"])

with tab1:
    if df is not None:
        st.caption(_data_freshness_caption(season))
        render_by_event(df, season, event_filter, gender_filter)
    else:
        st.error("No data available.")

with tab2:
    if df is not None:
        st.caption(_data_freshness_caption(season))
        render_composite(df, season, gender_filter, event_filter)

        # Handle PDF export trigger
        if st.session_state.pop("trigger_pdf", False):
            with st.spinner("Generating PDF..."):
                try:
                    comp = composite_view(df)
                    pdf_bytes = generate_pdf(
                        df, comp, season, bubble_ref,
                        school_name=config.get("pdf", {}).get("school_name", "Villanova T&F"),
                        gender_filter=gender_filter,
                    )
                    st.download_button(
                        label="Download PDF",
                        data=pdf_bytes,
                        file_name=f"villanova_tf_{season}_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf",
                    )
                except Exception as e:
                    st.error(f"PDF generation failed: {e}")
    else:
        st.error("No data available.")

with tab3:
    # Athlete Lookup: search the full roster by name (not limited to ranking list athletes)
    st.subheader("Athlete Lookup")

    if roster:
        # Apply gender filter consistent with sidebar
        lookup_roster = roster
        if gender_filter != "Both":
            g_code = "M" if gender_filter == "Men" else "F"
            lookup_roster = [a for a in roster if a.get("gender") == g_code]

        # Sort alphabetically; build "Name (Year)" labels for clarity
        lookup_sorted = sorted(lookup_roster, key=lambda a: a.get("name", ""))
        lookup_options = ["— type or select an athlete —"] + [
            f"{a['name']} ({a.get('year', '?')})" for a in lookup_sorted
        ]
        lookup_id_map = {
            f"{a['name']} ({a.get('year', '?')})": str(a["athlete_id"])
            for a in lookup_sorted
        }

        chosen_label = st.selectbox(
            "Athlete",
            lookup_options,
            key="tab3_athlete_select",
            help="All roster athletes — includes those not yet on any ranking list.",
        )

        if chosen_label != "— type or select an athlete —":
            athlete_id = lookup_id_map[chosen_label]
            st.session_state["selected_athlete_id"] = athlete_id
            st.session_state["show_profile"] = True
            render_athlete_profile(athlete_id, roster_lookup, season, bubble_ref)
    else:
        st.info("Roster not loaded yet. Use Refresh Data in the sidebar.")

with tab4:
    render_data_status(
        unmatched_athletes,
        st.session_state.get("manual_overrides", []),
        season,
        config,
    )
