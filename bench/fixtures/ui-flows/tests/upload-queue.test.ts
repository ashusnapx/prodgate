import assert from 'node:assert/strict';
import { test } from 'node:test';
import { FakeBackend } from '../src/api.ts';
import { MemoryStore, UploadQueue } from '../src/flows/upload-queue.ts';
import { settle } from './helpers.ts';

const file = (name: string, size = 4) => ({ name, bytes: new Uint8Array(size) });

test('uploads everything, two at a time', async () => {
  const api = new FakeBackend();
  let inFlight = 0;
  let peak = 0;
  api.before = async (op) => {
    if (op !== 'uploadBytes') return;
    peak = Math.max(peak, ++inFlight);
    await settle(2);
    inFlight--;
  };
  const queue = new UploadQueue(api, new MemoryStore());
  queue.add([file('a.pdf'), file('b.pdf'), file('c.pdf')]);
  await settle(30);
  assert.deepEqual(queue.summary, { queued: 0, uploading: 0, done: 3, failed: 0 });
  assert.equal(peak, 2);
  assert.equal(api.uploads.filter((u) => u.complete).length, 3);
});

test('a failed upload can be retried', async () => {
  const api = new FakeBackend();
  api.failNext('uploadBytes');
  const queue = new UploadQueue(api, new MemoryStore());
  queue.add([file('cim.pdf')]);
  await settle();
  assert.equal(queue.items[0].status, 'failed');
  assert.equal(queue.items[0].error, 'Service unavailable');
  queue.retry(queue.items[0].id);
  await settle();
  assert.equal(queue.items[0].status, 'done');
});

test('queued files survive a reload', () => {
  const api = new FakeBackend();
  api.before = () => new Promise(() => {});
  const store = new MemoryStore();
  const first = new UploadQueue(api, store, 1);
  first.add([file('a.pdf'), file('b.pdf')]);
  assert.ok(store.saved.some((s) => s.name === 'b.pdf' && s.status === 'queued'));
  const second = new UploadQueue(new FakeBackend(), store, 1);
  second.restore();
  assert.equal(second.items[0].name, 'b.pdf');
});

test('clear finished keeps failures', async () => {
  const api = new FakeBackend();
  api.failNext('createUploadSession');
  const queue = new UploadQueue(api, new MemoryStore());
  queue.add([file('bad.pdf'), file('good.pdf')]);
  await settle();
  queue.clearFinished();
  assert.deepEqual(
    queue.items.map((i) => i.name),
    ['bad.pdf'],
  );
});
