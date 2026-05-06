"""
Tier 1 scraper: Villanova roster from TFRRS team pages.
Fetches both men's and women's pages and returns a unified list of athletes.
"""
import json
import logging
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from .cache import get_cache
from .rate_limiter import fetch
from ..tfrrs_selectors import (
    ATHLETE_HREF_RE,
    BASE_URL,
    ROSTER_TABLE_CLASS,
    TEAM_PAGE_URL,
    VILLANOVA_MEN_SLUG,
    VILLANOVA_WOMEN_SLUG,
)

logger = logging.getLogger(__name__)

_OVERRIDES_PATH = Path(__file__).parent.parent / "data" / "roster_overrides.json"


def _load_overrides() -> dict:
    if _OVERRIDES_PATH.exists():
        with open(_OVERRIDES_PATH) as f:
            return json.load(f)
    return {"add": [], "remove": []}


def _parse_year(raw: str) -> str:
    """Convert TFRRS year string like 'SR-4', 'JR-3', 'SO-2', 'FR-1' to Fr/So/Jr/Sr."""
    mapping = {"FR": "Fr", "SO": "So", "JR": "Jr", "SR": "Sr"}
    prefix = raw.split("-")[0].upper() if "-" in raw else raw.upper()
    return mapping.get(prefix, raw)


def _parse_roster_html(html: str, gender: str) -> list[dict]:
    """
    Parse team page HTML and return a deduplicated list of athlete dicts.
    Prefers the NAME/YEAR table (alphabetical full roster) over event-grouped tables.
    """
    soup = BeautifulSoup(html, "html.parser")
    all_tables = soup.find_all("table", class_=lambda c: c and ROSTER_TABLE_CLASS in c.split())
    if not all_tables:
        return []

    # Use the table whose headers are NAME + YEAR (the alphabetical full roster).
    # Fall back to scanning all tables and aggregating.
    def _is_name_year_table(t) -> bool:
        headers = [th.get_text(strip=True).upper() for th in t.find_all("th")]
        return "NAME" in headers and "YEAR" in headers

    roster_table = next((t for t in all_tables if _is_name_year_table(t)), None)
    tables_to_parse = [roster_table] if roster_table else all_tables

    seen_ids: set[str] = set()
    athletes: list[dict] = []

    for table in tables_to_parse:
        for row in table.find_all("tr")[1:]:  # skip header
            cells = row.find_all("td")
            if not cells:
                continue

            # Find the cell containing an athlete link
            link = None
            year_raw = ""
            for ci, cell in enumerate(cells):
                a = cell.find("a", href=re.compile(ATHLETE_HREF_RE))
                if a:
                    link = a
                    # Year is typically the next cell
                    if ci + 1 < len(cells):
                        year_raw = cells[ci + 1].get_text(strip=True)
                    break

            if not link:
                continue

            href = link.get("href", "")
            id_match = re.search(ATHLETE_HREF_RE, href)
            if not id_match:
                continue

            athlete_id = id_match.group(1)
            if athlete_id in seen_ids:
                continue
            seen_ids.add(athlete_id)

            name_raw = link.get_text(strip=True)  # "Last, First"
            parts = name_raw.split(",", 1)
            name = f"{parts[1].strip()} {parts[0].strip()}" if len(parts) == 2 else name_raw

            athletes.append(
                {
                    "athlete_id": athlete_id,
                    "name": name,
                    "name_raw": name_raw,
                    "year": _parse_year(year_raw),
                    "gender": gender,
                    "tfrrs_href": href,
                }
            )

    return athletes


def _scrape_team_page(slug: str, gender: str) -> list[dict]:
    """Fetch one gender's team page and return list of athlete dicts."""
    url = TEAM_PAGE_URL.format(slug=slug)
    cache = get_cache()

    cache_key = f"roster_{slug}"
    cached_html = cache.get_ranking_list(cache_key, ttl_hours=24)
    if cached_html:
        html = cached_html
        logger.debug("Roster cache hit: %s", slug)
    else:
        logger.info("Fetching roster: %s", url)
        resp = fetch(url)
        html = resp.text
        cache.set_ranking_list(cache_key, html)
        cache.log("roster_fetch", url=url)

    athletes = _parse_roster_html(html, gender)
    if not athletes:
        logger.warning("No roster athletes found at %s", url)
    logger.info("Found %d athletes on %s roster", len(athletes), slug)
    return athletes


def get_roster() -> list[dict]:
    """
    Return the full Villanova roster (men + women) with override layer applied.
    Each dict has: athlete_id, name, year, gender, tfrrs_href.
    """
    men = _scrape_team_page(VILLANOVA_MEN_SLUG, "M")
    women = _scrape_team_page(VILLANOVA_WOMEN_SLUG, "F")
    all_athletes = men + women

    overrides = _load_overrides()

    # Remove excluded IDs
    exclude_ids = set(str(x) for x in overrides.get("remove", []))
    all_athletes = [a for a in all_athletes if a["athlete_id"] not in exclude_ids]

    # Add manual entries (walk-ons etc)
    for entry in overrides.get("add", []):
        if not any(a["athlete_id"] == str(entry.get("athlete_id", "")) for a in all_athletes):
            all_athletes.append(
                {
                    "athlete_id": str(entry.get("athlete_id", f"manual_{entry['name']}")),
                    "name": entry["name"],
                    "year": entry.get("year", ""),
                    "gender": entry.get("gender", ""),
                    "tfrrs_href": entry.get("tfrrs_href", ""),
                    "manual_entry": True,
                }
            )

    # Deduplicate by athlete_id (keep first occurrence)
    seen: set[str] = set()
    unique: list[dict] = []
    for a in all_athletes:
        if a["athlete_id"] not in seen:
            seen.add(a["athlete_id"])
            unique.append(a)

    logger.info("Final roster: %d athletes (%d men, %d women)", len(unique),
                sum(1 for a in unique if a["gender"] == "M"),
                sum(1 for a in unique if a["gender"] == "F"))
    return unique
