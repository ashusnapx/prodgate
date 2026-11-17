#!/usr/bin/env python3
"""Score QA findings against the answer keys in bench/truth/.

  score.py candidates <run.json>            -> pairs for the mechanism judge (stdout JSON)
  score.py report <run.json> [<judged.json>] [<adjudicated.json>]  -> per-mode table (stdout JSON + text)

run.json:        {"mode": "...", "apps": {"<app>": {"findings": [{file, line, function?, bug, ...}], "tokens": {...}}}}
judged.json:     {"<app>": {"<finding index>": "<bug id>" | null}}   (mechanism check of each candidate pair)
adjudicated.json:{"<app>": {"<finding index>": true | false}}        (true = a real bug the key does not list)
Without judged.json every candidate pair counts (lenient); the report says so.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TRUTH = Path(os.environ.get("BENCH_TRUTH") or Path(__file__).parent / "truth")
WINDOW = 10


def norm(path: str, app: str) -> str:
    p = path.replace("\\", "/")
    marker = f"/{app}/"
    if marker in p:
        p = p.split(marker, 1)[1]
    return p.lstrip("./")


def truth(app: str) -> dict:
    return json.loads((TRUTH / f"{app}.json").read_text())


def near(f: dict, span: list[int], pad: int) -> bool:
    line = f.get("line") or 0
    return span[0] - pad <= line <= span[1] + pad


def candidates(app: str, findings: list[dict]) -> list[dict]:
    t, out = truth(app), []
    for i, f in enumerate(findings):
        file = norm(f.get("file", ""), app)
        for b in t["bugs"]:
            same_fn = b.get("function") and f.get("function") and b["function"].split(".")[-1] == f["function"].split(".")[-1]
            if file == b["file"] and (near(f, b["lines"], WINDOW) or same_fn):
                out.append({"app": app, "finding": i, "bug": b["id"], "finding_text": f.get("bug", ""), "bug_text": b["summary"]})
    return out


def score(app: str, findings: list[dict], judged: dict | None, adjudicated: dict | None) -> dict:
    t = truth(app)
    pairs = candidates(app, findings)
    if judged is not None:
        ok = judged.get(app, {})
        pairs = [p for p in pairs if ok.get(str(p["finding"])) == p["bug"]]
    matched: dict[str, int] = {}
    used: set[int] = set()
    for p in pairs:  # greedy, in finding order: each bug and each finding at most once
        if p["bug"] not in matched and p["finding"] not in used:
            matched[p["bug"]] = p["finding"]
            used.add(p["finding"])
    dupes = {p["finding"] for p in pairs if p["finding"] not in used and p["bug"] in matched}
    decoy = set()
    for i, f in enumerate(findings):
        if i in used or i in dupes:
            continue
        for d in t.get("decoys", []):
            if norm(f.get("file", ""), app) == d["file"] and near(f, d["lines"], 3):
                decoy.add(i)
    rest = [i for i in range(len(findings)) if i not in used | dupes | decoy]
    adj = (adjudicated or {}).get(app, {})
    real_extra = [i for i in rest if adj.get(str(i)) is True]
    false_pos = [i for i in rest if adj.get(str(i)) is not True]
    unique = len(findings) - len(dupes)
    return {
        "seeded": len(t["bugs"]),
        "found": len(matched),
        "found_ids": sorted(matched),
        "missed_ids": sorted(b["id"] for b in t["bugs"] if b["id"] not in matched),
        "reported": len(findings),
        "duplicates": len(dupes),
        "decoy_hits": len(decoy),
        "real_unseeded": len(real_extra),
        "false_positives": len(false_pos) + len(decoy),
        "unadjudicated": 0 if adjudicated is not None else len(rest),
        "precision": round((len(matched) + len(real_extra)) / unique, 3) if unique else None,
        "by_class": {b["class"]: b["id"] in matched for b in t["bugs"]},
    }


def main(argv: list[str]) -> None:
    if len(argv) < 3:
        sys.exit(__doc__)
    run = json.loads(Path(argv[2]).read_text())
    if argv[1] == "candidates":
        print(json.dumps([c for app, a in run["apps"].items() for c in candidates(app, a["findings"])], indent=1))
        return
    judged = json.loads(Path(argv[3]).read_text()) if len(argv) > 3 else None
    adjudicated = json.loads(Path(argv[4]).read_text()) if len(argv) > 4 else None
    # judge files from collect.py are keyed by mode, then app
    if judged is not None and run["mode"] in judged:
        judged = judged[run["mode"]]
    if adjudicated is not None:
        adjudicated = adjudicated.get(run["mode"], {}) if any(k in adjudicated for k in ("oneshot", "prompt", "prodgate")) else adjudicated
    if run["mode"].startswith("recheck"):
        global TRUTH
        TRUTH = TRUTH / "regressions"
    per = {app: score(app, a["findings"], judged, adjudicated) for app, a in run["apps"].items()}
    seeded = sum(s["seeded"] for s in per.values())
    found = sum(s["found"] for s in per.values())
    unique = sum(s["reported"] - s["duplicates"] for s in per.values())
    good = sum(s["found"] + s["real_unseeded"] for s in per.values())
    total = {
        "mode": run["mode"],
        "recall": round(found / seeded, 3) if seeded else None,
        "precision": round(good / unique, 3) if unique else None,
        "found": found,
        "seeded": seeded,
        "reported": sum(s["reported"] for s in per.values()),
        "false_positives": sum(s["false_positives"] for s in per.values()),
        "decoy_hits": sum(s["decoy_hits"] for s in per.values()),
        "real_unseeded": sum(s["real_unseeded"] for s in per.values()),
        "lenient_matching": judged is None,
        "tokens": run.get("tokens"),
    }
    print(json.dumps({"total": total, "apps": per}, indent=1))


if __name__ == "__main__":
    main(sys.argv)
