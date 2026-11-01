#!/bin/sh
# Execute from the project root. DOES NOT use docker compose or mount production data.
set -eu
cd "$(dirname "$0")/.."
IMAGE="valbrick-v83-isolation-test:$(basename "$PWD")"
docker build -t "$IMAGE" .
docker run --rm --network none --entrypoint python \
  -e DATABASE_URL=sqlite:////tmp/valbrick-test-never-production.sqlite \
  "$IMAGE" -m unittest discover -s tests -p test_v83_multi_campaign_auto.py -v
