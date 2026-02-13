from __future__ import annotations

from datetime import date as dt_date, datetime as dt_datetime
from typing import Literal

from pydantic import BaseModel, Field


class PerformanceRow(BaseModel):
    athlete_name: str
    team: str
    gender: Literal["M", "F"]
    season: Literal["indoor", "outdoor"]
    event: str
    mark_raw: str
    mark_value: float | None
    mark_units: Literal["seconds", "meters", "points"] | None
    wind: float | None = None
    altitude_flag: bool | None = None
    wind_legal: bool | None = None
    meet_name: str | None = None
    meet_date: dt_date | None = None
    scope: str
    source_file: str
    file_modified_at: dt_datetime
    ingested_at: dt_datetime
    confidence: Literal["HIGH", "LOW"] = "HIGH"
    issues: list[str] = Field(default_factory=list)


class FileClassification(BaseModel):
    file_type: Literal["current", "confmeet"]
    season: Literal["indoor", "outdoor"]
    gender: Literal["M", "F", "BOTH"] = "BOTH"
    scope: str
    date: dt_date | None = None
    year: int | None = None


class IngestAudit(BaseModel):
    ingest_timestamp: dt_datetime
    files_processed: int
    rows_created: int
    warnings: list[str] = Field(default_factory=list)
    file_hashes: dict[str, str] = Field(default_factory=dict)
