#!/usr/bin/env python3
"""Count the tokens a run really used, from Claude Code's agent transcripts (JSONL).

  tokens.py <dir-or-file> [...]   -> {"agents", "input", "cache_write", "cache_read", "output", "total"}

Each assistant message is counted once (transcripts repeat a message's usage on every content block).
"total" is every token the model processed: fresh input + cache writes + cache reads + output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def files(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        out += sorted(p.rglob("*.jsonl")) if p.is_dir() else [p]
    return [f for f in out if f.name != "journal.jsonl"]


def count(paths: list[Path]) -> dict:
    seen: set[str] = set()
    t = {"agents": 0, "input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    for f in paths:
        used = False
        for line in f.read_text(errors="ignore").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = rec.get("message") if isinstance(rec, dict) else None
            if not isinstance(msg, dict) or msg.get("role") != "assistant" or not msg.get("usage"):
                continue
            mid = msg.get("id") or f"{f}:{rec.get('uuid')}"
            if mid in seen:
                continue
            seen.add(mid)
            u = msg["usage"]
            t["input"] += u.get("input_tokens", 0)
            t["cache_write"] += u.get("cache_creation_input_tokens", 0)
            t["cache_read"] += u.get("cache_read_input_tokens", 0)
            t["output"] += u.get("output_tokens", 0)
            used = True
        t["agents"] += used
    t["total"] = t["input"] + t["cache_write"] + t["cache_read"] + t["output"]
    return t


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(json.dumps(count(files(sys.argv[1:])), indent=1))
