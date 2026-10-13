import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import bench_candidates  # noqa: E402
import classify_task  # noqa: E402


def run(script, *args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], input=stdin,
                          capture_output=True, text=True)


class ClassifyTask(unittest.TestCase):
    def test_english_keywords_match_whole_words_only(self):
        self.assertEqual(classify_task.classify("add a checkout flow")["kind"], "implement")
        self.assertEqual(classify_task.classify("check the login flow")["kind"], "verify")
        self.assertEqual(classify_task.classify("prefix the addresses")["kind"], "implement")


class Rank(unittest.TestCase):
    def test_unpriced_scores_rank_after_priced_ones(self):
        priced = {"model": "priced", "cost": {"output": 10.0},
                  "benchmark": {"best_score": 50.0, "best_source": "external"}}
        unpriced = {"model": "unpriced", "cost": {"output": None},
                    "benchmark": {"best_score": 90.0, "best_source": "measured"}}
        unknown = {"model": "unknown", "cost": {"output": 1.0}, "benchmark": None}
        ranked = bench_candidates.rank([unknown, unpriced, priced])
        self.assertEqual([c["model"] for c in ranked], ["priced", "unpriced", "unknown"])


class TaskGate(unittest.TestCase):
    def gate(self, verify_extra):
        state = {"tasks": [
            {"id": "t1", "kind": "implement", "vendor": "openai", "status": "done", "artifact": "a.diff"},
            {"id": "t2", "kind": "verify", "vendor": "openai", "status": "done", "verdict": "pass",
             "verifies": "t1", **verify_extra},
        ]}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            return run("task_gate.py", str(path))

    def test_same_vendor_fails_without_the_fallback_flag(self):
        result = self.gate({})
        self.assertEqual(result.returncode, 3)
        self.assertIn("G3", result.stdout)

    def test_declared_same_vendor_fallback_passes(self):
        self.assertEqual(self.gate({"no_cross_vendor_candidate": True}).returncode, 0)


class Record(unittest.TestCase):
    def ledger(self, d):
        path = Path(d) / "ledger.db"
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE models (slug TEXT PRIMARY KEY, vendor TEXT, in_price REAL, out_price REAL, notes TEXT);
            CREATE TABLE benchmarks (name TEXT PRIMARY KEY, domain TEXT);
            CREATE TABLE scores (model TEXT, bench TEXT, score REAL, source TEXT, recorded_at TEXT,
                                 PRIMARY KEY (model, bench));
        """)
        conn.close()
        return path

    def test_new_model_requires_vendor(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = self.ledger(d)
            refused = run("record.py", "--ledger", str(ledger), "--model", "m1", "--bench", "b", "--score", "80")
            self.assertEqual(refused.returncode, 2)
            self.assertIn("vendor_required_for_new_model", refused.stdout)
            ok = run("record.py", "--ledger", str(ledger), "--model", "m1", "--bench", "b", "--score", "80",
                     "--vendor", "openai")
            self.assertEqual(ok.returncode, 0, ok.stderr)
            conn = sqlite3.connect(ledger)
            self.assertEqual(conn.execute("SELECT vendor FROM models WHERE slug='m1'").fetchone()[0], "openai")
            conn.close()


if __name__ == "__main__":
    unittest.main()
