#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
image=valbrick-v92-publica-isolated
docker build -t "$image" .
for pattern in test_v88_concurrency.py test_v88_http_security.py; do
  docker run --rm --network none --entrypoint python -e DATABASE_URL=sqlite:////tmp/v91-test.sqlite "$image" -m unittest discover -s tests -p "$pattern" -v
done
