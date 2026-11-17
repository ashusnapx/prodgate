# prodgate-bench: fixture spec

prodgate-bench measures how well a QA pipeline finds **state bugs**: bugs in how an app moves between states, which ordinary tests miss. Each fixture is a small, realistic app with a known set of seeded bugs and a few **decoys** (code that looks suspicious but is correct). The answer key lives outside the fixture, so the pipeline under test never sees it.

## Layout

```
bench/fixtures/<app>/            # what the pipeline reviews (never contains the answer key)
  README.md                      # what the app does, in plain words (no hints about bugs)
  app/ or src/                   # the code
  tests/                         # a small passing test suite that does NOT catch the seeded bugs
  run_tests.sh                   # one command that runs the suite and exits 0 today
bench/truth/<app>.json           # the answer key (see schema)
```

## Size and realism
- 400–900 lines of source per app, laid out the way real apps are: routers or handlers, services, models, a job runner or a store.
- Seeded bugs must look like real mistakes a good engineer makes, never like planted puzzles. No comments that hint at them. Name things normally.
- Python apps: FastAPI + SQLAlchemy 2 on SQLite, tested with pytest, using only `fastapi`, `sqlalchemy`, `pydantic`, `httpx`, `pytest` (bench/requirements.txt).
- TypeScript apps: plain TS modules (stores, mutation managers, pollers, wizards) with no npm dependencies, tested with `node --test` (Node 22.18+ strips types natively). Model React Query-style semantics yourself, e.g. "per-call callbacks run only for the latest call" (document it in the README as how the library works).
- The tests must pass with the bugs in place.

## Bug classes (use them all across the suite; label each bug with one)
| class | meaning |
|---|---|
| `race` | two requests, users, tabs or jobs interleave: read-then-write with no lock or compare-and-swap, unchecked rowcount, double claim |
| `stuck` | a state with no way out after a failure, crash, timeout or lost message |
| `overwrite` | a later or stale write clobbers a newer or terminal state |
| `illegal-transition` | a move the state machine should refuse (terminal re-entered, skipping a step, acting on a withdrawn item) |
| `scope` | a missing tenant/org/owner check that exposes or changes another tenant's data |
| `double-submit` | a repeated request creates duplicates or applies an effect twice |
| `wrong-item` | state kept for the wrong entity after a switch, delete, refetch or reset |
| `ui-unhandled` | the UI mishandles a state the backend returns (spinner forever, error never cleared, wrong action offered, lost callback) |

## Answer key schema (`bench/truth/<app>.json`)
```json
{
  "app": "jobs-queue",
  "bugs": [
    {
      "id": "jq-1",
      "class": "race",
      "file": "app/services/jobs.py",
      "lines": [42, 58],
      "function": "claim_next_job",
      "summary": "two workers can claim the same job: SELECT then UPDATE with no lock or compare-and-swap",
      "repro": "worker A selects job 7; worker B selects job 7; both update it to running and run it twice",
      "severity": "high"
    }
  ],
  "decoys": [
    {
      "id": "jq-d1",
      "file": "app/services/jobs.py",
      "lines": [70, 80],
      "why_correct": "the UPDATE ... WHERE status='queued' checks rowcount, so a lost race is a no-op"
    }
  ]
}
```
`lines` is the span a reviewer would reasonably point at (keep it to 30 lines or fewer). Each app has 6–9 bugs and 2–3 decoys.

## Scoring (bench/score.py)
- A finding matches a bug when the file is the same, the finding's line is inside `lines` widened by 10 either side (or it names the same function), and the description is about the same mechanism. Each bug matches at most one finding.
- A finding on a decoy is a false positive. Any other unmatched finding goes to adjudication: a separate judge, given the code, has to write a failing test. If the test fails, the finding is a real unseeded bug (counted separately, not as a false positive); otherwise it is a false positive.
- Report recall (bugs found / bugs seeded), precision ((matched + real unseeded) / reported), decoy false positives, agents used, output tokens and wall time per mode.
