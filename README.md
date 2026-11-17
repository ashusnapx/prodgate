<div align="center">

# prodgate

### The QA pipeline for Claude Code that hunts state bugs until zero, and proves every one with a failing test.

Race conditions · stuck states · stale overwrites · illegal transitions · missing tenant checks · double submits · lost UI state

[![License: MIT](https://img.shields.io/badge/license-MIT-black?style=flat-square)](LICENSE)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-D97757?style=flat-square)](#install)
[![skills.sh](https://skills.sh/b/ashusnapx/prodgate)](https://skills.sh/ashusnapx/prodgate)
[![Benchmark: 8 apps, 59 seeded bugs](https://img.shields.io/badge/benchmark-8%20apps%20%C2%B7%2059%20seeded%20bugs-2F6FEB?style=flat-square)](bench/)

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

**1. Install prodgate**, in one line with npx:

```bash
npx skills add ashusnapx/prodgate
```

Or as a Claude Code plugin:

```text
/plugin marketplace add ashusnapx/prodgate
/plugin install prodgate@prodgate
```

**2. Install the two plugins prodgate requires.** Every agent prodgate runs uses both at their maximum setting, and prodgate refuses to start without them:

```bash
claude plugin marketplace add JuliusBrussee/caveman && claude plugin install caveman@caveman
claude plugin marketplace add DietrichGebert/ponytail && claude plugin install ponytail@ponytail
```

**3. Run it.** In any repo, say `/prodgate`, "run QA", "set up a QA pipeline", "make it prod ready" or "bug hunt until zero".

It works on any language Claude Code can read. Optional extras make the gate sharper: the code-review-graph MCP (blast radius), plus `gitleaks`, `npm audit` and `pip-audit`.

## Standing on the shoulders of caveman and ponytail

prodgate's token discipline comes from two open-source projects. Every agent prodgate starts loads both at `ultra`, with no opt-out.

<table>
<tr>
<td width="50%" align="center" valign="top">
<a href="https://github.com/JuliusBrussee/caveman"><img src="https://raw.githubusercontent.com/JuliusBrussee/caveman/main/docs/assets/caveman-logo-banner.png" alt="caveman" width="320"></a>
<br><br>
<b><a href="https://github.com/JuliusBrussee/caveman">caveman</a></b> by <a href="https://github.com/JuliusBrussee">Julius Brussee</a>
<br><br>
Makes agents say less and read less. prodgate uses <code>ultra</code>, the strongest measured voice: <b>35% fewer output tokens than "be concise"</b>, by caveman's own measurement. When the caveman CLI is installed, prodgate's test runner also uses <code>caveman shrink</code>.
</td>
<td width="50%" align="center" valign="top">
<a href="https://github.com/DietrichGebert/ponytail"><picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/DietrichGebert/ponytail/main/assets/logo-dark.png"><img src="https://raw.githubusercontent.com/DietrichGebert/ponytail/main/assets/logo.png" alt="ponytail" width="220"></picture></a>
<br><br>
<b><a href="https://github.com/DietrichGebert/ponytail">ponytail</a></b> by <a href="https://github.com/DietrichGebert">Dietrich Gebert</a>
<br><br>
Makes agents write the smallest complete change. prodgate uses <code>ultra</code>, so fixers question the request first. By ponytail's own benchmark: <b>45% fewer tokens and 53% less code</b>, with 98% of risky logic shipping with a test.
</td>
</tr>
</table>

<sub>Logos belong to their projects and are shown here only to credit them. prodgate works with caveman and ponytail; it is not affiliated with or endorsed by either. caveman is Apache-2.0, ponytail is MIT.</sub>

## Built to waste nothing

Most of an agent run's cost is the input it reads, re-sent on every turn. prodgate cuts input first:

- **A ledger of coverage.** Every file is recorded with the commit it was checked at. A round reads only the diff, never-reviewed files and their callers.
- **Frozen commits.** Nobody hunts code that is still changing, so no finding goes stale before it is read.
- **Batched checks.** One checker per group of files settles all of that group's findings, so each file is read once.
- **Compact test output.** One line on a pass, only the failing lines on a fail.
- **Lean agents.** Every agent reads by line range, never reads a file twice, and answers with a schema. Low-risk state machines can run on a lighter model.

## Benchmark

[`bench/`](bench/) is a public benchmark for state-bug finders: **8 realistic apps** (FastAPI + SQLAlchemy, plus TypeScript UI state), with **59 seeded bugs** across 8 bug classes and **24 decoys**, code that looks wrong but is correct. Every seeded bug was confirmed with a failing test, every decoy with a passing one, and every app's own test suite passes with the bugs in place.

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
