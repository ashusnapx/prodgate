export const meta = {
  name: 'prodgate',
  description: 'prodgate QA round: map state machines, or hunt a frozen commit, check each finding against the code, prove it with a failing test, and fix test-first',
  whenToUse: 'Called by the prodgate skill with args {mode: "map"|"round", repo, sha, ...}; never on code that is still changing',
  phases: [
    { title: 'Map', detail: 'inventory the implicit state machines per cluster' },
    { title: 'Hunt', detail: 'find bugs in the scope on the frozen commit' },
    { title: 'Verify', detail: 'refute with cited code, confirm, or mark unproven' },
    { title: 'Prove', detail: 'report-only runs: a failing test or it is dropped' },
    { title: 'Design', detail: 'simplify machines that keep breaking' },
    { title: 'Fix', detail: 'test-first, one owner per file group, checked fixes only' },
  ],
}

// args: {mode, repo, sha, base, scope, machines, seen, hot, strict, commands, clusters,
//        fix (default true), preamble, qaRun, scratch,
//        models: {map, hunt, light, verify, prove, fix, design}, designAgents: {critic, simplicity}, maxHunters}
const A = args || {}
// Required in every agent, with no opt-out: caveman at ultra (its strongest measured voice) and
// ponytail at ultra (smallest complete change), plus read-once rules that cut input, where most tokens go.
const LEAN =
  'REQUIRED before anything else: call the Skill tool with skill "caveman" (args "ultra"), then skill "ponytail" (args "ultra"), and follow both for the whole task. ' +
  'If either skill is missing, stop and answer only "prodgate needs the caveman and ponytail plugins". ' +
  'Then: no prose between tool calls; grep -n first, then read only the line ranges you need; never read a file twice; never print whole files; ' +
  'final answer = the schema only, terse fragments, code, paths and errors verbatim.\n\n'
const PRE = LEAN + (A.preamble ? `${A.preamble.trim()}\n\n` : '')
const RUN = A.qaRun || 'qa-run'
const M = A.models || {}
const SCRATCH = A.scratch || '/tmp/prodgate-prove'
const CMDS = JSON.stringify(A.commands || {})
const KINDS = ['race', 'stuck', 'overwrite', 'illegal-transition', 'scope', 'double-submit', 'wrong-item', 'ui-unhandled', 'other']
const FROZEN = `Repo ${A.repo} at commit ${A.sha}. Read-only: do not edit the repo, start servers or call models. Read code with git show ${A.sha}:<path> or the working tree (it equals that commit).`
const opt = (o, model) => (model ? { ...o, model } : o)

const MACHINES = {
  type: 'object',
  properties: {
    machines: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          files: { type: 'array', items: { type: 'string' } },
          states: { type: 'array', items: { type: 'string' } },
          transitions: { type: 'array', items: { type: 'string' } },
          guards: { type: 'array', items: { type: 'string' } },
          actors: { type: 'string' },
          risk: { type: 'string', enum: ['high', 'medium', 'low'] },
        },
        required: ['id', 'name', 'files', 'states', 'transitions', 'risk'],
      },
    },
  },
  required: ['machines'],
}
const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          machine: { type: 'string' },
          kind: { type: 'string', enum: KINDS },
          file: { type: 'string' },
          line: { type: 'integer' },
          function: { type: 'string' },
          bug: { type: 'string' },
          repro: { type: 'string' },
          why: { type: 'string' },
          fix: { type: 'string' },
          severity: { type: 'string', enum: ['high', 'medium', 'low'] },
          files: { type: 'array', items: { type: 'string' } },
        },
        required: ['machine', 'kind', 'file', 'line', 'bug', 'repro', 'why', 'fix', 'severity', 'files'],
      },
    },
    not_covered: { type: 'array', items: { type: 'string' } },
  },
  required: ['findings'],
}
const VERDICTS = {
  type: 'object',
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: { key: { type: 'string' }, verdict: { type: 'string', enum: ['refuted', 'confirmed', 'unproven'] }, evidence: { type: 'string' } },
        required: ['key', 'verdict', 'evidence'],
      },
    },
  },
  required: ['results'],
}
const PROVED = {
  type: 'object',
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          key: { type: 'string' },
          outcome: { type: 'string', enum: ['refuted', 'reproduced', 'not_reproduced', 'no_harness_traced', 'no_harness_unsure'] },
          evidence: { type: 'string' },
          test: { type: 'string' },
        },
        required: ['key', 'outcome', 'evidence'],
      },
    },
  },
  required: ['results'],
}
const DESIGN = {
  type: 'object',
  properties: { machine: { type: 'string' }, plan: { type: 'string' }, files: { type: 'array', items: { type: 'string' } } },
  required: ['machine', 'plan'],
}
const FIXED = {
  type: 'object',
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          key: { type: 'string' },
          status: { type: 'string', enum: ['fixed', 'not_reproduced', 'skipped'] },
          files: { type: 'array', items: { type: 'string' } },
          test: { type: 'string' },
          failed_before: { type: 'boolean' },
          passes_after: { type: 'integer' },
          fails_without_fix: { type: 'boolean' },
          note: { type: 'string' },
        },
        required: ['key', 'status'],
      },
    },
  },
  required: ['results'],
}

