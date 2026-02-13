from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ingest.schema import FileClassification

CURRENT_RE = re.compile(
    r"^current__(indoor|outdoor)__(M|F)__(BIGEAST|NCAA_INDOOR_QUAL|NCAA_OUTDOOR_EAST_QUAL|OTHER)__(\d{4}-\d{2}-\d{2})__\.html$"
)
CONFMEET_RE = re.compile(r"^confmeet__BIGEAST__(indoor|outdoor)__(\d{4})__\.html$")


@dataclass
class ScannedFile:
    path: Path
    file_hash: str
    modified_ts: float
    classification: FileClassification | None


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_filename(name: str) -> FileClassification | None:
    m = CURRENT_RE.match(name)
    if m:
        season, gender, scope, d = m.groups()
        return FileClassification(file_type="current", season=season, gender=gender, scope=scope, date=date.fromisoformat(d))
    m = CONFMEET_RE.match(name)
    if m:
        season, year = m.groups()
        return FileClassification(file_type="confmeet", season=season, gender="BOTH", scope="confmeet_BIGEAST", year=int(year))
    return None


def load_classifications(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_classifications(path: Path, data: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def scan_folder(folder: Path, class_path: Path) -> list[ScannedFile]:
    user_class = load_classifications(class_path)
    out: list[ScannedFile] = []
    for p in sorted(folder.glob("*")):
        if not p.is_file() or p.suffix.lower() not in {".html", ".csv"}:
            continue
        h = file_hash(p)
        cls = parse_filename(p.name)
        if cls is None and h in user_class:
            cls = FileClassification(**user_class[h])
        out.append(ScannedFile(path=p, file_hash=h, modified_ts=p.stat().st_mtime, classification=cls))
    return out
