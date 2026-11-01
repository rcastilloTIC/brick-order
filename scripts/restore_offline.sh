#!/bin/sh
# Stop app, then restore both SQLite and documents in one reversible data tree.
set -eu
cd "$(dirname "$0")/.."
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "Usage: sh scripts/restore_offline.sh ./data/backups/backup_NAME.zip" >&2
  exit 2
fi
backup_file=$(cd "$(dirname "$1")" && pwd -P)/$(basename "$1")
project_dir=$(pwd -P)
case "$backup_file" in
  "$project_dir"/*) archive_in_container="/host/${backup_file#"$project_dir"/}" ;;
  *) echo "Copy the backup into this project first (for example data/backups/)." >&2; exit 2 ;;
esac
edition=$(cat EDITION)
case "$edition" in PUBLICA|EXTENDED) ;; *) echo 'Invalid EDITION file' >&2; exit 2 ;; esac
printf '%s\n' 'IMPORTANT: stop any external cron/scheduler for VALBRICK before continuing.'
printf '%s\n' 'Stopping app container (no volumes removed)...'
docker compose stop app
if docker run --rm --network none --user 0 \
  -v "$project_dir:/host" -w /host \
  --entrypoint python python:3.11-slim \
  /host/scripts/restore_offline.py \
  --archive "$archive_in_container" --data-dir /host/data \
  --edition "$edition" --confirm RESTORE_OFFLINE; then
  echo 'Starting app again...'
  docker compose up -d app
  echo 'Restore succeeded. Inspect the old data.pre-restore-* copy before deletion.'
else
  echo 'Restore failed. The app REMAINS STOPPED. Inspect the error before restarting.' >&2
  exit 1
fi
