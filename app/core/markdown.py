"""
Renders the merged transcription turns into a Markdown document with YAML front matter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Turn:
    speaker_label: str   # "Speaker 1", "Speaker 2", …
    start: float         # seconds
    end: float           # seconds
    text: str


def _fmt_duration(seconds: float) -> str:
    td = timedelta(seconds=int(seconds))
    h, rem = divmod(int(td.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_timestamp(seconds: float) -> str:
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def render_markdown(
    turns: list[Turn],
    title: str,
    model_name: str,
    device_label: str,
    source_audio: str,
    recorded_at: datetime | None = None,
) -> str:
    if not turns:
        total_duration = 0.0
    else:
        total_duration = max(t.end for t in turns)

    speaker_set = list(dict.fromkeys(t.speaker_label for t in turns))
    num_speakers = len(speaker_set)
    date_str = (recorded_at or datetime.now()).isoformat(timespec="seconds")

    lines: list[str] = []

    # YAML front matter
    lines += [
        "---",
        f'title: "{title}"',
        f'date: "{date_str}"',
        f'duration: "{_fmt_duration(total_duration)}"',
        f"speakers: {num_speakers}",
        f'model: "{model_name}"',
        f'device: "{device_label}"',
        f'source_audio: "{source_audio}"',
        "---",
        "",
        f"# Transcription: {title}",
        "",
        "---",
        "",
    ]

    for turn in turns:
        ts = _fmt_timestamp(turn.start)
        lines += [
            f"## [{ts}] {turn.speaker_label}",
            "",
            turn.text,
            "",
        ]

    return "\n".join(lines)


def merge_segments(
    transcript_segments: list,    # list[TranscriptSegment]
    diarization_segments: list,   # list[DiarizationSegment]
) -> list[Turn]:
    """
    Assign each transcript segment to the speaker with maximum overlap,
    then group consecutive same-speaker segments into Turns.
    """
    # Build speaker label map (SPEAKER_00 → Speaker 1, in appearance order)
    speaker_order: dict[str, int] = {}
    for dseg in diarization_segments:
        if dseg.speaker not in speaker_order:
            speaker_order[dseg.speaker] = len(speaker_order) + 1

    def _speaker_label(raw: str) -> str:
        return f"Speaker {speaker_order.get(raw, '?')}"

    def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
        return max(0.0, min(a_end, b_end) - max(a_start, b_start))

    assigned: list[tuple[str, float, float, str]] = []  # (speaker_label, start, end, text)
    for tseg in transcript_segments:
        best_speaker = "Speaker ?"
        best_overlap = -1.0
        for dseg in diarization_segments:
            ov = _overlap(tseg.start, tseg.end, dseg.start, dseg.end)
            if ov > best_overlap:
                best_overlap = ov
                best_speaker = _speaker_label(dseg.speaker)
        assigned.append((best_speaker, tseg.start, tseg.end, tseg.text))

    # Group consecutive same-speaker segments
    turns: list[Turn] = []
    for speaker, start, end, text in assigned:
        if turns and turns[-1].speaker_label == speaker:
            turns[-1].text += " " + text
            turns[-1].end = end
        else:
            turns.append(Turn(speaker_label=speaker, start=start, end=end, text=text))

    return turns
