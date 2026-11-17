---
name: prodgate
description: The QA pipeline for every repo. Takes code to production quality by finding and fixing state bugs (races, stuck states, stale overwrites, illegal transitions, missing tenant checks, double submits, lost UI state) in rounds on frozen commits until a round finds nothing, then runs a production gate. Every bug it reports comes with a failing test. Use when the user says "prodgate", "run QA", "QA pipeline", "set up QA", "QA my app", "make it prod ready", "production readiness check", "bug hunt", "bug hunt until zero", "loop until 0 bugs", "find race conditions", or asks to find the implicit state machines in an app. Use this instead of ad-hoc bug-hunt loops or one-off reviews whenever the goal is shipping safely.
---

# prodgate

QA that ends in "safe for production", without wasted tokens. Each check runs once, on code that is not changing, and is recorded so it is never repeated. A bug counts only when a test proves it.

`<skill>` below means this skill's base directory (the folder this file was loaded from).

## Required: caveman and ponytail at ultra

prodgate does not run without the [caveman](https://github.com/JuliusBrussee/caveman) and [ponytail](https://github.com/DietrichGebert/ponytail) plugins. Every agent it runs, and this session for the whole run, loads both at their maximum: caveman `ultra` (its strongest measured voice) and ponytail `ultra` (the smallest complete change, with the request questioned first).
- First, run `<skill>/bin/require-plugins`. If it fails, show its install lines and stop.
- Then call the Skill tool with skill `caveman` (args `ultra`) and skill `ponytail` (args `ultra`) in this session.
- The workflow puts the same requirement at the top of every agent's prompt, with no opt-out. Any other agent you start during prodgate (gate reviewers, the contract check, security) starts its prompt with: `REQUIRED before anything else: call the Skill tool with skill "caveman" (args "ultra"), then skill "ponytail" (args "ultra"), and follow both for the whole task.`

## Rules (never break them)

1. **Freeze before you hunt.** Hunters read one committed SHA. Nobody edits while a hunt runs. Fixes start after the findings are checked, and the next hunt starts after those fixes are committed.
2. **Never re-read what was checked.** The ledger records each file and the SHA it was reviewed at. A round's scope is the files changed since then, plus files never reviewed, plus their blast radius. Unchanged code costs nothing. A full re-read only happens on the first run or with `scope --full`.
3. **Tests decide, not opinions.** A verifier can kill a finding only by quoting the code that makes it impossible. Anything it cannot settle is "unproven" and goes to a test, never to the bin. A fix counts only if its test failed before the fix, passes 3 times after it, and fails again when the fix alone is undone.
4. **One owner per file.** Findings are grouped by the files they touch. Groups never share a file, and one fixer handles each group. Fixers never commit, stash, reset or checkout.
5. **One test process at a time.** Every test goes through `<skill>/bin/qa-run`, which holds a shared lock and returns compact output. Fixers run targeted tests only. The main session runs the full suites, once per round.
6. **Simplify, don't patch forever.** A state machine with confirmed bugs in 3 rounds in a row gets a design step first. A critic and a simplicity reviewer review it, then merge into the smallest redesign that removes the whole class of bug.
7. **Noise budget.** A bug kind that is mostly refuted or not reproduced in this repo (over 50%, after 4 or more reports) must come with a line-by-line repro from then on (`ledger.py strict`).
8. **Plain words outside.** Tickets, PRs and commits describe the bug and the fix in plain words, not the pipeline.

## Files

- `<skill>/bin/ledger.py`: the ledger at `~/.claude/qa/<repo>-<hash>/ledger.json` (or `$PRODGATE_HOME`). It holds the map, coverage, seen keys, streaks and per-kind noise.
- `<skill>/bin/require-plugins`: checks that caveman and ponytail are installed, and prints their install lines if not.
- `<skill>/bin/qa-run`: runs a test or build command under the shared lock. It prints one line on a pass, and the failing lines plus the tail on a fail.
- `<skill>/prodgate.workflow.js`: runs one round (map, or hunt → verify → prove or fix). Run it with the Workflow tool, `{scriptPath, args}`.

## Procedure

**0. Freeze and scope** (main session, cheap)
- `git status`: if the tree is dirty, ask whether to commit it first or run against HEAD.
- `python3 <skill>/bin/ledger.py scope` prints `sha`, `base`, `changed`, `unreviewed`, `machines_touched` and `first_run`. If `changed` and `unreviewed` are both empty, stop: nothing to check, 0 tokens spent.
- Blast radius: unchanged files that call changed code are where fixes break things. If the code-review-graph MCP is connected, run `get_impact_radius_tool` on `changed`. Otherwise grep for the changed functions' callers. Add those files to the scope.
- Find the repo's commands once (CLAUDE.md, Makefile, package.json, pyproject) and save them: `ledger.py set-commands '{"backend_test":"…","frontend_test":"…","typecheck":"…","lint":"…","build":"…"}'`.

**1. Map** (first run, or when `unreviewed` holds files no mapped machine covers)
- Split the repo into 4–8 clusters by top-level module and size (`wc -l`), or use code-review-graph `list_communities_tool`. Skip vendored, generated and test code.
- Run Workflow with `{scriptPath: "<skill>/prodgate.workflow.js", args: {mode: "map", repo, sha, clusters: [{name, paths}]}}`. Save the result: `ledger.py save-map <file with result.machines>`.

**2. Round** (repeat until clean)
- `args`:
  - `mode: "round"`, with `repo`, `sha`, `base`, and `scope` (changed + unreviewed + blast radius);
  - `machines`: from the ledger;
  - `seen`: `ledger.py seen`;
  - `hot`: `ledger.py hot`;
  - `strict`: `ledger.py strict`;
  - `commands`, and `qaRun: "<skill>/bin/qa-run"`.
  - Optional: `models: {hunt, light, verify, prove, fix, design}` for per-stage routing (for example `light: "sonnet"` for low-risk machines, `verify: "sonnet"`); `fix: false` for a report-only run, where every finding must reproduce in a scratch test.
- It returns `confirmed`, `unproven`, `rejected`, `fix_results` and `design`. `fix_results` statuses are fixed (with full evidence), unchecked (claimed without the evidence: look before you commit), not_reproduced, or skipped.
- If `design` is present, apply the simplest plan first, test-first, and say so in one line.
- Run the full suites, typecheck, lint and build through `qa-run`. Fix anything red, test-first, then commit in the repo's style.
- `ledger.py record-round <file with {sha, scope, machines, confirmed, rejected, not_reproduced, fixed}>`.
- **Stop when** the round returns 0 confirmed and 0 unproven, nothing is `not_covered`, and the scope covered everything changed since the last round. Otherwise take the new SHA and scope (only what the last round changed, plus anything still unreviewed) and run the next round.

**3. Production gate** (once, after the clean round). Use what is installed and skip the rest, saying which were skipped.
- The full suites, typecheck, lint and build: all green.
- A fresh-eyes review of the whole branch diff against main: the `code-review` skill, or `ponytail-review` if installed. Fix what it confirms, test-first, then run one more round on that diff.
- Security: a security review of untrusted-input paths in the diff (parsers, uploads, webhooks, auth).
- DB migrations: a single head, and the chain test if one exists.
- Secrets: `gitleaks detect` if installed, otherwise grep the diff for keys, tokens and passwords.
- Dependencies: `npm audit --omit=dev` and `pip-audit` if available. Report high and critical only.
- A contract check, for apps with a frontend and an API: one agent maps every frontend call to a backend route, body and response fields, and reports only breaks.
- For web apps: start the app once, open the main pages with a browser tool, watch for console errors, then stop everything.
- If a gate item fails: fix it, commit, and run one more round on that diff. Close by proving every gate item with its command output. Claim nothing unverified.

**4. Report** (once, at the end): a short table of rounds, confirmed and fixed per round, the gate results, what remains open, and the commits.

## Token rules

- Every agent starts with caveman `ultra` and ponytail `ultra` (required, no opt-out). It reads by line range after `grep -n`, never reads a file twice, and answers with the schema only.
- After round 1, hunters get only the scope files, their machines from the map and the seen keys. They never get the whole repo.
- High-risk machines (two actors at once, money, auth, tenancy, deletion) get their own hunter. Low-risk ones are packed together and can run on `models.light`.
- Verifiers read only the cited lines and their callers. Provers and fixers get one group of files each.
- Test output comes back compact through `qa-run` (or `caveman shrink` when the caveman CLI is installed).
- The main session keeps only round summaries and never reads agent transcripts.
- A low-memory machine (8 GB or less) gets one heavy process at a time: `qa-run` waits for dev servers there.
