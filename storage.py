from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

CACHE_DIR = Path("data/cache")
AUDIT_DIR = Path("data/audit")
STATE_FILE = CACHE_DIR / "state.json"


def ensure_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def save_cache(name: str, df: pd.DataFrame) -> Path:
    ensure_dirs()
    path = CACHE_DIR / f"{name}.parquet"
    df.to_parquet(path, index=False)
    return path


def load_cache(name: str) -> pd.DataFrame:
    path = CACHE_DIR / f"{name}.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def write_state(last_data_added: str | None, last_successful_refresh: str | None, coverage: dict) -> None:
    ensure_dirs()
    payload = {
        "last_data_added": last_data_added,
        "last_successful_refresh": last_successful_refresh,
        "coverage": coverage,
    }
    STATE_FILE.write_text(json.dumps(payload, indent=2))


def read_state() -> dict:
    if not STATE_FILE.exists():
        return {"last_data_added": None, "last_successful_refresh": None, "coverage": {}}
    return json.loads(STATE_FILE.read_text())


def write_audit(files_processed: int, rows_created: int, warnings: list[str], file_hashes: dict[str, str]) -> Path:
    ensure_dirs()
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    p = AUDIT_DIR / f"{ts}.json"
    p.write_text(
        json.dumps(
            {
                "ingest_timestamp": ts,
                "files_processed": files_processed,
                "rows_created": rows_created,
                "warnings": warnings,
                "file_hashes": file_hashes,
            },
            indent=2,
        )
    )
    return p


def read_recent_audits(limit: int = 20) -> list[dict]:
    ensure_dirs()
    files = sorted(AUDIT_DIR.glob("*.json"), reverse=True)[:limit]
    return [json.loads(p.read_text()) for p in files]
