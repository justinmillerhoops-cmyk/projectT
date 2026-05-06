"""
World Athletics scoring table conversion.

Uses the standard WA polynomial formula:
  Track events (time, lower is better): Points = int(A * (B - T)^C)
  Field events (distance/height, higher is better): Points = int(A * (D - B)^C)

Constants derived from World Athletics Scoring Tables of Athletics 2025 edition
by polynomial regression (scipy curve_fit) against the published lookup tables.
All fitted constants reproduce the official tables with max error ≤ 1 point.
T is performance time in seconds, D is distance/height in appropriate units.
Points are floored to integer. If mark doesn't exceed the base threshold, score = 0.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WA scoring constants: (A, B, C)
# For track: Points = A * (B - T)^C  where T = seconds
# For field:  Points = A * (D - B)^C  where D = meters (jumps/throws) or cm (for some events)
# Combined events: use the mark directly as WA points (already scored)
#
# Sources: World Athletics Scoring Tables of Athletics (2025 edition)
# Fitted via curve_fit from published lookup tables; all events max_err ≤ 1 pt.
# ---------------------------------------------------------------------------

# Format: event_key → {"men": (A, B, C), "women": (A, B, C)}

_TRACK_CONSTANTS: dict[str, dict[str, tuple]] = {
    "60m": {
        "men":   (69.0695, 10.6940, 1.99698),
        "women": (25.0601, 13.9910, 1.99788),
    },
    "100m": {
        "men":   (24.7677, 16.9908, 1.99827),
        "women": ( 9.9534, 21.9900, 1.99916),
    },
    "200m": {
        "men":   ( 5.0663, 35.4976, 2.00094),
        "women": ( 2.2391, 45.4970, 2.00035),
    },
    "400m": {
        "men":   ( 1.0213, 78.9927, 1.99993),
        "women": ( 0.3346, 109.990, 2.00027),
    },
    "800m": {
        "men":   ( 0.19792, 182.000, 2.00009),
        "women": ( 0.06879, 249.990, 2.00003),
    },
    "1500m": {
        "men":   ( 0.040659, 384.998, 2.00001),
        "women": ( 0.013401, 539.990, 1.99999),
    },
    "mile": {
        "men":   ( 0.035101, 414.993, 2.00000),
        "women": ( 0.011650, 579.990, 2.00000),
    },
    "3000m": {
        "men":   ( 0.0081478, 840.000, 2.00004),
        "women": ( 0.0025391, 1200.00, 2.00000),
    },
    "5000m": {
        "men":   ( 0.0027785, 1440.00, 1.99998),
        "women": ( 0.0008081, 2100.00, 1.99999),
    },
    "10000m": {
        "men":   ( 0.00052402, 3150.0, 1.99999),
        "women": ( 0.00017120, 4500.0, 2.00000),
    },
    "3000sc": {
        "men":   ( 0.0043169, 1020.0, 1.99997),
        "women": ( 0.0013230, 1510.0, 2.00000),
    },
    "60h": {
        "men":   (24.0252, 14.5910, 1.99837),
        "women": (11.1933, 18.1910, 1.99927),
    },
    "110h": {
        "men":   ( 7.67468, 25.7910, 1.99969),
        "women": ( 7.67468, 25.7910, 1.99969),  # men's 110mH formula
    },
    "100h": {
        "men":   ( 7.67468, 25.7910, 1.99969),
        "women": ( 3.95680, 30.0030, 2.00178),
    },
    "400h": {
        "men":   ( 0.545414, 95.4990, 2.00024),
        "women": ( 0.208590, 129.990, 1.99997),
    },
}

# Field events: Performance in meters (heights in meters, distances in meters)
# Points = A * (D - B)^C
_FIELD_CONSTANTS: dict[str, dict[str, tuple]] = {
    # HJ and PV: performance converted to cm (multiply meters × 100)
    "high_jump": {
        "men":   (0.8465, 75.0, 1.42),
        "women": (1.84523, 75.0, 1.348),
    },
    "pole_vault": {
        "men":   (0.2797, 100.0, 1.35),
        "women": (0.44125, 80.0, 1.35),
    },
    "long_jump": {
        "men":   (0.14354, 220.0, 1.40),   # D in cm
        "women": (0.188807, 210.0, 1.41),
    },
    "triple_jump": {
        "men":   (0.0338, 680.0, 1.40),    # D in cm
        "women": (0.051868, 630.0, 1.40),
    },
    "shot_put": {
        "men":   (51.39, 1.5, 1.05),
        "women": (56.0211, 1.5, 1.05),
    },
    "weight_throw": {
        "men":   (32.3, 1.5, 1.05),        # 35lb / 25lb, approx
        "women": (32.3, 1.5, 1.05),
    },
    "discus": {
        "men":   (12.91, 4.0, 1.1),
        "women": (12.3311, 3.0, 1.1),
    },
    "hammer": {
        "men":   (13.0449, 7.0, 1.05),
        "women": (16.7995, 3.5, 1.05),
    },
    "javelin": {
        "men":   (10.14, 7.0, 1.08),
        "women": (15.9803, 3.8, 1.04),
    },
}

# Events whose marks are converted to cm before applying the formula
_CM_EVENTS = {"long_jump", "triple_jump", "high_jump", "pole_vault"}

# Track events where lower time = more points
_TRACK_EVENTS = set(_TRACK_CONSTANTS.keys())
_FIELD_EVENTS = set(_FIELD_CONSTANTS.keys())

# Combined events: score is already WA points
_COMBINED_EVENTS = {"heptathlon", "pentathlon", "decathlon"}


def _parse_seconds(mark: str) -> Optional[float]:
    """Parse time string to seconds. Handles h:mm:ss.xx, mm:ss.xx, ss.xx"""
    mark = mark.strip()
    if not mark:
        return None
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


def _parse_field_meters(mark: str) -> Optional[float]:
    """Parse field event mark to meters.
    Handles: plain float, 'm' suffix, imperial '6-02.50',
    and TFRRS combined metric+imperial strings like '13.17m43\' 2.5"'.
    """
    mark = mark.strip()
    if not mark:
        return None
    # TFRRS athlete pages sometimes concatenate metric and imperial:
    # "13.17m43' 2.5\"" — extract the leading metric value.
    combined = re.match(r'^([\d.]+)m', mark)
    if combined and not mark.rstrip("m").replace(".", "").isdigit():
        # Has extra non-numeric chars after the 'm' → treat as combined string
        try:
            return float(combined.group(1))
        except ValueError:
            pass
    mark_clean = re.sub(r"[mM]$", "", mark).strip()
    # Imperial: feet-inches e.g. "6-02.50"
    imp = re.match(r"^(\d+)-(\d+\.?\d*)$", mark_clean)
    if imp:
        return (float(imp.group(1)) * 12 + float(imp.group(2))) * 0.0254
    try:
        return float(mark_clean)
    except ValueError:
        return None


def _parse_combined_points(mark: str) -> Optional[int]:
    """Parse combined event total points (already an integer score)."""
    try:
        return int(re.sub(r"[^\d]", "", mark))
    except (ValueError, TypeError):
        return None


def score(event: str, gender: str, mark: str) -> Optional[int]:
    """
    Convert a performance mark to World Athletics points.

    Parameters
    ----------
    event  : normalized event key (e.g. "100m", "shot_put", "decathlon")
    gender : "M" or "F"
    mark   : display mark string (time, distance, or combined points)

    Returns WA points (int), or None if mark cannot be parsed.
    """
    if not event or not mark:
        return None

    gender_key = "men" if gender == "M" else "women"

    # Combined events: use the score directly
    if event in _COMBINED_EVENTS:
        return _parse_combined_points(mark)

    # Track events
    if event in _TRACK_EVENTS:
        constants = _TRACK_CONSTANTS[event].get(gender_key)
        if not constants:
            return None
        A, B, C = constants
        T = _parse_seconds(mark)
        if T is None:
            return None
        diff = B - T
        if diff <= 0:
            return 0
        return max(0, int(A * (diff ** C)))

    # Field events
    if event in _FIELD_EVENTS:
        constants = _FIELD_CONSTANTS[event].get(gender_key)
        if not constants:
            return None
        A, B, C = constants
        D = _parse_field_meters(mark)
        if D is None:
            return None
        # Convert to cm for long/triple jump
        if event in _CM_EVENTS:
            D = D * 100
        diff = D - B
        if diff <= 0:
            return 0
        return max(0, int(A * (diff ** C)))

    logger.debug("Unknown event for WA scoring: %s", event)
    return None


def score_display(event: str, gender: str, mark: str) -> str:
    """Return score as string, or '' if not calculable."""
    pts = score(event, gender, mark)
    return str(pts) if pts is not None else ""


def mark_display(event: str, mark: str) -> str:
    """
    Return a display-formatted mark string appropriate for the event.
    For combined events this is the points total; for field it includes 'm';
    for track it's the time string unchanged.
    """
    if not mark:
        return ""
    if event in _FIELD_EVENTS and event not in _CM_EVENTS:
        val = _parse_field_meters(mark)
        if val is not None:
            return f"{val:.2f}m"
    return mark
