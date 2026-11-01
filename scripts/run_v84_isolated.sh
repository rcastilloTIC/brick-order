#!/bin/sh
# V84 isolated suite; no volumes, no network, no production database.
set -eu
cd "$(dirname "$0")/.."
IMAGE="valbrick-v84-autotest:$(basename "$PWD")"
docker build -t "$IMAGE" .
docker run --rm --network none --entrypoint python \
  -e DATABASE_URL=sqlite:////tmp/valbrick-v84-isolated.sqlite \
  "$IMAGE" -m unittest discover -s tests -p 'test_v84_full_order_rehearsal.py' -v
