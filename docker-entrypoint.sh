#!/bin/sh
set -eu

PUID="${PUID:-1026}"
PGID="${PGID:-100}"
UMASK="${UMASK:-022}"
DOWNLOAD_DIR="${DOWNLOAD_DIR:-/downloads}"
DATA_DIR="${DATA_DIR:-/data}"
TEMP_DIR="${TEMP_DIR:-/data/temp}"

umask "$UMASK"

if ! getent group "$PGID" >/dev/null 2>&1; then
  groupadd -g "$PGID" appgroup
fi

if ! id appuser >/dev/null 2>&1; then
  useradd -u "$PUID" -g "$PGID" -d "$DATA_DIR" -s /usr/sbin/nologin appuser
fi

mkdir -p "$DOWNLOAD_DIR" "$DATA_DIR" "$TEMP_DIR"
chown -R "$PUID:$PGID" "$DATA_DIR" "$TEMP_DIR"

exec gosu "$PUID:$PGID" "$@"
