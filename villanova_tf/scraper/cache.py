"""
SQLite-backed cache for all scraped data.

Tables:
  ranking_list_cache  — full HTML of ranking list pages, expires after TTL
  athlete_cache       — athlete detail data (JSON), expires when season best changes
  scrape_log          — audit log of all scrape activity
"""
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "cache.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ranking_list_cache (
    list_key    TEXT PRIMARY KEY,
    html        TEXT NOT NULL,
    fetched_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS athlete_cache (
    athlete_id      TEXT PRIMARY KEY,
    data_json       TEXT NOT NULL,
    season_best_key TEXT NOT NULL,   -- "{season}:{event}:{mark}" — invalidates on change
    fetched_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scrape_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    action      TEXT NOT NULL,
    url         TEXT,
    status      TEXT,
    detail      TEXT
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Cache:
    def __init__(self, db_path: Optional[str] = None):
        db_path_obj = Path(db_path) if db_path else _DEFAULT_DB_PATH
        try:
            db_path_obj.parent.mkdir(parents=True, exist_ok=True)
            # Test that the directory is writable
            _write_test = db_path_obj.parent / ".write_test"
            _write_test.touch()
            _write_test.unlink()
        except OSError:
            logger.warning(
                "Data directory %s is not writable; using /tmp fallback",
                db_path_obj.parent,
            )
            db_path_obj = Path("/tmp/villanova_tf_cache/cache.db")
            db_path_obj.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(db_path_obj), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Ranking list cache
    # ------------------------------------------------------------------

    def get_ranking_list(self, list_key: str, ttl_hours: float = 24) -> Optional[str]:
        row = self._conn.execute(
            "SELECT html, fetched_at FROM ranking_list_cache WHERE list_key = ?",
            (list_key,),
        ).fetchone()
        if not row:
            return None
        fetched = datetime.fromisoformat(row["fetched_at"])
        age_hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
        if age_hours > ttl_hours:
            logger.debug("Cache expired for %s (%.1fh old)", list_key, age_hours)
            return None
        return row["html"]

    def set_ranking_list(self, list_key: str, html: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO ranking_list_cache (list_key, html, fetched_at) VALUES (?,?,?)",
            (list_key, html, _now_iso()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Athlete detail cache
    # ------------------------------------------------------------------

    def get_athlete(self, athlete_id: str, current_season_best_key: str) -> Optional[dict]:
        """
        Returns cached athlete data if season best hasn't changed.
        current_season_best_key is "{season}:{event}:{mark}" from the ranking list.
        Pass None to skip invalidation check (always return cached if present).
        """
        row = self._conn.execute(
            "SELECT data_json, season_best_key FROM athlete_cache WHERE athlete_id = ?",
            (athlete_id,),
        ).fetchone()
        if not row:
            return None
        if current_season_best_key and row["season_best_key"] != current_season_best_key:
            logger.debug(
                "Athlete %s cache invalidated: best changed %s → %s",
                athlete_id, row["season_best_key"], current_season_best_key,
            )
            return None
        return json.loads(row["data_json"])

    def set_athlete(self, athlete_id: str, data: dict, season_best_key: str) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO athlete_cache
               (athlete_id, data_json, season_best_key, fetched_at)
               VALUES (?,?,?,?)""",
            (athlete_id, json.dumps(data), season_best_key, _now_iso()),
        )
        self._conn.commit()

    def get_athlete_last_fetched(self, athlete_id: str) -> Optional[datetime]:
        row = self._conn.execute(
            "SELECT fetched_at FROM athlete_cache WHERE athlete_id = ?",
            (athlete_id,),
        ).fetchone()
        if not row:
            return None
        return datetime.fromisoformat(row["fetched_at"])

    # ------------------------------------------------------------------
    # Scrape log
    # ------------------------------------------------------------------

    def log(self, action: str, url: str = None, status: str = "ok", detail: str = None) -> None:
        self._conn.execute(
            "INSERT INTO scrape_log (ts, action, url, status, detail) VALUES (?,?,?,?,?)",
            (_now_iso(), action, url, status, detail),
        )
        self._conn.commit()

    def get_recent_log(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ts, action, url, status, detail FROM scrape_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_last_refresh(self, list_key: str) -> Optional[datetime]:
        row = self._conn.execute(
            "SELECT fetched_at FROM ranking_list_cache WHERE list_key = ?",
            (list_key,),
        ).fetchone()
        if not row:
            return None
        return datetime.fromisoformat(row["fetched_at"])

    def close(self) -> None:
        self._conn.close()


# Module-level singleton
_cache_instance: Optional[Cache] = None


def get_cache(db_path: Optional[str] = None) -> Cache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = Cache(db_path)
    return _cache_instance
