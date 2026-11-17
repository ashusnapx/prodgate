# documents

A document store for project data rooms. Users upload files into a project; an external reader service extracts their text; users can search the text, re-read a document, withdraw it and restore it. Built with FastAPI and SQLAlchemy on SQLite.

## Concepts

- **Organisation**: every user route takes `X-Org-Id` (and `X-User-Id` for uploads). An organisation sees and changes only its own projects, documents and readings.
- **Project**: has a short `code` (used in URLs) and a display name. Documents belong to a project by its code.
- **Document**: an uploaded file. Status is `processing` while a reading is running, `ready` once it has a current reading, `failed` if its first reading failed, or `withdrawn`.
- **Reading**: one pass of the reader over a document (`running`, `done`, `failed` or `superseded`). A document has at most one current reading; listings, search and `GET /documents/{id}/reading` use it.

## Flows

- **Upload** `POST /projects/{code}/documents?filename=...` with the file as the body and its `Content-Type`. Text, Markdown, CSV, JSON and PDF up to 20 MB. A file whose content is already live in the project (same SHA-256) returns the existing document with `duplicate: true` instead of a second copy; withdrawn copies don't count. A new upload starts reading 1 and sends the file to the reader.
- **Reader callbacks** (`Authorization: Bearer <reader token>`): `POST /internal/readings/{id}/result {text, page_count}` or `.../error {error}`. Callbacks may be repeated or arrive late; each reading ends once. When a reading finishes it becomes the current reading and the document is ready. When it fails, the previous reading (if any) stays current.
- **Re-read** `POST /documents/{id}/reread` starts a new reading of a ready or failed document. The old reading stays current until the new one finishes. One reading runs at a time.
- **Expire** `POST /internal/readings/expire` (cron, every 5 minutes) fails readings the reader has not answered within 30 minutes, so the document can be re-read.
- **Withdraw** `POST /documents/{id}/withdraw` hides a document from listings, search, downloads and its current-reading route. It stays withdrawn until restored. Withdrawn documents are listed with `?include_withdrawn=true`.
- **Restore** `POST /documents/{id}/restore` puts a withdrawn document back in its project with its current reading.
- **Rename** `PATCH /projects/{code} {code, name}` changes a project's code and name; all its documents move with it.
- **Search** `GET /projects/{code}/search?q=` matches the current reading text of the project's ready documents.

Errors come back as Problem Details JSON (`404` not found, `409` wrong state, `422` bad upload).

## Running

```
./run_tests.sh
```
