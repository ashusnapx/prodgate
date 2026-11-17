// Runs prodgate.workflow.js with fake agents to check its control flow (no model calls).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const src = readFileSync(new URL('../skills/prodgate/prodgate.workflow.js', import.meta.url), 'utf8').replace(/^export const meta/m, 'const meta')
const run = (args, fake) => {
  const calls = []
  const agent = async (prompt, o) => { calls.push({ prompt, ...o }); return fake(o.label, prompt) }
  const parallel = async thunks => Promise.all(thunks.map(t => t().catch(() => null)))
  const body = new Function('args', 'agent', 'parallel', 'phase', 'log', 'workflow', `return (async () => {${src}\n})()`)
  return body(args, agent, parallel, () => {}, () => {}, null).then(result => ({ result, calls }))
}
const finding = (file, line, bug, extra = {}) => ({ machine: 'm1', kind: 'race', file, line, bug, repro: 'r', why: 'w', fix: 'f', severity: 'medium', files: [file], ...extra })
const base = { mode: 'round', repo: '/r', sha: 'abc', base: 'abc', scope: ['a.py', 'b.py'], machines: [{ id: 'm1', name: 'jobs', files: ['a.py'], states: [], transitions: [], risk: 'high' }] }

test('map returns the machines from every cluster', async () => {
  const { result, calls } = await run({ mode: 'map', repo: '/r', sha: 'abc', clusters: [{ name: 'x', paths: ['a'] }, { name: 'y', paths: ['b'] }] }, () => ({ machines: [{ id: 'm' }] }))
  assert.equal(result.machines.length, 2)
  assert.match(calls[0].prompt, /Find all of the implicit state machines in my app/)
  assert.match(calls[0].prompt, /^REQUIRED.*caveman.*ultra.*ponytail.*ultra/s)
})

test('empty scope spends no agents', async () => {
  const { result, calls } = await run({ ...base, scope: [] }, () => null)
  assert.equal(calls.length, 0)
  assert.equal(result.note, 'empty scope')
})

test('report-only: tests decide; seen keys and duplicates are dropped before checking', async () => {
  const fake = label => {
    if (label.startsWith('hunt')) return { findings: [finding('a.py', 10, 'double claim of job'), finding('a.py', 10, 'double claim of job'), finding('b.py', 5, 'old bug seen'), finding('a.py', 40, 'stuck running')] }
    if (label.startsWith('prove')) return { results: [{ key: 'a.py::double claim of job', outcome: 'reproduced', evidence: 'assert 2 == 1' }, { key: 'a.py::stuck running', outcome: 'not_reproduced', evidence: 'passes' }] }
  }
  const { result, calls } = await run({ ...base, fix: false, seen: ['b.py::old bug seen'] }, fake)
  assert.deepEqual(result.confirmed.map(f => f.key), ['a.py::double claim of job'])
  assert.deepEqual(result.rejected.map(f => f.outcome), ['not_reproduced'])
  assert.equal(calls.filter(c => c.label.startsWith('prove')).length, 1, 'one prover per file group')
})

test('fix mode: a refute needs quoted code, unsure goes to the fixer, fixes need full evidence', async () => {
  const fake = label => {
    if (label.startsWith('hunt')) return { findings: [finding('a.py', 10, 'one'), finding('a.py', 20, 'two'), finding('b.py', 5, 'three', { files: ['b.py'] })] }
    if (label.startsWith('verify')) return { results: [
      { key: 'a.py::one', verdict: 'refuted', evidence: 'looks fine' },
      { key: 'a.py::two', verdict: 'refuted', evidence: 'a.py:22 WHERE status=queued' },
      { key: 'b.py::three', verdict: 'confirmed', evidence: 'b.py:5' },
    ] }
    if (label.startsWith('fix')) return { results: [
      { key: 'a.py::one', status: 'fixed', failed_before: true, passes_after: 3, fails_without_fix: true },
      { key: 'b.py::three', status: 'fixed', failed_before: true, passes_after: 1 },
    ] }
  }
  const { result, calls } = await run(base, fake)
  assert.deepEqual(result.rejected.map(r => r.key), ['a.py::two'])
  assert.deepEqual(result.unproven.map(f => f.key), ['a.py::one'], 'a refute without a quote is not a refute')
  const st = Object.fromEntries(result.fix_results.map(r => [r.key, r.status]))
  assert.equal(st['a.py::one'], 'fixed')
  assert.equal(st['b.py::three'], 'unchecked', 'a fix without the full evidence is not accepted')
  assert.equal(calls.filter(c => c.label.startsWith('fix')).length, 2, 'one fixer per file group')
})

test('hot machines go to design, not to fixers', async () => {
  const fake = label => {
    if (label.startsWith('hunt')) return { findings: [finding('a.py', 10, 'one')] }
    if (label.startsWith('verify')) return { results: [{ key: 'a.py::one', verdict: 'confirmed', evidence: 'a.py:10' }] }
    if (label.endsWith(':plan')) return { machine: 'm1', plan: 'merge' }
    if (label.startsWith('design')) return 'critique'
    if (label.startsWith('fix')) throw new Error('should not fix a held machine')
  }
  const { result } = await run({ ...base, hot: ['m1'] }, fake)
  assert.equal(result.design.length, 1)
  assert.equal(result.held_for_design.length, 1)
})

test('caveman and ponytail at ultra are required in every agent, even with a custom preamble', async () => {
  const fake = label => {
    if (label.startsWith('hunt')) return { findings: [finding('a.py', 10, 'one')] }
    if (label.startsWith('verify')) return { results: [{ key: 'a.py::one', verdict: 'confirmed', evidence: 'a.py:10' }] }
    if (label.endsWith(':plan')) return { machine: 'm1', plan: 'merge' }
    if (label.startsWith('design')) return 'critique'
  }
  const { calls } = await run({ ...base, lean: false, preamble: 'HELLO', hot: ['m1'] }, fake)
  assert.ok(calls.length >= 5)
  for (const c of calls) {
    assert.match(c.prompt, /^REQUIRED before anything else: call the Skill tool with skill "caveman" \(args "ultra"\), then skill "ponytail" \(args "ultra"\)/, c.label)
    assert.match(c.prompt, /HELLO/, c.label)
  }
})
