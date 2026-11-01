#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
IMAGE="valbrick-v86-public-isolated"
docker build -t "$IMAGE" .
docker run --rm --network none --entrypoint python -e DATABASE_URL=sqlite:////tmp/v86-isolated.sqlite "$IMAGE" -m unittest discover -s tests -p 'test_v86_shortage_increase.py' -v
