#!/bin/sh
# Dedicated single-container scheduler. Never run in gunicorn workers.
set -eu
INTERVAL="${BOM_MAINTENANCE_INTERVAL_SECONDS:-1800}"
case "$INTERVAL" in ''|*[!0-9]*) echo 'Interval must be an integer number of seconds' >&2; exit 2;; esac
if [ "$INTERVAL" -lt 300 ] || [ "$INTERVAL" -gt 86400 ]; then
  echo 'Interval must be between 300 and 86400 seconds' >&2; exit 2
fi
cd /app
while :; do
  if sh scripts/run_v87_maintenance.sh; then
    echo 'Maintenance cycle completed' >&2
  else
    echo 'Maintenance cycle FAILED; inspect logs. Next retry remains scheduled.' >&2
  fi
  sleep "$INTERVAL"
done
