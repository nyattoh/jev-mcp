#!/usr/bin/env python3
"""Record a measured run into the bench ledger (the write path of the loop).

Usage (from a completed delegated task):
  python record.py --model gpt-6-luna --bench micro-implement --score 100 \
      --cost-per-task 0.42 --notes "TRAJEXA auth flow, passed 12/12"

--score 0 with --failure records a failed run (score 0, noted).
Models/benchmarks are created on first use; scores use source=measured so they
outrank external evidence in candidate ranking.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sqlite3

LEDGER_DEFAULT = r"D:/develop/works/bench-ledger-engine/bench_ledger.db"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", default=LEDGER_DEFAULT)
    parser.add_argument("--model", required=True)
    parser.add_argument("--bench", required=True)
    parser.add_argument("--score", required=True, type=float, help="0-100 task success score")
    parser.add_argument("--domain", default="coding-implement")
    parser.add_argument("--cost-per-task", type=float, default=None)
    parser.add_argument("--effort", default=None)
    parser.add_argument("--vendor", default=None, help="vendor for auto-created model rows")
    parser.add_argument("--notes", default=None)
    parser.add_argument("--failure", action="store_true")
    args = parser.parse_args()

    score = 0.0 if args.failure else args.score
    note_parts = []
    if args.effort:
        note_parts.append(f"effort={args.effort}")
    if args.cost_per_task is not None:
        note_parts.append(f"cost_per_task=${args.cost_per_task}")
    if args.failure:
        note_parts.append("FAILED RUN")
    if args.notes:
        note_parts.append(args.notes)

    conn = sqlite3.connect(args.ledger)
    try:
        known = conn.execute("SELECT 1 FROM models WHERE slug = ?", (args.model,)).fetchone()
        if known is None and not args.vendor:
            # An "unknown" vendor would make every new model look like one family to G3.
            print(json.dumps({"ok": False, "error": "vendor_required_for_new_model"}))
            return 2
        conn.execute("INSERT OR IGNORE INTO models (slug, vendor) VALUES (?, ?)",
                     (args.model, args.vendor))
        conn.execute("INSERT OR IGNORE INTO benchmarks (name, domain) VALUES (?, ?)",
                     (args.bench, args.domain))
        conn.execute(
            "INSERT OR REPLACE INTO scores (model, bench, score, source, recorded_at) "
            "VALUES (?, ?, ?, 'measured', ?)",
            (args.model, args.bench, score,
             datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        if note_parts:
            existing = conn.execute("SELECT notes FROM models WHERE slug = ?",
                                    (args.model,)).fetchone()[0]
            merged = (existing + " | " if existing else "") + " ".join(note_parts)
            conn.execute("UPDATE models SET notes = ? WHERE slug = ?", (merged, args.model))
        conn.commit()
        row = conn.execute(
            "SELECT model, bench, score, source, recorded_at FROM scores "
            "WHERE model = ? AND bench = ?", (args.model, args.bench)).fetchone()
        print(json.dumps({"recorded": {"model": row[0], "bench": row[1],
                                       "score": row[2], "source": row[3],
                                       "recorded_at": row[4]}}, ensure_ascii=False))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
