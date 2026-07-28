# MEGA NAS Downloader

Personal web UI for downloading public MEGA links directly on a NAS with Docker.

This project is not affiliated with or endorsed by MEGA.

## Status

Current release: `1.0.0`

The `1.0.0` release is intended as the first stable self-hosted Docker release for Synology NAS use.

Implemented:

- Single Docker image for `linux/amd64`
- Minimal Python web server and responsive web UI
- `/health`, `/api/status`, and `/api/jobs`
- MEGAcmd availability check
- Download and data volume write checks
- SQLite job storage
- Bulk URL registration from multi-line paste or copied text that contains MEGA URLs
- MEGA public file/folder link validation, including modern and legacy public link forms
- Queue concurrency enforced by `MAX_CONCURRENT_DOWNLOADS`
- `mega-get` execution through MEGAcmd
- Live progress parsing from `mega-get` output when MEGAcmd reports percentages
- Cancel for pending/running jobs
- Retry for failed/canceled/completed jobs
- Optional Basic authentication with `APP_USERNAME` and `APP_PASSWORD`
- Duplicate policies: `rename`, `skip`, `overwrite`
- Hidden temporary download folder before final file placement
- Completed/failed status persistence
- Basic per-job log storage
- Completed job file/size summary
- Recent job logs in the web UI

## Docker Image

Published image:

```text
ghcr.io/danhk0612/mega-nas-downloader:1.0.0
```

Use `:1.0.0` for stable deployments. `:latest` follows the latest published build from the default branch.

## Quick Start

Requirements:

- Docker / Docker Compose
- x86-64 host for the current MEGAcmd package wiring

```bash
docker compose up -d
```

Open:

```text
http://localhost:3010
```

Health check:

```bash
curl http://localhost:3010/health
```

## Synology Compose Example

The included `compose.yml` is prepared for the target Synology path layout:

```yaml
services:
  mega-downloader:
    image: ghcr.io/danhk0612/mega-nas-downloader:1.0.0
    container_name: mega-downloader
    restart: unless-stopped
    ports:
      - "3010:3000"
    environment:
      TZ: Asia/Seoul
      DOWNLOAD_DIR: /downloads
      DATA_DIR: /data
      MAX_CONCURRENT_DOWNLOADS: 2
      PUID: 1026
      PGID: 100
      UMASK: "022"
    volumes:
      - /volume1/Download/_mega/file:/downloads
      - /volume1/Download/_mega/data:/data
```

For local NAS-only settings such as credentials, prefer `compose.override.yml` so `git pull` does not conflict with local edits:

```yaml
services:
  mega-downloader:
    environment:
      APP_USERNAME: "your-user"
      APP_PASSWORD: "your-password"
```

## Build From Source

Normal deployments should use the published image. To build locally:

```bash
docker compose -f compose.yml -f compose.build.yml up -d --build
```

## Environment Variables

| Variable | Default | Description |
|---|---:|---|
| `APP_PORT` | `3000` | Web server port inside the container |
| `DOWNLOAD_DIR` | `/downloads` | Target directory for completed downloads |
| `DATA_DIR` | `/data` | Persistent application data directory |
| `TEMP_DIR` | `/data/temp` | Reserved temporary work directory |
| `MAX_CONCURRENT_DOWNLOADS` | `2` | Maximum number of downloads that can run at the same time |
| `MAX_VISIBLE_JOBS` | `500` | Maximum number of recent jobs returned to the web UI |
| `AUTO_START_PENDING` | `true` | Automatically start pending jobs after registration and app startup |
| `RETRY_ON_STARTUP` | `false` | Reserved startup retry setting |
| `MAX_RETRY_COUNT` | `3` | Reserved retry limit setting |
| `POLL_INTERVAL_MS` | `1000` | Reserved polling interval setting |
| `DEFAULT_DUPLICATE_POLICY` | `rename` | Duplicate file behavior: `rename`, `skip`, or `overwrite` |
| `APP_USERNAME` | empty | Optional Basic auth username. Auth is disabled when both auth variables are empty |
| `APP_PASSWORD` | empty | Optional Basic auth password. Auth is disabled when both auth variables are empty |
| `LOG_LEVEL` | `info` | Application log level |
| `TZ` | `Asia/Seoul` | Container timezone |
| `PUID` | `1026` | Runtime user id |
| `PGID` | `100` | Runtime group id |
| `UMASK` | `022` | File creation mask |

## Authentication

Set `APP_USERNAME` and `APP_PASSWORD` to protect the web UI and API with Basic Auth.

`/health` is intentionally left unauthenticated so Docker health checks continue to work.

Check unauthenticated access:

```bash
curl -i http://127.0.0.1:3010/api/status
```

Expected result when auth is enabled: `401 Unauthorized`.

Check authenticated access:

```bash
curl -i -u 'your-user:your-password' http://127.0.0.1:3010/api/status
```

Expected result: `200 OK`.

## MEGAcmd Packaging

The Dockerfile downloads MEGAcmd from MEGA's official Debian 12 package URL during image build. The binary package is not stored in this repository.

Current Dockerfile support is intentionally limited to `amd64`, which matches the target Synology x86-64 NAS environment. ARM64 can be reviewed later if MEGA package availability is confirmed.

## Security Notes

- Do not expose this service publicly without setting `APP_USERNAME`/`APP_PASSWORD` or placing a trusted reverse proxy in front of it.
- Full MEGA links may contain access keys. Do not share private MEGA links in logs, issues, screenshots, or public support messages.
- Host download paths must be mounted intentionally. User-provided subfolders are kept inside `DOWNLOAD_DIR`.

## License

This project is released under the MIT License. MEGAcmd is a separate project with its own license terms.
