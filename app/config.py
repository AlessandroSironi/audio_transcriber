"""
Application configuration loaded from ~/.config/audio_transcriber/config.yaml.
Falls back to safe defaults when the file does not exist (first-run state).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path.home() / ".config" / "audio_transcriber" / "config.yaml"
DEFAULT_STORAGE = Path.home() / "AudioTranscriptions"

DEFAULTS: dict[str, Any] = {
    "storage_dir": str(DEFAULT_STORAGE),
    "whisper_model": "large-v3",
    "device_override": None,
    "host": "0.0.0.0",
    "port": 8000,
}


@dataclass
class Settings:
    storage_dir: Path = field(default_factory=lambda: DEFAULT_STORAGE)
    whisper_model: str = "large-v3"
    device_override: str | None = None
    host: str = "0.0.0.0"
    port: int = 8000


def load_settings() -> Settings:
    data: dict[str, Any] = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            file_data = yaml.safe_load(f) or {}
        data.update(file_data)

    storage = Path(str(data.get("storage_dir", DEFAULT_STORAGE))).expanduser().resolve()
    return Settings(
        storage_dir=storage,
        whisper_model=str(data.get("whisper_model", "large-v3")),
        device_override=data.get("device_override") or None,
        host=str(data.get("host", "0.0.0.0")),
        port=int(data.get("port", 8000)),
    )


def save_settings(data: dict[str, Any]) -> None:
    """Persist a partial dict of settings back to config.yaml."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            existing = yaml.safe_load(f) or {}
    existing.update(data)
    # Normalise Path objects to strings for YAML serialisation
    for k, v in existing.items():
        if isinstance(v, Path):
            existing[k] = str(v)
    with CONFIG_PATH.open("w") as f:
        yaml.dump(existing, f, default_flow_style=False)


def is_configured() -> bool:
    """Return True if a config file already exists (not first-run)."""
    return CONFIG_PATH.exists()
