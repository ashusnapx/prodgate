<div align="center">

# prodgate

### The QA pipeline for Claude Code that hunts state bugs until zero, and proves every one with a failing test.

Race conditions · stuck states · stale overwrites · illegal transitions · missing tenant checks · double submits · lost UI state

[![License: MIT](https://img.shields.io/badge/license-MIT-black?style=flat-square)](LICENSE)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-D97757?style=flat-square)](#install)
[![Benchmark: 8 apps, 60+ seeded bugs](https://img.shields.io/badge/benchmark-8%20apps%20%C2%B7%2060%2B%20seeded%20bugs-2F6FEB?style=flat-square)](bench/)

</div>

---

Most AI code review reads a diff and gives an opinion. **prodgate runs a loop until the code is safe to ship.** It maps every implicit state machine in your app, hunts bugs on a frozen commit, kills a finding only with quoted code, proves the rest with a failing test, fixes them test-first, and repeats until a round finds nothing. Then a production gate runs.

It is built for the bugs that pass review and code coverage and still break production: two requests interleaving, a job that crashes halfway, a webhook delivered twice, a tab left open on an old version, a screen that never stops polling.

```text
> /prodgate

  round 1  map 23 state machines · 41 findings · 12 refuted with quoted code · 29 proven with a failing test · 29 fixed
  round 2  scope: 14 changed files + 9 callers · 6 found · 6 fixed
  round 3  scope: 4 changed files · 0 found            ✓ clean round
  gate     suites ✓  types ✓  lint ✓  build ✓  review ✓  security ✓  secrets ✓  migrations ✓
```
<sub>Illustrative output. Real numbers are in the benchmark below.</sub>

## Why prodgate

| | Typical AI review | prodgate |
|---|---|---|
| What it reads | The diff, or the whole repo every time | Only what changed since the last check, plus never-reviewed files and their callers. **Unchanged code costs 0 tokens.** |
| When a finding counts | When the model sounds sure | When a test fails because of it |
| How a finding is dismissed | The model is unsure | Only by quoting the guard, lock or check that makes it impossible |
| When a fix counts | Tests pass | Its test failed before the fix, passes 3 times, and fails again when only the fix is undone |
| When it stops | After one pass | When a round on a frozen commit finds nothing, then a production gate |
| Repeats | Re-reports the same issues | Every finding is keyed and never argued about twice |

## The prompt at the heart of it

```text
Find all of the implicit state machines in my app.
```

Status columns, boolean flags, nullable timestamps, job queues, sessions, wizard steps, polling loops and cached screens are all state machines that nobody drew. Most production bugs live in the moves between their states. prodgate turns that one prompt into a pipeline: **map → hunt → check → prove → fix → loop → gate**. See [how it works](docs/HOW-IT-WORKS.md).

## Install

As a Claude Code plugin:

```text
/plugin marketplace add ashusnapx/prodgate
/plugin install prodgate@prodgate
```

Or as a plain skill:

```bash
git clone https://github.com/ashusnapx/prodgate
ln -s "$PWD/prodgate/skills/prodgate" ~/.claude/skills/prodgate
```

Then, in any repo, say `/prodgate`, "run QA", "make it prod ready" or "bug hunt until zero".

It works on any language Claude Code can read. Optional extras make it sharper and cheaper: [caveman](https://github.com/JuliusBrussee/caveman) and [ponytail](https://github.com/DietrichGebert/ponytail) (every agent runs them at `ultra` when installed), the code-review-graph MCP (blast radius), and `gitleaks`, `npm audit` and `pip-audit` for the gate.

## Built to waste nothing

Most of an agent run's cost is the input it reads, re-sent on every turn. prodgate cuts input first:

- **A ledger of coverage.** Every file is recorded with the commit it was checked at. A round reads only the diff, never-reviewed files and their callers.
- **Frozen commits.** Nobody hunts code that is still changing, so no finding goes stale before it is read.
- **Batched checks.** One checker per group of files settles all of that group's findings, so each file is read once.
- **Compact test output.** One line on a pass, only the failing lines on a fail.
- **Lean agents.** Every agent reads by line range, never reads a file twice, and answers with a schema. Low-risk state machines can run on a lighter model.

## Benchmark

[`bench/`](bench/) is a public benchmark for state-bug finders: **8 realistic apps** (FastAPI + SQLAlchemy, plus TypeScript UI state), each with **6 to 9 seeded bugs** across 8 bug classes and **2 to 3 decoys**, code that looks wrong but is correct. Every seeded bug was confirmed with a failing test, every decoy with a passing one, and every app's own test suite passes with the bugs in place.

It compares three ways to find bugs:

| Mode | What runs |
|---|---|
| `oneshot` | A plain "review this codebase for bugs" agent per app |
| `prompt` | The state-machine prompt alone, one pass, nothing checked |
| `prodgate` | The full pipeline, report-only |

And a **re-check** scenario: a small change lands in two apps, and each approach checks the repo again.

> **Results:** the first full run is in progress. Recall, precision, decoy hits and measured tokens (from the agents' own usage logs) will be published here. They will not be estimates.

## Research

prodgate's rules come from how Google, Meta, Amazon, Microsoft, AIxCC winners, Jepsen and FoundationDB decide what counts as a bug. The short version: **executable proof, not LLM opinion, decides**. Read [the evidence and what was taken from it](docs/RESEARCH.md).

## Repo layout

```text
skills/prodgate/          the skill: SKILL.md, prodgate.workflow.js, bin/ledger.py, bin/qa-run
bench/                    fixtures, answer keys, scorer, token counter, benchmark workflow
docs/                     how it works, research
tests/                    workflow control flow (fake agents), ledger and scorer tests
```

## Contributing

New fixture apps with seeded state bugs are the most useful contribution: see [bench/SPEC.md](bench/SPEC.md). Bug reports with a failing test are welcome too.

## License

MIT
