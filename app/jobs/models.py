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

    # Per-job asyncio.Queue for streaming progress to WebSocket handlers.
    ws_queue: asyncio.Queue = field(default_factory=asyncio.Queue, repr=False, compare=False)

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
