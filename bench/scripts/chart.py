#!/usr/bin/env python3
"""Draw assets/results.svg from bench/results (measured numbers only). Emphasis form: prodgate in the accent, the rest gray."""
import json
from pathlib import Path

B = Path(__file__).resolve().parents[1]
R = B / "results"
ACCENT, GRAY, INK, MUTED, FAINT, BG = "#8B5CF6", "#64748B", "#E2E8F0", "#94A3B8", "#1E293B", "#0B1020"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, Helvetica, Arial, sans-serif"


def load(name):
    return json.loads((R / f"{name}.json").read_text())


def distinct_real(mode):
    adj = json.loads((R / "adjudicated.json").read_text()).get(mode, {})
    jd = json.loads((R / "judged.json").read_text()).get(mode, {})
    seeded, extra = set(), set()
    for app, a in load(mode)["apps"].items():
        for i, f in enumerate(a["findings"]):
            b = jd.get(app, {}).get(str(i))
            if b:
                seeded.add(b)
            elif adj.get(app, {}).get(str(i)) is True:
                extra.add((app, f["file"], (f.get("function") or "").split(".")[-1] or f["line"] // 15))
    return len(seeded) + len(extra)


def bar(x, y, w, h, color):
    r = min(4, w / 2)  # 4px rounded data end, square at the baseline
    return f'<path d="M{x},{y}h{w - r:.1f}a{r},{r} 0 0 1 {r},{r}v{h - 2 * r}a{r},{r} 0 0 1 -{r},{r}h-{w - r:.1f}z" fill="{color}"/>'


def panel(px, title, note, rows, fmt, vmax):
    out = [f'<text x="{px}" y="104" font-size="17" font-weight="700" fill="{INK}">{title}</text>',
           f'<text x="{px}" y="126" font-size="13" fill="{MUTED}">{note}</text>']
    x0, width = px + 118, 196
    out.append(f'<line x1="{x0}" y1="146" x2="{x0}" y2="{150 + 44 * len(rows)}" stroke="{FAINT}" stroke-width="1"/>')
    for i, (label, value, accent) in enumerate(rows):
        y = 152 + 44 * i
        w = max(3, width * value / vmax)
        out.append(f'<text x="{x0 - 10}" y="{y + 18}" font-size="14" text-anchor="end" fill="{INK if accent else MUTED}" font-weight="{700 if accent else 500}">{label}</text>')
        out.append(bar(x0, y, w, 26, ACCENT if accent else GRAY))
        out.append(f'<text x="{x0 + w + 8}" y="{y + 18}" font-size="14" fill="{INK}" font-weight="{700 if accent else 500}">{fmt(value)}</text>')
    return out


naive, pg = load("recheck-naive"), load("recheck-prodgate")
n_tok, p_tok = naive["tokens"]["total"], pg["tokens"]["total"]
n_find = sum(len(a["findings"]) for a in naive["apps"].values())
p_find = sum(len(a["findings"]) for a in pg["apps"].values())
real = {m: distinct_real(m) for m in ("oneshot", "prompt", "prodgate")}
M = lambda v: f"{v / 1e6:.2f}M"

parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 340" width="1200" height="340" role="img" aria-labelledby="t d">',
    '<title id="t">prodgate benchmark results</title>',
    f'<desc id="d">First run: distinct real bugs found, plain review {real["oneshot"]}, prompt alone {real["prompt"]}, prodgate {real["prodgate"]}. '
    f'Re-check after a 2-file change: tokens {M(n_tok)} vs {M(p_tok)}; findings to read {n_find} vs {p_find}.</desc>',
    f'<rect width="1200" height="340" rx="24" fill="{BG}"/><rect x=".75" y=".75" width="1198.5" height="338.5" rx="23.5" fill="none" stroke="#FFFFFF" stroke-opacity=".08"/>',
    f'<g font-family="{FONT}">',
    f'<text x="40" y="54" font-size="22" font-weight="800" fill="{INK}">Benchmark</text>',
    f'<text x="182" y="54" font-size="15" fill="{MUTED}">8 apps · 59 seeded bugs · 24 decoys · every unmatched finding settled by a test</text>',
]
parts += panel(40, "Real bugs found", "first run · distinct bugs · higher is better",
               [("Plain review", real["oneshot"], False), ("Prompt alone", real["prompt"], False), ("prodgate", real["prodgate"], True)], str, 120)
parts += panel(430, "Re-check: tokens", f"2-file change · lower is better · −{1 - p_tok / n_tok:.0%}",
               [("Old way", n_tok, False), ("prodgate", p_tok, True)], M, n_tok * 1.25)
parts += panel(820, "Re-check: findings to read", f"repeats included · lower is better · −{1 - p_find / n_find:.0%}",
               [("Old way", n_find, False), ("prodgate", p_find, True)], str, n_find * 1.25)
parts += [f'<text x="40" y="300" font-size="12.5" fill="{MUTED}">Claude Opus 5.5. Tokens = every token the agents processed (input, cache, output), summed from their own usage logs.</text>',
          f'<text x="40" y="320" font-size="12.5" fill="{MUTED}">Both re-checks caught both new bugs. A re-run on unchanged code costs prodgate 0 tokens.</text>',
          '</g></svg>']
out = B.parent / "assets" / "results.svg"
out.write_text("\n".join(parts) + "\n")
print(out, real, M(n_tok), M(p_tok), n_find, p_find)
