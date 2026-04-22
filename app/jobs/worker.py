"""
Background daemon thread that processes transcription jobs one at a time.
Progress updates are forwarded to the per-job asyncio.Queue so WebSocket
handlers can stream them to the browser.
"""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from app.jobs import queue as job_queue
from app.jobs.models import Job

_main_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def _push(job: Job, pct: int, message: str, stage: str = "") -> None:
    if _main_loop is None:
        return
    payload = {
        "job_id": job.id,
        "stage": stage or _stage_from_pct(pct),
        "pct": pct,
        "message": message,
    }
    job.pct = pct
    job.message = message
    asyncio.run_coroutine_threadsafe(job.ws_queue.put(payload), _main_loop)


def _stage_from_pct(pct: int) -> str:
    if pct < 10:
        return "convert"
    if pct < 45:
        return "diarize"
    if pct < 85:
        return "transcribe"
    if pct < 100:
        return "merge"
    return "done"


def _worker_loop() -> None:
    from app.config import load_settings
    from app.storage.manager import StorageManager
    from app.core.pipeline import run_pipeline

    while True:
        job = job_queue.next_job_blocking()
        job.status = "running"
        _push(job, 0, "Starting …")

        try:
            settings = load_settings()
            storage = StorageManager(settings.storage_dir)

            def progress(pct: int, message: str) -> None:
                _push(job, pct, message)

            result_id = run_pipeline(
                job_id=job.id,
                upload_path=Path(job.upload_path),
                original_filename=job.original_filename,
                model_size=job.model_size,
                device_override=settings.device_override,
                storage=storage,
                progress=progress,
                cancel_event=job.cancel_event,
            )
            job.result_id = result_id
            job.status = "done"
            _push(job, 100, "Done", stage="done")

            if _main_loop:
                asyncio.run_coroutine_threadsafe(
                    job.ws_queue.put({
                        "job_id": job.id,
                        "stage": "done",
                        "pct": 100,
                        "message": "Transcription complete",
                        "result_id": result_id,
                    }),
                    _main_loop,
                )

        except InterruptedError:
            job.status = "cancelled"
            if _main_loop:
                asyncio.run_coroutine_threadsafe(
                    job.ws_queue.put({
                        "job_id": job.id,
                        "stage": "cancelled",
                        "pct": job.pct,
                        "message": "Transcription cancelled",
                    }),
                    _main_loop,
                )

        except Exception as exc:
            job.status = "error"
            job.error = str(exc)
            if _main_loop:
                asyncio.run_coroutine_threadsafe(
                    job.ws_queue.put({
                        "job_id": job.id,
                        "stage": "error",
                        "pct": None,
                        "message": str(exc),
                        "error": str(exc),
                    }),
                    _main_loop,
                )


def start_worker() -> threading.Thread:
    t = threading.Thread(target=_worker_loop, daemon=True, name="transcription-worker")
    t.start()
    return t
