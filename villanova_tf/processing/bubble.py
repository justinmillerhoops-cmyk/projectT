"""Bubble gap calculations — utilities used by composite.py and athlete_profile."""
from typing import Optional


def compute_bubble_gaps(
    event: str,
    gender: str,
    mark_str: str,
    wa_points: Optional[int],
    bubble_info: Optional[dict],
) -> tuple[Optional[float], Optional[int]]:
    """
    Returns (gap_mark, gap_points) relative to the historical bubble mark.
    Positive gap means the athlete is ahead of the bubble.
    Returns (None, None) if data is unavailable.
    """
    if not bubble_info or not mark_str:
        return None, None

    from ..scraper.bubble import _parse_mark_float, _is_time_event
    from .wa_points import score as wa_score

    bubble_mark = bubble_info.get("bubble_mark")
    if bubble_mark is None:
        return None, None

    perf_val = _parse_mark_float(mark_str, event)
    if perf_val is None:
        return None, None

    if _is_time_event(event):
        gap_mark = round(bubble_mark - perf_val, 4)  # positive = faster than bubble
    else:
        gap_mark = round(perf_val - bubble_mark, 4)  # positive = farther than bubble

    bubble_pts = wa_score(event, gender, str(bubble_mark))
    gap_points: Optional[int] = None
    if bubble_pts is not None and wa_points is not None:
        gap_points = wa_points - bubble_pts

    return gap_mark, gap_points
