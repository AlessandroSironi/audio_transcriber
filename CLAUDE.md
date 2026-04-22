# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
# First run (browser setup wizard opens automatically)
source .venv/bin/activate
python run.py

# Subsequent runs
python run.py
python run.py --no-browser     # headless / SSH
python run.py --port 9000      # custom port
python run.py --setup          # force CLI setup wizard
```

The server binds to `0.0.0.0:8000` by default (LAN-accessible). Config is persisted at `~/.config/audio_transcriber/config.yaml`; transcriptions are saved under `~/AudioTranscriptions/` by default.

## Installation

```bash
python -m venv .venv && source .venv/bin/activate

# Base (all platforms)
pip install -r requirements.txt

# Apple Silicon only (adds mlx + mlx-whisper)
pip install -r requirements-apple.txt

# NVIDIA only (replaces torch with CUDA build)
pip install -r requirements-cuda.txt
```

System dependency: `ffmpeg` must be on `PATH` (`brew install ffmpeg` / `apt install ffmpeg`).

There are no tests or linters configured.

## Architecture

### Request → response flow

1. Browser uploads a file → `POST /api/upload` saves it to a temp dir, creates a `Job` object, puts the job ID in `job_queue._work_queue`.
2. The single background daemon thread in `app/jobs/worker.py` picks up the job and calls `app/core/pipeline.py:run_pipeline()`.
3. `run_pipeline` runs five stages sequentially: convert → diarize → transcribe → merge → save. Between every stage it checks `cancel_event` and raises `InterruptedError` if set.
4. Progress updates travel from the worker thread → `job.ws_queue` (an `asyncio.Queue`) via `asyncio.run_coroutine_threadsafe` → the WebSocket handler at `WS /ws/{job_id}` → browser.
5. On completion, the markdown and WAV are written to the user-configured storage directory via `app/storage/manager.py`.

### Pipeline stages (`app/core/pipeline.py`)

| Stage | % range | Module |
|---|---|---|
| Audio conversion | 0–10 | `app/core/audio.py` — pydub → 16 kHz mono WAV |
| Diarization | 10–45 | `app/core/diarizer.py` — ECAPA-TDNN + silero-vad + spectral clustering |
| Transcription | 45–85 | `app/core/transcriber.py` — mlx-whisper (Apple) or faster-whisper |
| Merge | 85–92 | `app/core/markdown.py:merge_segments()` — overlap-based speaker assignment |
| Save | 92–100 | `app/storage/manager.py` |

### Device / backend selection (`app/core/device.py`)

`detect_device()` returns a `DeviceProfile` (NamedTuple: backend, device, compute_type, diarizer_device). Priority: CUDA → MPS+mlx-whisper → MPS+faster-whisper → CPU. Can be overridden via `device_override` in config. `app/core/hardware.py` exposes `inspect_hardware()` (cached with `@lru_cache`) for the `/api/hardware` endpoint and Settings UI.

### Diarizer (`app/core/diarizer.py`)

Three-step process: silero-vad identifies speech segments → sliding 1.5s windows (0.75s stride) produce 192-D ECAPA-TDNN embeddings via SpeechBrain → spectral clustering with eigengap heuristic selects `k` speakers automatically. Models load lazily on first `diarize()` call. ECAPA-TDNN always runs on CPU (SpeechBrain MPS support is unstable).

SpeechBrain model cache: `~/.cache/speechbrain/ecapa-voxceleb/`  
Whisper model cache: `~/.cache/huggingface/hub/models--{org}--{name}/`

### Transcription backends (`app/core/transcriber.py`)

`build_transcriber(model_size, profile)` returns either `MLXWhisperTranscriber` or `FasterWhisperTranscriber`. The MLX variant calls `mlx_whisper.transcribe()` with a HF repo ID; the faster-whisper variant uses CTranslate2. Both check `cancel_event` per segment and raise `InterruptedError` on cancellation.

### WebSocket protocol

Server → client JSON shape:
```json
{ "stage": "diarize", "pct": 32, "message": "Embedding 14/40 …" }
{ "stage": "done",    "pct": 100, "result_id": "2026-04-21_143022_meeting" }
{ "stage": "error",   "pct": null, "error": "…" }
{ "stage": "cancelled", "pct": 42, "message": "Transcription cancelled" }
```

Stage names map to pipeline phases: `convert`, `diarize`, `transcribe`, `merge`, `done`, `error`, `cancelled`. The frontend (`static/app.js`) drives the progress timeline UI from these messages.

### Frontend

Single-page app served from `app/templates/index.html`. All logic is in `static/app.js` (vanilla JS, no framework). The setup wizard is a separate page at `/setup` served from `app/templates/setup.html` with `static/setup.js`. `marked.js` (bundled locally at `static/marked.min.js`) renders transcription markdown in the Viewer tab.

Key JS globals: `_hwData` (hardware info), `_selectedModel` (settings), `activeJobId` (in-progress job). `stripFrontMatter(text)` strips YAML front matter before passing to `marked.parse()` — uses `indexOf('\n---', 3)` rather than `split('---', 3)` to avoid truncating content that contains `---` horizontal rules.

### Storage layout

```
~/AudioTranscriptions/
  audio/           YYYY-MM-DD_HHMMSS_stem.wav
  transcriptions/  YYYY-MM-DD_HHMMSS_stem.md   ← has YAML front matter
```

The `result_id` (e.g. `2026-04-21_143022_meeting`) is the shared stem across both files and is used as the key in all API routes.

### Config

Plain `@dataclass` + YAML, no pydantic. `app/config.py:load_settings()` reads `~/.config/audio_transcriber/config.yaml` and merges with hard-coded defaults. `save_settings(dict)` does a partial merge — only pass the keys you want to change. `settings` module-level singleton is loaded at import time; callers that need fresh values after a save should call `load_settings()` again.

## Key API endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/upload` | Upload file, start job |
| GET | `/api/jobs/{id}` | Poll job status |
| POST | `/api/jobs/{id}/cancel` | Set `cancel_event` |
| WS | `/ws/{job_id}` | Stream progress |
| GET | `/api/transcriptions` | List library |
| GET/DELETE | `/api/transcriptions/{id}` | View / delete |
| GET | `/api/hardware` | Cached hardware info |
| GET/DELETE | `/api/models` `/api/models/{size}` | Model download status / delete |
| GET/POST | `/api/settings` | Read / write config |
| GET | `/api/system` | Live CPU/RAM/GPU stats |
| POST | `/api/shutdown` | SIGTERM with 350ms delay |
