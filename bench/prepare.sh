#!/bin/bash
# Copy each fixture into its own git repo under <workdir>, away from the answer keys,
# and print apps.json: [{name, path, sha, files, commands}].
# Usage: bench/prepare.sh <workdir> [app ...]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
work="${1:?usage: prepare.sh <workdir> [app ...]}"
shift || true
apps=("$@")
[ ${#apps[@]} -eq 0 ] && apps=($(ls "$here/fixtures"))
mkdir -p "$work"
git_() { git -c user.name=bench -c user.email=bench@example.com -c commit.gpgsign=false "$@"; }

echo "["
first=1
for app in "${apps[@]}"; do
  dst="$work/$app"
  if [ ! -d "$dst/.git" ]; then
    mkdir -p "$dst"
    (cd "$here/fixtures/$app" && tar --exclude .venv --exclude __pycache__ --exclude .pytest_cache -cf - .) | (cd "$dst" && tar -xf -)
    (cd "$dst" && git init -q && git_ add -A && git_ commit -qm "$app")
  fi
  sha=$(git -C "$dst" rev-parse HEAD)
  files=$(git -C "$dst" ls-files | grep -E '\.(py|ts|js|mjs)$' | grep -vE '(^|/)tests?/|test_|\.test\.' | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read().split()))')
  [ $first -eq 1 ] || echo ","
  first=0
  printf '{"name":"%s","path":"%s","sha":"%s","files":%s,"commands":{"test":"bash run_tests.sh"}}' "$app" "$dst" "$sha" "$files"
done
echo "]"
