from __future__ import annotations

import sqlite3
import threading
from typing import Any

from .config import Config
from .db import get_job, list_jobs, utc_now
from .megacmd import MegaDownloader, mask_mega_url, validate_public_mega_url
from .paths import resolve_download_target


class JobService:
    def __init__(self, config: Config, db: sqlite3.Connection, lock: threading.Lock):
        self.config = config
        self.db = db
        self.lock = lock
        self.downloader = MegaDownloader(db, lock, on_job_finished=self.start_pending_jobs)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self.lock:
            return list_jobs(self.db, include_logs=True, limit=self.config.max_visible_jobs)

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self.lock:
            return get_job(self.db, job_id, include_logs=True)

    def create_jobs(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        mega_urls = parse_mega_urls(payload)
        name = str(payload.get("name") or "").strip() or None
        subfolder = str(payload.get("subfolder") or "").strip()
        duplicate_policy = self.config.default_duplicate_policy
        if duplicate_policy != "rename":
            raise ValueError("Only the 'rename' duplicate policy is implemented in this stage.")

        target_dir = resolve_download_target(self.config.download_dir, subfolder)

        jobs: list[dict[str, Any]] = []
        with self.lock:
            for mega_url in mega_urls:
                cursor = self.db.execute(
                    """
                    INSERT INTO jobs (
                        name, mega_url, mega_url_masked, subfolder, target_dir,
                        duplicate_policy, status, registered_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        name if len(mega_urls) == 1 else None,
                        mega_url,
                        mask_mega_url(mega_url),
                        subfolder,
                        str(target_dir),
                        duplicate_policy,
                        utc_now(),
                    ),
                )
                job_id = int(cursor.lastrowid)
                job = get_job(self.db, job_id)
                if job is not None:
                    jobs.append(job)
            self.db.commit()

        self.start_pending_jobs()
        return jobs

    def start_pending_jobs(self) -> None:
        with self.lock:
            running = self.db.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE status = 'running'"
            ).fetchone()["count"]
            available = max(0, self.config.max_concurrent_downloads - int(running))
            if available <= 0:
                return
            rows = self.db.execute(
                """
                SELECT id
                  FROM jobs
                 WHERE status = 'pending'
                 ORDER BY registered_at ASC, id ASC
                 LIMIT ?
                """,
                (available,),
            ).fetchall()
            job_ids = [int(row["id"]) for row in rows]
            now = utc_now()
            for job_id in job_ids:
                self.db.execute(
                    """
                    UPDATE jobs
                       SET status = 'running',
                           started_at = ?,
                           error_message = NULL
                     WHERE id = ?
                    """,
                    (now, job_id),
                )
            self.db.commit()

        for job_id in job_ids:
            self.downloader.start_job(job_id)


def parse_mega_urls(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    raw_many = payload.get("mega_urls")
    if isinstance(raw_many, list):
        values.extend(str(item).strip() for item in raw_many)

    raw_one = str(payload.get("mega_url", ""))
    values.extend(line.strip() for line in raw_one.splitlines())
    values = [value for value in values if value]
    if not values:
        raise ValueError("At least one MEGA URL is required.")

    seen: set[str] = set()
    urls: list[str] = []
    for index, value in enumerate(values, start=1):
        try:
            url = validate_public_mega_url(value)
        except ValueError as exc:
            raise ValueError(f"Line {index}: {exc}") from exc
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls
