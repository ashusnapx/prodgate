import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiError, FakeServer } from '../src/api/fake-server.ts';
import { QueryClient } from '../src/lib/query-client.ts';
import { DocumentListController } from '../src/screens/document-list.ts';
import { ReviewPanelController, availableActions } from '../src/screens/review-panel.ts';
import { settle } from './helpers.ts';

function setup(user = 'ben') {
  const api = new FakeServer();
  const client = new QueryClient();
  const list = new DocumentListController(api, client, 'inbox', user);
  const panel = new ReviewPanelController(api, client, user);
  return { api, client, list, panel };
}

test('loads the folder newest first', async () => {
  const { api, list } = setup();
  api.seedDoc({ title: 'Old' });
  api.seedDoc({ title: 'New' });
  api.seedDoc({ title: 'Elsewhere', folder: 'archive' });
  await list.load();
  assert.deepEqual(
    list.docs.map((d) => d.title),
    ['New', 'Old'],
  );
});

test('load error is shown and cleared on retry', async () => {
  const { api, list } = setup();
  api.failNext('listDocs');
  await list.load();
  assert.equal(list.loadError, 'Something went wrong');
  await list.load();
  assert.equal(list.loadError, null);
});

test('quick add shows a pending row until the document exists', async () => {
  const { list } = setup();
  await list.load();
  list.addDocument('Board pack');
  assert.equal(list.pendingRows.length, 1);
  await settle();
  assert.deepEqual(list.pendingRows, []);
  assert.deepEqual(
    list.docs.map((d) => d.title),
    ['Board pack'],
  );
});

test('a failed quick add marks its row failed', async () => {
  const { api, list } = setup();
  api.failNext('createDoc', new ApiError(422, 'Title is required'));
  list.addDocument(' ');
  await settle();
  assert.equal(list.pendingRows[0].failed, true);
  list.dismissFailed(list.pendingRows[0].tempId);
  assert.deepEqual(list.pendingRows, []);
});

test('star toggles optimistically and sticks', async () => {
  const { api, list } = setup();
  const doc = api.seedDoc({ title: 'Model' });
  await list.load();
  list.toggleStar(doc.id);
  assert.equal(list.docs[0].starred, true);
  await settle();
  assert.equal(list.star.state.status, 'success');
  assert.equal(list.docs[0].starred, true);
});

test('delete removes the row', async () => {
  const { api, list } = setup();
  const a = api.seedDoc({ title: 'A' });
  api.seedDoc({ title: 'B' });
  await list.load();
  await list.deleteDocument(a.id);
  assert.deepEqual(
    list.docs.map((d) => d.title),
    ['B'],
  );
});

test('workflow buttons follow the document status', () => {
  const base = { id: 'd', title: 't', folder: 'f', author: 'ana', starred: false, updatedAt: 1 };
  assert.deepEqual(availableActions({ ...base, status: 'draft' }), ['submit', 'archive']);
  assert.deepEqual(availableActions({ ...base, status: 'archived' }), ['reopen']);
});

test('panel runs an action and shows history', async () => {
  const { api, list, panel } = setup('ben');
  const doc = api.seedDoc({ title: 'Memo', author: 'ana', status: 'in_review' });
  await list.load();
  list.select(doc.id);
  await panel.show(list.selected);
  panel.run('approve');
  await settle();
  assert.equal(panel.doc?.status, 'approved');
  assert.equal(list.docs[0].status, 'approved');
  await panel.show(panel.doc);
  assert.deepEqual(
    panel.activity.map((a) => a.action),
    ['approve'],
  );
});

test('panel shows the server refusal', async () => {
  const { api, panel } = setup();
  const doc = api.seedDoc({ title: 'Memo', status: 'approved' });
  await panel.show(doc);
  panel.run('submit');
  await settle();
  assert.equal(panel.actionError, 'Cannot submit a document that is approved');
});

test('bulk archive reports how many were archived', async () => {
  const { api, list, panel } = setup();
  const a = api.seedDoc({ title: 'A' });
  const b = api.seedDoc({ title: 'B', status: 'approved' });
  await list.load();
  await panel.archiveMany([a.id, b.id]);
  assert.equal(panel.notice, 'Archived 2 documents');
  assert.equal(panel.busy, false);
  assert.deepEqual(
    list.docs.map((d) => d.status),
    ['archived', 'archived'],
  );
});
