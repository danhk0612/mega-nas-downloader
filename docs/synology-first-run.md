# Synology First Run

This checklist verifies the current alpha build on Synology DSM with Container Manager.

Assumptions:

- Repository: `https://github.com/danhk0612/mega-nas-downloader.git`
- Project path: `/volume1/docker/mega-nas-downloader`
- Download path: `/volume1/download/mega`
- App data path: `/volume1/docker/mega-downloader/data`
- Host port: `3000`
- DSM user UID/GID example: `PUID=1026`, `PGID=100`

Adjust paths and IDs before running if your NAS uses different values.

## 1. Prepare Directories

```bash
mkdir -p /volume1/docker
mkdir -p /volume1/download/mega
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

If the repository already exists:

```bash
cd /volume1/docker/mega-nas-downloader
git pull
```

## 3. Review Compose Settings

Open `compose.yml` and verify:

```yaml
ports:
  - "3000:3000"
volumes:
  - /volume1/download/mega:/downloads
  - /volume1/docker/mega-downloader/data:/data
environment:
  PUID: 1026
  PGID: 100
```

## 4. Build And Start

```bash
cd /volume1/docker/mega-nas-downloader
sudo docker compose up -d --build
```

Check container status:

```bash
sudo docker compose ps
```

## 5. Check Logs

```bash
sudo docker compose logs --tail=100 mega-downloader
```

Useful lines to look for:

- Python server started on port `3000`
- No permission error for `/downloads`
- No permission error for `/data`
- No MEGAcmd install error during build

## 6. Check Health

From the NAS terminal:

```bash
curl -i http://127.0.0.1:3000/health
curl -s http://127.0.0.1:3000/api/status
```

Expected result:

- `/health` returns `200 OK`
- `/api/status` shows `megacmd.available: true`
- `downloads.writable: true`
- `data.writable: true`

## 7. Open Web UI

Open this from a browser on the same network:

```text
http://NAS_IP:3000
```

At this stage, use only public MEGA file/folder links for testing.

## 8. Test One Download

Use a small public MEGA test link first.

After creating a job, check:

```bash
sudo docker compose logs --tail=100 mega-downloader
ls -la /volume1/download/mega
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

Please send these outputs after the first run:

```bash
id
sudo docker compose ps
sudo docker compose logs --tail=100 mega-downloader
curl -i http://127.0.0.1:3000/health
curl -s http://127.0.0.1:3000/api/status
```

Do not paste MEGA links that include private keys unless they are intentionally public test links.
