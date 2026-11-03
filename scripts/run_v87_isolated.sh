#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
IMAGE="valbrick-v87-public-isolated"
docker build -t "$IMAGE" .
docker run --rm --network none --entrypoint python \
  -e DATABASE_URL=sqlite:////tmp/v87-isolated.sqlite \
  "$IMAGE" -m unittest discover -s tests -p 'test_v87_maintenance.py' -v
