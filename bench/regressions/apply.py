#!/usr/bin/env python3
"""The re-check scenario: a small change lands in two apps, each turning correct code into a bug.

  apply.py <workdir>   edits <workdir>/jobs-queue and <workdir>/ui-flows (copies made by prepare.sh) and commits each.
The answer key for the two new bugs is bench/truth/regressions.json.
"""

import subprocess
import sys
from pathlib import Path

CHANGES = {
    "jobs-queue": (
        "app/services/batches.py",
        """    result = db.execute(
        update(Batch)
        .where(Batch.id == batch_id, Batch.status == BatchStatus.OPEN)
        .values(status=final, finished_at=utcnow())
    )
    if result.rowcount == 1 and batch.callback_url:
        _queue_callback(db, batch, final, succeeded, dead)
""",
        """    batch.status = final
    batch.finished_at = utcnow()
    if batch.callback_url:
        _queue_callback(db, batch, final, succeeded, dead)
""",
        "Close batches through the loaded row",
    ),
    "ui-flows": (
        "src/flows/job-poller.ts",
        """  stop(): void {
    this.generation++;
    this.polling = false;
""",
        """  stop(): void {
    this.polling = false;
""",
        "Simplify stop(): watch() already starts a new generation",
    ),
}


def main(work: Path) -> None:
    for app, (path, old, new, msg) in CHANGES.items():
        f = work / app / path
        text = f.read_text()
        if new in text and old not in text:
            continue  # already applied
        assert text.count(old) == 1, f"{app}: expected the original code once"
        f.write_text(text.replace(old, new))
        git = ["git", "-C", str(work / app), "-c", "user.name=bench", "-c", "user.email=bench@example.com", "-c", "commit.gpgsign=false"]
        subprocess.run([*git, "commit", "-qam", msg], check=True)
        print(app, subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip())


if __name__ == "__main__":
    main(Path(sys.argv[1]))
