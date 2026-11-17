# What the best QA pipelines do, and what prodgate took from them

Every pipeline with credible precision has the same shape: **cheap generators inside deterministic filters**. Fuzzers, mutants, random workloads and LLM finders generate candidates cheaply. Then something *executes* and decides what is real, and people only see the survivors. prodgate is built around that rule.

## The evidence that shaped prodgate

| Finding | Source | What prodgate does with it |
|---|---|---|
| Google's Big Sleep reports only bugs it has reproduced with a crash or assertion | [Project Zero](https://projectzero.google/2024/10/from-naptime-to-big-sleep.html) | A bug counts only with a failing test |
| AIxCC's winner validated patches by re-running proofs of vulnerability: **91% accuracy, against 44%** for a top team without them | [Team Atlanta](https://team-atlanta.github.io/blog/post-afc) | Fixes must fail before and pass after |
| An LLM refuter cut false positives by 92%, but **threw out 314 real vulnerabilities** and lost 77–84% of the subtle classes | [arXiv 2601.22952](https://arxiv.org/html/2601.22952v1) | Refuting needs quoted code. "Unsure" goes to a test, never to the bin |
| Meta's LLM test generator keeps only tests that build, pass reliably and add coverage. 73% of survivors were accepted | [arXiv 2402.09171](https://arxiv.org/abs/2402.09171) | The fix acceptance check: fails before, passes 3×, fails again without the fix |
| Google's mutation testing on changed lines only: productive mutants went **from 15% to 89%** | [Petrović et al.](https://arxiv.org/pdf/2102.11378) | "Undo the fix, the test must fail": the smallest mutant on the changed lines |
| Meta's ACH used mutation as the filter: 277 of 571 accepted tests would have been dropped by a coverage rule | [arXiv 2501.12862](https://arxiv.org/pdf/2501.12862) | A test that cannot fail without the fix is not done |
| Google's Tricorder requires **under 10% effective false positives**, and noisy analyzers get turned off | [SWE at Google, ch. 20](https://abseil.io/resources/swe-book/html/ch20.html) | A per-kind noise budget: noisy kinds must bring a line-by-line repro |
| Meta's Infer: a **70% fix rate** for findings shown in code review, against 0% for batch reports | [CACM 2019](https://6826.csail.mit.edu/2020/papers/facebook-infer-cacm.pdf) | Findings come back as fixes with tests, in the same loop |
| Postgres READ COMMITTED is correct; app read-then-write code on top of it is not. A barrier between the read and the write reproduces a lost update on every run | [Jepsen](https://jepsen.io/analyses/postgresql-12.3), [lirbank](https://www.lirbank.com/harnessing-postgres-race-conditions) | Race proofs use a hook between the read and the write, never sleeps |
| A DynamoDB bug needed a 35-step trace that design and code reviews missed | [CACM 2015](https://lamport.azurewebsites.net/tla/formal-methods-amazon.pdf) | Hunters walk sequences of actions with two actors, not single calls |
| Verification cost scales with the number of candidates checked. Cheap models often find as well as strong ones | [Claude docs](https://code.claude.com/docs/en/code-review-costs), [arXiv 2606.15689](https://arxiv.org/pdf/2606.15689) | Risk-tiered models; checkers batched per file group |
| Empty output is a normal, valid result: Copilot stays silent on 29% of reviews | [GitHub](https://github.blog/ai-and-ml/github-copilot/60-million-copilot-code-reviews-and-counting/) | A clean round is allowed to say nothing, and costs nothing on unchanged code |

## Ranked additions, and where each one stands

| # | Addition | Status in prodgate |
|---|---|---|
| 1 | Reproduction replaces deletion when refuting | **Done.** Verdicts are refuted (with quoted code), confirmed or unproven. Unproven findings go to a test. |
| 2 | Fix acceptance filter with a diff-scoped mutant | **Done**, simplest form: fails before, passes 3×, fails with only the fix undone. mutmut and Stryker hooks are planned. |
| 3 | An invariant checker after every test | Planned. Repo-specific; see the roadmap. |
| 4 | Two-connection race tests for read-modify-write | **Done** for proofs: race findings are proven with a hook between the read and the write. |
| 5 | Executable state machines from the maps (Hypothesis, Schemathesis) | Planned. The maps already list states, transitions and guards. |
| 6 | Fault injection in job runners (crash after step k, for every k) | Planned. |
| 7 | Per-kind noise budget, with silence as a valid result | **Done** (`ledger.py strict`). |
| 8 | Every confirmed bug becomes a repo-wide check | Planned. |
| 9 | Post-deploy canary, bake and auto-rollback | Out of scope for a code-level tool. |
| 10 | Risk-tiered depth and model routing | **Done** (`risk` on each machine; `models.light`). |

## Honest limits

- Almost all of this evidence comes from very large companies. No study measures these practices for a team of one to three people, or on agent-written code. The transfer is inference.
- No published study measures LLM refuter accuracy on logic, state or concurrency bugs in web apps. The refuter critique extrapolates from security triage.
- A clean round measures the finder's attention, not the absence of bugs. Testing proves bugs are present, never that they are absent.
