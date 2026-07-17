"""
Background daemon thread that processes transcription jobs one at a time.
Progress updates are forwarded to the per-job asyncio.Queue so WebSocket
handlers can stream them to the browser.
"""
from __future__ import annotations

import asyncio
import shutil
import threading
from pathlib import Path

from app.jobs import queue as job_queue
from app.jobs.models import Job

_main_loop: asyncio.AbstractEventLoop | None = None
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def _push(job: Job, pct: int, message: str, stage: str = "", extra: dict | None = None) -> None:
    if _main_loop is None:
        return
    payload = {
        "job_id": job.id,
        "stage": stage or _stage_from_pct(pct),
        "pct": pct,
        "message": message,
    }
    if extra:
        payload.update(extra)
    job.pct = pct
    job.message = message
    for q in job.record_event(payload):
        asyncio.run_coroutine_threadsafe(q.put(payload), _main_loop)


def _stage_from_pct(pct: int) -> str:
    if pct < 10:
        return "convert"
    if pct < 45:
        return "diarize"
    if pct < 85:
        return "transcribe"
    if pct < 100:
        return "merge"
    return "save"


def _cleanup_upload(job: Job) -> None:
    path = Path(job.upload_path)
    tmp_dir = path.parent
    if tmp_dir.name.startswith("audiotx_upload_"):
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _worker_loop() -> None:
    from app.config import load_settings
    from app.storage.manager import StorageManager
    from app.core.pipeline import run_pipeline

    while True:
        job = job_queue.next_job_blocking()
        job.status = "running"
        _push(job, 0, "Starting …")

        settings = load_settings()
        storage = StorageManager(settings.storage_dir)

        try:
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
            _push(
                job,
                100,
                "Transcription complete",
                stage="done",
                extra={"result_id": result_id},
            )

        except InterruptedError:
            job.status = "cancelled"
            _push(job, job.pct, "Transcription cancelled", stage="cancelled")

        except Exception as exc:
            job.status = "error"
            job.error = str(exc)
            _push(job, job.pct, str(exc), stage="error", extra={"pct": None, "error": str(exc)})
        finally:
            storage.record_job(job.to_dict())
            _cleanup_upload(job)


def start_worker() -> threading.Thread:
    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return _worker_thread
        _worker_thread = threading.Thread(
            target=_worker_loop,
            daemon=True,
            name="transcription-worker",
        )
        _worker_thread.start()
        return _worker_thread
