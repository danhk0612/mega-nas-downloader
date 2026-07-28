from __future__ import annotations

import subprocess
import threading
import re
import time
import os
import shutil
import signal
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
        self.processes: dict[int, subprocess.Popen[str]] = {}
        self.processes_lock = threading.Lock()

    def start_job(self, job_id: int) -> None:
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        thread.start()

    def cancel_job(self, job_id: int) -> bool:
        with self.processes_lock:
            process = self.processes.get(job_id)
        if process is None or process.poll() is not None:
            return False
        terminate_process(process)
        return True

    def _run_job(self, job_id: int) -> None:
        try:
            with self.lock:
                row = self.db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if row is None:
                    return
                add_log(self.db, job_id, "info", "Download started.")

            target_dir = Path(row["target_dir"])
            target_dir.mkdir(parents=True, exist_ok=True)
            temp_dir = prepare_job_temp_dir(target_dir, job_id)
            command = ["mega-get", row["mega_url"], str(temp_dir)]

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            with self.processes_lock:
                self.processes[job_id] = process
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
            with self.processes_lock:
                self.processes.pop(job_id, None)
            with self.lock:
                row = self.db.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
                was_canceled = row is not None and row["status"] == "canceled"

                if was_canceled:
                    add_log(self.db, job_id, "info", "Download canceled.")
                elif exit_code == 0:
                    changed_files = finalize_temp_download(
                        temp_dir,
                        target_dir,
                        str(row_duplicate_policy(self.db, job_id)),
                    )
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
            with self.processes_lock:
                self.processes.pop(job_id, None)
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


def terminate_process(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        process.terminate()

    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            process.kill()


def prepare_job_temp_dir(target_dir: Path, job_id: int) -> Path:
    temp_root = target_dir / ".mega-nas-downloader-tmp"
    temp_dir = temp_root / f"job-{job_id}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def row_duplicate_policy(db, job_id: int) -> str:
    row = db.execute("SELECT duplicate_policy FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return "rename"
    policy = row["duplicate_policy"]
    return policy if policy in {"rename", "skip", "overwrite"} else "rename"


def finalize_temp_download(
    temp_dir: Path,
    target_dir: Path,
    duplicate_policy: str,
) -> list[dict[str, int | str]]:
    moved: list[dict[str, int | str]] = []
    if not temp_dir.exists():
        return moved

    for source in sorted(temp_dir.iterdir(), key=lambda path: path.name):
        destination = target_dir / source.name
        final_destination = resolve_duplicate_destination(destination, duplicate_policy)
        if final_destination is None:
            remove_path(source)
            continue
        if duplicate_policy == "overwrite" and final_destination.exists():
            remove_path(final_destination)
        final_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(final_destination))
        moved.extend(snapshot_moved_files(final_destination, target_dir))

    try:
        temp_dir.rmdir()
        temp_dir.parent.rmdir()
    except OSError:
        pass
    return sorted(moved, key=lambda item: str(item["path"]))


def resolve_duplicate_destination(destination: Path, duplicate_policy: str) -> Path | None:
    if not destination.exists():
        return destination
    if duplicate_policy == "skip":
        return None
    if duplicate_policy == "overwrite":
        return destination
    return unique_destination(destination)


def unique_destination(destination: Path) -> Path:
    parent = destination.parent
    stem = destination.stem
    suffix = destination.suffix
    for index in range(1, 10000):
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find available filename for {destination.name}")


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def snapshot_moved_files(path: Path, root: Path) -> list[dict[str, int | str]]:
    files: list[dict[str, int | str]] = []
    if path.is_file():
        stat = path.stat()
        files.append({"path": path.relative_to(root).as_posix(), "size": stat.st_size})
        return files
    if not path.is_dir():
        return files
    for child in path.rglob("*"):
        if child.is_file():
            stat = child.stat()
            files.append({"path": child.relative_to(root).as_posix(), "size": stat.st_size})
    return files


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
