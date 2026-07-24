from __future__ import annotations

import subprocess
import threading
import re
import time
from pathlib import Path
from collections.abc import Iterator
from urllib.parse import urlparse

from collections.abc import Callable

from .db import add_log, utc_now

PERCENT_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*%")
SPEED_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(B|KB|KiB|MB|MiB|GB|GiB|TB|TiB)\s*/\s*s", re.IGNORECASE)
TRANSFER_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(B|KB|KiB|MB|MiB|GB|GiB|TB|TiB)\s*(?:/|of)\s*"
    r"(\d+(?:\.\d+)?)\s*(B|KB|KiB|MB|MiB|GB|GiB|TB|TiB)",
    re.IGNORECASE,
)

def validate_public_mega_url(url: str) -> str:
    value = url.strip().strip("<>()[]{}\"'`,;")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc.lower() != "mega.nz":
        raise ValueError("Only https://mega.nz public links are supported.")
    path = parsed.path.strip("/")
    fragment = parsed.fragment
    modern = path.split("/", 1)[0].lower() in {"file", "folder"}
    legacy = fragment.startswith("!") or fragment.startswith("F!")
    if not modern and not legacy:
        raise ValueError("Only MEGA public file/folder links are supported.")
    return value


def mask_mega_url(url: str) -> str:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    kind = path_parts[0] if path_parts else "link"
    token = path_parts[1] if len(path_parts) > 1 else ""
    visible = token[:6] if token else ""
    return f"https://mega.nz/{kind}/{visible}..."


class MegaDownloader:
    def __init__(self, db, lock: threading.Lock, on_job_finished: Callable[[], None] | None = None):
        self.db = db
        self.lock = lock
        self.on_job_finished = on_job_finished

    def start_job(self, job_id: int) -> None:
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        thread.start()

    def _run_job(self, job_id: int) -> None:
        try:
            with self.lock:
                row = self.db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if row is None:
                    return
                add_log(self.db, job_id, "info", "Download started.")

            target_dir = Path(row["target_dir"])
            target_dir.mkdir(parents=True, exist_ok=True)
            before_files = snapshot_files(target_dir)
            command = ["mega-get", row["mega_url"], str(target_dir)]

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            with self.lock:
                self.db.execute("UPDATE jobs SET process_id = ? WHERE id = ?", (process.pid, job_id))
                self.db.commit()

            recent_output: list[str] = []
            assert process.stdout is not None
            for line in iter_process_output(process.stdout):
                clean = line.strip()
                if clean:
                    recent_output.append(clean)
                    if len(recent_output) > 20:
                        recent_output.pop(0)
                    self._update_progress_from_output(job_id, clean)

            exit_code = process.wait()
            with self.lock:
                if exit_code == 0:
                    changed_files = diff_files(before_files, snapshot_files(target_dir))
                    downloaded_bytes = sum(item["size"] for item in changed_files)
                    self.db.execute(
                        """
                        UPDATE jobs
                           SET status = 'completed',
                               completed_at = ?,
                               process_id = NULL,
                               error_message = NULL,
                               progress = 100,
                               downloaded_bytes = ?,
                               total_bytes = ?
                         WHERE id = ?
                        """,
                        (utc_now(), downloaded_bytes, downloaded_bytes, job_id),
                    )
                    self.db.commit()
                    add_log(self.db, job_id, "info", "Download completed.")
                    if changed_files:
                        add_log(self.db, job_id, "info", format_changed_files(changed_files))
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
        finally:
            if self.on_job_finished is not None:
                self.on_job_finished()

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

    def _update_progress_from_output(self, job_id: int, line: str) -> None:
        progress = parse_progress_percent(line)
        if progress is None:
            return

        downloaded_bytes, total_bytes = parse_transfer_bytes(line)
        speed_bytes = parse_speed_bytes_per_sec(line)
        updates = ["progress = ?"]
        params: list[float | int | None] = [progress]

        if downloaded_bytes is not None:
            updates.append("downloaded_bytes = ?")
            params.append(downloaded_bytes)
        if total_bytes is not None:
            updates.append("total_bytes = ?")
            params.append(total_bytes)
        if speed_bytes is not None:
            updates.append("speed_bytes_per_sec = ?")
            params.append(speed_bytes)

        params.append(job_id)
        with self.lock:
            self.db.execute(
                f"UPDATE jobs SET {', '.join(updates)} WHERE id = ? AND status = 'running'",
                tuple(params),
            )
            self.db.commit()


def iter_process_output(stream) -> Iterator[str]:
    buffer = ""
    last_emit_at = time.monotonic()
    last_emitted = ""
    while True:
        char = stream.read(1)
        if char == "":
            if buffer and buffer != last_emitted:
                yield buffer
            return
        if char in "\r\n":
            if buffer and buffer != last_emitted:
                yield buffer
                last_emitted = buffer
                buffer = ""
                last_emit_at = time.monotonic()
            else:
                buffer = ""
            continue
        buffer += char
        now = time.monotonic()
        if "%" in buffer and now - last_emit_at >= 1:
            yield buffer
            last_emitted = buffer
            last_emit_at = now


def parse_progress_percent(line: str) -> float | None:
    matches = PERCENT_RE.findall(line)
    if not matches:
        return None
    progress = float(matches[-1])
    if progress < 0 or progress > 100:
        return None
    return progress


def parse_transfer_bytes(line: str) -> tuple[int | None, int | None]:
    match = TRANSFER_RE.search(line)
    if match is None:
        return (None, None)
    downloaded = parse_size_to_bytes(match.group(1), match.group(2))
    total = parse_size_to_bytes(match.group(3), match.group(4))
    return (downloaded, total)


def parse_speed_bytes_per_sec(line: str) -> int | None:
    match = SPEED_RE.search(line)
    if match is None:
        return None
    return parse_size_to_bytes(match.group(1), match.group(2))


def parse_size_to_bytes(value: str, unit: str) -> int:
    multipliers = {
        "b": 1,
        "kb": 1000,
        "kib": 1024,
        "mb": 1000**2,
        "mib": 1024**2,
        "gb": 1000**3,
        "gib": 1024**3,
        "tb": 1000**4,
        "tib": 1024**4,
    }
    return int(float(value) * multipliers[unit.lower()])


def snapshot_files(directory: Path) -> dict[Path, tuple[int, int]]:
    if not directory.exists():
        return {}
    files: dict[Path, tuple[int, int]] = {}
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        files[path.relative_to(directory)] = (stat.st_size, stat.st_mtime_ns)
    return files


def diff_files(
    before: dict[Path, tuple[int, int]],
    after: dict[Path, tuple[int, int]],
) -> list[dict[str, int | str]]:
    changed: list[dict[str, int | str]] = []
    for path, (size, mtime_ns) in after.items():
        if before.get(path) != (size, mtime_ns):
            changed.append({"path": path.as_posix(), "size": size})
    return sorted(changed, key=lambda item: str(item["path"]))


def format_changed_files(files: list[dict[str, int | str]]) -> str:
    visible = files[:10]
    names = ", ".join(str(item["path"]) for item in visible)
    remaining = len(files) - len(visible)
    suffix = f" and {remaining} more" if remaining > 0 else ""
    return f"Downloaded files: {names}{suffix}"
