#!/bin/sh
# SQLite lives under /data/db on the persistent bind mount.  Docker's
# bind mount masks directories created at image build time.
set -eu
mkdir -p "${BOM_DATA_DIR:-/data}/db"
exec "$@"
