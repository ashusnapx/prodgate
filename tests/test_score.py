"""score.py: matching findings to the answer key."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
KEY = {
    "app": "demo",
    "bugs": [
        {"id": "d-1", "class": "race", "file": "app/jobs.py", "lines": [40, 50], "function": "claim", "summary": "double claim", "repro": "", "severity": "high"},
        {"id": "d-2", "class": "stuck", "file": "app/jobs.py", "lines": [90, 100], "function": "lease", "summary": "stuck running", "repro": "", "severity": "high"},
    ],
    "decoys": [{"id": "d-d1", "file": "app/queue.py", "lines": [10, 20], "why_correct": "rowcount checked"}],
}


class Score(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        Path(cls.dir.name, "demo.json").write_text(json.dumps(KEY))
        os.environ["BENCH_TRUTH"] = cls.dir.name
        import score

        cls.score = score
        score.TRUTH = Path(cls.dir.name)

    def test_line_window_function_name_decoys_and_duplicates(self):
        findings = [
            {"file": "/tmp/x/demo/app/jobs.py", "line": 55, "bug": "two workers claim one job"},  # within 10 lines of d-1
            {"file": "app/jobs.py", "line": 45, "bug": "same double claim again"},  # duplicate of d-1
            {"file": "app/jobs.py", "line": 300, "function": "Jobs.lease", "bug": "lease never expires"},  # matches d-2 by function
            {"file": "app/queue.py", "line": 12, "bug": "race on update"},  # decoy
            {"file": "app/other.py", "line": 1, "bug": "something else"},  # unmatched
        ]
        s = self.score.score("demo", findings, None, {"demo": {"4": True}})
        self.assertEqual(s["found_ids"], ["d-1", "d-2"])
        self.assertEqual((s["duplicates"], s["decoy_hits"], s["real_unseeded"], s["false_positives"]), (1, 1, 1, 1))
        self.assertEqual(s["precision"], 0.75)  # (2 found + 1 real) / 4 unique reports

    def test_the_judge_can_reject_a_nearby_but_different_bug(self):
        findings = [{"file": "app/jobs.py", "line": 45, "bug": "typo in log message"}]
        s = self.score.score("demo", findings, {"demo": {"0": None}}, {"demo": {}})
        self.assertEqual(s["found"], 0)


    def test_a_proven_different_bug_on_decoy_lines_is_real_not_a_decoy_hit(self):
        findings = [
            {"file": "app/queue.py", "line": 12, "bug": "claims the guarded update races"},  # decoy, unproven
            {"file": "app/queue.py", "line": 15, "bug": "a different real bug on the same lines"},  # proven by a test
        ]
        s = self.score.score("demo", findings, {"demo": {}}, {"demo": {"0": False, "1": True}})
        self.assertEqual((s["decoy_hits"], s["real_unseeded"], s["false_positives"]), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
