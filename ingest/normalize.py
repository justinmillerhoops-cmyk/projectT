from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from compute.marks import parse_mark
from ingest.schema import FileClassification, PerformanceRow


def _pick_col(columns: list[str], candidates: list[str]) -> str | None:
    cols = {c.lower(): c for c in columns}
    for c in candidates:
        if c in cols:
            return cols[c]
    return None


def normalize_tables(
    tables: list[pd.DataFrame],
    cls: FileClassification,
    source_file: Path,
    modified_at: datetime,
) -> list[PerformanceRow]:
    rows: list[PerformanceRow] = []
    for t in tables:
        df = t.copy()
        df.columns = [str(c).strip() for c in df.columns]
        athlete_col = _pick_col(list(df.columns), ["athlete", "name", "competitor"])
        team_col = _pick_col(list(df.columns), ["team", "school", "institution"])
        event_col = _pick_col(list(df.columns), ["event"])
        mark_col = _pick_col(list(df.columns), ["mark", "time", "result", "performance"])
        wind_col = _pick_col(list(df.columns), ["wind"])
        altitude_col = _pick_col(list(df.columns), ["alt", "altitude"])

        if not athlete_col or not team_col or not event_col or not mark_col:
            continue

        for _, r in df.iterrows():
            athlete = str(r.get(athlete_col, "")).strip()
            team = str(r.get(team_col, "")).strip()
            event = str(r.get(event_col, "")).strip()
            mark_raw = str(r.get(mark_col, "")).strip()
            if not athlete or not team or not event or not mark_raw:
                continue

            wind_raw = str(r.get(wind_col, "")).strip() if wind_col else None
            alt_raw = str(r.get(altitude_col, "")).strip() if altitude_col else None
            parsed = parse_mark(mark_raw, event, wind_raw, alt_raw)

            genders = [cls.gender] if cls.gender != "BOTH" else ["M", "F"]
            for g in genders:
                rows.append(
                    PerformanceRow(
                        athlete_name=athlete,
                        team=team,
                        gender=g,
                        season=cls.season,
                        event=event,
                        mark_raw=mark_raw,
                        mark_value=parsed.mark_value,
                        mark_units=parsed.mark_units,
                        wind=parsed.wind,
                        altitude_flag=parsed.altitude_flag,
                        wind_legal=parsed.wind_legal,
                        meet_name=None,
                        meet_date=cls.date,
                        scope=cls.scope,
                        source_file=source_file.name,
                        file_modified_at=modified_at,
                        ingested_at=datetime.utcnow(),
                        confidence=parsed.confidence,
                        issues=parsed.issues,
                    )
                )
    return rows
