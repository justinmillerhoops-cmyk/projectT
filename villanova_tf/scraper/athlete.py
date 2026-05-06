"""
Tier 2 scraper: individual athlete detail pages.
Only fetched on-demand (when a coach clicks an athlete name) and cached
until the athlete's season best changes.
"""
import logging
import re
from datetime import date, datetime
from typing import Optional

from bs4 import BeautifulSoup

from .cache import get_cache
from .rate_limiter import fetch
from .lists import normalize_event
from ..tfrrs_selectors import (
    ATHLETE_HREF_RE,
    BASE_URL,
    BESTS_TABLE_INDOOR,
    BESTS_TABLE_OUTDOOR,
    MEET_HEADER_TH_CLASS,
    MEET_TABLE_CLASS,
    RESULT_HREF_RE,
)

logger = logging.getLogger(__name__)

# Wind values embedded in italic spans: "(1.2)" or "(-0.4)"
_WIND_RE = re.compile(r"\(([+-]?\d+\.?\d*)\)")
# Place + round: "4th (F)", "2nd (P)", "1st (H)"
_PLACE_RE = re.compile(r"(\d+)(?:st|nd|rd|th)?\s*(?:\((\w)\))?", re.IGNORECASE)


def _athlete_url(athlete_id: str, tfrrs_href: str) -> str:
    """Build full athlete page URL from href."""
    if tfrrs_href.startswith("http"):
        return tfrrs_href
    return BASE_URL + tfrrs_href


def _parse_bests_table(table) -> list[dict]:
    """
    Parse a season bests table (e.g. table.indoor_bests).
    Rows contain alternating event/mark cell pairs.
    Returns list of {event, mark, wind} dicts.
    """
    bests: list[dict] = []
    if not table:
        return bests

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        # Each row contains pairs: [event, mark, event, mark, ...]
        i = 0
        while i + 1 < len(cells):
            event_text = cells[i].get_text(strip=True)
            mark_cell = cells[i + 1]
            mark_full = mark_cell.get_text(strip=True)

            # Extract wind from mark string: "10.48 (1.2)"
            wind: Optional[float] = None
            wind_match = _WIND_RE.search(mark_full)
            if wind_match:
                try:
                    wind = float(wind_match.group(1))
                except ValueError:
                    pass
                mark_clean = _WIND_RE.sub("", mark_full).strip()
            else:
                mark_clean = mark_full

            if event_text and mark_clean:
                bests.append(
                    {
                        "event_raw": event_text,
                        "mark": mark_clean,
                        "wind": wind,
                    }
                )
            i += 2

    return bests


def _parse_meet_tables(soup: BeautifulSoup) -> list[dict]:
    """
    Parse all meet-by-meet result tables.
    Returns flat list of result dicts with meet info.
    """
    results: list[dict] = []

    # Tables with class "table table-hover >" (note trailing space and ">")
    for table in soup.find_all("table", class_=lambda c: c and "table-hover" in c):
        # Extract meet name and date from header th
        header_th = table.find("th", class_=MEET_HEADER_TH_CLASS)
        if not header_th:
            continue

        meet_link = header_th.find("a")
        meet_name = meet_link.get_text(strip=True) if meet_link else ""
        meet_href = meet_link.get("href", "") if meet_link else ""

        # Meet ID from href: /results/{id}/...
        meet_id_match = re.search(r"/results/(\d+)", meet_href)
        meet_id = meet_id_match.group(1) if meet_id_match else ""

        date_span = header_th.find("span")
        meet_date_raw = date_span.get_text(strip=True) if date_span else ""
        # Parse date string like "Apr 11, 2026"
        try:
            meet_date = datetime.strptime(meet_date_raw.strip(), "%b %d, %Y").date().isoformat()
        except (ValueError, AttributeError):
            meet_date = meet_date_raw.strip()

        # Each data row: event | mark (+wind) | place (round)
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            event_text = cells[0].get_text(strip=True)
            if not event_text:
                continue

            # Mark cell may have a link and a wind span
            mark_cell = cells[1]
            mark_link = mark_cell.find("a")
            mark_raw = mark_link.get_text(strip=True) if mark_link else mark_cell.get_text(strip=True)

            wind: Optional[float] = None
            wind_span = mark_cell.find("span")
            if wind_span:
                wind_text = wind_span.get_text(strip=True)
                w_match = _WIND_RE.match(wind_text)
                if w_match:
                    try:
                        wind = float(w_match.group(1))
                    except ValueError:
                        pass

            # Result href for meet_result_id
            result_href = mark_link.get("href", "") if mark_link else ""

            # Place column (may not exist)
            place_text = ""
            round_code = ""
            if len(cells) >= 3:
                place_raw = cells[2].get_text(strip=True)
                p_match = _PLACE_RE.search(place_raw)
                if p_match:
                    place_text = p_match.group(1)
                    round_code = p_match.group(2) or ""

            results.append(
                {
                    "meet_id": meet_id,
                    "meet": meet_name,
                    "meet_date": meet_date,
                    "event_raw": event_text,
                    "mark": mark_raw,
                    "wind": wind,
                    "place": place_text,
                    "round": round_code,
                    "result_href": result_href,
                }
            )

    return results


