from __future__ import annotations

from datetime import date, datetime
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
    meet_date: date | None = None
    scope: str
    source_file: str
    file_modified_at: datetime
    ingested_at: datetime
    confidence: Literal["HIGH", "LOW"] = "HIGH"
    issues: list[str] = Field(default_factory=list)


class FileClassification(BaseModel):
    file_type: Literal["current", "confmeet"]
    season: Literal["indoor", "outdoor"]
    gender: Literal["M", "F", "BOTH"] = "BOTH"
    scope: str
    date: date | None = None
    year: int | None = None


class IngestAudit(BaseModel):
    ingest_timestamp: datetime
    files_processed: int
    rows_created: int
    warnings: list[str] = Field(default_factory=list)
    file_hashes: dict[str, str] = Field(default_factory=dict)
