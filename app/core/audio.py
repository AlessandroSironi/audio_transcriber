"""
Audio conversion utilities.
Converts any input format to 16 kHz mono WAV using pydub (which delegates to ffmpeg).
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


def check_ffmpeg() -> bool:
    """Return True if ffmpeg binary is available on PATH."""
    return shutil.which("ffmpeg") is not None


def convert_to_wav(input_path: Path, output_dir: Path) -> Path:
    """
    Convert *input_path* to a 16 kHz mono WAV file inside *output_dir*.
    Returns the path to the converted WAV.
    Raises RuntimeError if ffmpeg is missing or conversion fails.
    """
    if not check_ffmpeg():
        raise RuntimeError(
            "ffmpeg not found in PATH. "
            "Install it with: brew install ffmpeg  (macOS) or  apt install ffmpeg  (Linux)"
        )

    from pydub import AudioSegment  # lazy import — heavy dependency

    try:
        audio = AudioSegment.from_file(str(input_path))
    except Exception as exc:
        raise RuntimeError(f"Could not read audio file '{input_path.name}': {exc}") from exc

    # Normalise: mono, 16 kHz, 16-bit PCM
    audio = audio.set_channels(1).set_frame_rate(16_000).set_sample_width(2)

    stem = _safe_stem(input_path.stem)
    out_path = output_dir / f"{stem}.wav"
    audio.export(str(out_path), format="wav")
    return out_path


def make_temp_dir(job_id: str) -> Path:
    """Create and return a temporary directory for a transcription job."""
    tmp = Path(tempfile.mkdtemp(prefix=f"audiotx_{job_id}_"))
    return tmp


def cleanup_temp_dir(tmp_dir: Path) -> None:
    """Remove temporary directory, ignoring errors."""
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _safe_stem(stem: str) -> str:
    """Replace characters that are unsafe in filenames."""
    import re
    return re.sub(r"[^\w\-.]", "_", stem)[:80]