const words = s => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().split(' ').slice(0, 7).join(' ')
const keyOf = f => `${f.file}::${words(f.bug)}`
const slim = f => ({ key: f.key, kind: f.kind, file: f.file, line: f.line, function: f.function, bug: f.bug, repro: f.repro, fix: f.fix })

// one owner per file: group findings whose file sets overlap (union-find)
const byFiles = list => {
  const parent = list.map((_, i) => i)
  const find = i => (parent[i] === i ? i : (parent[i] = find(parent[i])))
  const owner = {}
  list.forEach((f, i) =>
    [f.file, ...(f.files || [])].forEach(p => {
      if (owner[p] === undefined) owner[p] = i
      else parent[find(i)] = find(owner[p])
    }),
  )
  const groups = {}
  list.forEach((f, i) => (groups[find(i)] ||= []).push(f))
  return Object.values(groups)
}
const filesOf = g => [...new Set(g.flatMap(f => [f.file, ...(f.files || [])]))]

// ---------- map: one inventory pass per cluster ----------
if (A.mode === 'map') {
  phase('Map')
  const res = await parallel(
    (A.clusters || []).map(c => () =>
      agent(
        `${PRE}${FROZEN}\n\nFind all of the implicit state machines in my app, limited to: ${c.paths.join(', ')}.\n` +
          'A state machine is anything with states and moves between them: status columns, boolean flags, nullable timestamps, job or queue states, sessions, UI modes, wizard steps, polling loops, cached screens, locks.\n' +
          `For each one return: id (short kebab, unique, prefixed "${c.name}-"), name, files (repo-relative paths that read or write its state), states, transitions ("from -> to: trigger, where"), guards (where each transition is checked), actors (who can act at once: users, tabs, jobs, webhooks, admins), and risk: high if two actors can act at once or it touches money, auth, tenancy or deletion; low if it is single-actor UI state; otherwise medium.\n` +
          'Mapping only, no bugs. Use grep and targeted reads.',
        opt({ label: `map:${c.name}`, phase: 'Map', schema: MACHINES }, M.map),
      ),
    ),
  )
  const machines = res.filter(Boolean).flatMap(r => r.machines)
  log(`${machines.length} state machines mapped across ${(A.clusters || []).length} clusters`)
  return { machines }
}

// ---------- round: hunt -> verify -> (prove | design + fix) ----------
const scope = A.scope || []
const machines = A.machines || []
const empty = { confirmed: [], unproven: [], rejected: [], fix_results: [], design: [], not_covered: [] }
if (!scope.length) return { ...empty, note: 'empty scope' }

