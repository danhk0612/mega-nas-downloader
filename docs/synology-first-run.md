# Synology First Run

This checklist installs or updates the stable Docker image on Synology DSM with Container Manager.

Assumptions:

- Repository: `https://github.com/danhk0612/mega-nas-downloader.git`
- Docker image: `ghcr.io/danhk0612/mega-nas-downloader:1.0.0`
- Project path: `/volume1/docker/mega-nas-downloader`
- Download path: `/volume1/Download/_mega/file`
- App data path: `/volume1/Download/_mega/data`
- Host port: `3010`
- DSM user UID/GID example: `PUID=1026`, `PGID=100`

Adjust paths and IDs before running if your NAS uses different values.

## 1. Prepare Directories

```bash
mkdir -p /volume1/docker
mkdir -p /volume1/Download/_mega/file
mkdir -p /volume1/Download/_mega/data
```

Check your current user's UID/GID:

```bash
id
```

If the UID/GID differ from `1026:100`, override `PUID` and `PGID` in `compose.override.yml`.

## 2. Clone Or Update Repository

First clone:

```bash
cd /volume1/docker
git clone https://github.com/danhk0612/mega-nas-downloader.git
cd mega-nas-downloader
```

If the repository already exists:

```bash
cd /volume1/docker/mega-nas-downloader
git pull
```

If `git pull` fails because `compose.yml` was edited locally, save that local file and move local settings into `compose.override.yml`:

```bash
cd /volume1/docker/mega-nas-downloader
cp compose.yml compose.yml.local-backup
git stash push -m "local compose settings" -- compose.yml
git pull
```

## 3. Add Local Settings

Keep local credentials and NAS-specific settings in `compose.override.yml`:

```bash
vi compose.override.yml
```

Example:

```yaml
services:
  mega-downloader:
    environment:
      APP_USERNAME: "your-user"
      APP_PASSWORD: "your-password"
      PUID: 1026
      PGID: 100
```

Leave `APP_USERNAME` and `APP_PASSWORD` empty only when the service is limited to a trusted private network.

## 4. Review Compose Settings

```bash
sudo docker compose config
```

Check these values:

```yaml
image: ghcr.io/danhk0612/mega-nas-downloader:1.0.0
ports:
  - "3010:3000"
volumes:
  - /volume1/Download/_mega/file:/downloads
  - /volume1/Download/_mega/data:/data
```

## 5. Pull And Start

```bash
cd /volume1/docker/mega-nas-downloader
sudo docker compose pull
sudo docker compose up -d --force-recreate
```

Check container status:

```bash
sudo docker compose ps
```

## 6. Check Logs

```bash
sudo docker compose logs --tail=100 mega-downloader
```

Useful lines to look for:

- Python server started on port `3000`
- No permission error for `/downloads`
- No permission error for `/data`
- No MEGAcmd runtime error

## 7. Check Health And Version

From the NAS terminal:

```bash
curl -i http://127.0.0.1:3010/health
```

Expected result:

- `/health` returns `200 OK`

If authentication is disabled:

```bash
curl -s http://127.0.0.1:3010/api/status
```

If authentication is enabled:

```bash
curl -s -u 'your-user:your-password' http://127.0.0.1:3010/api/status
```

Expected result:

- `app.version` is `1.0.0`
- `megacmd.ok` is `true`
- `paths.download_dir_writable.ok` is `true`
- `paths.data_dir_writable.ok` is `true`

Unauthenticated `/api/status` should return `401 Unauthorized` when authentication is enabled.

## 8. Open Web UI

Open this from a browser on the same network:

```text
http://NAS_IP:3010
```

Use `http://` for direct access to port `3010`. If you open `https://NAS_IP:3010` directly, the app logs will show HTTP 400 errors because this container does not terminate TLS by itself.

## 9. Test One Download

Use a small public MEGA test link first.

After creating a job, check:

```bash
sudo docker compose logs --tail=100 mega-downloader
ls -la /volume1/Download/_mega/file
ls -la /volume1/Download/_mega/data
```

Expected behavior:

- Job is created in SQLite.
- `mega-get` is executed.
- Running jobs update `progress` when MEGAcmd reports percentages.
- Pending/running jobs can be canceled.
- Failed/canceled/completed jobs can be retried.
- Duplicate handling follows the selected policy: `rename`, `skip`, or `overwrite`.
- Completed jobs show `progress = 100`, downloaded bytes, and recent job logs.

## 10. Build Locally Instead

Normal deployments should use the published image. To build from source:

```bash
sudo docker compose -f compose.yml -f compose.build.yml up -d --build --force-recreate
```

## 11. Stop Or Restart

```bash
sudo docker compose restart
sudo docker compose down
```

## 12. Report Back

Please send these outputs after the first run:

```bash
id
sudo docker compose ps
sudo docker compose logs --tail=100 mega-downloader
curl -i http://127.0.0.1:3010/health
curl -s -u 'your-user:your-password' http://127.0.0.1:3010/api/status
```

Do not paste MEGA links that include private keys unless they are intentionally public test links.
