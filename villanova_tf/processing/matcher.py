"""
Athlete matching: cross-reference Villanova roster against ranking list entries.

Priority order:
  1. Exact TFRRS athlete_id match (most reliable — present when list includes ID in URLs)
  2. Fuzzy name match via rapidfuzz
  3. Flag low-confidence matches for manual review
  4. Never silently drop unmatched athletes
"""
import logging
import re
from typing import Optional

from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = 85  # below this score → flag for manual review


def _normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, normalize whitespace."""
    name = name.lower()
    name = re.sub(r"[',.-]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def _name_variants(name: str) -> list[str]:
    """Generate name variants: original + 'Last First' swap if comma present."""
    variants = [_normalize_name(name)]
    if "," in name:
        parts = name.split(",", 1)
        swapped = f"{parts[1].strip()} {parts[0].strip()}"
        variants.append(_normalize_name(swapped))
    return variants


def match_roster_to_list(
    roster: list[dict],
    list_rows: list[dict],
    threshold: int = _DEFAULT_THRESHOLD,
) -> tuple[list[dict], list[dict]]:
    """
    For each roster athlete, find their best match in list_rows.

    Returns:
      matched:   list of {**roster_athlete, "list_row": <matching row>, "match_score": int, "match_method": str}
      unmatched: list of {**roster_athlete, "match_score": int, "best_candidate": str}
    """
    # Build lookup: athlete_id → list of rows
    id_to_rows: dict[str, list[dict]] = {}
    for row in list_rows:
        aid = row.get("athlete_id")
        if aid:
            id_to_rows.setdefault(aid, []).append(row)

    # Build name corpus for fuzzy matching: normalized name → list of rows
    name_corpus: dict[str, list[dict]] = {}
    for row in list_rows:
        for variant in _name_variants(row.get("athlete_name", "")):
            name_corpus.setdefault(variant, []).append(row)
    corpus_names = list(name_corpus.keys())

    matched: list[dict] = []
    unmatched: list[dict] = []

    for athlete in roster:
        aid = str(athlete.get("athlete_id", ""))
        gender = athlete.get("gender", "")

        # Strategy 1: ID match
        if aid and aid in id_to_rows:
            for row in id_to_rows[aid]:
                # Filter by gender if both present
                if gender and row.get("gender") and row["gender"] != gender:
                    continue
                matched.append(
                    {
                        **athlete,
                        "list_row": row,
                        "match_score": 100,
                        "match_method": "id",
                    }
                )
            if id_to_rows[aid]:
                continue  # found via ID, skip fuzzy

        # Strategy 2: fuzzy name match
        if not corpus_names:
            unmatched.append({**athlete, "match_score": 0, "best_candidate": ""})
            continue

        best_matches = []
        for variant in _name_variants(athlete.get("name", "")):
            result = process.extractOne(
                variant,
                corpus_names,
                scorer=fuzz.token_sort_ratio,
            )
            if result:
                best_matches.append(result)

        if not best_matches:
            unmatched.append({**athlete, "match_score": 0, "best_candidate": ""})
            continue

        best = max(best_matches, key=lambda r: r[1])
        best_name, score, _ = best

        if score < threshold:
            logger.debug(
                "No confident match for %s (best fuzzy candidate=%s, score=%d)",
                athlete["name"], best_name, score,
            )
            unmatched.append(
                {
                    **athlete,
                    "match_score": score,
                    "best_candidate": best_name,
                }
            )
            continue

        for row in name_corpus[best_name]:
            if gender and row.get("gender") and row["gender"] != gender:
                continue
            matched.append(
                {
                    **athlete,
                    "list_row": row,
                    "match_score": score,
                    "match_method": "fuzzy",
                }
            )

    logger.info(
        "Matching: %d roster athletes → %d matched rows, %d unmatched",
        len(roster), len(matched), len(unmatched),
    )
    return matched, unmatched


def apply_manual_overrides(
    matched: list[dict],
    unmatched: list[dict],
    overrides: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Apply manual name match overrides from admin UI.
    overrides is a list of {athlete_id, list_athlete_name, event}.
    """
    override_map = {str(o["athlete_id"]): o for o in overrides}

    still_unmatched = []
    for athlete in unmatched:
        aid = str(athlete.get("athlete_id", ""))
        if aid in override_map:
            o = override_map[aid]
            # Create a synthetic list row for this manual match
            matched.append(
                {
                    **athlete,
                    "list_row": {
                        "athlete_name": o.get("list_athlete_name", ""),
                        "event": o.get("event", ""),
                        "mark": o.get("mark", ""),
                        "rank": o.get("rank"),
                        "gender": athlete.get("gender", ""),
                    },
                    "match_score": 100,
                    "match_method": "manual",
                }
            )
        else:
            still_unmatched.append(athlete)

    return matched, still_unmatched
