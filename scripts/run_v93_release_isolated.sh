#!/bin/sh
# Disposable checks of the V93 release gates, no volumes or exposed ports.
set -eu
cd "$(dirname "$0")/.."
if [ "$(cat EDITION)" != "PUBLICA" ]; then
  echo "Incorrect edition directory" >&2
  exit 2
fi
image=valbrick-v93-publica-release-isolated
docker build -t "$image" .
for pattern in test_v93_offline_restore.py test_v93_release_http.py; do
  docker run --rm --network none --entrypoint python \
    -e DATABASE_URL=sqlite:////tmp/valbrick-v93-release.sqlite \
    "$image" -m unittest discover -s tests -p "$pattern" -v
done
