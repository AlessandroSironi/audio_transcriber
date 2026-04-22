"""
HTTP endpoints:
  POST /api/upload                   — upload audio, create job
  GET  /api/jobs/{job_id}            — job status
  GET  /api/transcriptions           — list all transcriptions
  GET  /api/transcriptions/{id}      — markdown content + metadata
  DELETE /api/transcriptions/{id}    — delete
  GET  /api/hardware                 — hardware capability report
  GET  /api/settings                 — current settings
  POST /api/settings                 — update settings
  GET  /api/models                   — list Whisper models with download status
  DELETE /api/models/{model_size}    — delete a downloaded Whisper model
  POST /api/setup/check              — ffmpeg + system check
  POST /api/setup/check-token        — validate HF token
  POST /api/setup/config             — write initial config
"""
from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from app.config import is_configured, load_settings, save_settings, settings
from app.core.audio import check_ffmpeg
from app.core.hardware import inspect_hardware, refresh_hardware
from app.jobs import queue as job_queue
from app.jobs.models import Job
from app.storage.manager import StorageManager

router = APIRouter()


# ── Upload ────────────────────────────────────────────────────────────────

@router.post("/api/upload")
async def upload_audio(file: UploadFile = File(...)):
    if not is_configured():
        raise HTTPException(status_code=400, detail="App not configured. Complete setup first.")

    cfg = load_settings()

    # Save upload to a temp location (worker picks it up from there)
    job_id = str(uuid.uuid4())
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"audiotx_upload_{job_id}_"))
    dest = tmp_dir / (file.filename or "audio")
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    job = Job(
        id=job_id,
        original_filename=file.filename or "audio",
        upload_path=str(dest),
        model_size=cfg.whisper_model,
    )
    job_queue.register(job)
    job_queue.enqueue(job_id)

    return JSONResponse(status_code=202, content={"job_id": job_id})


# ── Job status ────────────────────────────────────────────────────────────

@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("pending", "running"):
        return {"ok": False, "reason": f"Job is already {job.status}"}
    job.cancel_event.set()
    return {"ok": True}


# ── System resource stats ─────────────────────────────────────────────────

@router.get("/api/system")
async def system_stats():
    import psutil
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    data: dict = {
        "cpu_pct": cpu,
        "ram_used_mb": mem.used // 1_048_576,
        "ram_total_mb": mem.total // 1_048_576,
        "ram_pct": round(mem.percent, 1),
    }
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            reserved = torch.cuda.memory_reserved(0)
            data["gpu_type"] = "cuda"
            data["gpu_used_mb"] = reserved // 1_048_576
            data["gpu_total_mb"] = props.total_memory // 1_048_576
            data["gpu_pct"] = round(reserved / props.total_memory * 100, 1)
        elif torch.backends.mps.is_available():
            used = torch.mps.current_allocated_memory()   # bytes allocated by torch
            driver = torch.mps.driver_allocated_memory()  # bytes committed by driver
            total = mem.total                              # unified memory = system RAM
            data["gpu_type"] = "mps"
            data["gpu_used_mb"] = driver // 1_048_576
            data["gpu_total_mb"] = total // 1_048_576
            data["gpu_pct"] = round(driver / total * 100, 1) if total else 0
    except Exception:
        pass
    return data


# ── Transcriptions ────────────────────────────────────────────────────────

@router.get("/api/transcriptions")
async def list_transcriptions():
    cfg = load_settings()
    storage = StorageManager(cfg.storage_dir)
    return storage.list_transcriptions()


@router.get("/api/transcriptions/{result_id}")
async def get_transcription(result_id: str):
    cfg = load_settings()
    storage = StorageManager(cfg.storage_dir)
    try:
        md = storage.read_markdown(result_id)
        meta = storage.get_metadata(result_id)
        meta["result_id"] = result_id
        return {"metadata": meta, "markdown": md}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Transcription not found")


@router.delete("/api/transcriptions/{result_id}")
async def delete_transcription(result_id: str):
    cfg = load_settings()
    storage = StorageManager(cfg.storage_dir)
    storage.delete(result_id)
    return {"deleted": result_id}


# ── Hardware ──────────────────────────────────────────────────────────────

@router.get("/api/hardware")
async def hardware_info():
    hw = inspect_hardware()
    data = hw.to_dict()
    data["recommended_model"] = hw.recommended_model()
    return data


# ── Settings ──────────────────────────────────────────────────────────────

