#!/bin/sh
# Build and run the complete pytest suite without host dependencies or volumes.
set -eu
cd "$(dirname "$0")/.."
app_image=valbrick-v92-publica-isolated
pytest_image=valbrick-v92-publica-pytest-isolated

docker build -t "$app_image" .
docker build -t "$pytest_image" -f Dockerfile.pytest --build-arg "VALBRICK_BASE_IMAGE=$app_image" .
docker run --rm --network none --entrypoint python \
  -e DATABASE_URL=sqlite:////tmp/valbrick-v92-full-tests.sqlite \
  "$pytest_image" -m pytest -q tests
