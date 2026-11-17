export const meta = {
  name: 'prodgate-bench',
  description: 'prodgate-bench: run one QA mode over the fixture apps and return its findings, or judge findings against the answer keys',
  whenToUse: 'Run by bench/README.md steps, one mode per invocation so each mode gets its own token count',
  phases: [
    { title: 'Review', detail: 'the mode under test reads each app' },
    { title: 'Judge', detail: 'same mechanism? real bug outside the key?' },
  ],
}

// args: {mode: 'oneshot'|'prompt'|'prodgate'|'recheck'|'judge', apps: [{name, path, sha, files, commands}],
//        pg: '<abs path to prodgate.workflow.js>', qaRun, scratch, models, maps: {app: machines}, seen: {app: [keys]},
//        changes: {app: {base, files}}, pairs, unmatched}
const A = args || {}
const STAY = 'Stay inside the repo directory. Read-only: do not edit files.'
const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'integer' },
          function: { type: 'string' },
          bug: { type: 'string' },
          repro: { type: 'string' },
        },
        required: ['file', 'line', 'bug'],
      },
    },
  },
  required: ['findings'],
}
const ASK = 'For each bug give file (repo-relative path), line, function, a one-line description, and the steps that trigger it.'
const slim = f => ({ file: f.file, line: f.line, function: f.function, bug: f.bug, repro: f.repro, proof: f.proof })

const one = (app, prompt) =>
  agent(`Repo: ${app.path}. ${STAY}\n\n${prompt}\n${ASK}`, { label: `${A.mode}:${app.name}`, phase: 'Review', schema: FINDINGS }).then(r => ({
    app: app.name,
    findings: (r?.findings || []).map(slim),
  }))

const pgRound = (app, extra) =>
  workflow(
    { scriptPath: A.pg },
    {
      mode: 'round',
      repo: app.path,
      sha: app.sha,
      base: app.sha,
      fix: false,
      qaRun: A.qaRun,
      scratch: `${A.scratch}/${app.name}`,
      commands: app.commands,
      maxHunters: 2,
      models: A.models,
      ...extra,
    },
  )

let out = []
phase('Review')
if (A.mode === 'oneshot') {
  // a plain AI code review: the common baseline
  out = await parallel(A.apps.map(app => () => one(app, 'Review this codebase and report every real bug you find.')))
} else if (A.mode === 'prompt') {
  // the state-machine prompt on its own, one pass, nothing checked
  out = await parallel(A.apps.map(app => () => one(app, 'Find all of the implicit state machines in my app, then report every bug in them.')))
} else if (A.mode === 'prodgate') {
  // first run: map, then one report-only round over every source file
  out = await parallel(
    A.apps.map(app => async () => {
      const map = await workflow({ scriptPath: A.pg }, { mode: 'map', repo: app.path, sha: app.sha, clusters: [{ name: app.name, paths: app.files }], models: A.models })
      const r = await pgRound(app, { scope: app.files, machines: map?.machines || [] })
      return { app: app.name, findings: (r?.confirmed || []).map(slim), machines: map?.machines || [], seen: [...(r?.confirmed || []), ...(r?.rejected || [])].map(f => f.key), dropped: (r?.rejected || []).length }
    }),
  )
} else if (A.mode === 'recheck') {
  // a later run after a small change: only the changed files and their callers, with the saved map and seen keys
  out = await parallel(
    A.apps.map(app => async () => {
      const ch = (A.changes || {})[app.name]
      if (!ch || !ch.files.length) return { app: app.name, findings: [], skipped: true }
      const r = await pgRound(app, { base: ch.base, scope: ch.files, machines: (A.maps || {})[app.name] || [], seen: (A.seen || {})[app.name] || [] })
      return { app: app.name, findings: (r?.confirmed || []).map(slim) }
    }),
  )
} else if (A.mode === 'judge') {
  phase('Judge')
  // 1) does each candidate pair describe the same mechanism? (text only, cheap)
  const SAME = {
    type: 'object',
    properties: { pairs: { type: 'array', items: { type: 'object', properties: { id: { type: 'integer' }, same: { type: 'boolean' } }, required: ['id', 'same'] } } },
    required: ['pairs'],
  }
  const pairs = A.pairs || []
  const batches = Array.from({ length: Math.ceil(pairs.length / 60) }, (_, i) => pairs.slice(i * 60, i * 60 + 60))
  const same = (
    await parallel(
      batches.map((b, i) => () =>
        agent(
          'For each pair, say whether the REPORTED finding describes the same bug mechanism as the KNOWN bug (same wrong behaviour from the same cause; wording may differ). Be strict: same file but a different cause is not the same.\n' +
            JSON.stringify(b.map(p => ({ id: p.id, reported: p.finding_text, known: p.bug_text }))),
          { label: `judge:pairs:${i + 1}`, phase: 'Judge', schema: SAME, model: 'sonnet', effort: 'low' },
        ),
      ),
    )
  )
    .filter(Boolean)
    .flatMap(r => r.pairs)
  // 2) findings that match nothing in the key: is any of them a real bug? A test decides.
  const REAL = {
    type: 'object',
    properties: { results: { type: 'array', items: { type: 'object', properties: { id: { type: 'integer' }, real: { type: 'boolean' }, evidence: { type: 'string' } }, required: ['id', 'real', 'evidence'] } } },
    required: ['results'],
  }
  const byApp = {}
  for (const u of A.unmatched || []) (byApp[u.app] ||= []).push(u)
  const real = (
    await parallel(
      Object.entries(byApp).map(([name, list]) => () => {
        const app = A.apps.find(a => a.name === name)
        return agent(
          `Repo: ${app.path}. Do not edit the repo. Each item is a bug someone reported. Decide if it is a REAL bug: real=true only if you write a small test in ${A.scratch}/judge-${name}/ (outside the repo) that fails because of it, and run it. Otherwise real=false. Evidence = the failing assertion, or why it is not a bug. Delete the folder when done.\n` +
            JSON.stringify(list.map(u => ({ id: u.id, file: u.file, line: u.line, bug: u.bug, repro: u.repro }))),
          { label: `judge:real:${name}`, phase: 'Judge', schema: REAL, model: 'sonnet' },
        )
      }),
    )
  )
    .filter(Boolean)
    .flatMap(r => r.results)
  return { same, real }
}
return { mode: A.mode, apps: Object.fromEntries(out.filter(Boolean).map(o => [o.app, o])) }
