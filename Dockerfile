# CPU-only image — portable across any x86_64/arm64 Linux host
# (cloud VM, NAS, home server, or Apple Silicon via Docker Desktop's Linux VM).
# For an NVIDIA GPU host, build Dockerfile.cuda instead.
FROM python:3.11-slim

# ffmpeg: audio conversion: libsndfile1: soundfile (speechbrain dep)
# libgomp1: OpenMP runtime (torch/scikit-learn/scipy): curl: healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsndfile1 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user whose home directory is the single persistence point:
# $HOME/.config/audio_transcriber (settings), $HOME/.cache (model downloads),
# $HOME/AudioTranscriptions (audio + SQLite DB) all live under /data.
RUN useradd --create-home --home-dir /data --shell /bin/bash appuser

WORKDIR /app

COPY requirements.txt .
# CPU-only torch wheel (far smaller than the CUDA-bundled PyPI default);
# requirements.txt's "torch>=2.5" constraint is already satisfied afterwards.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchaudio \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

USER appuser
ENV HOME=/data
VOLUME /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/ || exit 1

# Setup (storage dir, model size, download) happens through the browser
# wizard on first visit — same flow as a native install.
CMD ["python", "run.py", "--no-browser", "--host", "0.0.0.0"]
