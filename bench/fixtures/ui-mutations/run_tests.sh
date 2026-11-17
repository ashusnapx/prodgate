#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

pick_node() {
  local candidate
  for candidate in "${NODE:-}" "$(command -v node || true)" /opt/homebrew/bin/node /usr/local/bin/node; do
    [ -n "$candidate" ] && [ -x "$candidate" ] || continue
    if "$candidate" -e 'const [a, b] = process.versions.node.split(".").map(Number); process.exit(a > 22 || (a === 22 && b >= 18) ? 0 : 1)'; then
      echo "$candidate"
      return
    fi
  done
  echo "Node 22.18 or newer is needed (it runs TypeScript directly)" >&2
  return 1
}

NODE_BIN="$(pick_node)"
exec "$NODE_BIN" --test tests/