const inScope = new Set(scope)
const touching = machines.filter(m => (m.files || []).some(f => inScope.has(f)))
const covered = new Set(touching.flatMap(m => m.files || []))
const loose = scope.filter(f => !covered.has(f))
const MAX_HUNTERS = A.maxHunters || 8
// risk-tiered depth: high-risk machines get their own hunter on the strong model;
// low-risk ones are packed together and may run on a lighter model
const rank = { high: 0, medium: 1, low: 2 }
const units = [
  ...touching.sort((a, b) => rank[a.risk || 'medium'] - rank[b.risk || 'medium']).map(m => ({ machines: [m], files: m.files || [], risk: m.risk || 'medium' })),
  ...Array.from({ length: Math.ceil(loose.length / 40) }, (_, i) => ({ machines: [], files: loose.slice(i * 40, i * 40 + 40), risk: 'medium' })),
]
const per = Math.max(1, Math.ceil(units.length / MAX_HUNTERS))
const groups = []
for (let i = 0; i < units.length; i += per) {
  const g = units.slice(i, i + per)
  groups.push({ machines: g.flatMap(u => u.machines), files: [...new Set(g.flatMap(u => u.files))], light: g.every(u => u.risk === 'low') })
}
const seen = new Set(A.seen || [])
const seenHint = (A.seen || []).slice(-80).join('\n')
const strict = (A.strict || []).length
  ? `These kinds have had many false reports in this repo; report them only with a line-by-line repro that names the exact interleaving or input: ${A.strict.join(', ')}.\n`
  : ''
const diffNote = A.base && A.base !== A.sha ? `Changed since the last check: \`git diff ${A.base}..${A.sha} -- <files>\`. Review those changes first, then the rest of each machine.\n` : ''

phase('Hunt')
const hunted = await parallel(
  groups.map((g, i) => () =>
    agent(
      `${PRE}${FROZEN}\n\nFind all of the implicit state machines in my app, limited to the machines and files below, and report BUGS ONLY.\n${diffNote}` +
        `Machines (from the map): ${JSON.stringify(g.machines.map(m => ({ id: m.id, name: m.name, states: m.states, transitions: m.transitions, guards: m.guards, actors: m.actors })))}\n` +
        `Files in scope: ${g.files.join(', ') || '(only the machines above)'}\n\n` +
        'Report bugs of these kinds (set `kind`):\n' +
        '- race: two users, tabs, jobs, retries or redelivered messages interleave (read-then-write with no lock or compare-and-swap; rowcount unchecked; double claim);\n' +
        '- stuck: a state with no way out after a failure, crash, timeout or lost message;\n' +
        '- overwrite: a later or stale write clobbers a newer or terminal state;\n' +
        '- illegal-transition: a move the machine should refuse (terminal re-entered, step skipped, acting on a withdrawn item);\n' +
        '- scope: a missing tenant, org or owner check;\n' +
        '- double-submit: a repeated request creates duplicates or applies an effect twice;\n' +
        '- wrong-item: state kept for the wrong entity after a switch, delete, refetch or reset;\n' +
        '- ui-unhandled: a backend state the screen mishandles, an action offered that the backend refuses, per-call callbacks lost when a newer call starts, errors never cleared, polling that never ends.\n' +
        strict +
        'Walk sequences of up to 5 actions, with two tabs or users where reachable.\n' +
        'For callers and blast radius, prefer the code-review-graph MCP (query_graph_tool callers_of, get_impact_radius_tool) if it is connected, over wide greps.\n' +
        'Each bug must be reachable from the UI, the API, a job or a CLI. No style, perf-only or theoretical items.\n' +
        `Do not report these already-seen issues again:\n${seenHint || '(none)'}\n` +
        'Per bug: `function` = the function that holds the bug, `files` = every file the fix would touch. List files you did not read fully in not_covered.',
      opt({ label: `hunt:${i + 1}/${groups.length}`, phase: 'Hunt', schema: FINDINGS }, g.light ? M.light || M.hunt : M.hunt),
    ),
  ),
)
const notCovered = hunted.filter(Boolean).flatMap(r => r.not_covered || [])
const all = hunted.filter(Boolean).flatMap(r => r.findings)
const fresh = []
const keys = new Set()
for (const f of all) {
  const k = keyOf(f)
  if (seen.has(k) || keys.has(k)) continue
  keys.add(k)
  fresh.push({ ...f, key: k })
}
log(`${all.length} reported, ${fresh.length} new after de-duplication`)
if (!fresh.length) return { ...empty, not_covered: notCovered }

// checkers work per group of files, so each file is read once for all of its findings
const chunk = (g, n) => Array.from({ length: Math.ceil(g.length / n) }, (_, i) => g.slice(i * n, i * n + n))
const checkGroups = byFiles(fresh).flatMap(g => chunk(g, 8))
const REFUTE = '- refuted: only if you can quote the code (file:line) that makes the repro impossible: a guard, a lock, a compare-and-swap, a check that runs first, or the path being unreachable.\n'

