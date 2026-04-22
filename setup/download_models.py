"""
Downloads diarization + Whisper models to the local cache.
No HuggingFace authentication required.
Can be called standalone (from CLI wizard) or from the browser setup endpoint.
Accepts an optional progress callback: fn(stage, pct, message).
"""
from __future__ import annotations

from typing import Callable

ProgressFn = Callable[[str, int, str], None]  # (stage, pct, message)


def download_all(
    model_size: str = "large-v3",
    progress: ProgressFn | None = None,
    hf_token: str = "",  # unused — kept for backward compatibility
) -> None:
    """Download resemblyzer + silero-vad diarization models, then Whisper."""
    _emit(progress, "download", 0, "Starting model download …")

    # ── Diarization models (no auth needed) ───────────────────────────────
    _emit(progress, "download", 5, "Downloading diarization models …")
    try:
        _download_diarization(progress)
        _emit(progress, "download", 35, "Diarization models ready")
    except Exception as exc:
        raise RuntimeError(f"Failed to download diarization models: {exc}") from exc

    # ── Whisper model ─────────────────────────────────────────────────────
    _emit(progress, "download", 40, f"Downloading Whisper {model_size} …")
    try:
        _download_whisper(model_size, progress)
        _emit(progress, "download", 95, f"Whisper {model_size} ready")
    except Exception as exc:
        raise RuntimeError(f"Failed to download Whisper model: {exc}") from exc

    _emit(progress, "done", 100, "All models downloaded successfully")


def _download_diarization(progress: ProgressFn | None) -> None:
    """Pre-download ECAPA-TDNN (SpeechBrain) and silero-vad."""
    import torch
    from pathlib import Path

    # ECAPA-TDNN: public HF repo, ~80 MB, no auth required
    _emit(progress, "download", 8, "Downloading ECAPA-TDNN speaker encoder (~80 MB) …")
    from speechbrain.inference.classifiers import EncoderClassifier
    savedir = str(Path.home() / ".cache" / "speechbrain" / "ecapa-voxceleb")
    EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=savedir,
        run_opts={"device": "cpu"},
    )
    _emit(progress, "download", 28, "ECAPA-TDNN ready")

    # silero-vad: ~2 MB via torch hub
    _emit(progress, "download", 30, "Downloading silero-vad (~2 MB) …")
    torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        trust_repo=True,
        verbose=False,
    )
    _emit(progress, "download", 35, "silero-vad ready")


def _download_whisper(model_size: str, progress: ProgressFn | None) -> None:
    """Download Whisper — tries mlx-whisper first on Apple Silicon, else faster-whisper."""
    import sys

    try:
        import torch
        mps_available = torch.backends.mps.is_available() and sys.platform == "darwin"
    except ImportError:
        mps_available = False

    if mps_available:
        try:
            import mlx_whisper
            _hf_map = {
                "tiny":           "mlx-community/whisper-tiny-mlx",
                "base":           "mlx-community/whisper-base-mlx",
                "small":          "mlx-community/whisper-small-mlx",
                "medium":         "mlx-community/whisper-medium-mlx",
                "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
                "large-v3":       "mlx-community/whisper-large-v3-mlx",
            }
            model_id = _hf_map.get(model_size, f"mlx-community/whisper-{model_size}-mlx")
            _emit(progress, "download", 60, f"Downloading MLX Whisper ({model_id}) …")
            import numpy as np
            silence = np.zeros(16_000, dtype=np.float32)
            mlx_whisper.transcribe(silence, path_or_hf_repo=model_id)
            return
        except ImportError:
            pass  # Fall through to faster-whisper

    # faster-whisper download
    _emit(progress, "download", 60, f"Downloading faster-whisper {model_size} …")
    from faster_whisper import WhisperModel
    WhisperModel(model_size, device="cpu", compute_type="int8")


def _emit(fn: ProgressFn | None, stage: str, pct: int, message: str) -> None:
    if fn:
        fn(stage, pct, message)
    else:
        print(f"[{pct:3d}%] {message}")
