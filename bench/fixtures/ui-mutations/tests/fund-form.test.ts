import assert from 'node:assert/strict';
import { test } from 'node:test';
import { FakeServer } from '../src/api/fake-server.ts';
import { QueryClient } from '../src/lib/query-client.ts';
import { FundFormController, changes, toDraft } from '../src/screens/fund-form.ts';
import { settle } from './helpers.ts';

function setup() {
  const api = new FakeServer();
  const form = new FundFormController(api, new QueryClient());
  return { api, form };
}

test('opens a fund into a draft', async () => {
  const { api, form } = setup();
  const fund = api.seedFund({ name: 'Growth I', targetSize: 250_000_000 });
  await form.open(fund.id);
  assert.equal(form.loading, false);
  assert.deepEqual(form.draft, toDraft(fund));
  assert.equal(form.canSave, false);
});

test('edit and save sends only the changed fields', async () => {
  const { api, form } = setup();
  const fund = api.seedFund({ name: 'Growth I' });
  await form.open(fund.id);
  form.update('name', 'Growth II');
  assert.deepEqual(changes(form.fund!, form.draft!), { name: 'Growth II' });
  form.submit();
  assert.equal(form.canSave, false);
  await settle();
  assert.equal(form.fund?.name, 'Growth II');
  assert.equal(form.fund?.version, 2);
  assert.equal(form.dirty, false);
});

test('invalid fields block the save', async () => {
  const { api, form } = setup();
  const fund = api.seedFund({ name: 'Growth I' });
  await form.open(fund.id);
  form.update('targetSize', '-5');
  form.submit();
  assert.deepEqual(form.fieldErrors, { targetSize: 'Enter a positive amount' });
  assert.equal(form.save.state.status, 'idle');
  form.update('targetSize', '5');
  assert.deepEqual(form.fieldErrors, {});
});

test('a conflict shows the server message', async () => {
  const { api, form } = setup();
  const fund = api.seedFund({ name: 'Growth I' });
  await form.open(fund.id);
  await api.updateFund(fund.id, { notes: 'someone else' }, 1);
  form.update('name', 'Mine');
  form.submit();
  await settle();
  assert.equal(form.errorMessage, 'This fund was changed by someone else. Reload it.');
  assert.equal(form.dirty, true);
});

test('discard goes back to the saved values', async () => {
  const { api, form } = setup();
  const fund = api.seedFund({ name: 'Growth I' });
  await form.open(fund.id);
  form.update('notes', 'draft note');
  form.discard();
  assert.deepEqual(form.draft, toDraft(fund));
  assert.equal(form.dirty, false);
});

test('a missing fund shows a load error', async () => {
  const { form } = setup();
  await form.open('fund-404');
  assert.equal(form.loadError, 'Fund fund-404 not found');
  assert.equal(form.loading, false);
});
