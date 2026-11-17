#!/bin/bash
# Runs this app's test suite. Python comes from $BENCH_PYTHON, or the nearest .venv above this folder.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
PY="${BENCH_PYTHON:-}"
d="$PWD"
while [ -z "$PY" ] && [ "$d" != / ]; do
  [ -x "$d/.venv/bin/python" ] && PY="$d/.venv/bin/python"
  d="$(dirname "$d")"
done
exec "${PY:-python3}" -m pytest -q -p no:cacheprovider "$@"
