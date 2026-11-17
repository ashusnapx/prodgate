# Deal workspace UI flows

Client-side state for four interactive pieces of an investment team's web app,
written as plain TypeScript classes so they can be tested without a browser.
The view layer (not included) renders their fields and calls their methods.
`src/api.ts` is an in-memory stand-in for the HTTP API with the same rules as
the real server.

No npm dependencies. `./run_tests.sh` runs the suite with `node --test`
(Node 22.18+ runs the TypeScript directly).

## Job status chip (`JobPoller`)

Imports and model runs are background jobs. `watch(jobId)` checks the job
every two seconds and shows a label (waiting, running with progress, finished,
failed, cancelled). Polling stops by itself once the job has finished, failed
or been cancelled, and calls `onFinished`. A status check that fails because of
the network or a 5xx answer is simply tried again on the next tick; a 404 means
the job is gone, so the chip shows the error and stops. Watching another job,
or `stop()`, drops the old one.

## Add investment wizard (`InvestmentWizard`)

Three steps (Company, Terms, Review) in a side sheet. One wizard instance
serves every fund: `open(fundId)` starts a fresh wizard for a different fund
and keeps progress if the same fund is reopened. Next validates the current
step. Back never validates. The stepper at the top lets the user jump to any
step they have already reached. Submit on the Review step creates the
investment; a double click creates it once.

## Scenario bar (`ScenarioBar`)

Above the returns model. Shows which saved scenario is open and whether there
are unsaved edits. Save writes into the open scenario (refused if someone else
saved it since it was opened) or creates a new one. Open loads a saved
scenario; if there are unsaved edits it asks first (`confirmDiscard`). Reset
starts a fresh, untitled scenario from the default inputs, so the next Save
creates a new scenario.

## Upload tray (`UploadQueue`)

Files dropped on the data room upload two at a time (create session, send
bytes, complete). A failed file stays in the tray with its error and a Retry
button. The tray keeps its files in a store (IndexedDB in the app) so that
after a reload or crash every file that has not finished uploading is still
there and uploads again. Clear finished removes the completed rows.
