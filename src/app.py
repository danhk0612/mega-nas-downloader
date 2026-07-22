from __future__ import annotations

import json
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import load_config
from .diagnostics import build_status, health

CONFIG = load_config()
STARTED_AT = datetime.now(timezone.utc).isoformat()
ROOT = Path(__file__).resolve().parent


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
            self._send_json(build_status(CONFIG, STARTED_AT))
            return
        if self.path == "/api/settings":
            self._send_json(public_settings())
            return
        if self.path == "/api/jobs":
            self._send_json({"jobs": []})
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


def public_settings() -> dict[str, Any]:
    return {
        "app_port": CONFIG.app_port,
        "download_dir": CONFIG.download_dir,
        "data_dir": CONFIG.data_dir,
        "temp_dir": CONFIG.temp_dir,
        "max_concurrent_downloads": CONFIG.max_concurrent_downloads,
        "auto_start_pending": CONFIG.auto_start_pending,
        "retry_on_startup": CONFIG.retry_on_startup,
        "max_retry_count": CONFIG.max_retry_count,
        "poll_interval_ms": CONFIG.poll_interval_ms,
        "default_duplicate_policy": CONFIG.default_duplicate_policy,
        "log_level": CONFIG.log_level,
        "timezone": CONFIG.timezone,
    }


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", CONFIG.app_port), AppHandler)
    print(f"mega-nas-downloader listening on :{CONFIG.app_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