def roster_profile_rows(
    roster: list[dict],
    season: str,
    athlete_ids_already_covered: set[str],
) -> list[dict]:
    """
    Fetch TFRRS profile pages for every roster athlete whose athlete_id is NOT
    already in *athlete_ids_already_covered* (i.e. not found on any ranking list).

    Returns synthetic ranking-list rows for the uncovered athletes so that
    build_dataframe can treat them identically to list-sourced rows.  These
    rows carry real marks but rank=0 (no list position).

    Results are cached by fetch_athlete, so subsequent calls are instant.
    """
    rows: list[dict] = []
    bests_key = f"{season}_bests"

    for athlete in roster:
        aid = str(athlete.get("athlete_id", ""))
        if not aid or aid in athlete_ids_already_covered:
            continue

        tfrrs_href = athlete.get("tfrrs_href", "")
        if not tfrrs_href:
            continue

        try:
            data = fetch_athlete(aid, tfrrs_href)
        except Exception as exc:
            logger.warning("Could not fetch profile for %s: %s", athlete.get("name"), exc)
            continue

        bests: list[dict] = data.get(bests_key, [])
        for b in bests:
            event_raw = b.get("event_raw", "")
            mark = b.get("mark", "")
            if not event_raw or not mark:
                continue
            event_norm = normalize_event(event_raw)
            rows.append(
                {
                    "rank": 0,
                    "athlete_id": aid,
                    "athlete_name": athlete.get("name", ""),
                    "year": athlete.get("year", ""),
                    "team": "Villanova",
                    "mark": mark,
                    "meet": "",
                    "meet_date": "",
                    "wind": b.get("wind"),
                    "event": event_norm,
                    "gender": athlete.get("gender", "M"),
                    "list_key": f"profile_{season}",
                }
            )

    logger.info(
        "roster_profile_rows: fetched profiles for %d uncovered athletes → %d rows",
        sum(1 for a in roster if str(a.get("athlete_id")) not in athlete_ids_already_covered),
        len(rows),
    )
    return rows


def build_prev_marks_from_profiles(
    roster: list[dict],
    season: str,
) -> dict[str, dict[str, str]]:
    """
    Build a lookup of previous-season best marks for every roster athlete by
    scraping their individual TFRRS profile pages.

    Profile pages contain full career meet-by-meet results with dates, so we
    filter to the calendar year prior to the current season and keep the best
    (fastest / furthest) mark per event — determined by WA points internally,
    but stored as the raw mark string so downstream code can display it directly
    without being sensitive to WA coefficient changes between seasons.

    Returns: {athlete_id → {event → mark_string}}

    Profile pages are cached in SQLite after the first fetch, so subsequent
    calls are instant.
    """
    from ..processing.wa_points import score

    current_year = date.today().year
    # "Last season" is the calendar year before the current one.
    # For outdoor: the prior year's outdoor season (Mar–Aug).
    # For indoor: Jan–Mar of the prior year covers the main indoor season.
    last_year = current_year - 1

    lookup: dict[str, dict[str, str]] = {}

    for athlete in roster:
        aid = str(athlete.get("athlete_id", ""))
        tfrrs_href = athlete.get("tfrrs_href", "")
        gender = athlete.get("gender", "M")
        if not aid or not tfrrs_href:
            continue

        try:
            data = fetch_athlete(aid, tfrrs_href)
        except Exception as exc:
            logger.warning(
                "build_prev_marks_from_profiles: could not fetch %s: %s",
                athlete.get("name"), exc,
            )
            continue

        all_results = data.get("results", [])
        # Track best WA points seen (used only to pick the best mark per event;
        # the points themselves are NOT stored or used for comparison).
        athlete_best_pts: dict[str, int] = {}
        athlete_best_mark: dict[str, str] = {}

        for r in all_results:
            date_str = r.get("meet_date", "")
            try:
                result_year = int(date_str[:4]) if len(date_str) >= 4 else 0
            except (ValueError, TypeError):
                continue
            if result_year != last_year:
                continue

            event_norm = normalize_event(r.get("event_raw", ""))
            mark_str = r.get("mark", "")
            if not event_norm or not mark_str:
                continue

            pts = score(event_norm, gender, mark_str)
            if pts is None:
                continue

            if pts > athlete_best_pts.get(event_norm, -1):
                athlete_best_pts[event_norm] = pts
                athlete_best_mark[event_norm] = mark_str

        if athlete_best_mark:
            lookup[aid] = athlete_best_mark

    logger.info(
        "build_prev_marks_from_profiles: %d athletes have prev-season (%d) data",
        len(lookup), last_year,
    )
    return lookup


def fetch_athlete(athlete_id: str, tfrrs_href: str, season_best_key: str = "") -> dict:
    """
    Fetch (or return cached) athlete detail page.
    season_best_key is "{season}:{event}:{mark}" — used to invalidate cache.

    Returns dict:
    {
      "athlete_id": str,
      "indoor_bests": [...],
      "outdoor_bests": [...],
      "results": [...]   # meet-by-meet
    }
    """
    cache = get_cache()

    cached = cache.get_athlete(athlete_id, season_best_key)
    if cached:
        logger.debug("Athlete cache hit: %s", athlete_id)
        return cached

    url = _athlete_url(athlete_id, tfrrs_href)
    logger.info("Fetching athlete detail: %s", url)
    resp = fetch(url)
    html = resp.text
    cache.log("athlete_fetch", url=url, detail=athlete_id)

    soup = BeautifulSoup(html, "html.parser")

    indoor_table = soup.find("table", class_=lambda c: c and "indoor_bests" in (c or ""))
    outdoor_table = soup.find("table", class_=lambda c: c and "outdoor_bests" in (c or ""))

    data = {
        "athlete_id": athlete_id,
        "indoor_bests": _parse_bests_table(indoor_table),
        "outdoor_bests": _parse_bests_table(outdoor_table),
        "results": _parse_meet_tables(soup),
    }

    cache.set_athlete(athlete_id, data, season_best_key)
    return data
