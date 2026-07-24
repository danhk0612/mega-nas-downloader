# MEGA NAS Downloader

Personal web UI for downloading public MEGA links directly on a NAS with Docker.

This project is not affiliated with or endorsed by MEGA.

## Recommended Repository Description

```text
Personal web UI for downloading public MEGA links directly on a NAS with Docker.
```

Recommended license: **MIT License**. This project is a small personal utility and the MIT License keeps reuse, self-hosting, and contribution rules simple. MEGAcmd remains a separate upstream project with its own license terms.

## Status

`0.1.0-alpha.7` includes bulk job registration, enforced queue concurrency, completed-job file summaries, fast registration responses that start queued downloads in the background, more tolerant MEGA URL extraction from pasted text, and live progress parsing from MEGAcmd output.

Implemented:

- Single Docker image skeleton
- Minimal Python web server
- `/health`
- `/api/status`
- Basic responsive web UI
- MEGAcmd availability check
- Download and data volume write checks
- MEGA public file/folder link validation, including modern and legacy public link forms
- SQLite job storage
- Download job creation API and UI form
- Bulk URL registration from multi-line paste or copied text that contains MEGA URLs
- Queue concurrency enforced by `MAX_CONCURRENT_DOWNLOADS`
- Basic `mega-get` execution
- Live progress parsing from `mega-get` output when MEGAcmd reports percentages
- Completed/failed status persistence
- Basic per-job log storage
- Completed job file/size summary
- Recent job logs in the web UI

Not implemented yet:

- Cancel, retry
- Authentication
- Fully enforced duplicate policies beyond the default `rename` behavior

## Quick Start

Requirements:

- Docker / Docker Compose
- x86-64 host for the current MEGAcmd package wiring

```bash
docker compose up -d --build
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

Edit the host paths in `compose.yml` before running in Synology Container Manager.

```yaml
services:
  mega-downloader:
    build: .
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
      - /volume1/docker/mega-downloader/downloads:/downloads
      - /volume1/docker/mega-downloader/data:/data
```

## Environment Variables

| Variable | Default | Description |
|---|---:|---|
| `APP_PORT` | `3000` | Web server port inside the container |
| `DOWNLOAD_DIR` | `/downloads` | Target directory for completed downloads |
| `DATA_DIR` | `/data` | Persistent application data directory |
| `TEMP_DIR` | `/data/temp` | Temporary work directory |
| `MAX_CONCURRENT_DOWNLOADS` | `2` | Maximum number of downloads that can run at the same time |
| `MAX_VISIBLE_JOBS` | `500` | Maximum number of recent jobs returned to the web UI |
| `AUTO_START_PENDING` | `true` | Planned startup behavior for pending jobs |
| `RETRY_ON_STARTUP` | `false` | Planned startup behavior for interrupted jobs |
| `MAX_RETRY_COUNT` | `3` | Planned retry limit |
| `POLL_INTERVAL_MS` | `1000` | Planned UI/API polling interval |
| `DEFAULT_DUPLICATE_POLICY` | `rename` | Duplicate file behavior. Only `rename` is implemented in the current stage |
| `LOG_LEVEL` | `info` | Application log level |
| `TZ` | `Asia/Seoul` | Container timezone |
| `PUID` | `1026` | Runtime user id |
| `PGID` | `100` | Runtime group id |
| `UMASK` | `022` | File creation mask |

## MEGAcmd Packaging

The Dockerfile downloads MEGAcmd from MEGA's official Debian 12 package URL during image build. The binary package is not stored in this repository.

Current Dockerfile support is intentionally limited to `amd64`, which matches the target Synology x86-64 NAS environment. ARM64 can be reviewed later if MEGA package availability is confirmed.

## Security Notes

- Do not expose this service publicly without authentication or a trusted reverse proxy in front of it.
- Full MEGA links may contain access keys. Application logs should avoid printing full links when download jobs are implemented.
- Host download paths must be mounted intentionally. User-provided subfolders will need to stay inside `DOWNLOAD_DIR`.

## License

This project is released under the MIT License. MEGAcmd is a separate project with its own license terms.
