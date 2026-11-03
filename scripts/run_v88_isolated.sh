#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker build -t valbrick-v88-public-isolated .
docker run --rm --network none --entrypoint python -e DATABASE_URL=sqlite:////tmp/v88.sqlite valbrick-v88-public-isolated -m unittest discover -s tests -p 'test_v88_*.py' -v
