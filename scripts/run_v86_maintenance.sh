#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Run only INSIDE a configured application/maintenance container.
# Do not suppress database integrity errors or overdue campaign failures.
python -m flask --app run:app check-shortage
capture-insights
