"""
Tier 1 scraper: ranking lists (Big East, NCAA East regional, NCAA national).

Each list page serves all events in a single HTML document inside a <turbo-frame>.
We parse the div-based performance-list layout (not <table> elements).

Returned structure per row:
{
  "rank": int,
  "athlete_id": str,
  "athlete_name": str,
  "year": str,
  "team": str,
  "mark": str,          # raw mark string from page
  "meet": str,
  "meet_date": str,
  "wind": str | None,
  "event": str,         # normalized event key (e.g. "100m", "shot_put")
  "gender": str,        # "M" or "F"
  "list_key": str,
}
"""
import logging
import re
from typing import Optional

import yaml
from bs4 import BeautifulSoup, Tag

from .cache import get_cache
from .rate_limiter import fetch
from ..tfrrs_selectors import (
    ATHLETE_HREF_RE,
    BASE_URL,
    COL_ATHLETE,
    COL_MEET,
    COL_NARROW,
    COL_PLACE,
    COL_TEAM,
    DATA_LABEL_DATE,
    DATA_LABEL_TIME,
    DATA_LABEL_WIND,
    DATA_LABEL_YEAR,
    EVENT_SECTION_HEADER,
    LIST_PAGE_URL,
    PERF_LIST_BODY,
    PERF_LIST_ROW,
    TF_BASE_URL,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event name normalisation
# ---------------------------------------------------------------------------

_EVENT_NORMALIZE: dict[str, str] = {
    # Track
    "60 meters": "60m",
    "60m": "60m",
    "60": "60m",
    "100 meters": "100m",
    "100m": "100m",
    "100": "100m",
    "200 meters": "200m",
    "200m": "200m",
    "200": "200m",
    "400 meters": "400m",
    "400m": "400m",
    "400": "400m",
    "800 meters": "800m",
    "800m": "800m",
    "800": "800m",
    "1500 meters": "1500m",
    "1500m": "1500m",
    "1500": "1500m",
    "mile": "mile",
    "1 mile": "mile",
    "one mile": "mile",
    "3000 meters": "3000m",
    "3000m": "3000m",
    "3000": "3000m",
    "5000 meters": "5000m",
    "5000m": "5000m",
    "5,000 meters": "5000m",
    "5000": "5000m",
    "10,000 meters": "10000m",
    "10000 meters": "10000m",
    "10000m": "10000m",
    "10000": "10000m",
    "10,000": "10000m",
    "3000 meter steeplechase": "3000sc",
    "3000 steeplechase": "3000sc",
    "3000m steeplechase": "3000sc",
    "3000s": "3000sc",
    "3000sc": "3000sc",
    # Indoor non-standard distances (no WA scoring but normalize for display)
    "500": "500m",
    "500m": "500m",
    "500 meters": "500m",
    "600": "600m",
    "600m": "600m",
    "600 meters": "600m",
    "1000": "1000m",
    "1000m": "1000m",
    "1000 meters": "1000m",
    "60 meter hurdles": "60h",
    "60m hurdles": "60h",
    "60h": "60h",
    "100 meter hurdles": "100h",
    "100m hurdles": "100h",
    "100h": "100h",
    "100 hurdles": "100h",
    "110 meter hurdles": "110h",
    "110m hurdles": "110h",
    "110h": "110h",
    "110 hurdles": "110h",
    "400 meter hurdles": "400h",
    "400m hurdles": "400h",
    "400h": "400h",
    "400 hurdles": "400h",
    # Field
    "high jump": "high_jump",
    "hj": "high_jump",
    "pole vault": "pole_vault",
    "pv": "pole_vault",
    "long jump": "long_jump",
    "lj": "long_jump",
    "triple jump": "triple_jump",
    "tj": "triple_jump",
    "shot put": "shot_put",
    "sp": "shot_put",
    "weight throw": "weight_throw",
    "wt": "weight_throw",
    "weight": "weight_throw",
    "discus throw": "discus",
    "discus": "discus",
    "dt": "discus",
    "hammer throw": "hammer",
    "hammer": "hammer",
    "ht": "hammer",
    "javelin throw": "javelin",
    "javelin": "javelin",
    "jt": "javelin",
    # Combined
    "heptathlon": "heptathlon",
    "hep": "heptathlon",
    "pentathlon": "pentathlon",
    "pent": "pentathlon",
    "decathlon": "decathlon",
    "dec": "decathlon",
}


def normalize_event(raw: str) -> str:
    key = raw.lower().strip()
    # Remove trailing "(men)" / "(women)"
    key = re.sub(r"\s*\((?:men|women)\)\s*$", "", key)
    return _EVENT_NORMALIZE.get(key, key)


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _get_col_text(row_div: Tag, col_class: str, data_label: Optional[str] = None) -> str:
    """Return stripped text from a div matching col_class within a row."""
    if data_label:
        col = row_div.find("div", class_=col_class, attrs={"data-label": data_label})
    else:
        col = row_div.find("div", class_=col_class)
    if not col:
        return ""
    return col.get_text(strip=True)


def _get_col_href(row_div: Tag, col_class: str, data_label: Optional[str] = None) -> Optional[str]:
    if data_label:
        col = row_div.find("div", class_=col_class, attrs={"data-label": data_label})
    else:
        col = row_div.find("div", class_=col_class)
    if not col:
        return None
    link = col.find("a")
    return link.get("href") if link else None


def _parse_athlete_id(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    m = re.search(ATHLETE_HREF_RE, href)
    return m.group(1) if m else None


def _parse_event_sections(frame_html: str) -> list[dict]:
    """
    Parse all event sections from the turbo-frame HTML.
    Returns flat list of performance dicts, one per ranking row.
    """
    soup = BeautifulSoup(frame_html, "html.parser")
    results: list[dict] = []

    event_sections = soup.find_all("div", class_=EVENT_SECTION_HEADER)
    for section_div in event_sections:
        # Event name is in the <h3>
        h3 = section_div.find("h3")
        if not h3:
            continue
        event_raw = h3.get_text(strip=True)
        event_key = normalize_event(event_raw)
        gender = "F" if "(Women)" in event_raw or "(women)" in event_raw else "M"

        # Performance list is the next sibling div
        perf_list = section_div.find_next_sibling("div", class_=lambda c: c and "performance-list" in c)
        if not perf_list:
            # try parent-level approach
            perf_list = section_div.parent.find("div", class_=lambda c: c and PERF_LIST_BODY in (c or ""))
        if not perf_list:
            continue

        body = perf_list.find("div", class_=lambda c: c and PERF_LIST_BODY in (c or ""))
        if not body:
            body = perf_list

        rows = body.find_all("div", class_=lambda c: c and PERF_LIST_ROW in (c or ""))

        for row_div in rows:
            # Place / rank
            place_div = row_div.find("div", class_=COL_PLACE)
            rank_text = place_div.get_text(strip=True) if place_div else ""
            try:
                rank = int(re.sub(r"\D", "", rank_text))
            except ValueError:
                rank = 0

            # Athlete name + ID
            athlete_div = row_div.find("div", class_=COL_ATHLETE)
            if not athlete_div:
                continue
            athlete_link = athlete_div.find("a")
            athlete_name = athlete_link.get_text(strip=True) if athlete_link else ""
            athlete_href = athlete_link.get("href") if athlete_link else None
            athlete_id = _parse_athlete_id(athlete_href)
            if not athlete_id:
                continue  # no usable ID → can't match to roster, skip

            # Year (first col-narrow with data-label="Year")
            year_div = row_div.find("div", class_=COL_NARROW, attrs={"data-label": DATA_LABEL_YEAR})
            year = year_div.get_text(strip=True) if year_div else ""

            # Team
            team_div = row_div.find("div", class_=COL_TEAM)
            team = team_div.get_text(strip=True) if team_div else ""

            # Mark (col-narrow with data-label="Time" — used for all events)
            mark_div = row_div.find("div", class_=COL_NARROW, attrs={"data-label": DATA_LABEL_TIME})
            mark = mark_div.get_text(strip=True) if mark_div else ""

            # Meet
            meet_div = row_div.find("div", class_=COL_MEET)
            meet = meet_div.get_text(strip=True) if meet_div else ""

            # Date (col-narrow with data-label="Meet Date")
            date_div = row_div.find("div", class_=COL_NARROW, attrs={"data-label": DATA_LABEL_DATE})
            meet_date = date_div.get_text(strip=True) if date_div else ""

            # Wind (col-narrow with data-label="Wind") — may not exist
            wind_div = row_div.find("div", class_=COL_NARROW, attrs={"data-label": DATA_LABEL_WIND})
            wind = wind_div.get_text(strip=True) if wind_div else None

            results.append(
                {
                    "rank": rank,
                    "athlete_id": athlete_id,
                    "athlete_name": athlete_name,
                    "year": year,
                    "team": team,
                    "mark": mark,
                    "meet": meet,
                    "meet_date": meet_date,
                    "wind": wind if wind else None,
                    "event": event_key,
                    "gender": gender,
                }
            )

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _build_list_url(list_key: str, config: dict, limit: Optional[int] = None) -> str:
    list_ids = config.get("list_ids", {})
    list_slugs = config.get("list_slugs", {})
    base_urls = config.get("list_base_urls", {})

    list_id = list_ids.get(list_key)
    slug = list_slugs.get(list_key, "")
    base = base_urls.get(list_key, "https://www.tfrrs.org")

    url = f"{base}/lists/{list_id}/{slug}"
    if limit:
        url += f"?limit={limit}"
    return url


def fetch_list(list_key: str, config: dict, ttl_hours: float = 24, limit: Optional[int] = None) -> list[dict]:
    """
    Fetch and parse a single ranking list (all events, both genders combined).
    Results are cached per list_key (incorporating limit in the cache key so
    changing the limit triggers a fresh fetch).
    """
    cache = get_cache()
    # Include limit in cache key so top-50 and top-100 fetches are stored separately
    cache_key = f"{list_key}_top{limit}" if limit else list_key
    cached_html = cache.get_ranking_list(cache_key, ttl_hours=ttl_hours)

    if cached_html:
        logger.debug("List cache hit: %s", cache_key)
        html = cached_html
    else:
        url = _build_list_url(list_key, config, limit=limit)
        logger.info("Fetching ranking list %s: %s", cache_key, url)
        resp = fetch(url)
        html = resp.text
        cache.set_ranking_list(cache_key, html)
        cache.log("list_fetch", url=url, detail=cache_key)

    rows = _parse_event_sections(html)
    for row in rows:
        row["list_key"] = list_key  # keep original list_key for downstream logic

    logger.info("Parsed %d rows from list %s", len(rows), cache_key)
    return rows


def fetch_prev_season_marks(config: dict, season: str = "outdoor") -> dict[str, dict[str, dict]]:
    """
    Fetch the previous completed season's NCAA qualifying list and return a
    lookup of athlete_id → {event → {mark, wa_points}} (season best per event).

    Uses the first entry in ncaa_outdoor_history / ncaa_indoor_history.
    Cached with ttl_hours=8760 (1 year) since these are final historical lists.

    Returns an empty dict on any failure.
    """
    from ..processing.wa_points import score

    history_key = "ncaa_outdoor_history" if season == "outdoor" else "ncaa_indoor_history"
    slug_key = "ncaa_outdoor_history_slugs" if season == "outdoor" else "ncaa_indoor_history_slugs"

    history_ids = config.get("list_ids", {}).get(history_key, [])
    if not history_ids:
        logger.warning("No %s list IDs in config", history_key)
        return {}

    list_id = history_ids[0]
    slug_map = config.get(slug_key, {})
    slug = slug_map.get(list_id, slug_map.get(str(list_id), ""))

    # Build a minimal fake config so we can reuse fetch_list
    fake_key = f"hist_{list_id}"
    fake_config = {
        "list_ids": {fake_key: list_id},
        "list_slugs": {fake_key: slug},
        "list_base_urls": {fake_key: "https://tf.tfrrs.org"},
    }

    # Use the same limit as current-season lists for consistent coverage
    limit = config.get("ranking_list_limit", 100)
    try:
        rows = fetch_list(fake_key, fake_config, ttl_hours=8760, limit=limit)
    except Exception as exc:
        logger.error("Failed to fetch previous season list %s: %s", list_id, exc)
        return {}

    # Build lookup: athlete_id → event → best {mark, wa_points}
    lookup: dict[str, dict[str, dict]] = {}
    for row in rows:
        aid = row.get("athlete_id")
        event = row.get("event", "")
        mark_str = row.get("mark", "")
        gender = row.get("gender", "M")
        if not aid or not event or not mark_str:
            continue
        pts = score(event, gender, mark_str)
        if pts is None:
            continue
        athlete_bests = lookup.setdefault(str(aid), {})
        existing = athlete_bests.get(event)
        if existing is None or pts > existing["wa_points"]:
            athlete_bests[event] = {"mark": mark_str, "wa_points": pts}

    logger.info("Prev season marks: %d athletes from list %s", len(lookup), list_id)
    return lookup


def fetch_all_lists(config: dict, season: str = "outdoor") -> dict[str, list[dict]]:
    """
    Fetch all relevant ranking lists for the given season.
    Returns dict keyed by list_key → list of row dicts.

    The number of entries fetched per event is controlled by
    config["ranking_list_limit"] (default 100).  TFRRS supports
    ?limit=50/100/200/500 via a query parameter.
    """
    if season == "outdoor":
        keys = ["big_east_outdoor", "ncaa_east_outdoor", "ncaa_national_outdoor"]
    else:
        keys = ["big_east_indoor", "ncaa_national_indoor"]

    ttl = config.get("cache", {}).get("ranking_list_ttl_hours", 24)
    limit = config.get("ranking_list_limit", 100)

    results: dict[str, list[dict]] = {}
    for key in keys:
        try:
            results[key] = fetch_list(key, config, ttl_hours=ttl, limit=limit)
        except Exception as exc:
            logger.error("Failed to fetch list %s: %s", key, exc)
            results[key] = []

    return results
