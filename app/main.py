"""
FastAPI application factory.
"""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router
from app.api.websocket import ws_router
from app.config import is_configured
from app.jobs import worker as job_worker

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR.parent / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
PROJECT_DIR = BASE_DIR.parent.resolve()

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _venv_activate_cmd() -> str | None:
    """Return the shell command to activate the current venv, or None if not in one."""
    if sys.prefix == sys.base_prefix:
        return None  # not in a virtual environment
    activate = Path(sys.prefix) / "bin" / "activate"
    if activate.exists():
        return f"source {activate}"
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Store the event loop reference so the worker thread can push updates
    loop = asyncio.get_event_loop()
    job_worker.set_event_loop(loop)
    job_worker.start_worker()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Audio Transcriber", lifespan=lifespan)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(router)
    app.include_router(ws_router)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        if not is_configured():
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/setup")
        activate_cmd = _venv_activate_cmd()
        return templates.TemplateResponse(request, "index.html", {
            "project_dir": str(PROJECT_DIR),
            "activate_cmd": activate_cmd,
        })

    @app.get("/setup", response_class=HTMLResponse)
    async def setup(request: Request):
        return templates.TemplateResponse(request, "setup.html")

    return app


app = create_app()
