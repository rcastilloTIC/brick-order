#!/bin/sh
# Real Flask/SQLite E2E rehearsal of PUBLIC V92. No host volumes or production DB.
set -eu
cd "$(dirname "$0")/.."
if grep -q 'class FinalExtensionInterest' app/models.py; then
  echo 'ERROR: paquete Extended detectado en la carpeta Publica; no mezclar ediciones.' >&2
  exit 2
fi
image=valbrick-v92-publica-e2e-only
docker build -t "$image" .
docker run --rm --network none --entrypoint python \
  -e DATABASE_URL=sqlite:////tmp/valbrick-v92-publica-e2e-external-unused.sqlite \
  "$image" -m unittest discover -s tests -p 'test_v92_campaign_e2e.py' -v
