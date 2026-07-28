# Changelog

## 1.0.0 - 2026-07-28

First stable self-hosted Docker release for Synology NAS use.

### Added

- Published Docker image target: `ghcr.io/danhk0612/mega-nas-downloader:1.0.0`
- GitHub Actions workflow for GHCR image publishing
- Stable `compose.yml` that pulls the published image
- `compose.build.yml` for local source builds
- Optional Basic authentication with `APP_USERNAME` and `APP_PASSWORD`
- Cancel action for pending/running jobs
- Retry action for failed/canceled/completed jobs
- Duplicate policies: `rename`, `skip`, `overwrite`
- Hidden temporary download folder before final file placement
- Live progress parsing from MEGAcmd output when percentages are reported

### Changed

- Promoted application version from `0.1.0-alpha.8` to `1.0.0`
- Reworked README around stable image deployment
- Reworked Synology first-run instructions around image pull, local override files, and authenticated checks

### Notes

- The Docker image currently targets `linux/amd64`.
- `/health` remains unauthenticated for Docker health checks.