@router.get("/api/settings")
async def get_settings():
    cfg = load_settings()
    return {
        "storage_dir": str(cfg.storage_dir),
        "whisper_model": cfg.whisper_model,
        "device_override": cfg.device_override,
        "host": cfg.host,
        "port": cfg.port,
    }


@router.post("/api/settings")
async def update_settings(body: dict):
    allowed = {"storage_dir", "whisper_model", "device_override", "host", "port"}
    data = {k: v for k, v in body.items() if k in allowed}
    save_settings(data)
    if "device_override" in data:
        refresh_hardware()
    return {"ok": True}


# ── Model cache ───────────────────────────────────────────────────────────

_MLX_HF_MAP = {
    "tiny":           "mlx-community/whisper-tiny-mlx",
    "base":           "mlx-community/whisper-base-mlx",
    "small":          "mlx-community/whisper-small-mlx",
    "medium":         "mlx-community/whisper-medium-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3":       "mlx-community/whisper-large-v3-mlx",
}


def _dir_size_mb(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) // 1_048_576


def _whisper_cache_entry(model_size: str) -> dict:
    """Return {downloaded, path, size_mb, backend} for a given model size."""
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"

    # MLX (Apple Silicon)
    repo_id = _MLX_HF_MAP.get(model_size)
    if repo_id:
        mlx_dir = hf_cache / ("models--" + repo_id.replace("/", "--"))
        if mlx_dir.exists():
            return {"downloaded": True, "path": str(mlx_dir),
                    "size_mb": _dir_size_mb(mlx_dir), "backend": "mlx"}

    # faster-whisper (NVIDIA / CPU)
    fw_dir = hf_cache / f"models--Systran--faster-whisper-{model_size}"
    if fw_dir.exists():
        return {"downloaded": True, "path": str(fw_dir),
                "size_mb": _dir_size_mb(fw_dir), "backend": "faster-whisper"}

    return {"downloaded": False, "path": None, "size_mb": 0, "backend": None}


@router.get("/api/models")
async def list_models():
    from app.core.hardware import MODEL_SIZES
    return {size: _whisper_cache_entry(size) for size in MODEL_SIZES}


@router.delete("/api/models/{model_size}")
async def delete_model(model_size: str):
    from app.core.hardware import MODEL_SIZES
    if model_size not in MODEL_SIZES:
        raise HTTPException(status_code=400, detail=f"Unknown model size: {model_size}")
    entry = _whisper_cache_entry(model_size)
    if not entry["downloaded"]:
        raise HTTPException(status_code=404, detail="Model not downloaded")
    shutil.rmtree(entry["path"])
    return {"deleted": model_size, "path": entry["path"]}


# ── Setup endpoints ───────────────────────────────────────────────────────

@router.post("/api/setup/check")
async def setup_check():
    import sys, platform
    ffmpeg_ok = check_ffmpeg()
    return {
        "ffmpeg": ffmpeg_ok,
        "platform": sys.platform,
        "python": sys.version,
        "os": platform.platform(),
    }


@router.post("/api/shutdown")
async def shutdown():
    import asyncio, os, signal
    # Delay slightly so the HTTP response is flushed before the process exits.
    asyncio.get_event_loop().call_later(0.35, lambda: os.kill(os.getpid(), signal.SIGTERM))
    return {"ok": True}


@router.post("/api/setup/config")
async def setup_save_config(body: dict):
    required = {"storage_dir", "whisper_model"}
    missing = required - body.keys()
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing fields: {missing}")
    save_settings(body)
    return {"ok": True}


@router.post("/api/setup/download")
async def setup_download(body: dict):
    """
    Kick off model download in a background thread.
    Progress is streamed via WS /ws/setup/{session_id}.
    """
    import asyncio
    import threading
    from app.api.websocket import push_setup_progress

    session_id = body.get("session_id", "default")
    cfg = load_settings()
    loop = asyncio.get_event_loop()

    def _run():
        from setup.download_models import download_all

        def progress(stage: str, pct: int, message: str) -> None:
            push_setup_progress(session_id, {
                "stage": stage, "pct": pct, "message": message,
            }, loop)

        try:
            download_all(
                model_size=cfg.whisper_model,
                progress=progress,
            )
        except Exception as exc:
            push_setup_progress(session_id, {
                "stage": "error", "pct": None, "error": str(exc),
            }, loop)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "session_id": session_id}
