"""
Storage manager — handles all file I/O outside the project folder.

Layout:
  {storage_dir}/
    audio/          YYYY-MM-DD_HHMMSS_sanitized_stem.wav
    transcriptions/ YYYY-MM-DD_HHMMSS_sanitized_stem.md
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

import yaml

_RESULT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,180}$")


class StorageManager:
    def __init__(self, storage_dir: Path) -> None:
        self.root = storage_dir.expanduser().resolve()
        self.audio_dir = self.root / "audio"
        self.trans_dir = self.root / "transcriptions"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.trans_dir.mkdir(parents=True, exist_ok=True)

    # ── Naming ────────────────────────────────────────────────────────────

    def make_result_id(self, stem: str) -> str:
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe = _safe(stem)
        return f"{ts}_{safe}"

    def audio_path(self, result_id: str) -> Path:
        return self.audio_dir / f"{_safe_result_id(result_id)}.wav"

    def markdown_path(self, result_id: str) -> Path:
        return self.trans_dir / f"{_safe_result_id(result_id)}.md"

    # ── Save ─────────────────────────────────────────────────────────────

    def save(self, result_id: str, wav_path: Path, markdown_text: str) -> None:
        shutil.copy2(wav_path, self.audio_path(result_id))
        self.markdown_path(result_id).write_text(markdown_text, encoding="utf-8")

    # ── Read ──────────────────────────────────────────────────────────────

    def read_markdown(self, result_id: str) -> str:
        path = self.markdown_path(result_id)
        if not path.exists():
            raise FileNotFoundError(f"Transcription '{result_id}' not found")
        return path.read_text(encoding="utf-8")

    def get_metadata(self, result_id: str) -> dict:
        """Parse YAML front matter from a transcription file."""
        path = self.markdown_path(result_id)
        if not path.exists():
            return {}
        text = path.read_text(encoding="utf-8")
        return _parse_front_matter(text)

    # ── List ──────────────────────────────────────────────────────────────

    def list_transcriptions(self) -> list[dict]:
        """Return metadata dicts for all transcriptions, newest first."""
        results = []
        for md_file in sorted(self.trans_dir.glob("*.md"), reverse=True):
            result_id = md_file.stem
            meta = _parse_front_matter(md_file.read_text(encoding="utf-8"))
            meta["result_id"] = result_id
            meta.setdefault("title", result_id)
            results.append(meta)
        return results

    def update_metadata(self, result_id: str, updates: dict) -> dict:
        """Update title and/or date in the YAML front matter (in-place)."""
        path = self.markdown_path(result_id)
        if not path.exists():
            raise FileNotFoundError(f"Transcription '{result_id}' not found")
        text = path.read_text(encoding="utf-8")
        split = _split_front_matter(text)
        if split is None:
            raise ValueError("No YAML front matter found")
        fm, body = split
        meta = yaml.safe_load(fm) or {}
        if "title" in updates:
            new_title = str(updates["title"])
            old_title = meta.get("title", "")
            body = body.replace(f"# Transcription: {old_title}", f"# Transcription: {new_title}", 1)
            meta["title"] = new_title
        if "date" in updates:
            new_date = str(updates["date"])
            meta["date"] = new_date
        fm_text = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
        path.write_text(f"---\n{fm_text}---{body}", encoding="utf-8")
        return meta

    def delete(self, result_id: str) -> None:
        try:
            self.markdown_path(result_id).unlink(missing_ok=True)
            self.audio_path(result_id).unlink(missing_ok=True)
        except FileNotFoundError:
            return


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
