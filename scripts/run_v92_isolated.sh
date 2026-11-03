#!/bin/sh
# V92 smoke/HTTP checks: backwards-compatible wrapper around the V91 suite.
set -eu
exec sh "$(dirname "$0")/run_v91_isolated.sh"
