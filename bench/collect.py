#!/usr/bin/env python3
"""Turn benchmark workflow outputs into clean result files, judge inputs, and the final table.

  collect.py run <raw workflow output> <mode> <tokens.json> <out.json>
      keep only findings (paths made repo-relative, local paths scrubbed) and the measured tokens
  collect.py prep <results dir> <out.json>
      candidate pairs (finding near a known bug) and unmatched findings, with ids, for the judge workflow
  collect.py apply <results dir> <judge output> <prep.json>
      write judged.json and adjudicated.json next to the results
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import score  # noqa: E402

LOCAL = re.compile(r"(/private)?/(tmp|var|Users|home)/\S*?/(bench-work/(base|recheck)/)?(?=[a-z-]+/)")


def scrub(v):
    if isinstance(v, str):
        return LOCAL.sub("", v)
    if isinstance(v, list):
        return [scrub(x) for x in v]
    if isinstance(v, dict):
        return {k: scrub(x) for k, x in v.items()}
    return v


def run(raw: str, mode: str, tokens: str, out: str) -> None:
    data = json.loads(Path(raw).read_text())
    result = data.get("result", data)
    apps = {}
    for app, a in result["apps"].items():
        findings = []
        for f in a.get("findings", []):
            f = scrub(f)
            f["file"] = score.norm(f.get("file", ""), app)
            findings.append(f)
        apps[app] = {"findings": findings}
    Path(out).write_text(json.dumps({"mode": mode, "tokens": json.loads(Path(tokens).read_text()), "apps": apps}, indent=1))
    print(f"{mode}: {sum(len(a['findings']) for a in apps.values())} findings")


def prep(results: str, out: str) -> None:
    pairs, unmatched = [], []
    for f in sorted(Path(results).glob("*.json")):
        r = json.loads(f.read_text())
        if "apps" not in r:
            continue
        mode, truth_dir = r["mode"], ("regressions" if r["mode"].startswith("recheck") else None)
        if truth_dir:
            score.TRUTH = Path(__file__).parent / "truth" / "regressions"
        else:
            score.TRUTH = Path(__file__).parent / "truth"
        for app, a in r["apps"].items():
            if not (score.TRUTH / f"{app}.json").exists():
                continue
            cand = score.candidates(app, a["findings"])
            near = {c["finding"] for c in cand}
            for c in cand:
                pairs.append({**c, "id": len(pairs), "mode": mode})
            t = score.truth(app)
            for i, fd in enumerate(a["findings"]):
                on_decoy = any(score.norm(fd.get("file", ""), app) == d["file"] and score.near(fd, d["lines"], 3) for d in t.get("decoys", []))
                if i not in near and not on_decoy and not truth_dir:
                    unmatched.append({"id": len(unmatched), "mode": mode, "app": app, "finding": i, **{k: fd.get(k) for k in ("file", "line", "bug", "repro")}})
    Path(out).write_text(json.dumps({"pairs": pairs, "unmatched": unmatched}, indent=1))
    print(f"{len(pairs)} candidate pairs, {len(unmatched)} unmatched findings")


def apply(results: str, judge_out: str, prep_file: str) -> None:
    j = json.loads(Path(judge_out).read_text())
    j = j.get("result", j)
    p = json.loads(Path(prep_file).read_text())
    same = {x["id"]: x["same"] for x in j.get("same", [])}
    real = {x["id"]: x["real"] for x in j.get("real", [])}
    judged: dict = {}
    for c in p["pairs"]:
        slot = judged.setdefault(c["mode"], {}).setdefault(c["app"], {})
        if same.get(c["id"]):
            slot[str(c["finding"])] = c["bug"]
        else:
            slot.setdefault(str(c["finding"]), None)
    adjudicated: dict = {}
    for u in p["unmatched"]:
        adjudicated.setdefault(u["mode"], {}).setdefault(u["app"], {})[str(u["finding"])] = bool(real.get(u["id"]))
    Path(results, "judged.json").write_text(json.dumps(judged, indent=1))
    Path(results, "adjudicated.json").write_text(json.dumps(adjudicated, indent=1))
    print(f"{sum(same.values())}/{len(same)} pairs same mechanism, {sum(real.values())}/{len(real)} unmatched findings proven real")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"run": run, "prep": prep, "apply": apply}.get(cmd, lambda *a: sys.exit(__doc__))(*sys.argv[2:])
