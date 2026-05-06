"""
Speaker diarization using ECAPA-TDNN (SpeechBrain) + silero-vad + spectral clustering.

Improvements over the previous resemblyzer-based stack:
- ECAPA-TDNN embeddings: ~1% EER vs ~5-8% for GE2E — much better speaker discrimination
- Sliding-window sub-segmentation: catches speaker changes inside long VAD blocks
- Spectral clustering with eigengap heuristic: more reliable speaker count estimation
  than silhouette + agglomerative
"""
from __future__ import annotations

import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

SAMPLE_RATE = 16_000

# Sliding window parameters for sub-segmentation
WINDOW_SEC  = 1.5    # each window's duration
STEP_SEC    = 0.75   # stride (50% overlap)
MIN_WIN_SEC = 0.5    # skip windows shorter than this

# Post-processing
MIN_SEG_SEC = 0.3    # drop merged segments shorter than this
MERGE_GAP   = 1.5    # merge same-speaker windows if gap ≤ this (seconds)


@dataclass
class DiarizationSegment:
    start: float   # seconds
    end: float     # seconds
    speaker: str   # e.g. "SPEAKER_00"


ProgressCallback = Callable[[int, str], None]


class Diarizer:
    def __init__(self, device: str = "cpu") -> None:
        self._device = device
        self._encoder = None
        self._vad_model = None
        self._vad_utils = None

    # ── Model loading ─────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._encoder is not None:
            return
        import types
        import torch

        # SpeechBrain 1.0+ registers optional integrations (k2_fsa,
        # huggingface.wordemb, …) as LazyModules in
        # speechbrain.utils.importutils. When their dependencies aren't
        # installed, ensure_module() raises ImportError. Patch it once to
        # cache a stub module instead, covering all missing integrations.
        try:
            from speechbrain.utils.importutils import LazyModule as _SBLazy
            if not getattr(_SBLazy, "_patched_silent", False):
                _orig_ensure = _SBLazy.ensure_module
                def _safe_ensure(self, stacklevel, _o=_orig_ensure, _t=types):
                    try:
                        return _o(self, stacklevel)
                    except ImportError:
                        stub = _t.ModuleType(self.target)
                        self.lazy_module = stub
                        return stub
                _SBLazy.ensure_module = _safe_ensure
                _SBLazy._patched_silent = True
        except Exception:
            pass

        from speechbrain.inference.classifiers import EncoderClassifier

        savedir = str(Path.home() / ".cache" / "speechbrain" / "ecapa-voxceleb")
        # ECAPA-TDNN: public HF repo, ~80 MB, no auth required
        self._encoder = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=savedir,
            run_opts={"device": "cpu"},  # SpeechBrain MPS support is unstable
        )

        # silero-vad: ~2 MB, torch hub, no auth required
        self._vad_model, self._vad_utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True,
            verbose=False,
        )

    # ── Audio helpers ─────────────────────────────────────────────────────

    def _read_wav(self, path: Path) -> np.ndarray:
        with wave.open(str(path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
        return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

    def _run_vad(self, audio: np.ndarray) -> list[tuple[float, float]]:
        import torch
        get_speech_timestamps = self._vad_utils[0]
        audio_tensor = torch.from_numpy(audio)
        timestamps = get_speech_timestamps(
            audio_tensor,
            self._vad_model,
            sampling_rate=SAMPLE_RATE,
            min_speech_duration_ms=250,
            min_silence_duration_ms=300,
            return_seconds=True,
        )
        return [(float(t["start"]), float(t["end"])) for t in timestamps]

    # ── Embedding ─────────────────────────────────────────────────────────

    def _embed_window(self, audio: np.ndarray, start_s: float, end_s: float) -> np.ndarray | None:
        """Embed a single time window; returns L2-normalised 192-D vector or None if too short."""
        import torch
        s = int(start_s * SAMPLE_RATE)
        e = int(end_s   * SAMPLE_RATE)
        chunk = audio[s:e]
        if len(chunk) < int(MIN_WIN_SEC * SAMPLE_RATE):
            return None
        wav_t = torch.from_numpy(chunk).unsqueeze(0)  # (1, T)
        with torch.no_grad():
            emb = self._encoder.encode_batch(wav_t)   # (1, 1, 192)
        emb = emb.squeeze().numpy()                    # (192,)
        norm = np.linalg.norm(emb)
        if norm > 1e-8:
            emb /= norm
        return emb

    def _windows_for_segment(
        self, vad_start: float, vad_end: float
    ) -> list[tuple[float, float]]:
        """
        Return (win_start, win_end) pairs for a VAD segment.
        Short segments get a single window; long ones get overlapping windows.
        """
        duration = vad_end - vad_start
        if duration <= WINDOW_SEC * 2:
            return [(vad_start, vad_end)]
        windows = []
        t = vad_start
        while t < vad_end:
            w_end = min(t + WINDOW_SEC, vad_end)
            windows.append((t, w_end))
            if w_end >= vad_end:
                break
            t += STEP_SEC
        return windows

    # ── Clustering ────────────────────────────────────────────────────────

    def _spectral_cluster(self, X: np.ndarray, max_speakers: int = 8) -> np.ndarray:
        """
        Spectral clustering with eigengap heuristic for automatic k selection.
        Returns integer label array of length len(X).
        """
        from sklearn.metrics.pairwise import cosine_similarity
        from sklearn.cluster import SpectralClustering
        from scipy.sparse.csgraph import laplacian as graph_laplacian

        n = len(X)
        if n == 1:
            return np.array([0])

        # Affinity matrix: shift cosine similarity to [0, 1]
        A = (cosine_similarity(X) + 1.0) / 2.0
        np.fill_diagonal(A, 1.0)

        # Eigengap heuristic: find k where λ[k] - λ[k-1] is largest
        L = graph_laplacian(A, normed=True)
        eigenvalues = np.sort(np.linalg.eigvalsh(L.toarray() if hasattr(L, "toarray") else L))
        max_k = min(max_speakers, n - 1)
        gaps = np.diff(eigenvalues[1:max_k + 2])  # skip trivial λ₀ ≈ 0
        k = int(np.argmax(gaps)) + 2              # +2: 1-indexed, skip λ₀
        k = max(1, min(k, max_speakers, n))

        if k == 1:
            return np.zeros(n, dtype=int)

        labels = SpectralClustering(
            n_clusters=k,
            affinity="precomputed",
            assign_labels="kmeans",
            random_state=42,
            n_init=20,
        ).fit_predict(A)
        return labels

    # ── Post-processing ───────────────────────────────────────────────────

    def _merge_windows(
        self, windows: list[tuple[float, float, int]]
    ) -> list[DiarizationSegment]:
        """
        Merge adjacent windows with the same speaker label (allowing small gaps),
        then drop segments shorter than MIN_SEG_SEC.
        Input: list of (start, end, label).
        """
        if not windows:
            return []

        segments: list[list] = []  # [start, end, label]
        for w_start, w_end, label in windows:
            if (
                segments
                and segments[-1][2] == label
                and w_start - segments[-1][1] <= MERGE_GAP
            ):
                segments[-1][1] = w_end
            else:
                segments.append([w_start, w_end, label])

        return [
            DiarizationSegment(start=s, end=e, speaker=f"SPEAKER_{lbl:02d}")
            for s, e, lbl in segments
            if e - s >= MIN_SEG_SEC
        ]

    # ── Public API ────────────────────────────────────────────────────────

    def diarize(
        self,
        audio_path: Path,
        progress: ProgressCallback | None = None,
        pct_start: int = 10,
        pct_end: int = 45,
        cancel_event: threading.Event | None = None,
    ) -> list[DiarizationSegment]:
        def _cancelled() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        if progress:
            progress(pct_start, "Loading ECAPA-TDNN diarization model …")
        self._load()

        if progress:
            progress(pct_start + 3, "Running voice activity detection …")
        if _cancelled():
            raise InterruptedError("Job cancelled")
        audio = self._read_wav(audio_path)
        vad_segs = self._run_vad(audio)
        if not vad_segs:
            return []

        # Build all sliding windows across all VAD segments
        all_windows: list[tuple[float, float]] = []
        for vstart, vend in vad_segs:
            all_windows.extend(self._windows_for_segment(vstart, vend))

        if progress:
            progress(pct_start + 8, f"Embedding {len(all_windows)} windows …")

        embeddings: list[np.ndarray] = []
        valid_windows: list[tuple[float, float]] = []
        n_wins = len(all_windows)

        for i, (w_start, w_end) in enumerate(all_windows):
            if _cancelled():
                raise InterruptedError("Job cancelled")
            emb = self._embed_window(audio, w_start, w_end)
            if emb is not None:
                embeddings.append(emb)
                valid_windows.append((w_start, w_end))
            if progress:
                pct = pct_start + 8 + int((i + 1) / max(n_wins, 1) * 25)
                progress(min(pct, pct_end - 6), f"Embedding {i+1}/{n_wins} …")

        if not embeddings:
            return []

        if progress:
            progress(pct_end - 5, "Clustering speakers …")

        X = np.array(embeddings)
        labels = self._spectral_cluster(X)

        if progress:
            progress(pct_end, "Diarization complete")

        window_triples = [
            (ws, we, int(lbl))
            for (ws, we), lbl in zip(valid_windows, labels)
        ]
        return self._merge_windows(window_triples)
