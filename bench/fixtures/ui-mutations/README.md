# Documents and funds UI state

The client-side state for two screens of an investment team's web app, written
as plain TypeScript controllers so it can be tested without a browser. The
view layer (not included) renders whatever a controller holds and calls its
methods on clicks.

- `src/lib/` is a small data library modelled on React Query.
- `src/api/fake-server.ts` is an in-memory stand-in for the HTTP API, with the
  same rules as the real server.
- `src/screens/` holds one controller per screen part.

No npm dependencies. `./run_tests.sh` runs the suite with `node --test`
(Node 22.18+ runs the TypeScript directly).

## The data library

**QueryClient** caches server data by key (`['docs', folder]`, `['fund', id]`).
`fetchQuery` loads and caches (two callers asking at once share one request),
`setQueryData` writes the cache and notifies subscribers, and
`invalidateQueries(prefix)` refetches every watched query under a prefix.

**Mutation** wraps one kind of server write, like React Query's `useMutation`:

- Options given when the mutation is created (`onMutate`, `onSuccess`,
  `onError`, `onSettled`) run for **every** call. `onMutate` runs before the
  request and its return value is passed to the others as `context`, which is
  how optimistic updates are rolled back.
- Callbacks passed to a single call, `mutate(vars, { onSuccess, onError,
  onSettled })`, run **only for the latest call**. If `mutate` is called again
  before an earlier call settles, the earlier call's per-call callbacks are
  dropped (its request still completes and the creation-time options still run).
- `state` (`status`, `data`, `error`, `variables`) always describes the latest
  call. `isPending` is true while the latest call is in flight.
- `reset()` returns the mutation to `idle` and drops the per-call callbacks of
  any call still in flight.
- `mutate` never throws; `mutateAsync` returns a promise that rejects on error.

## Screens

**Documents table** (`DocumentListController`): the documents in one folder,
newest first. A row can be selected to open it in the side panel. Quick add
shows a "saving" row for each new title until the server has created it, or
marks the row failed. Star toggles immediately and is undone if the server
refuses. Delete removes the row.

**Review panel** (`ReviewPanelController`): the selected document, its history
and its workflow buttons. Documents go draft -> in review -> approved or sent
back; drafts, approved and sent-back documents can be archived, and archived
ones reopened. A reviewer cannot approve or send back a document they wrote.
Bulk archive archives the selected rows one by one and shows a spinner while it
works.

**Edit fund form** (`FundFormController`): one form controller serves whichever
fund is open. Editing marks the form dirty; Save sends only the changed fields
with the version it loaded, so the server refuses a save over someone else's
change. Errors from a failed save are shown above the form until the next
successful save. Discard goes back to the saved values.
