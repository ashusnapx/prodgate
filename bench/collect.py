#!/usr/bin/env python3
"""Turn benchmark workflow outputs into clean result files, judge inputs, and the final scores.

  collect.py run <raw workflow output> <mode> <tokens.json> <out.json>
      keep only findings (paths made repo-relative, local paths scrubbed) and the measured tokens
  collect.py pairs <results dir> <work dir>
      step 1: candidate pairs (a finding near a known bug) -> <work>/pairs.json + batch files for the judge
  collect.py unmatched <results dir> <work dir> <judge step-1 output>
      step 2: findings with no same-mechanism pair and not on a decoy -> <work>/unmatched.json + one file per app
  collect.py apply <results dir> <work dir> <judge step-1 output> <judge step-2 output>
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


def _results(results: str):
    for f in sorted(Path(results).glob("*.json")):
        r = json.loads(f.read_text())
        if "apps" in r and "mode" in r:
            yield r


def _key_dir(mode: str) -> Path:
    return Path(__file__).parent / "truth" / ("regressions" if mode.startswith("recheck") else "")


def _judge_list(path: str, field: str) -> list:
    d = json.loads(Path(path).read_text())
    return d.get("result", d).get(field, [])


def pairs(results: str, work: str) -> None:
    out, batches = [], []
    for r in _results(results):
        score.TRUTH = _key_dir(r["mode"])
        for app, a in r["apps"].items():
            if (score.TRUTH / f"{app}.json").exists():
                out += [{**c, "id": len(out) + i, "mode": r["mode"]} for i, c in enumerate(score.candidates(app, a["findings"]))]
    Path(work).mkdir(parents=True, exist_ok=True)
    Path(work, "pairs.json").write_text(json.dumps(out))
    for i in range(0, len(out), 60):
        f = Path(work, f"pairs-{i // 60 + 1}.json")
        f.write_text(json.dumps([{"id": c["id"], "reported": c["finding_text"], "known": c["bug_text"]} for c in out[i : i + 60]], indent=0))
        batches.append(str(f))
    print(json.dumps({"pairs": len(out), "files": batches}))


def unmatched(results: str, work: str, step1: str) -> None:
    same = {x["id"] for x in _judge_list(step1, "same") if x["same"]}
    hit = {(c["mode"], c["app"], c["finding"]) for c in json.loads(Path(work, "pairs.json").read_text()) if c["id"] in same}
    out = []
    for r in _results(results):
        if r["mode"].startswith("recheck"):
            continue
        score.TRUTH = _key_dir(r["mode"])
        for app, a in r["apps"].items():
            t = score.truth(app)
            for i, fd in enumerate(a["findings"]):
                on_decoy = any(score.norm(fd.get("file", ""), app) == d["file"] and score.near(fd, d["lines"], 3) for d in t.get("decoys", []))
                if (r["mode"], app, i) not in hit and not on_decoy:
                    out.append({"id": len(out), "mode": r["mode"], "app": app, "finding": i, **{k: fd.get(k) for k in ("file", "line", "bug", "repro")}})
    Path(work, "unmatched.json").write_text(json.dumps(out))
    files = {}
    for app in sorted({u["app"] for u in out}):
        f = Path(work, f"unmatched-{app}.json")
        f.write_text(json.dumps([{k: u[k] for k in ("id", "file", "line", "bug", "repro")} for u in out if u["app"] == app], indent=0))
        files[app] = str(f)
    print(json.dumps({"unmatched": len(out), "files": files}))


def apply(results: str, work: str, step1: str, step2: str) -> None:
    same = {x["id"] for x in _judge_list(step1, "same") if x["same"]}
    real = {x["id"] for x in _judge_list(step2, "real") if x["real"]}
    judged: dict = {}
    for c in json.loads(Path(work, "pairs.json").read_text()):
        slot = judged.setdefault(c["mode"], {}).setdefault(c["app"], {})
        if c["id"] in same:
            slot[str(c["finding"])] = c["bug"]
        else:
            slot.setdefault(str(c["finding"]), None)
    adjudicated: dict = {}
    for u in json.loads(Path(work, "unmatched.json").read_text()):
        adjudicated.setdefault(u["mode"], {}).setdefault(u["app"], {})[str(u["finding"])] = u["id"] in real
    Path(results, "judged.json").write_text(json.dumps(judged, indent=1))
    Path(results, "adjudicated.json").write_text(json.dumps(adjudicated, indent=1))
    print(f"{len(same)} pairs judged same mechanism, {len(real)} unmatched findings proven real")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"run": run, "pairs": pairs, "unmatched": unmatched, "apply": apply}.get(cmd, lambda *a: sys.exit(__doc__))(*sys.argv[2:])
