"""
Storage manager — handles all file I/O and DB access outside the project folder.

Layout:
  {storage_dir}/
    audio/                 YYYY-MM-DD_HHMMSS_sanitized_stem.wav
    transcriptions/        legacy *.md files (pre-SQLite); migrated on startup
    audio_transcriber.db   SQLite DB — transcription metadata/text + job history
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import yaml

from app.storage import db

_RESULT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,180}$")
_TURN_HEADING_RE = re.compile(r"^## \[(\d{2}):(\d{2}):(\d{2})\] (.+)$")


class StorageManager:
    def __init__(self, storage_dir: Path) -> None:
        self.root = storage_dir.expanduser().resolve()
        self.audio_dir = self.root / "audio"
        self.trans_dir = self.root / "transcriptions"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.trans_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "audio_transcriber.db"
        db.init_db(self.db_path)

    # ── Naming ────────────────────────────────────────────────────────────

    def make_result_id(self, stem: str) -> str:
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe = _safe(stem)
        return f"{ts}_{safe}"

    def audio_path(self, result_id: str) -> Path:
        return self.audio_dir / f"{_safe_result_id(result_id)}.wav"

    # ── Save ─────────────────────────────────────────────────────────────

    def save(self, result_id: str, wav_path: Path, markdown_text: str, metadata: dict, turns: list) -> None:
        import shutil
        shutil.copy2(wav_path, self.audio_path(result_id))
        db.insert_transcription(self.db_path, result_id, metadata, markdown_text, turns)

    # ── Read ──────────────────────────────────────────────────────────────

    def read_markdown(self, result_id: str) -> str:
        row = db.get_transcription(self.db_path, _safe_result_id(result_id))
        if row is None:
            raise FileNotFoundError(f"Transcription '{result_id}' not found")
        return row["markdown"]

    def get_metadata(self, result_id: str) -> dict:
        row = db.get_transcription(self.db_path, _safe_result_id(result_id))
        if row is None:
            return {}
        row.pop("markdown", None)
        row.pop("created_at", None)
        row.pop("updated_at", None)
        return row

    # ── List ──────────────────────────────────────────────────────────────

    def list_transcriptions(self) -> list[dict]:
        """Return metadata dicts for all transcriptions, newest first."""
        results = db.list_transcriptions(self.db_path)
        for meta in results:
            meta.setdefault("title", meta["result_id"])
        return results

    def update_metadata(self, result_id: str, updates: dict) -> dict:
        """Update title and/or date for a transcription (in the DB)."""
        return db.update_transcription(self.db_path, _safe_result_id(result_id), updates)

    def delete(self, result_id: str) -> None:
        safe_id = _safe_result_id(result_id)
        db.delete_transcription(self.db_path, safe_id)
        self.audio_path(result_id).unlink(missing_ok=True)

    # ── Job history ───────────────────────────────────────────────────────

    def record_job(self, job: dict) -> None:
        db.upsert_job(self.db_path, job)

    # ── Legacy migration ──────────────────────────────────────────────────

    def migrate_legacy_markdown(self) -> int:
        """
        Import pre-SQLite *.md files (with WAV counterparts) into the DB.
        Idempotent: skips any result_id already present in `transcriptions`.
        Leaves the original .md files on disk untouched.
        """
        migrated = 0
        for md_file in sorted(self.trans_dir.glob("*.md")):
            result_id = md_file.stem
            if not _RESULT_ID_RE.fullmatch(result_id):
                continue
            if db.get_transcription(self.db_path, result_id) is not None:
                continue
            text = md_file.read_text(encoding="utf-8")
            meta = _parse_front_matter(text)
            if not meta:
                continue
            meta.setdefault("title", result_id)
            turns = _parse_turns(text, meta.get("duration"))
            db.insert_transcription(self.db_path, result_id, meta, text, turns)
            migrated += 1
        return migrated


# ── Helpers ───────────────────────────────────────────────────────────────

def _safe(stem: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", stem)[:60].strip("._-")
    return safe or "audio"


def _safe_result_id(result_id: str) -> str:
    value = str(result_id)
    if not _RESULT_ID_RE.fullmatch(value):
        raise FileNotFoundError(f"Transcription '{result_id}' not found")
    return value


def _split_front_matter(text: str) -> tuple[str, str] | None:
    if not text.startswith("---"):
        return None
    close_idx = text.find("\n---", 3)
    if close_idx == -1:
        return None
    return text[3:close_idx], text[close_idx + 4:]


def _parse_front_matter(text: str) -> dict:
    split = _split_front_matter(text)
    if split is None:
        return {}
    fm, _body = split
    try:
        return yaml.safe_load(fm) or {}
    except yaml.YAMLError:
        return {}


def _duration_to_seconds(duration: str | None) -> float:
    if not duration:
        return 0.0
    parts = [int(p) for p in duration.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3:]
    return h * 3600 + m * 60 + s


class _LegacyTurn:
    __slots__ = ("speaker_label", "start", "end", "text")

    def __init__(self, speaker_label: str, start: float, end: float, text: str) -> None:
        self.speaker_label = speaker_label
        self.start = start
        self.end = end
        self.text = text


def _parse_turns(text: str, duration: str | None) -> list:
    """Best-effort recovery of turns from rendered markdown for migration.
    Only the start time of each turn is stored in the file, so end_seconds
    is approximated (next turn's start, or total duration for the last turn).
    """
    split = _split_front_matter(text)
    body = split[1] if split else text

    raw: list[tuple[float, str, list[str]]] = []
    for line in body.splitlines():
        m = _TURN_HEADING_RE.match(line)
        if m:
            h, mi, s, speaker = m.groups()
            start = int(h) * 3600 + int(mi) * 60 + int(s)
            raw.append((float(start), speaker, []))
        elif raw and line.strip() and not line.startswith("#"):
            raw[-1][2].append(line.strip())

    total = _duration_to_seconds(duration)
    turns: list[_LegacyTurn] = []
    for i, (start, speaker, text_lines) in enumerate(raw):
        end = raw[i + 1][0] if i + 1 < len(raw) else max(start, total)
        turns.append(_LegacyTurn(speaker, start, end, " ".join(text_lines)))
    return turns
