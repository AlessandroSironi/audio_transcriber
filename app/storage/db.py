"""
SQLite persistence for transcription metadata/text and job history.

Audio (WAV) files stay on disk — only their absolute path is stored here.
Connections are short-lived (opened and closed per call) since callers
construct a fresh StorageManager per request/job from potentially
different threads.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transcriptions (
    result_id    TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    date         TEXT NOT NULL,
    duration     TEXT,
    speakers     INTEGER,
    model        TEXT,
    device       TEXT,
    source_audio TEXT,
    markdown     TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id     TEXT NOT NULL REFERENCES transcriptions(result_id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,
    speaker_label TEXT NOT NULL,
    start_seconds REAL NOT NULL,
    end_seconds   REAL NOT NULL,
    text          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_result_id ON turns(result_id);

CREATE TABLE IF NOT EXISTS jobs (
    id                TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    model_size        TEXT NOT NULL,
    status            TEXT NOT NULL,
    pct               INTEGER NOT NULL DEFAULT 0,
    message           TEXT,
    error             TEXT,
    result_id         TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
"""

_META_COLUMNS = ("title", "date", "duration", "speakers", "model", "device", "source_audio")


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(db_path)) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def insert_transcription(
    db_path: Path,
    result_id: str,
    metadata: dict,
    markdown: str,
    turns: list,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO transcriptions
                    (result_id, title, date, duration, speakers, model, device,
                     source_audio, markdown, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                        COALESCE((SELECT created_at FROM transcriptions WHERE result_id = ?), ?),
                        ?)
                """,
                (
                    result_id,
                    metadata.get("title", result_id),
                    metadata.get("date", now),
                    metadata.get("duration"),
                    metadata.get("speakers"),
                    metadata.get("model"),
                    metadata.get("device"),
                    metadata.get("source_audio"),
                    markdown,
                    result_id,
                    now,
                    now,
                ),
            )
            conn.execute("DELETE FROM turns WHERE result_id = ?", (result_id,))
            conn.executemany(
                """
                INSERT INTO turns (result_id, seq, speaker_label, start_seconds, end_seconds, text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (result_id, seq, t.speaker_label, t.start, t.end, t.text)
                    for seq, t in enumerate(turns)
                ],
            )


def list_transcriptions(db_path: Path) -> list[dict]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT result_id, title, date, duration, speakers, model, device, source_audio
            FROM transcriptions
            ORDER BY date DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_transcription(db_path: Path, result_id: str) -> dict | None:
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT * FROM transcriptions WHERE result_id = ?", (result_id,)
        ).fetchone()
    return dict(row) if row else None


def update_transcription(db_path: Path, result_id: str, updates: dict) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT * FROM transcriptions WHERE result_id = ?", (result_id,)
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Transcription '{result_id}' not found")

        meta = dict(row)
        markdown = meta["markdown"]

        if "title" in updates:
            new_title = str(updates["title"])
            old_title = meta.get("title", "")
            markdown = markdown.replace(
                f"# Transcription: {old_title}", f"# Transcription: {new_title}", 1
            )
            meta["title"] = new_title
        if "date" in updates:
            meta["date"] = str(updates["date"])

        with conn:
            conn.execute(
                """
                UPDATE transcriptions
                SET title = ?, date = ?, markdown = ?, updated_at = ?
                WHERE result_id = ?
                """,
                (meta["title"], meta["date"], markdown, now, result_id),
            )

    return {k: meta[k] for k in _META_COLUMNS}


def delete_transcription(db_path: Path, result_id: str) -> None:
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute("DELETE FROM transcriptions WHERE result_id = ?", (result_id,))


def upsert_job(db_path: Path, job: dict) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO jobs
                    (id, original_filename, model_size, status, pct, message, error,
                     result_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                        COALESCE((SELECT created_at FROM jobs WHERE id = ?), ?),
                        ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    pct = excluded.pct,
                    message = excluded.message,
                    error = excluded.error,
                    result_id = excluded.result_id,
                    updated_at = excluded.updated_at
                """,
                (
                    job["id"],
                    job["original_filename"],
                    job["model_size"],
                    job["status"],
                    job["pct"],
                    job.get("message"),
                    job.get("error"),
                    job.get("result_id"),
                    job["id"],
                    now,
                    now,
                ),
            )
