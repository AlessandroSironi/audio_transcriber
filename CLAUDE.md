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

## Docker deployment

`Dockerfile` (CPU, portable to any x86_64/arm64 Linux host) and `Dockerfile.cuda` (NVIDIA GPU, requires the [NVIDIA Container Toolkit](https://github.com/NVIDIA/nvidia-container-toolkit) on the host) are both built on `python:3.11-slim` / `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04` respectively. **Apple Silicon's `mlx-whisper` needs macOS Metal, which isn't available inside a Linux container** — Docker deployments always run `faster-whisper` on CPU or CUDA, never MLX.

```bash
# CPU
docker compose up --build

# NVIDIA GPU
docker compose --profile gpu up --build audio-transcriber-cuda
```

Both services run as a non-root `appuser` whose `$HOME` is `/data` — this makes `/data` the single volume that needs to persist across container recreation, since `app/config.py` (`~/.config/audio_transcriber/`), the Whisper/SpeechBrain model caches (`~/.cache/...`), and the default `storage_dir` (`~/AudioTranscriptions/`, containing the SQLite DB + WAVs) all resolve under `Path.home()`. `docker-compose.yml` maps this to a named volume (`audiotx-data`). There's no env-var-based config path: visit `http://<host>:8000/` after starting the container and complete the same browser setup wizard used for native installs (model download happens there too, so the image itself stays small).

`run.py`'s browser auto-open is disabled via `--no-browser` in both Dockerfiles' `CMD`, since there's no local display inside a container.

## Architecture

### Request → response flow

1. Browser uploads a file → `POST /api/upload` saves it to a temp dir, creates a `Job` object, puts the job ID in `job_queue._work_queue`.
2. The single background daemon thread in `app/jobs/worker.py` picks up the job and calls `app/core/pipeline.py:run_pipeline()`.
3. `run_pipeline` runs five stages sequentially: convert → diarize → transcribe → merge → save. Between every stage it checks `cancel_event` and raises `InterruptedError` if set.
4. Progress updates travel from the worker thread → each subscribed WebSocket queue via `asyncio.run_coroutine_threadsafe` — this bridge is necessary because the worker runs in a plain `threading.Thread` while the WebSocket handler is an asyncio coroutine in the main event loop.
5. On completion, the WAV is copied into the storage directory and the transcript (metadata + full markdown + per-turn rows) is written to the SQLite database via `app/storage/manager.py`.

### Pipeline stages (`app/core/pipeline.py`)

| Stage | % range | Module |
|---|---|---|
| Audio conversion | 0–10 | `app/core/audio.py` — pydub → 16 kHz mono WAV |
| Diarization | 10–45 | `app/core/diarizer.py` — ECAPA-TDNN + silero-vad + spectral clustering |
| Transcription | 45–85 | `app/core/transcriber.py` — mlx-whisper (Apple) or faster-whisper |
| Merge | 85–92 | `app/core/markdown.py:merge_segments()` — overlap-based speaker assignment |
| Save | 92–100 | `app/storage/manager.py` — WAV copy + `app/storage/db.py` insert |

### Device / backend selection (`app/core/device.py`)

`detect_device()` returns a `DeviceProfile` (NamedTuple: backend, device, compute_type, diarizer_device). Priority: CUDA → MPS+mlx-whisper → CPU. CTranslate2/faster-whisper does not support `mps`, so Apple Silicon falls back to CPU unless `mlx-whisper` is installed. Can be overridden via `device_override` in config. `app/core/hardware.py` exposes `inspect_hardware()` (cached with `@lru_cache`) for the `/api/hardware` endpoint and Settings UI.

**Intel iGPU is not a supported backend.** CTranslate2 (faster-whisper) only targets CPU and NVIDIA CUDA — no oneAPI/Level-Zero or Quick Sync path — so an Intel integrated GPU (e.g. UHD 630 on a NAS/home-server CPU) is never used, on bare metal or in Docker, no matter what `device_override` is set to. Getting real iGPU acceleration would require adding a whole new backend (`optimum-intel`'s OpenVINO `OVModelForSpeechSeq2Seq`, or whisper.cpp's SYCL build) — not currently implemented, and likely not worth it for older iGPUs (e.g. UHD 630 is Gen9.5, no tensor/matrix units) where the gain over CPU would be marginal.

### Diarizer (`app/core/diarizer.py`)

Three-step process: silero-vad identifies speech segments → sliding 1.5s windows (0.75s stride) produce 192-D ECAPA-TDNN embeddings via SpeechBrain → spectral clustering with eigengap heuristic selects `k` speakers automatically. Models load lazily on first `diarize()` call. ECAPA-TDNN always runs on CPU (SpeechBrain MPS support is unstable).

SpeechBrain model cache: `~/.cache/speechbrain/ecapa-voxceleb/`  
Whisper model cache: `~/.cache/huggingface/hub/models--{org}--{name}/`

### Transcription backends (`app/core/transcriber.py`)

`build_transcriber(model_size, profile)` returns either `MLXWhisperTranscriber` or `FasterWhisperTranscriber`. The MLX variant calls `mlx_whisper.transcribe()` with a HF repo ID; the faster-whisper variant uses CTranslate2. Both check `cancel_event` per segment and raise `InterruptedError` on cancellation.

### Markdown output format

`app/core/markdown.py:build_metadata()` computes the front-matter dict (duration, speaker count, etc.) from the merged turns, and `render_markdown(turns, metadata)` renders it into a markdown string with this structure — the string itself is stored verbatim in the `transcriptions.markdown` SQLite column (see Storage layout below), not written to a file:

```
---
title: "stem"
date: "2026-04-21T14:30:22"
duration: "00:42:11"
speakers: 2
model: "large-v3"
device: "mlx-whisper (mps)"
source_audio: "/abs/path/to/audio/2026-04-21_143022_stem.wav"
---

# Transcription: stem

---

## [00:00:04] Speaker 1

text of turn …

## [00:01:22] Speaker 2

text of turn …
```

`source_audio` in the front matter is the **absolute path** to the stored WAV file. Turn headings follow the pattern `## [HH:MM:SS] Speaker N` — the timestamp is the start time of that speaker turn in `HH:MM:SS` format.

### WebSocket protocol

Server → client JSON shape:
```json
{ "stage": "diarize", "pct": 32, "message": "Embedding 14/40 …" }
{ "stage": "done",    "pct": 100, "result_id": "2026-04-21_143022_meeting" }
{ "stage": "error",   "pct": null, "error": "…" }
{ "stage": "cancelled", "pct": 42, "message": "Transcription cancelled" }
```

Stage names map to pipeline phases: `convert`, `diarize`, `transcribe`, `merge`, `save`, `done`, `error`, `cancelled`. The frontend (`static/app.js`) drives the progress timeline UI from these messages.

A second WebSocket at `WS /ws/setup/{session_id}` streams model-download progress during first-run setup; `push_setup_progress()` in `app/api/websocket.py` is the bridge from the download thread.

### Frontend

Single-page app served from `app/templates/index.html`. All logic is in `static/app.js` (vanilla JS, no framework). The setup wizard is a separate page at `/setup` served from `app/templates/setup.html` with `static/setup.js`. `marked.js` (bundled locally at `static/marked.min.js`) renders transcription markdown in the Viewer tab.

Key JS module-level state:
- `activeJobId` — job currently running (upload tab)
- `_currentResultId`, `_currentMarkdown`, `_currentMeta` — transcription open in viewer tab
- `_currentAudio`, `_currentTurns`, `_lastActiveTurn` — audio player state (viewer tab)
- `_hwData`, `_selectedModel` — hardware info and selected Whisper model (settings tab)
- `_txList`, `_sortKey`, `_sortDir` — library list and sort state

`stripFrontMatter(text)` strips YAML front matter before passing to `marked.parse()` — uses `indexOf('\n---', 3)` rather than `split('---', 3)` to avoid truncating content that contains `---` horizontal rules.

Speaker headings (`h2`) in the viewer are color-coded using `SP_HUES = [240, 287, 340, 28, 75, 170, 200, 55]` (one hue per speaker index) and CSS variables `--sp1`–`--sp8` defined in `static/style.css`.

### Audio player (`static/app.js`)

After `marked.parse()`, `renderViewer()` calls `wrapTurns(container)` which walks the rendered DOM and wraps each `## [HH:MM:SS] Speaker N` heading plus its following paragraph(s) into a `<div class="turn" data-start="{seconds}">`. The static `Array.from(container.childNodes)` snapshot is taken before any moves so the iteration is safe while nodes are being reparented.

`buildAudioPlayer(resultId)` creates the sticky player bar (injected between `viewer-meta-strip` and `viewer-body`), constructs an `<audio>` element pointing at `GET /api/transcriptions/{id}/audio`, and wires all events. `syncHighlight(currentTime)` is called on every `timeupdate` but only touches the DOM when `_lastActiveTurn` changes index, keeping it cheap.

Cleanup on navigation: `openViewer()` pauses and nulls `_currentAudio`, clears `_currentTurns`, and removes the player bar before loading a new transcription.

### Storage layout

```
~/AudioTranscriptions/
  audio/                 YYYY-MM-DD_HHMMSS_stem.wav
  transcriptions/        legacy *.md files from before the SQLite migration (read-only, untouched)
  audio_transcriber.db   SQLite — transcription metadata/text + job history
```

`app/storage/db.py` owns the schema (`transcriptions`, `turns`, `jobs` tables) and all SQL; `app/storage/manager.py:StorageManager` is the only caller and copies WAVs to `audio/` while delegating everything else to `db.py`. Only the WAV audio lives as a loose file — transcript text, per-turn speaker/timing rows, and full rendered markdown all live in the `transcriptions`/`turns` tables, keyed by `result_id` (e.g. `2026-04-21_143022_meeting`), which is used as the key in all API routes. `source_audio` (column + front-matter field) is the **absolute path** to the WAV file.

`StorageManager.migrate_legacy_markdown()` runs once at app startup (see `lifespan()` in `app/main.py`) and imports any pre-existing `transcriptions/*.md` files into the database (skipping ones already imported); the original `.md` files are left in place but are no longer read once migrated.

Job records (`app/jobs/models.py:Job`) are mirrored into the `jobs` table via `StorageManager.record_job()` for durable history — once on creation (`POST /api/upload`) and once on each terminal state (`done`/`error`/`cancelled`) — but the live in-process `Job` (with its `cancel_event`/WebSocket queues) remains the source of truth for an in-flight job; nothing currently reads the `jobs` table back out via the API.

### Config

Plain `@dataclass` + YAML, no pydantic. `app/config.py:load_settings()` reads `~/.config/audio_transcriber/config.yaml` and merges with hard-coded defaults. `save_settings(dict)` does a partial merge — only pass the keys you want to change. Callers should use `load_settings()` when they need current values. Settings intentionally stay in YAML rather than moving into SQLite: `storage_dir` (where the DB file lives) is itself a setting, and the first-run setup wizard must be able to read/write config before any storage directory — and therefore any DB — exists.

## Key API endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/upload` | Upload file, start job |
| GET | `/api/jobs/{id}` | Poll job status |
| POST | `/api/jobs/{id}/cancel` | Set `cancel_event` |
| WS | `/ws/{job_id}` | Stream progress |
| GET | `/api/transcriptions` | List library |
| GET | `/api/transcriptions/{id}` | Markdown content + parsed metadata |
| PATCH | `/api/transcriptions/{id}` | Update `title` and/or `date` in front matter |
| DELETE | `/api/transcriptions/{id}` | Delete markdown + WAV |
| GET | `/api/transcriptions/{id}/audio` | Stream the stored WAV (supports Range requests) |
| GET | `/api/hardware` | Cached hardware info |
| GET/DELETE | `/api/models` `/api/models/{size}` | Model download status / delete |
| GET/POST | `/api/settings` | Read / write config |
| GET | `/api/system` | Live CPU/RAM/GPU stats |
| POST | `/api/shutdown` | SIGTERM with 350ms delay |
| POST | `/api/setup/download` | Kick off model download; progress via WS |
| WS | `/ws/setup/{session_id}` | Stream model-download progress |
