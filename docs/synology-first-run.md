# Synology First Run

This checklist verifies the current alpha build on Synology DSM with Container Manager.

Assumptions:

- Repository: `https://github.com/danhk0612/mega-nas-downloader.git`
- Project path: `/volume1/docker/mega-nas-downloader`
- Download path: `/volume1/docker/mega-downloader/downloads`
- App data path: `/volume1/docker/mega-downloader/data`
- Host port: `3010`
- DSM user UID/GID example: `PUID=1026`, `PGID=100`

Adjust paths and IDs before running if your NAS uses different values.

## 1. Prepare Directories

```bash
mkdir -p /volume1/docker
mkdir -p /volume1/docker/mega-downloader/downloads
mkdir -p /volume1/docker/mega-downloader/data
```

Check your current user's UID/GID:

```bash
id
```

If the UID/GID differ from `1026:100`, edit `compose.yml` before building.

## 2. Clone Or Update Repository

First clone:

```bash
cd /volume1/docker
git clone https://github.com/danhk0612/mega-nas-downloader.git
cd mega-nas-downloader
```

If `git` is not installed, install Git from DSM Package Center first. A downloaded ZIP also works, but Synology may not include `unzip` by default.

If the repository already exists:

```bash
cd /volume1/docker/mega-nas-downloader
git pull
```

If `git pull` is blocked by local edits to `compose.yml`, stash the local compose edit before pulling:

```bash
git stash push -m "local compose before pull" compose.yml
git pull
```

## 3. Review Compose Settings

Open `compose.yml` and verify:

```yaml
ports:
  - "3010:3000"
volumes:
  - /volume1/docker/mega-downloader/downloads:/downloads
  - /volume1/docker/mega-downloader/data:/data
environment:
  PUID: 1026
  PGID: 100
```

Port `3010` is used to avoid conflicts with other local services that may already use port `3000`.

If the mounted host directory was created by another user, fix ownership before starting:

```bash
sudo chown -R 1026:100 /volume1/docker/mega-downloader
sudo chmod -R u+rwX,g+rwX /volume1/docker/mega-downloader
```

## 4. Build And Start

```bash
cd /volume1/docker/mega-nas-downloader
sudo docker compose up -d --build --force-recreate
```

Check container status:

```bash
sudo docker compose ps
```

## 5. Check Logs

```bash
sudo docker compose logs --tail=150 mega-downloader
```

Useful lines to look for:

- `mega-downloader starting as 1026:100`
- Download directory is writable
- Data directory is writable
- `mega-nas-downloader listening on :3000`

## 6. Check Health

From the NAS terminal:

```bash
curl -i http://127.0.0.1:3010/health
curl -s http://127.0.0.1:3010/api/status
```

Expected result:

- `/health` returns `200 OK`
- `/api/status` shows `megacmd.ok: true`
- `/api/status` shows `paths.download_dir_writable.ok: true`
- `/api/status` shows `paths.data_dir_writable.ok: true`

Verified Synology result from the first NAS run:

- Container status: `Up`, health check starting then ready
- Port mapping: `0.0.0.0:3010->3000/tcp`
- MEGAcmd version: `2.5.2.1`
- Download and data paths writable
- Free space reported from `/downloads`

## 7. Open Web UI

Open this from a browser on the same network:

```text
http://NAS_IP:3010
```

At this stage, use only public MEGA file/folder links for testing.

## 8. Test One Download

Use a small public MEGA test link first.

After creating a job, check:

```bash
sudo docker compose logs --tail=150 mega-downloader
ls -la /volume1/docker/mega-downloader/downloads
ls -la /volume1/docker/mega-downloader/data
```

Current expected behavior:

- Job is created in SQLite.
- `mega-get` is executed.
- Job becomes `completed` or `failed`.
- Progress tracking is not implemented yet.

## 9. Stop Or Restart

```bash
sudo docker compose restart
sudo docker compose down
```

## 10. Report Back

Please send these outputs after the first download test:

```bash
cd /volume1/docker/mega-nas-downloader
sudo docker compose ps
sudo docker compose logs --tail=150 mega-downloader
ls -la /volume1/docker/mega-downloader/downloads
ls -la /volume1/docker/mega-downloader/data
curl -s http://127.0.0.1:3010/api/status
```

Do not paste MEGA links that include private keys unless they are intentionally public test links.
