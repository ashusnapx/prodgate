"""ledger.py: scope, coverage, seen keys, streaks and the noise budget, on a throwaway repo."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / "skills/prodgate/bin/ledger.py"


class Ledger(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.dir.name) / "repo"
        self.repo.mkdir()
        self.env = {**os.environ, "PRODGATE_HOME": str(Path(self.dir.name) / "qa")}
        self.git("init", "-q")
        self.commit({"app/jobs.py": "x = 1\n", "tests/test_jobs.py": "pass\n"})

    def tearDown(self):
        self.dir.cleanup()

    def git(self, *a):
        cfg = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
        return subprocess.run(["git", *cfg, *a], cwd=self.repo, check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, files):
        for name, text in files.items():
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / name).write_text(text)
        self.git("add", "-A")
        self.git("commit", "-qm", "c")
        return self.git("rev-parse", "HEAD")

    def run_l(self, *a):
        out = subprocess.run([sys.executable, str(LEDGER), *a], cwd=self.repo, env=self.env, check=True, capture_output=True, text=True).stdout
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return out

    def record(self, **r):
        f = Path(self.dir.name) / "round.json"
        f.write_text(json.dumps(r))
        return self.run_l("record-round", str(f))

    def test_first_run_scopes_source_only(self):
        s = self.run_l("scope")
        self.assertTrue(s["first_run"])
        self.assertEqual(s["changed"], ["app/jobs.py"])

    def test_unchanged_code_has_empty_scope(self):
        sha = self.git("rev-parse", "HEAD")
        self.record(sha=sha, scope=["app/jobs.py"])
        s = self.run_l("scope")
        self.assertEqual((s["changed"], s["unreviewed"]), ([], []))

    def test_only_the_diff_comes_back(self):
        sha = self.git("rev-parse", "HEAD")
        self.record(sha=sha, scope=["app/jobs.py"])
        self.commit({"app/billing.py": "y = 2\n"})
        s = self.run_l("scope")
        self.assertEqual(s["changed"], ["app/billing.py"])
        self.assertEqual(s["base"], sha)

    def test_streak_makes_a_machine_hot_after_three_rounds(self):
        sha = self.git("rev-parse", "HEAD")
        for i in range(3):
            self.record(sha=sha, scope=[], machines=["jobs"], confirmed=[{"key": f"k{i}", "machine": "jobs", "kind": "race"}])
        self.assertEqual(self.run_l("hot"), ["jobs"])
        self.record(sha=sha, scope=[], machines=["jobs"], confirmed=[])
        self.assertEqual(self.run_l("hot"), [])

    def test_noise_budget_marks_a_mostly_refuted_kind(self):
        sha = self.git("rev-parse", "HEAD")
        self.record(sha=sha, scope=[], confirmed=[{"key": "a", "kind": "race"}], rejected=[{"key": "b", "kind": "race"}, {"key": "c", "kind": "race"}], not_reproduced=[{"key": "d", "kind": "race"}])
        self.assertEqual(self.run_l("strict"), ["race"])
        self.assertEqual(sorted(self.run_l("seen")), ["a", "b", "c", "d"])


if __name__ == "__main__":
    unittest.main()
