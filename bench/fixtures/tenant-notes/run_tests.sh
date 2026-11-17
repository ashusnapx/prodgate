#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
BENCH_VENV="$(cd ../.. && pwd)/.venv"
if [ -n "${BENCH_PYTHON:-}" ]; then
  PY="$BENCH_PYTHON"
elif [ -x "$BENCH_VENV/bin/python" ]; then
  PY="$BENCH_VENV/bin/python"
else
  PY="python3"
fi
exec "$PY" -m pytest -q -p no:cacheprovider "$@"
