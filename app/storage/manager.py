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
        return self.audio_dir / f"{result_id}.wav"

    def markdown_path(self, result_id: str) -> Path:
        return self.trans_dir / f"{result_id}.md"

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
        if not text.startswith("---"):
            raise ValueError("No YAML front matter found")
        parts = text.split("---", 2)
        if len(parts) < 3:
            raise ValueError("Malformed front matter")
        meta = yaml.safe_load(parts[1]) or {}
        fm = parts[1]
        body = parts[2]
        if "title" in updates:
            new_title = str(updates["title"])
            old_title = meta.get("title", "")
            fm = re.sub(r'^title:.*$', f'title: "{new_title}"', fm, flags=re.MULTILINE)
            body = body.replace(f"# Transcription: {old_title}", f"# Transcription: {new_title}", 1)
            meta["title"] = new_title
        if "date" in updates:
            new_date = str(updates["date"])
            fm = re.sub(r'^date:.*$', f'date: "{new_date}"', fm, flags=re.MULTILINE)
            meta["date"] = new_date
        path.write_text(f"---{fm}---{body}", encoding="utf-8")
        return meta

    def delete(self, result_id: str) -> None:
        self.markdown_path(result_id).unlink(missing_ok=True)
        self.audio_path(result_id).unlink(missing_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────

def _safe(stem: str) -> str:
    return re.sub(r"[^\w\-]", "_", stem)[:60]


def _parse_front_matter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
