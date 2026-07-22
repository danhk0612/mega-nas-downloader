from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    port = os.environ.get("APP_PORT", "3000")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return 0 if response.status == 200 and payload.get("ok") is True else 1
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
