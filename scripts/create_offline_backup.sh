#!/bin/sh
# Stop the Docker app, create a validated offline ZIP and start it again.
set -eu
cd "$(dirname "$0")/.."
project_dir=$(pwd -P)
case "$(cat EDITION)" in PUBLICA|EXTENDED) edition=$(cat EDITION) ;; *) echo 'Invalid EDITION' >&2; exit 2 ;; esac
stamp=$(date -u +%Y%m%dT%H%M%SZ)
name="backup_${edition}_${stamp}.zip"
mkdir -p data/backups
echo 'Stop any external scheduler before backing up.'
docker compose stop app
if docker run --rm --network none --user 0 \
  -v "$project_dir:/host" -w /host \
  --entrypoint python python:3.11-slim \
  /host/scripts/create_offline_backup.py --data-dir /host/data \
  --output "/host/data/backups/$name" --edition "$edition" \
  --confirm BACKUP_OFFLINE; then
  docker compose up -d app
  echo "Backup ready in data/backups/$name. COPY IT OFF THIS SERVER."
else
  echo 'Backup failed. The app REMAINS STOPPED.' >&2
  exit 1
fi
