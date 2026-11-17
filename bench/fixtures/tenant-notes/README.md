# Team notes

A multi-tenant notes service. People belong to workspaces; every note lives in
exactly one workspace and is only visible to that workspace's members.
FastAPI, SQLAlchemy 2, SQLite.

## Concepts

- **Workspace**: a tenant. Members have a role: `owner`, `editor` or `viewer`.
  Viewers read; editors also write, delete, restore and share; owners also
  manage members and delete or restore the workspace.
- **Note**: title and body. Every edit sends the `base_version` it started
  from; an edit based on an older version is refused with 409 so nobody
  overwrites a colleague's change. A create can carry a client `request_id` so
  that a retried or double-clicked create returns the note that was already
  made instead of a second one.
- **Trash**: deleting a note is a soft delete. Editors can restore it from
  the workspace trash.
- **Deleting a workspace** hides it and moves all of its live notes to the
  trash together. Restoring the workspace brings back exactly those notes;
  notes that were already in the trash before stay there. While a workspace is
  deleted its content is gone for everyone, including share links.
- **Share links**: an editor can create a public read-only link to a note,
  optionally expiring after some hours. `/s/{token}` shows the note and
  `/s/{token}/raw` downloads it as Markdown. Revoking a link ends both.
- **Exports**: a member can export the whole workspace, or a chosen list of
  its notes, to one Markdown file. Exports run in the background, one at a
  time per workspace. A queued or running export can be cancelled; a
  cancelled export never produces a file.

## Auth

Requests carry `X-User-Id`. Anything outside your workspaces answers 404.

## Running

```
./run_tests.sh
uvicorn app.main:create_app --factory
```
