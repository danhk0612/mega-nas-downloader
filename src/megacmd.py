from __future__ import annotations

import re
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlparse

from .db import add_log, utc_now

MEGA_PUBLIC_RE = re.compile(r"^https://mega\.nz/(file|folder)/[^\s]+$", re.IGNORECASE)


def validate_public_mega_url(url: str) -> str:
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc.lower() != "mega.nz":
        raise ValueError("Only https://mega.nz public links are supported.")
    if not MEGA_PUBLIC_RE.match(value):
        raise ValueError("Only https://mega.nz/file/... and https://mega.nz/folder/... links are supported.")
    return value


def mask_mega_url(url: str) -> str:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    kind = path_parts[0] if path_parts else "link"
    token = path_parts[1] if len(path_parts) > 1 else ""
    visible = token[:6] if token else ""
    return f"https://mega.nz/{kind}/{visible}..."


class MegaDownloader:
    def __init__(self, db, lock: threading.Lock):
        self.db = db
        self.lock = lock

    def start_job(self, job_id: int) -> None:
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        thread.start()

    def _run_job(self, job_id: int) -> None:
        with self.lock:
            row = self.db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return
            self.db.execute(
                "UPDATE jobs SET status = 'running', started_at = ?, error_message = NULL WHERE id = ?",
                (utc_now(), job_id),
            )
            self.db.commit()
            add_log(self.db, job_id, "info", "Download started.")

        target_dir = Path(row["target_dir"])
        target_dir.mkdir(parents=True, exist_ok=True)
        command = ["mega-get", row["mega_url"], str(target_dir)]

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            with self.lock:
                self.db.execute("UPDATE jobs SET process_id = ? WHERE id = ?", (process.pid, job_id))
                self.db.commit()

            recent_output: list[str] = []
            assert process.stdout is not None
            for line in process.stdout:
                clean = line.strip()
                if clean:
                    recent_output.append(clean)
                    if len(recent_output) > 20:
                        recent_output.pop(0)

            exit_code = process.wait()
            with self.lock:
                if exit_code == 0:
                    self.db.execute(
                        """
                        UPDATE jobs
                           SET status = 'completed',
                               completed_at = ?,
                               process_id = NULL,
                               error_message = NULL
                         WHERE id = ?
                        """,
                        (utc_now(), job_id),
                    )
                    self.db.commit()
                    add_log(self.db, job_id, "info", "Download completed.")
                else:
                    message = "\n".join(recent_output[-5:]) or f"mega-get exited with code {exit_code}"
                    self.db.execute(
                        """
                        UPDATE jobs
                           SET status = 'failed',
                               completed_at = ?,
                               process_id = NULL,
                               error_message = ?
                         WHERE id = ?
                        """,
                        (utc_now(), message, job_id),
                    )
                    self.db.commit()
                    add_log(self.db, job_id, "error", f"Download failed with exit code {exit_code}.")
        except FileNotFoundError:
            self._fail_job(job_id, "mega-get executable not found.")
        except Exception as exc:
            self._fail_job(job_id, str(exc))

    def _fail_job(self, job_id: int, message: str) -> None:
        with self.lock:
            self.db.execute(
                """
                UPDATE jobs
                   SET status = 'failed',
                       completed_at = ?,
                       process_id = NULL,
                       error_message = ?
                 WHERE id = ?
                """,
                (utc_now(), message, job_id),
            )
            self.db.commit()
            add_log(self.db, job_id, "error", message)
