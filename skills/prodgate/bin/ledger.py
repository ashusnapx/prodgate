#!/usr/bin/env python3
"""prodgate ledger: what was reviewed at which SHA, the state-machine map, seen finding keys, streaks.

Lives at ~/.claude/qa/<repo>-<hash>/ledger.json (or $PRODGATE_HOME) so no repo is touched. Run from inside the repo.
  scope [--full]              -> JSON {sha, base, first_run, changed, unreviewed, machines_touched}
  set-commands '<json>'       -> store the repo's test/typecheck/lint/build commands
  save-map <file.json>        -> merge machines [{id, name, files, ...}] into the map
  seen                        -> JSON list of finding keys already seen (confirmed or rejected)
  hot                         -> JSON list of machine ids with bugs 3 rounds running
  strict                      -> JSON list of finding kinds that are mostly refuted here (noise budget)
  record-round <file.json>    -> {sha, scope:[files], machines:[ids], confirmed:[{key, machine, kind}],
                                  rejected:[{key, kind}], not_reproduced:[{key, kind}], fixed:int}
  status                      -> one-screen summary
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

SOURCE = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rb", ".java", ".kt", ".cs", ".php", ".sql", ".bicep", ".tf", ".swift", ".rs")
SKIP = ("node_modules/", "dist/", "build/", ".next/", "vendor/", "__pycache__/", ".venv/", "coverage/", "floorplan/")


def git(*a: str) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True, check=True).stdout.strip()


def is_source(p: str) -> bool:
    name = p.rsplit("/", 1)[-1]
    if not p.endswith(SOURCE) or any(s in p for s in SKIP):
        return False
    return not (name.startswith("test_") or ".test." in name or ".spec." in name or "/tests/" in p or p.startswith("tests/"))


def path() -> Path:
    top = git("rev-parse", "--show-toplevel")
    try:
        remote = git("config", "--get", "remote.origin.url")
    except subprocess.CalledProcessError:
        remote = top
    slug = f"{Path(top).name}-{hashlib.sha1(remote.encode()).hexdigest()[:8]}"
    home = Path(os.environ.get("PRODGATE_HOME") or Path.home() / ".claude" / "qa")
    p = home / slug / "ledger.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load() -> dict:
    p = path()
    base = {"commands": {}, "machines": [], "reviewed": {}, "seen": [], "streak": {}, "rounds": [], "last_sha": None, "kinds": {}}
    return {**base, **json.loads(p.read_text())} if p.exists() else base


def save(d: dict) -> None:
    path().write_text(json.dumps(d, indent=1))


def scope(full: bool = False) -> dict:
    d, sha = load(), git("rev-parse", "HEAD")
    tracked = [f for f in git("ls-files").splitlines() if is_source(f)]
    first = d["last_sha"] is None or full
    if first:
        changed = tracked
    else:
        diff = git("diff", "--name-only", "--diff-filter=d", f"{d['last_sha']}..{sha}").splitlines()
        changed = [f for f in diff if is_source(f)]
    unreviewed = [f for f in tracked if f not in d["reviewed"] and f not in changed]
    touched = sorted({m["id"] for m in d["machines"] if set(m.get("files", [])) & (set(changed) | set(unreviewed))})
    return {"sha": sha, "base": d["last_sha"] or sha, "first_run": first, "changed": changed, "unreviewed": unreviewed, "machines_touched": touched}


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else "status"
    d = load()
    if cmd == "scope":
        print(json.dumps(scope("--full" in argv), indent=1))
    elif cmd == "set-commands":
        d["commands"].update(json.loads(argv[2]))
        save(d)
        print(json.dumps(d["commands"], indent=1))
    elif cmd == "save-map":
        new = json.loads(Path(argv[2]).read_text())
        new = new.get("machines", new) if isinstance(new, dict) else new
        by = {m["id"]: m for m in d["machines"]}
        by.update({m["id"]: m for m in new})
        d["machines"] = list(by.values())
        save(d)
        print(f"{len(d['machines'])} machines mapped")
    elif cmd == "seen":
        print(json.dumps(d["seen"]))
    elif cmd == "strict":
        # noise budget: a kind whose reports are refuted or fail to reproduce more than half the time
        # (over 4 or more) must come with a line-by-line repro from now on
        print(json.dumps(sorted(k for k, v in d["kinds"].items() if v["n"] >= 4 and v["bad"] / v["n"] > 0.5)))
    elif cmd == "hot":
        print(json.dumps(sorted(m for m, n in d["streak"].items() if n >= 3)))
    elif cmd == "record-round":
        r = json.loads(Path(argv[2]).read_text())
        for f in r.get("scope", []):
            d["reviewed"][f] = r["sha"]
        good, bad = r.get("confirmed", []), r.get("rejected", []) + r.get("not_reproduced", [])
        d["seen"] = sorted(set(d["seen"]) | {c["key"] for c in good + bad})
        for c, is_bad in [(c, False) for c in good] + [(c, True) for c in bad]:
            k = d["kinds"].setdefault(c.get("kind") or "other", {"n": 0, "bad": 0})
            k["n"] += 1
            k["bad"] += is_bad
        hit = {c.get("machine") for c in r.get("confirmed", []) if c.get("machine")}
        for m in set(r.get("machines", [])) | hit:
            d["streak"][m] = d["streak"].get(m, 0) + 1 if m in hit else 0
        d["rounds"].append({"sha": r["sha"], "scope": len(r.get("scope", [])), "confirmed": len(r.get("confirmed", [])), "fixed": r.get("fixed", 0)})
        d["last_sha"] = r["sha"]
        save(d)
        print(json.dumps(d["rounds"][-1]))
    elif cmd == "status":
        s = scope()
        print(
            json.dumps(
                {
                    "ledger": str(path()),
                    "machines": len(d["machines"]),
                    "reviewed_files": len(d["reviewed"]),
                    "rounds": d["rounds"][-8:],
                    "hot": sorted(m for m, n in d["streak"].items() if n >= 3),
                    "kinds": d["kinds"],
                    "next_scope": {"changed": len(s["changed"]), "unreviewed": len(s["unreviewed"])},
                    "commands": d["commands"],
                },
                indent=1,
            )
        )
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
