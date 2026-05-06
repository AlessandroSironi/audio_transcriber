"""
Transcription abstraction over faster-whisper and mlx-whisper.
Both implementations return list[TranscriptSegment] with per-segment timestamps.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from app.core.device import DeviceProfile


@dataclass
class TranscriptSegment:
    start: float   # seconds
    end: float     # seconds
    text: str


ProgressCallback = Callable[[int, str], None]  # (pct_0_to_100, message)


# ---------------------------------------------------------------------------
# Protocol / interface
# ---------------------------------------------------------------------------

class Transcriber(Protocol):
    def transcribe(
        self,
        audio_path: Path,
        progress: ProgressCallback | None = None,
        pct_start: int = 45,
        pct_end: int = 85,
        cancel_event: threading.Event | None = None,
    ) -> list[TranscriptSegment]: ...


# ---------------------------------------------------------------------------
# faster-whisper backend
# ---------------------------------------------------------------------------

class FasterWhisperTranscriber:
    def __init__(self, model_size: str, profile: DeviceProfile) -> None:
        from faster_whisper import WhisperModel  # lazy import

        self._model = WhisperModel(
            model_size,
            device=profile.device,
            compute_type=profile.compute_type,
        )

    def transcribe(
        self,
        audio_path: Path,
        progress: ProgressCallback | None = None,
        pct_start: int = 45,
        pct_end: int = 85,
        cancel_event: threading.Event | None = None,
    ) -> list[TranscriptSegment]:
        segments_iter, info = self._model.transcribe(
            str(audio_path),
            word_timestamps=True,
            vad_filter=True,
        )

        segments: list[TranscriptSegment] = []
        total_duration = info.duration or 1.0

        for seg in segments_iter:
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Job cancelled")
            segments.append(TranscriptSegment(start=seg.start, end=seg.end, text=seg.text.strip()))
            if progress:
                pct = int(pct_start + (seg.end / total_duration) * (pct_end - pct_start))
                pct = min(pct, pct_end)
                progress(pct, f"Transcribing … {seg.end:.0f}s / {total_duration:.0f}s")

        return segments


# ---------------------------------------------------------------------------
# mlx-whisper backend (Apple Silicon)
# ---------------------------------------------------------------------------

class MLXWhisperTranscriber:
    def __init__(self, model_size: str) -> None:
        # mlx-whisper uses HuggingFace model IDs; map size names accordingly
        _hf_map = {
            "tiny":           "mlx-community/whisper-tiny-mlx",
            "base":           "mlx-community/whisper-base-mlx",
            "small":          "mlx-community/whisper-small-mlx",
            "medium":         "mlx-community/whisper-medium-mlx",
            "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
            "large-v3":       "mlx-community/whisper-large-v3-mlx",
        }
        self._model_size = model_size
        self._model_id = _hf_map.get(model_size, f"mlx-community/whisper-{model_size}-mlx")

    def transcribe(
        self,
        audio_path: Path,
        progress: ProgressCallback | None = None,
        pct_start: int = 45,
        pct_end: int = 85,
        cancel_event: threading.Event | None = None,
    ) -> list[TranscriptSegment]:
        import mlx_whisper  # lazy import

        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Job cancelled")

        # mlx_whisper.transcribe() is a blocking call with no progress callback.
        # Run it in a sub-thread and tick elapsed time every 2 s so the browser
        # shows live feedback instead of a frozen "Loading model…" message.
        result_holder: list = [None]
        error_holder: list = [None]
        done = threading.Event()

        def _run() -> None:
            try:
                result_holder[0] = mlx_whisper.transcribe(
                    str(audio_path),
                    path_or_hf_repo=self._model_id,
                    word_timestamps=True,
                )
            except Exception as exc:
                error_holder[0] = exc
            finally:
                done.set()

        threading.Thread(target=_run, daemon=True).start()

        start = time.monotonic()
        model_label = self._model_size
        while not done.wait(timeout=2.0):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Job cancelled")
            if progress:
                elapsed = int(time.monotonic() - start)
                progress(pct_start + 2, f"Transcribing with Whisper ({model_label}) … {elapsed}s")

        if error_holder[0]:
            raise error_holder[0]

        result = result_holder[0]
        segments: list[TranscriptSegment] = []
        raw_segments = result.get("segments", [])
        total = len(raw_segments) or 1

        for i, seg in enumerate(raw_segments):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Job cancelled")
            segments.append(
                TranscriptSegment(
                    start=seg["start"],
                    end=seg["end"],
                    text=seg["text"].strip(),
                )
            )
            if progress:
                pct = int(pct_start + ((i + 1) / total) * (pct_end - pct_start))
                progress(min(pct, pct_end), f"Transcribing … segment {i + 1}/{total}")

        return segments


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_transcriber(model_size: str, profile: DeviceProfile) -> Transcriber:
    if profile.backend == "mlx-whisper":
        return MLXWhisperTranscriber(model_size)
    return FasterWhisperTranscriber(model_size, profile)