// ---------- report-only runs: refute with quoted code, or prove with a failing test ----------
if (A.fix === false) {
  phase('Prove')
  const proved = (
    await parallel(
      checkGroups.map((g, i) => () =>
        agent(
          `${PRE}Repo ${A.repo} at commit ${A.sha}. Do NOT edit the repo. Check each reported bug below against the code, then settle it as one of:\n${REFUTE}` +
            `- reproduced: you wrote the smallest test that FAILS because of the bug, in a new folder under ${SCRATCH}/${i + 1}/ (outside the repo) that calls the repo code, and ran it through ${RUN}. For races, put a hook between the read and the write (monkeypatch or a wrapper) that performs the competing action; no sleeps.\n` +
            '- not_reproduced: your test passes, so the bug is not there.\n' +
            '- no_harness_traced: the code cannot run in a test here, but you traced the repro step by step and nothing stops it (quote the lines).\n' +
            '- no_harness_unsure: none of the above.\n' +
            `Evidence = the quoted lines or the failing assertion. Delete the folder when done. Repo commands: ${CMDS}.\nBugs:\n${JSON.stringify(g.map(slim))}`,
          opt({ label: `prove:${i + 1}/${checkGroups.length}`, phase: 'Prove', schema: PROVED }, M.prove),
        ),
      ),
    )
  )
    .filter(Boolean)
    .flatMap(r => r.results)
  const out = new Map(proved.map(p => [p.key, p]))
  const kept = new Set(['reproduced', 'no_harness_traced'])
  const confirmed = fresh.filter(f => kept.has(out.get(f.key)?.outcome)).map(f => ({ ...f, proof: out.get(f.key).outcome, test: out.get(f.key).test, evidence: out.get(f.key).evidence }))
  const rejected = fresh.filter(f => !kept.has(out.get(f.key)?.outcome)).map(f => ({ key: f.key, kind: f.kind, outcome: out.get(f.key)?.outcome || 'unchecked', evidence: out.get(f.key)?.evidence }))
  log(`${confirmed.length} reported (${confirmed.filter(f => f.proof === 'reproduced').length} with a failing test), ${rejected.length} dropped`)
  return { ...empty, confirmed, rejected, not_covered: notCovered }
}

// a verifier kills a finding only by quoting the code that makes it impossible;
// anything it cannot settle is "unproven" and goes to the fixer's failing test, never to the bin
phase('Verify')
const verdicts = (
  await parallel(
    checkGroups.map((g, i) => () =>
      agent(
        `${PRE}${FROZEN}\n\nCheck each reported bug below by reading the cited code and its callers (read only what you need), and give each a verdict:\n${REFUTE}` +
          '- confirmed: you traced the repro step by step and nothing stops it; quote the lines.\n' +
          '- unproven: anything else (unsure, depends on timing or config). Unproven bugs go to a test, so never guess refuted.\n' +
          `Put the quoted lines in evidence.\nBugs:\n${JSON.stringify(g.map(f => ({ key: f.key, kind: f.kind, file: f.file, line: f.line, bug: f.bug, repro: f.repro, why: f.why })))}`,
        opt({ label: `verify:${i + 1}/${checkGroups.length}`, phase: 'Verify', schema: VERDICTS, effort: 'medium' }, M.verify),
      ),
    ),
  )
)
  .filter(Boolean)
  .flatMap(r => r.results)
const vmap = new Map(verdicts.map(v => [v.key, v]))
const verdictOf = f => {
  const v = vmap.get(f.key)
  if (v?.verdict === 'refuted' && /\d/.test(v.evidence || '')) return 'refuted'
  return v?.verdict === 'confirmed' ? 'confirmed' : 'unproven'
}
const confirmed = fresh.filter(f => verdictOf(f) === 'confirmed').map(f => ({ ...f, evidence: vmap.get(f.key)?.evidence }))
const unproven = fresh.filter(f => verdictOf(f) === 'unproven')
const rejected = fresh.filter(f => verdictOf(f) === 'refuted').map(f => ({ key: f.key, kind: f.kind, evidence: vmap.get(f.key)?.evidence }))
log(`${confirmed.length} confirmed, ${unproven.length} unproven, ${rejected.length} refuted with quoted code`)
const live = [...confirmed, ...unproven]
if (!live.length) return { ...empty, rejected, not_covered: notCovered }

