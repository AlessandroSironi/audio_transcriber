"""
Hardware inspection: detect accelerator type, available memory, and compute
which Whisper model sizes can run accelerated vs. CPU-only.
"""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

import psutil

# ---------------------------------------------------------------------------
# VRAM requirements per model (Whisper + diarization overhead, in MB)
# ---------------------------------------------------------------------------

MODEL_SIZES: list[str] = [
    "tiny",
    "base",
    "small",
    "medium",
    "large-v3-turbo",
    "large-v3",
]

# (whisper_mb, diarization_overhead_mb)
_MODEL_VRAM: dict[str, tuple[int, int]] = {
    "tiny":           (1_024,  1_024),
    "base":           (1_024,  1_024),
    "small":          (2_048,  1_024),
    "medium":         (5_120,  1_024),
    "large-v3-turbo": (6_144,  1_024),
    "large-v3":       (10_240, 1_024),
}

_MODEL_DESCRIPTIONS: dict[str, dict] = {
    "tiny":           {"accuracy": "Basic",     "speed": "Very fast"},
    "base":           {"accuracy": "Low",       "speed": "Fast"},
    "small":          {"accuracy": "Good",      "speed": "Fast"},
    "medium":         {"accuracy": "Very good", "speed": "Moderate"},
    "large-v3-turbo": {"accuracy": "Excellent", "speed": "Moderate"},
    "large-v3":       {"accuracy": "Best",      "speed": "Slow"},
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ModelCapability:
    name: str
    vram_required_mb: int
    status: Literal["accelerated", "tight", "cpu_only"]
    note: str
    accuracy: str
    speed: str


@dataclass
class HardwareInfo:
    accelerator: Literal["cuda", "mps", "cpu"]
    accelerator_name: str
    vram_total_mb: int
    vram_free_mb: int
    ram_total_mb: int
    ram_free_mb: int
    model_capabilities: dict[str, ModelCapability] = field(default_factory=dict)

    def to_dict(self) -> dict:
        caps = {
            k: {
                "name": v.name,
                "vram_required_mb": v.vram_required_mb,
                "status": v.status,
                "note": v.note,
                "accuracy": v.accuracy,
                "speed": v.speed,
            }
            for k, v in self.model_capabilities.items()
        }
        return {
            "accelerator": self.accelerator,
            "accelerator_name": self.accelerator_name,
            "vram_total_mb": self.vram_total_mb,
            "vram_free_mb": self.vram_free_mb,
            "ram_total_mb": self.ram_total_mb,
            "ram_free_mb": self.ram_free_mb,
            "model_capabilities": caps,
        }

    def recommended_model(self) -> str:
        """Return highest-quality model with 'accelerated' status, else best available."""
        priority = list(reversed(MODEL_SIZES))
        for name in priority:
            cap = self.model_capabilities.get(name)
            if cap and cap.status == "accelerated":
                return name
        # Fallback: largest tight model, then cpu_only
        for status in ("tight", "cpu_only"):
            for name in priority:
                cap = self.model_capabilities.get(name)
                if cap and cap.status == status:
                    return name
        return "small"


# ---------------------------------------------------------------------------
# Capability computation
# ---------------------------------------------------------------------------

def _compute_capabilities(vram_free_mb: int) -> dict[str, ModelCapability]:
    caps: dict[str, ModelCapability] = {}
    for name in MODEL_SIZES:
        whisper_mb, overhead_mb = _MODEL_VRAM[name]
        required = whisper_mb + overhead_mb
        desc = _MODEL_DESCRIPTIONS[name]

        if vram_free_mb <= 0:
            status: Literal["accelerated", "tight", "cpu_only"] = "cpu_only"
            note = "No GPU/unified memory available — CPU int8 mode"
        elif vram_free_mb >= required * 1.1:
            status = "accelerated"
            note = f"{required:,} MB needed · {vram_free_mb:,} MB available"
        elif vram_free_mb >= required * 0.85:
            status = "tight"
            note = f"{required:,} MB needed · {vram_free_mb:,} MB available (may be slow)"
        else:
            status = "cpu_only"
            note = f"{required:,} MB needed · only {vram_free_mb:,} MB available — CPU int8 mode"

        caps[name] = ModelCapability(
            name=name,
            vram_required_mb=required,
            status=status,
            note=note,
            accuracy=desc["accuracy"],
            speed=desc["speed"],
        )
    return caps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def inspect_hardware() -> HardwareInfo:
    """Detect hardware and compute model capabilities. Result is cached."""
    vm = psutil.virtual_memory()
    ram_total = vm.total // (1024 * 1024)
    ram_free  = vm.available // (1024 * 1024)

    # --- Try NVIDIA CUDA ---
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            vram_total = props.total_memory // (1024 * 1024)
            # reserved is memory held by PyTorch allocator; free = total - reserved
            reserved = torch.cuda.memory_reserved(0) // (1024 * 1024)
            vram_free = vram_total - reserved
            name = torch.cuda.get_device_name(0)
            caps = _compute_capabilities(vram_free)
            return HardwareInfo(
                accelerator="cuda",
                accelerator_name=name,
                vram_total_mb=vram_total,
                vram_free_mb=vram_free,
                ram_total_mb=ram_total,
                ram_free_mb=ram_free,
                model_capabilities=caps,
            )
    except Exception:
        pass

    # --- Try Apple Silicon MPS ---
    try:
        import torch
        if torch.backends.mps.is_available() and sys.platform == "darwin":
            # Unified memory: GPU and CPU share the same pool
            vram_total = ram_total
            vram_free  = ram_free
            chip = platform.processor() or "Apple Silicon"
            caps = _compute_capabilities(vram_free)
            return HardwareInfo(
                accelerator="mps",
                accelerator_name=chip,
                vram_total_mb=vram_total,
                vram_free_mb=vram_free,
                ram_total_mb=ram_total,
                ram_free_mb=ram_free,
                model_capabilities=caps,
            )
    except Exception:
        pass

    # --- CPU only ---
    caps = _compute_capabilities(0)
    return HardwareInfo(
        accelerator="cpu",
        accelerator_name="CPU (no GPU acceleration)",
        vram_total_mb=0,
        vram_free_mb=0,
        ram_total_mb=ram_total,
        ram_free_mb=ram_free,
        model_capabilities=caps,
    )


def refresh_hardware() -> HardwareInfo:
    """Clear cache and re-inspect (useful after settings change)."""
    inspect_hardware.cache_clear()
    return inspect_hardware()
