"""
In-process job registry.
Jobs are stored in a plain dict keyed by job_id.
A threading.Queue feeds the background worker thread.
"""
from __future__ import annotations

import queue
import threading
from typing import Optional

from app.jobs.models import Job

_jobs: dict[str, Job] = {}
_work_queue: queue.Queue[str] = queue.Queue()  # job IDs to process
_lock = threading.Lock()


def register(job: Job) -> None:
    with _lock:
        _jobs[job.id] = job


def enqueue(job_id: str) -> None:
    _work_queue.put(job_id)


def get_job(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)


def all_jobs() -> list[Job]:
    with _lock:
        return list(_jobs.values())


def next_job_blocking() -> Job:
    """Block until a job_id is available, then return the Job."""
    while True:
        job_id = _work_queue.get()
        job = _jobs.get(job_id)
        if job is not None:
            return job
