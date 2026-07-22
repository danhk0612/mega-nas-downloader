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
        self.downloader = MegaDownloader(db, lock)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self.lock:
            return list_jobs(self.db)

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self.lock:
            return get_job(self.db, job_id)

    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        mega_url = validate_public_mega_url(str(payload.get("mega_url", "")))
        name = str(payload.get("name") or "").strip() or None
        subfolder = str(payload.get("subfolder") or "").strip()
        duplicate_policy = self.config.default_duplicate_policy
        if duplicate_policy != "rename":
            raise ValueError("Only the 'rename' duplicate policy is implemented in this stage.")

        target_dir = resolve_download_target(self.config.download_dir, subfolder)

        with self.lock:
            cursor = self.db.execute(
                """
                INSERT INTO jobs (
                    name, mega_url, mega_url_masked, subfolder, target_dir,
                    duplicate_policy, status, registered_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    name,
                    mega_url,
                    mask_mega_url(mega_url),
                    subfolder,
                    str(target_dir),
                    duplicate_policy,
                    utc_now(),
                ),
            )
            job_id = int(cursor.lastrowid)
            self.db.commit()
            job = get_job(self.db, job_id)

        self.downloader.start_job(job_id)
        return job or {"id": job_id}
