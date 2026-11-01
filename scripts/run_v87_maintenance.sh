#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python -m flask --app run:app check-shortage
python -m flask --app run:app capture-insights
