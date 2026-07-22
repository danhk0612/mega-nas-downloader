FROM python:3.12-slim-bookworm

ARG TARGETARCH

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_PORT=3000 \
    DOWNLOAD_DIR=/downloads \
    DATA_DIR=/data \
    TEMP_DIR=/data/temp \
    TZ=Asia/Seoul \
    PUID=1026 \
    PGID=100 \
    UMASK=022

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gosu tini \
    && case "${TARGETARCH:-amd64}" in \
        amd64) curl -fsSL -o /tmp/megacmd.deb "https://mega.nz/linux/repo/Debian_12/amd64/megacmd-Debian_12_amd64.deb" ;; \
        *) echo "MEGAcmd package install is currently wired for amd64 only. TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && apt-get install -y --no-install-recommends /tmp/megacmd.deb \
    && rm -f /tmp/megacmd.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY src/ /app/src/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /downloads /data /data/temp

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -m src.healthcheck

ENTRYPOINT ["/usr/bin/tini", "--", "docker-entrypoint.sh"]
CMD ["python", "-m", "src.app"]
