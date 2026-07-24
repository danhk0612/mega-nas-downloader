from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import load_config
from .db import connect, init_db, job_counts
from .diagnostics import build_status, health
from .jobs import JobService

CONFIG = load_config()
STARTED_AT = datetime.now(timezone.utc).isoformat()
ROOT = Path(__file__).resolve().parent
DB_LOCK = threading.Lock()
DB = connect(CONFIG.database_path)
init_db(DB)
JOBS = JobService(CONFIG, DB, DB_LOCK)


class AppHandler(BaseHTTPRequestHandler):
    server_version = "mega-nas-downloader/0.1"

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self._send_file(ROOT / "templates" / "index.html", "text/html; charset=utf-8")
            return
        if self.path == "/static/app.css":
            self._send_file(ROOT / "static" / "app.css", "text/css; charset=utf-8")
            return
        if self.path == "/static/app.js":
            self._send_file(ROOT / "static" / "app.js", "application/javascript; charset=utf-8")
            return
        if self.path == "/health":
            code, payload = health(CONFIG, STARTED_AT)
            payload = {"ok": code == 200, **payload}
            self._send_json(payload, code)
            return
        if self.path == "/api/status":
            status = build_status(CONFIG, STARTED_AT)
            with DB_LOCK:
                status["jobs"] = {**status["jobs"], **job_counts(DB)}
            self._send_json(status)
            return
        if self.path == "/api/settings":
            self._send_json(public_settings())
            return
        if self.path == "/api/jobs":
            self._send_json({"jobs": JOBS.list_jobs()})
            return
        if self.path.startswith("/api/jobs/"):
            job_id = parse_job_id(self.path)
            if job_id is None:
                self._send_json({"error": {"code": "not_found", "message": "Not found"}}, HTTPStatus.NOT_FOUND)
                return
            job = JOBS.get_job(job_id)
            if job is None:
                self._send_json({"error": {"code": "not_found", "message": "Job not found"}}, HTTPStatus.NOT_FOUND)
                return
            self._send_json({"job": job})
            return
        self._send_json({"error": {"code": "not_found", "message": "Not found"}}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path == "/api/jobs":
            try:
                payload = self._read_json()
                jobs = JOBS.create_jobs(payload)
            except ValueError as exc:
                self.log_message("POST /api/jobs rejected: %s", str(exc))
                self._send_json(
                    {"error": {"code": "invalid_request", "message": str(exc)}},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            except Exception as exc:
                self._send_json(
                    {"error": {"code": "internal_error", "message": str(exc)}},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return
            response = {"jobs": jobs, "created_count": len(jobs)}
            if len(jobs) == 1:
                response["job"] = jobs[0]
            self._send_json(response, HTTPStatus.CREATED)
            return
        self._send_json({"error": {"code": "not_found", "message": "Not found"}}, HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{timestamp} {self.address_string()} {format % args}", flush=True)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            self._send_json({"error": {"code": "not_found", "message": "Not found"}}, HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], status: int | HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload


def public_settings() -> dict[str, Any]:
    return {
        "app_port": CONFIG.app_port,
        "download_dir": CONFIG.download_dir,
        "data_dir": CONFIG.data_dir,
        "temp_dir": CONFIG.temp_dir,
        "max_concurrent_downloads": CONFIG.max_concurrent_downloads,
        "max_visible_jobs": CONFIG.max_visible_jobs,
        "auto_start_pending": CONFIG.auto_start_pending,
        "retry_on_startup": CONFIG.retry_on_startup,
        "max_retry_count": CONFIG.max_retry_count,
        "poll_interval_ms": CONFIG.poll_interval_ms,
        "default_duplicate_policy": CONFIG.default_duplicate_policy,
        "log_level": CONFIG.log_level,
        "timezone": CONFIG.timezone,
    }


def parse_job_id(path: str) -> int | None:
    parts = path.strip("/").split("/")
    if len(parts) != 3 or parts[:2] != ["api", "jobs"]:
        return None
    try:
        return int(parts[2])
    except ValueError:
        return None


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", CONFIG.app_port), AppHandler)
    print(f"mega-nas-downloader listening on :{CONFIG.app_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
