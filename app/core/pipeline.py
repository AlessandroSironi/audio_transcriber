"""
Full transcription pipeline: convert → diarize → transcribe → merge → save.
Designed to run in a background thread; uses a ProgressCallback to push
updates to the WebSocket layer.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.core.audio import convert_to_wav, make_temp_dir, cleanup_temp_dir
from app.core.diarizer import Diarizer
from app.core.markdown import build_metadata, merge_segments, render_markdown
from app.core.transcriber import build_transcriber
from app.core.device import detect_device
from app.storage.manager import StorageManager

ProgressCallback = Callable[[int, str], None]  # (pct 0–100, message)


def run_pipeline(
    job_id: str,
    upload_path: Path,
    original_filename: str,
    model_size: str,
    device_override: str | None,
    storage: StorageManager,
    progress: ProgressCallback,
    cancel_event: threading.Event | None = None,
) -> str:
    """
    Run the full pipeline.  Returns the result_id (stem used for storage naming).
    Raises InterruptedError on cancellation, or other exceptions on failure.
    """
    tmp_dir = make_temp_dir(job_id)
    try:
        return _pipeline(
            job_id, upload_path, original_filename,
            model_size, device_override, storage, progress, tmp_dir, cancel_event,
        )
    finally:
        cleanup_temp_dir(tmp_dir)


def _check(cancel_event: threading.Event | None) -> None:
    if cancel_event and cancel_event.is_set():
        raise InterruptedError("Job cancelled")


def _pipeline(
    job_id: str,
    upload_path: Path,
    original_filename: str,
    model_size: str,
    device_override: str | None,
    storage: StorageManager,
    progress: ProgressCallback,
    tmp_dir: Path,
    cancel_event: threading.Event | None,
) -> str:
    # ── Stage 1: Audio conversion ──────────────────────────────────────────
    progress(0, "Converting audio …")
    _check(cancel_event)
    wav_path = convert_to_wav(upload_path, tmp_dir)
    progress(10, "Audio conversion complete")

    # ── Stage 2: Speaker diarization ──────────────────────────────────────
    _check(cancel_event)
    profile = detect_device(device_override)
    diarizer = Diarizer(device=profile.diarizer_device)
    diar_segments = diarizer.diarize(
        wav_path,
        progress=progress,
        pct_start=10,
        pct_end=45,
        cancel_event=cancel_event,
    )

    # ── Stage 3: Transcription ─────────────────────────────────────────────
    _check(cancel_event)
    progress(45, f"Loading Whisper ({model_size}) …")
    transcriber = build_transcriber(model_size, profile)
    transcript_segments = transcriber.transcribe(
        wav_path,
        progress=progress,
        pct_start=45,
        pct_end=85,
        cancel_event=cancel_event,
    )

    # ── Stage 4: Merge speaker labels with transcript ──────────────────────
    _check(cancel_event)
    progress(85, "Merging speaker labels …")
    turns = merge_segments(transcript_segments, diar_segments)
    progress(92, "Generating markdown …")

    # ── Stage 5: Render markdown & save ───────────────────────────────────
    _check(cancel_event)
    stem = Path(original_filename).stem
    device_label = f"{profile.backend} ({profile.device})"

    result_id = storage.make_result_id(stem)
    saved_wav = storage.audio_path(result_id)

    metadata = build_metadata(
        turns=turns,
        title=stem,
        model_name=model_size,
        device_label=device_label,
        source_audio=str(saved_wav),
        recorded_at=datetime.now(),
    )
    md_text = render_markdown(turns, metadata)

    storage.save(result_id, wav_path, md_text, metadata, turns)
    progress(100, "Done")

    return result_id
