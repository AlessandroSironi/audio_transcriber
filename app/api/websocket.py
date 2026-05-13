"""
WebSocket endpoints:
  WS /ws/{job_id}   — streams job progress to the browser
  WS /ws/setup      — streams model-download progress during first-run wizard
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.jobs import queue as job_queue

ws_router = APIRouter()

# Registry for setup download progress queues
_setup_queues: dict[str, asyncio.Queue] = {}


@ws_router.websocket("/ws/{job_id}")
async def job_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    job = job_queue.get_job(job_id)
    if not job:
        await websocket.send_json({"stage": "error", "error": "Job not found"})
        await websocket.close()
        return

    # If job already finished before the client connected, send terminal message immediately
    if job.status == "done":
        await websocket.send_json({
            "job_id": job_id, "stage": "done", "pct": 100,
            "message": "Transcription complete", "result_id": job.result_id,
        })
        await websocket.close()
        return

    if job.status == "error":
        await websocket.send_json({
            "job_id": job_id, "stage": "error", "pct": None,
            "error": job.error,
        })
        await websocket.close()
        return

    if job.status == "cancelled":
        await websocket.send_json({
            "job_id": job_id, "stage": "cancelled", "pct": job.pct,
            "message": "Transcription cancelled",
        })
        await websocket.close()
        return

    q = job.add_ws_queue()
    last_event = job.last_event()
    if last_event:
        await websocket.send_json(last_event)
        if last_event.get("stage") in ("done", "error", "cancelled"):
            job.remove_ws_queue(q)
            await websocket.close()
            return

    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a keepalive ping
                await websocket.send_json({"stage": "ping"})
                continue

            await websocket.send_json(msg)
            if msg.get("stage") in ("done", "error", "cancelled"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        job.remove_ws_queue(q)
        await websocket.close()


# ── Setup download WebSocket ───────────────────────────────────────────────

def get_setup_queue(session_id: str) -> asyncio.Queue:
    if session_id not in _setup_queues:
        _setup_queues[session_id] = asyncio.Queue()
    return _setup_queues[session_id]


def push_setup_progress(session_id: str, msg: dict, loop: asyncio.AbstractEventLoop) -> None:
    q = get_setup_queue(session_id)
    if q and loop:
        asyncio.run_coroutine_threadsafe(q.put(msg), loop)


@ws_router.websocket("/ws/setup/{session_id}")
async def setup_progress(websocket: WebSocket, session_id: str):
    await websocket.accept()
    q = get_setup_queue(session_id)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=60.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"stage": "ping"})
                continue
            await websocket.send_json(msg)
            if msg.get("stage") in ("done", "error"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        _setup_queues.pop(session_id, None)
        await websocket.close()
