from __future__ import annotations

import os
from dataclasses import dataclass


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    app_port: int
    download_dir: str
    data_dir: str
    temp_dir: str
    max_concurrent_downloads: int
    max_visible_jobs: int
    auto_start_pending: bool
    retry_on_startup: bool
    max_retry_count: int
    poll_interval_ms: int
    default_duplicate_policy: str
    log_level: str
    timezone: str
    database_path: str


def load_config() -> Config:
    max_concurrent_downloads = max(1, env_int("MAX_CONCURRENT_DOWNLOADS", 2))
    return Config(
        app_port=env_int("APP_PORT", 3000),
        download_dir=os.environ.get("DOWNLOAD_DIR", "/downloads"),
        data_dir=os.environ.get("DATA_DIR", "/data"),
        temp_dir=os.environ.get("TEMP_DIR", "/data/temp"),
        max_concurrent_downloads=max_concurrent_downloads,
        max_visible_jobs=max(1, env_int("MAX_VISIBLE_JOBS", 500)),
        auto_start_pending=env_bool("AUTO_START_PENDING", True),
        retry_on_startup=env_bool("RETRY_ON_STARTUP", False),
        max_retry_count=env_int("MAX_RETRY_COUNT", 3),
        poll_interval_ms=env_int("POLL_INTERVAL_MS", 1000),
        default_duplicate_policy=os.environ.get("DEFAULT_DUPLICATE_POLICY", "rename"),
        log_level=os.environ.get("LOG_LEVEL", "info"),
        timezone=os.environ.get("TZ", "Asia/Seoul"),
        database_path=os.path.join(os.environ.get("DATA_DIR", "/data"), "app.sqlite3"),
    )
