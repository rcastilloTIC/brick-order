#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
IMAGE="valbrick-v85-public-isolated"
docker build -t "$IMAGE" .
docker run --rm --network none --entrypoint python -e DATABASE_URL=sqlite:////tmp/v85-isolated.sqlite "$IMAGE" -m unittest discover -s tests -p 'test_v85_shortage.py' -v
