import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Mutation } from '../src/lib/mutation.ts';
import { QueryClient } from '../src/lib/query-client.ts';
import { deferred, settle } from './helpers.ts';

test('mutation moves pending -> success and keeps data', async () => {
  const m = new Mutation({ mutationFn: async (n: number) => n * 2 });
  const run = m.mutateAsync(21);
  assert.equal(m.isPending, true);
  assert.equal(await run, 42);
  assert.deepEqual([m.state.status, m.state.data], ['success', 42]);
});

test('mutation error state and reset', async () => {
  const m = new Mutation({ mutationFn: async () => Promise.reject(new Error('nope')) });
  await assert.rejects(m.mutateAsync(undefined), /nope/);
  assert.equal(m.isError, true);
  m.reset();
  assert.deepEqual(m.state, { status: 'idle', data: undefined, error: null, variables: undefined });
});

test('per-call callbacks run only for the latest call; hook callbacks run for every call', async () => {
  const gates = [deferred(), deferred()];
  const hookCalls: number[] = [];
  const m = new Mutation({
    mutationFn: async (i: number) => {
      await gates[i].promise;
      return i;
    },
    onSuccess: (data) => {
      hookCalls.push(data);
    },
  });
  const perCall: number[] = [];
  m.mutate(0, { onSuccess: (d) => perCall.push(d) });
  m.mutate(1, { onSuccess: (d) => perCall.push(d) });
  gates[0].resolve();
  gates[1].resolve();
  await settle();
  assert.deepEqual(hookCalls, [0, 1]);
  assert.deepEqual(perCall, [1]);
  assert.equal(m.state.data, 1);
});

test('query client dedupes in-flight fetches and notifies on write', async () => {
  const client = new QueryClient();
  let calls = 0;
  const fetcher = async () => ++calls;
  const [a, b] = await Promise.all([client.fetchQuery(['x'], fetcher), client.fetchQuery(['x'], fetcher)]);
  assert.deepEqual([a, b, calls], [1, 1, 1]);
  let seen = 0;
  client.subscribe(['x'], () => seen++);
  client.setQueryData<number>(['x'], (old = 0) => old + 10);
  assert.deepEqual([client.getQueryData(['x']), seen], [11, 1]);
});

test('invalidateQueries refetches watched queries under a prefix', async () => {
  const client = new QueryClient();
  let version = 0;
  await client.fetchQuery(['docs', 'inbox'], async () => ++version);
  client.subscribe(['docs', 'inbox'], () => {});
  await client.invalidateQueries(['docs']);
  assert.equal(client.getQueryData(['docs', 'inbox']), 2);
});
