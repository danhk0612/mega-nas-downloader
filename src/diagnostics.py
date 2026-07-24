from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from . import APP_VERSION
from .config import Config


def _check_writable(path: str) -> dict[str, Any]:
    target = Path(path)
    try:
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target, prefix=".write-test-", delete=True) as handle:
            handle.write(b"ok")
        return {"ok": True, "path": str(target)}
    except Exception as exc:
        return {"ok": False, "path": str(target), "error": str(exc)}


def _megacmd_version() -> dict[str, Any]:
    commands = (
        ("mega-version",),
        ("mega-cmd", "--version"),
    )
    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=8,
            )
        except FileNotFoundError:
            continue
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        output = result.stdout.strip()
        return {
            "ok": result.returncode == 0,
            "command": list(command),
            "version": output or "unknown",
            "exit_code": result.returncode,
        }

    return {"ok": False, "error": "MEGAcmd executable not found"}


def build_status(config: Config, started_at: str) -> dict[str, Any]:
    download_check = _check_writable(config.download_dir)
    data_check = _check_writable(config.data_dir)
    usage = shutil.disk_usage(config.download_dir) if os.path.exists(config.download_dir) else None
    return {
        "app": {
            "name": "mega-nas-downloader",
            "version": APP_VERSION,
            "started_at": started_at,
            "timezone": config.timezone,
        },
        "paths": {
            "download_dir": config.download_dir,
            "data_dir": config.data_dir,
            "temp_dir": config.temp_dir,
            "download_dir_writable": download_check,
            "data_dir_writable": data_check,
        },
        "download_disk": {
            "total": usage.total if usage else None,
            "used": usage.used if usage else None,
            "free": usage.free if usage else None,
        },
        "megacmd": _megacmd_version(),
        "config": {
            "max_concurrent_downloads": config.max_concurrent_downloads,
            "max_visible_jobs": config.max_visible_jobs,
            "poll_interval_ms": config.poll_interval_ms,
        },
        "jobs": {
            "running": 0,
            "pending": 0,
            "completed": 0,
            "failed": 0,
            "total_speed": None,
        },
    }


def health(config: Config, started_at: str) -> tuple[int, dict[str, Any]]:
    status = build_status(config, started_at)
    checks = {
        "web": True,
        "data_dir_writable": bool(status["paths"]["data_dir_writable"]["ok"]),
        "megacmd": bool(status["megacmd"]["ok"]),
    }
    status["checks"] = checks
    healthy = all(checks.values())
    return (200 if healthy else 503), status
