"""
One-time/manual scraper for NCAA championship entry lists (bubble reference).
Fetches the last N completed championship seasons and finds the last qualifying mark per event.
Result is written to data/bubble_reference.json.

Run manually from the Admin tab or command line after each championship season.
"""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .lists import fetch_list, normalize_event
from ..tfrrs_selectors import LIST_IDS

logger = logging.getLogger(__name__)

_OUTPUT_PATH = Path(__file__).parent.parent / "data" / "bubble_reference.json"

# Events whose marks are times (lower = better)
_TIME_EVENTS = {
    "60m", "100m", "200m", "400m", "800m", "1500m", "mile",
    "3000m", "5000m", "10000m", "3000sc",
    "60h", "100h", "110h", "400h",
}


def _is_time_event(event: str) -> bool:
    return event in _TIME_EVENTS


def _parse_mark_float(mark: str, event: str) -> Optional[float]:
    """
    Parse a display mark string to a float in consistent units.
    Track: seconds (handles h:mm:ss.xx and mm:ss.xx and ss.xx)
    Field: meters (handles "18.45m", "1.95m", "6-02.50" imperial)
    """
    mark = mark.strip()
    if not mark:
        return None

    if _is_time_event(event):
        # Handle h:mm:ss.xx or mm:ss.xx or ss.xx
        parts = mark.split(":")
        try:
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            else:
                return float(parts[0])
        except ValueError:
            return None
    else:
        # Field events: could be "18.45", "18.45m", "1.95m", "6-02.50" (imperial)
        mark = mark.rstrip("m").strip()
        # Imperial format "6-02.50" → feet-inches
        imp_match = re.match(r"^(\d+)-(\d+\.?\d*)$", mark)
        if imp_match:
            feet = float(imp_match.group(1))
            inches = float(imp_match.group(2))
            return (feet * 12 + inches) * 0.0254  # to meters
        try:
            return float(mark)
        except ValueError:
            return None


def _unit_for_event(event: str) -> str:
    if _is_time_event(event):
        return "seconds"
    if event in ("high_jump", "pole_vault", "long_jump", "triple_jump"):
        return "meters"
    return "meters"


def build_bubble_reference(config: dict) -> dict:
    """
    For each historical list, find the last-place qualifying mark per event.
    Returns the reference structure to be saved to bubble_reference.json.

    Slugs are sourced from config keys ncaa_outdoor_history_slugs and
    ncaa_indoor_history_slugs (int-keyed dicts).  Update config.yaml when
    TFRRS renames a historical list — no code change required.
    """
    outdoor_list_ids = config.get("list_ids", {}).get("ncaa_outdoor_history", [])
    indoor_list_ids = config.get("list_ids", {}).get("ncaa_indoor_history", [])

    # Read slugs from config; fall back to empty dict (will warn per list_id)
    outdoor_slugs = {int(k): v for k, v in config.get("ncaa_outdoor_history_slugs", {}).items()}
    indoor_slugs = {int(k): v for k, v in config.get("ncaa_indoor_history_slugs", {}).items()}

    def _fetch_history(list_id: int, slug: str) -> list[dict]:
        fake_config = {
            "list_ids": {f"hist_{list_id}": list_id},
            "list_slugs": {f"hist_{list_id}": slug},
            "list_base_urls": {f"hist_{list_id}": "https://tf.tfrrs.org"},
        }
        return fetch_list(f"hist_{list_id}", fake_config, ttl_hours=8760)  # 1 year

    def _process_season(list_ids: list[int], slugs: dict) -> dict:
        per_event_per_year: dict[str, dict[int, float]] = {}

        for list_id in list_ids:
            slug = slugs.get(list_id, "")
            if not slug:
                logger.warning("No slug for list ID %d", list_id)
                continue
            rows = _fetch_history(list_id, slug)
            for row in rows:
                event = row["event"]
                if not event:
                    continue
                mark_val = _parse_mark_float(row.get("mark", ""), event)
                if mark_val is None:
                    continue
                if event not in per_event_per_year:
                    per_event_per_year[event] = {}
                # Track the worst (last qualifying) mark
                existing = per_event_per_year[event].get(list_id)
                if existing is None:
                    per_event_per_year[event][list_id] = mark_val
                elif _is_time_event(event):
                    per_event_per_year[event][list_id] = max(existing, mark_val)
                else:
                    per_event_per_year[event][list_id] = min(existing, mark_val)

        # Average across years
        result: dict[str, dict] = {}
        for event, year_marks in per_event_per_year.items():
            vals = list(year_marks.values())
            if vals:
                avg = sum(vals) / len(vals)
                result[event] = {
                    "bubble_mark": round(avg, 4),
                    "unit": _unit_for_event(event),
                    "years": sorted(year_marks.keys()),
                }
        return result

    logger.info("Building outdoor bubble reference from %d seasons...", len(outdoor_list_ids))
    outdoor = _process_season(outdoor_list_ids, outdoor_slugs)

    logger.info("Building indoor bubble reference from %d seasons...", len(indoor_list_ids))
    indoor = _process_season(indoor_list_ids, indoor_slugs)

    return {
        "indoor": indoor,
        "outdoor": outdoor,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def save_bubble_reference(data: dict, path: Optional[Path] = None) -> None:
    out_path = path or _OUTPUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info("Bubble reference saved to %s", out_path)


_STALE_DAYS = 30


def load_bubble_reference(path: Optional[Path] = None) -> dict:
    p = path or _OUTPUT_PATH
    if not p.exists():
        return {"indoor": {}, "outdoor": {}}
    with open(p) as f:
        data = json.load(f)

    generated_at = data.get("generated_at")
    if generated_at:
        try:
            age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(generated_at)).days
            if age_days > _STALE_DAYS:
                logger.warning(
                    "Bubble reference is %d days old (threshold %d). "
                    "Consider rebuilding via Admin tab.",
                    age_days, _STALE_DAYS,
                )
        except (ValueError, TypeError):
            pass
    else:
        logger.warning("Bubble reference has no generated_at timestamp; rebuild recommended.")

    return data