// machines that keep breaking get a design step; their findings wait for it
const hot = new Set(A.hot || [])
const hotHit = [...new Set(live.filter(f => hot.has(f.machine)).map(f => f.machine))]
phase('Design')
const DA = A.designAgents || {}
const design = (
  await parallel(
    hotHit.map(m => async () => {
      const brief = `${FROZEN}\n\nState machine "${m}" has had confirmed bugs in 3 or more rounds in a row. This round's:\n${JSON.stringify(live.filter(f => f.machine === m).map(slim))}\nCritique its design as code (not a document): what structure keeps producing these bugs, and what is the smallest change that removes the whole class? 8 lines or fewer.`
      const [hostile, simple] = await parallel([
        () => agent(`${PRE}You are a hostile architecture critic. Read-only.\n${brief}`, opt({ label: `design:${m}:critic`, phase: 'Design', ...(DA.critic ? { agentType: DA.critic } : {}) }, M.design)),
        () => agent(`${PRE}You are a simplicity reviewer (YAGNI: delete, merge, drop rules). Read-only.\n${brief}`, opt({ label: `design:${m}:simplicity`, phase: 'Design', ...(DA.simplicity ? { agentType: DA.simplicity } : {}) }, M.design)),
      ])
      return agent(
        `${PRE}${FROZEN}\n\nTwo reviews of state machine "${m}":\nCRITIC: ${hostile}\nSIMPLICITY: ${simple}\n` +
          'Merge them into ONE smallest redesign that removes the class of bug, preferring deletion and consolidation over new code. Give the plan in 5 lines or fewer, plus the files it touches.',
        opt({ label: `design:${m}:plan`, phase: 'Design', schema: DESIGN }, M.design),
      )
    }),
  )
).filter(Boolean)

const toFix = live.filter(f => !hotHit.includes(f.machine))
const fixGroups = byFiles(toFix)

phase('Fix')
const fixed = await parallel(
  fixGroups.map((g, i) => () =>
    agent(
      `${PRE}Repo ${A.repo}, branch at ${A.sha}. You own ONLY these files (plus their tests): ${filesOf(g).join(', ')}. Other fixers are editing other files at the same time. Never commit, stash, reset or checkout. Edit with exact-string replacements.\n` +
        'Fix each bug test-first. A fix counts only with all of this evidence:\n' +
        '1. Write a failing test in the matching existing test file. Run it: it must fail for the stated reason (failed_before=true). For races, hook between the read and the write; no sleeps.\n' +
        '2. Make the smallest fix, with a one-line plain comment on why.\n' +
        '3. Run the test 3 times: it passes every time (passes_after=3).\n' +
        '4. Undo only the fix (keep the test), run it: it fails again (fails_without_fix=true). Then put the fix back.\n' +
        'If step 1 cannot fail, leave the code alone and mark it not_reproduced; that is a valid, useful answer.\n' +
        `Run EVERY test command through ${RUN} (it queues tests and waits for dev servers), targeted files only, never the full suite. Repo commands: ${CMDS}. Lint and format the changed files.\n` +
        `Bugs:\n${JSON.stringify(g.map(slim))}`,
      opt({ label: `fix:${i + 1}/${fixGroups.length}`, phase: 'Fix', schema: FIXED }, M.fix),
    ),
  ),
)
const results = fixed.filter(Boolean).flatMap(r => r.results)
// the acceptance check: a "fixed" claim without the evidence is returned for a human look
const accepted = r => r.status === 'fixed' && r.failed_before && (r.passes_after || 0) >= 3 && r.fails_without_fix
const fixResults = results.map(r => (r.status === 'fixed' && !accepted(r) ? { ...r, status: 'unchecked' } : r))
log(`${fixResults.filter(r => r.status === 'fixed').length} fixed with full evidence, ${fixResults.filter(r => r.status === 'unchecked').length} unchecked, ${fixResults.filter(r => r.status === 'not_reproduced').length} not reproduced, ${design.length} design plans waiting`)
return { ...empty, confirmed, unproven, rejected, fix_results: fixResults, design, held_for_design: live.filter(f => hotHit.includes(f.machine)), not_covered: notCovered }
