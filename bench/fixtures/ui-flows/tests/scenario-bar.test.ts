import assert from 'node:assert/strict';
import { test } from 'node:test';
import { FakeBackend } from '../src/api.ts';
import { DEFAULT_INPUTS, ScenarioBar } from '../src/flows/scenario-bar.ts';

const yes = async () => true;
const no = async () => false;

test('a new scenario is clean until edited', () => {
  const bar = new ScenarioBar(new FakeBackend(), yes);
  assert.equal(bar.dirty, false);
  bar.edit('exitMultiple', 12);
  assert.equal(bar.dirty, true);
  assert.equal(bar.title, 'Untitled scenario (edited)');
});

test('save creates a version, then saves into it', async () => {
  const api = new FakeBackend();
  const bar = new ScenarioBar(api, yes);
  bar.edit('holdYears', 6);
  await bar.save('Base case');
  assert.equal(bar.dirty, false);
  assert.equal(bar.title, 'Base case');
  bar.edit('holdYears', 7);
  await bar.save();
  assert.equal(api.versions.size, 1);
  assert.equal(api.versions.get(bar.openedId!)?.inputs.holdYears, 7);
  assert.equal(bar.revision, 2);
});

test('open asks before dropping edits to an opened scenario', async () => {
  const api = new FakeBackend();
  const base = await api.createVersion('Base', { ...DEFAULT_INPUTS, exitMultiple: 9 });
  const upside = await api.createVersion('Upside', { ...DEFAULT_INPUTS, exitMultiple: 14 });
  const bar = new ScenarioBar(api, no);
  await bar.open(base.id);
  bar.edit('ebitdaMargin', 0.3);
  assert.equal(await bar.open(upside.id), false);
  assert.equal(bar.openedName, 'Base');
  assert.equal(bar.inputs.ebitdaMargin, 0.3);
});

test('a conflicting save keeps the edits and shows why', async () => {
  const api = new FakeBackend();
  const base = await api.createVersion('Base', DEFAULT_INPUTS);
  const bar = new ScenarioBar(api, yes);
  await bar.open(base.id);
  await api.updateVersion(base.id, { ...DEFAULT_INPUTS, holdYears: 3 }, 1);
  bar.edit('holdYears', 8);
  await bar.save();
  assert.equal(bar.saveError, 'Someone saved this scenario after you opened it');
  assert.equal(bar.dirty, true);
});

test('reset goes back to the defaults', () => {
  const bar = new ScenarioBar(new FakeBackend(), yes);
  bar.edit('revenueGrowth', 0.2);
  bar.reset();
  assert.deepEqual(bar.inputs, DEFAULT_INPUTS);
  assert.equal(bar.dirty, false);
});
