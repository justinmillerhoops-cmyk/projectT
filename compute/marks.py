from __future__ import annotations

import re
from dataclasses import dataclass

INVALID_MARKS = {"DNS", "DNF", "FOUL", "NM", "NH", "NT"}


EVENT_CONFIG: dict[str, dict[str, object]] = {
    "100m": {"direction": "lower_is_better", "wind_applicable": True, "units": "seconds", "type": "track"},
    "200m": {"direction": "lower_is_better", "wind_applicable": True, "units": "seconds", "type": "track"},
    "400m": {"direction": "lower_is_better", "wind_applicable": False, "units": "seconds", "type": "track"},
    "800m": {"direction": "lower_is_better", "wind_applicable": False, "units": "seconds", "type": "track"},
    "1500m": {"direction": "lower_is_better", "wind_applicable": False, "units": "seconds", "type": "track"},
    "5000m": {"direction": "lower_is_better", "wind_applicable": False, "units": "seconds", "type": "track"},
    "100mH": {"direction": "lower_is_better", "wind_applicable": True, "units": "seconds", "type": "track"},
    "110mH": {"direction": "lower_is_better", "wind_applicable": True, "units": "seconds", "type": "track"},
    "400mH": {"direction": "lower_is_better", "wind_applicable": False, "units": "seconds", "type": "track"},
    "4x100m": {"direction": "lower_is_better", "wind_applicable": False, "units": "seconds", "type": "relay"},
    "4x400m": {"direction": "lower_is_better", "wind_applicable": False, "units": "seconds", "type": "relay"},
    "Long Jump": {"direction": "higher_is_better", "wind_applicable": True, "units": "meters", "type": "field"},
    "Triple Jump": {"direction": "higher_is_better", "wind_applicable": True, "units": "meters", "type": "field"},
    "High Jump": {"direction": "higher_is_better", "wind_applicable": False, "units": "meters", "type": "field"},
    "Pole Vault": {"direction": "higher_is_better", "wind_applicable": False, "units": "meters", "type": "field"},
    "Shot Put": {"direction": "higher_is_better", "wind_applicable": False, "units": "meters", "type": "field"},
    "Discus": {"direction": "higher_is_better", "wind_applicable": False, "units": "meters", "type": "field"},
    "Hammer": {"direction": "higher_is_better", "wind_applicable": False, "units": "meters", "type": "field"},
    "Javelin": {"direction": "higher_is_better", "wind_applicable": False, "units": "meters", "type": "field"},
    "Decathlon": {"direction": "higher_is_better", "wind_applicable": False, "units": "points", "type": "multi"},
    "Heptathlon": {"direction": "higher_is_better", "wind_applicable": False, "units": "points", "type": "multi"},
    "Pentathlon": {"direction": "higher_is_better", "wind_applicable": False, "units": "points", "type": "multi"},
}


@dataclass
class MarkParseResult:
    mark_value: float | None
    mark_units: str | None
    wind: float | None
    altitude_flag: bool | None
    wind_legal: bool | None
    confidence: str
    issues: list[str]


def _feet_inches_to_meters(mark: str) -> float | None:
    m = re.match(r"^\s*(\d+)'\s*(\d+(?:\.\d+)?)\"\s*$", mark)
    if not m:
        return None
    feet, inches = float(m.group(1)), float(m.group(2))
    return (feet * 12 + inches) * 0.0254


def _parse_time_to_seconds(mark: str) -> float | None:
    if ":" in mark:
        mm, ss = mark.split(":", 1)
        return float(mm) * 60 + float(ss)
    return float(mark)


def parse_mark(mark_raw: str, event: str, wind_raw: str | None = None, altitude_raw: str | None = None) -> MarkParseResult:
    cleaned = (mark_raw or "").strip()
    issues: list[str] = []
    confidence = "HIGH"

    altitude_flag = "^" in cleaned or (altitude_raw or "").strip() == "^"
    cleaned = cleaned.replace("^", "").strip()

    if cleaned.upper() in INVALID_MARKS:
        return MarkParseResult(None, None, None, altitude_flag, None, "LOW", [f"invalid_outcome:{cleaned.upper()}"])

    cfg = EVENT_CONFIG.get(event)
    if not cfg:
        return MarkParseResult(None, None, None, altitude_flag, None, "LOW", ["unknown_event_config"])

    wind = None
    if wind_raw:
        try:
            wind = float(wind_raw)
        except ValueError:
            issues.append("invalid_wind")
            confidence = "LOW"

    try:
        if cfg["units"] == "seconds":
            mark_value = _parse_time_to_seconds(cleaned.lower().replace("h", ""))
        elif cfg["units"] == "meters":
            fi = _feet_inches_to_meters(cleaned)
            mark_value = fi if fi is not None else float(cleaned)
        else:
            mark_value = float(int(float(cleaned)))
    except Exception:
        return MarkParseResult(None, cfg["units"], wind, altitude_flag, None, "LOW", ["unparseable_mark"])

    wind_legal = None
    if cfg["wind_applicable"]:
        if wind is None:
            confidence = "LOW"
            issues.append("wind_missing")
        else:
            wind_legal = wind <= 2.0
            if not wind_legal:
                confidence = "LOW"
                issues.append("wind_illegal_tailwind")

    return MarkParseResult(mark_value, cfg["units"], wind, altitude_flag, wind_legal, confidence, issues)
