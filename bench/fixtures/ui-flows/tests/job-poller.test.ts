import assert from 'node:assert/strict';
import { test } from 'node:test';
import { FakeBackend } from '../src/api.ts';
import { JobPoller } from '../src/flows/job-poller.ts';
import { ManualScheduler, settle } from './helpers.ts';

function setup() {
  const api = new FakeBackend();
  const clock = new ManualScheduler();
  return { api, clock, poller: new JobPoller(api, clock, 1000) };
}

test('polls until the job succeeds, then stops', async () => {
  const { api, clock, poller } = setup();
  api.setJob({ id: 'j1', status: 'running', progress: 0.25 });
  const finished: string[] = [];
  poller.onFinished = (job) => finished.push(job.status);
  poller.watch('j1');
  await settle();
  assert.equal(poller.label, 'Running (25%)');
  api.setJob({ id: 'j1', status: 'succeeded', progress: 1 });
  await clock.advance(1000);
  assert.equal(poller.label, 'Finished');
  assert.equal(poller.polling, false);
  assert.equal(clock.pending, 0);
  assert.deepEqual(finished, ['succeeded']);
});

test('a failed job shows its message', async () => {
  const { api, poller } = setup();
  api.setJob({ id: 'j1', status: 'failed', message: 'bad header row' });
  poller.watch('j1');
  await settle();
  assert.equal(poller.label, 'Failed: bad header row');
  assert.equal(poller.polling, false);
});

test('a missing job stops with an error', async () => {
  const { poller, clock } = setup();
  poller.watch('nope');
  await settle();
  assert.equal(poller.error, 'Job nope not found');
  assert.equal(poller.polling, false);
  assert.equal(clock.pending, 0);
});

test('watching another job drops the first', async () => {
  const { api, clock, poller } = setup();
  api.setJob({ id: 'a', status: 'running' });
  api.setJob({ id: 'b', status: 'queued' });
  poller.watch('a');
  await settle();
  poller.watch('b');
  await settle();
  await clock.advance(1000);
  assert.equal(poller.job?.id, 'b');
  assert.equal(poller.label, 'Waiting to start');
});

test('stop cancels the next check', async () => {
  const { api, clock, poller } = setup();
  api.setJob({ id: 'a', status: 'running' });
  poller.watch('a');
  await settle();
  poller.stop();
  assert.equal(clock.pending, 0);
  await clock.advance(5000);
  assert.equal(poller.polling, false);
});
