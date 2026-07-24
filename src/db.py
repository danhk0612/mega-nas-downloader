from __future__ import annotations

import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(database_path: str) -> sqlite3.Connection:
    parent = Path(database_path).parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        db = sqlite3.connect(database_path, check_same_thread=False)
    except sqlite3.OperationalError as exc:
        stat = parent.stat()
        details = (
            f"unable to open SQLite database at {database_path}; "
            f"parent={parent}, mode={oct(stat.st_mode & 0o777)}, "
            f"uid={stat.st_uid}, gid={stat.st_gid}, "
            f"process_uid={os.getuid()}, process_gid={os.getgid()}"
        )
        raise sqlite3.OperationalError(details) from exc
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            mega_url TEXT NOT NULL,
            mega_url_masked TEXT NOT NULL,
            subfolder TEXT NOT NULL DEFAULT '',
            target_dir TEXT NOT NULL,
            duplicate_policy TEXT NOT NULL,
            status TEXT NOT NULL,
            progress REAL,
            downloaded_bytes INTEGER,
            total_bytes INTEGER,
            speed_bytes_per_sec INTEGER,
            eta_seconds INTEGER,
            registered_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            error_message TEXT,
            process_id INTEGER,
            retry_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS job_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL
        );
        """
    )
    db.execute(
        """
        UPDATE jobs
           SET status = 'failed',
               completed_at = ?,
               error_message = 'Application restarted while this job was running.',
               process_id = NULL
         WHERE status = 'running'
        """,
        (utc_now(),),
    )
    db.commit()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def add_log(db: sqlite3.Connection, job_id: int, level: str, message: str) -> None:
    db.execute(
        "INSERT INTO job_logs (job_id, created_at, level, message) VALUES (?, ?, ?, ?)",
        (job_id, utc_now(), level, message),
    )
    db.commit()


def list_jobs(
    db: sqlite3.Connection,
    include_logs: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    limit_sql = "" if limit is None else "LIMIT ?"
    params: tuple[int, ...] = () if limit is None else (limit,)
    rows = db.execute(
        f"""
        SELECT *
          FROM jobs
         ORDER BY registered_at DESC, id DESC
         {limit_sql}
        """,
        params,
    ).fetchall()
    jobs = [row_to_dict(row) for row in rows]
    if include_logs:
        for job in jobs:
            job["logs"] = list_job_logs(db, int(job["id"]))
    return jobs


def get_job(db: sqlite3.Connection, job_id: int, include_logs: bool = False) -> dict[str, Any] | None:
    row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    job = row_to_dict(row)
    if include_logs:
        job["logs"] = list_job_logs(db, job_id)
    return job


def list_job_logs(db: sqlite3.Connection, job_id: int, limit: int = 20) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT id, created_at, level, message
          FROM job_logs
         WHERE job_id = ?
         ORDER BY id DESC
         LIMIT ?
        """,
        (job_id, limit),
    ).fetchall()
    return [row_to_dict(row) for row in reversed(rows)]


def job_counts(db: sqlite3.Connection) -> dict[str, int]:
    rows = db.execute("SELECT status, COUNT(*) AS count FROM jobs GROUP BY status").fetchall()
    counts = {row["status"]: row["count"] for row in rows}
    return {
        "running": counts.get("running", 0),
        "pending": counts.get("pending", 0),
        "completed": counts.get("completed", 0),
        "failed": counts.get("failed", 0),
    }
