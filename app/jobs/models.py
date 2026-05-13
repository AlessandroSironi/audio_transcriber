"""
Job dataclass representing a single transcription job.
"""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


JobStatus = Literal["pending", "running", "done", "error", "cancelled"]


@dataclass
class Job:
    id: str
    original_filename: str
    upload_path: str           # absolute path to the uploaded file in tmp
    model_size: str
    status: JobStatus = "pending"
    pct: int = 0
    message: str = ""
    error: str | None = None
    result_id: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    # Set this event to request cancellation of the running pipeline.
    cancel_event: threading.Event = field(
        default_factory=threading.Event, repr=False, compare=False
    )

    # Per-connection queues for streaming progress to WebSocket handlers.
    _ws_queues: list[asyncio.Queue] = field(default_factory=list, repr=False, compare=False)
    _ws_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    event_history: list[dict] = field(default_factory=list, repr=False, compare=False)

    def add_ws_queue(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        with self._ws_lock:
            self._ws_queues.append(q)
        return q

    def remove_ws_queue(self, q: asyncio.Queue) -> None:
        with self._ws_lock:
            if q in self._ws_queues:
                self._ws_queues.remove(q)

    def record_event(self, payload: dict) -> list[asyncio.Queue]:
        with self._ws_lock:
            self.event_history.append(dict(payload))
            self.event_history = self.event_history[-200:]
            return list(self._ws_queues)

    def last_event(self) -> dict | None:
        with self._ws_lock:
            return dict(self.event_history[-1]) if self.event_history else None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "original_filename": self.original_filename,
            "model_size": self.model_size,
            "status": self.status,
            "pct": self.pct,
            "message": self.message,
            "error": self.error,
            "result_id": self.result_id,
            "created_at": self.created_at.isoformat(),
        }
