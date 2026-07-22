from __future__ import annotations

import os
from pathlib import Path


class PathValidationError(ValueError):
    pass


def resolve_download_target(download_dir: str, subfolder: str | None) -> Path:
    root = Path(download_dir).resolve()
    raw = (subfolder or "").strip().replace("\\", "/")
    if raw.startswith("/") or "\x00" in raw:
        raise PathValidationError("Download subfolder must be a relative path.")

    parts = [part for part in raw.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise PathValidationError("Download subfolder cannot contain '..'.")

    target = (root / Path(*parts)).resolve() if parts else root
    common = os.path.commonpath([str(root), str(target)])
    if common != str(root):
        raise PathValidationError("Download subfolder must stay inside DOWNLOAD_DIR.")
    return target
