"""
Hardware detection — returns a DeviceProfile that downstream modules use
to select the right backend and compute type.
"""
from __future__ import annotations

import sys
from typing import NamedTuple, Literal


class DeviceProfile(NamedTuple):
    backend: Literal["faster-whisper", "mlx-whisper"]
    device: Literal["cuda", "mps", "cpu"]
    compute_type: Literal["float16", "int8"]
    diarizer_device: Literal["cuda", "mps", "cpu"]


def _profile_for(override: str) -> DeviceProfile:
    override = override.lower().strip()
    if override == "cuda":
        return DeviceProfile("faster-whisper", "cuda", "float16", "cuda")
    if override == "mps":
        return DeviceProfile("faster-whisper", "mps", "float16", "mps")
    # cpu or anything else
    return DeviceProfile("faster-whisper", "cpu", "int8", "cpu")


def detect_device(override: str | None = None) -> DeviceProfile:
    """
    Return a DeviceProfile for the best available accelerator.

    Priority:
      1. Explicit override from config
      2. NVIDIA CUDA (faster-whisper + float16)
      3. Apple MPS — prefer mlx-whisper if installed, else faster-whisper on MPS
      4. CPU fallback (faster-whisper + int8)
    """
    if override:
        return _profile_for(override)

    try:
        import torch

        if torch.cuda.is_available():
            return DeviceProfile("faster-whisper", "cuda", "float16", "cuda")

        if torch.backends.mps.is_available() and sys.platform == "darwin":
            try:
                import mlx_whisper  # noqa: F401 — presence check only
                return DeviceProfile("mlx-whisper", "mps", "float16", "mps")
            except ImportError:
                return DeviceProfile("faster-whisper", "mps", "float16", "mps")

    except ImportError:
        pass  # torch not installed at all

    return DeviceProfile("faster-whisper", "cpu", "int8", "cpu")
