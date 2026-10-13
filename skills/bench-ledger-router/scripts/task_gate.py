#!/usr/bin/env python3
"""Task-graph gate: machine-enforced rules for the bench-ledger router protocol.

Checks a task-graph state file (JSON) against the protocol and exits non-zero
with a machine-readable verdict when a rule is violated. Use it AFTER each
implement/verify pair completes (or claims to complete).

State file shape:
{
  "tasks": [
    {"id": "t1", "kind": "implement", "model": "gpt-6.1-sol", "vendor": "openai",
     "status": "done", "artifact": "path/or/null", "domain": "coding-implement",
     "cost_usd": 0.65},
    {"id": "t2", "kind": "verify", "model": "claude-sonnet-5-5", "vendor": "anthropic",
     "status": "done", "verdict": "pass", "verifies": "t1", "cost_usd": 0.30}
  ],
  "budget_usd": 5.0
}

Rules enforced (exit 3 on violation):
  G1  every implement task with status=done has a non-null artifact
  G2  every implement task has a verify task with verdict in {pass}
      (fail/needs_review/missing -> not done)
  G3  implement.vendor != verify.vendor for every pair (systematic diversity)
  G4  sum(cost_usd) <= budget_usd when budget_usd is present
Exit 0 = graph may be reported as complete.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state", type=Path)
    parser.add_argument("--budget-usd", type=float, default=None)
    args = parser.parse_args()
    try:
        state = json.loads(args.state.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"ok": False, "violations": [f"state file unreadable: {exc}"]}))
        return 3
    tasks = state.get("tasks") or []
    violations: list[str] = []

    impls = [t for t in tasks if t.get("kind") == "implement"]
    verifies = [t for t in tasks if t.get("kind") == "verify"]

    # G1 artifacts
    for t in impls:
        if t.get("status") == "done" and not t.get("artifact"):
            violations.append(f"G1: implement task {t.get('id')} has status=done but no hand-over artifact")

    # G2 every implement verified with pass
    verdict_by_target = {}
    for v in verifies:
        verdict_by_target.setdefault(v.get("verifies"), []).append(v)
    for t in impls:
        vs = verdict_by_target.get(t.get("id")) or []
        if not vs:
            violations.append(f"G2: implement task {t.get('id')} has no verify task")
            continue
        if not any((v.get("verdict") == "pass") for v in vs):
            verdicts = ", ".join(str(v.get("verdict")) for v in vs)
            violations.append(f"G2: implement task {t.get('id')} not passing (verdicts: {verdicts})")

    # G3 vendor diversity
    vendor_of = {t.get("id"): t.get("vendor") for t in tasks}
    for v in verifies:
        target = v.get("verifies")
        if target in vendor_of and vendor_of.get(target) and v.get("vendor"):
            if vendor_of[target] == v["vendor"]:
                violations.append(
                    f"G3: verify task {v.get('id')} ({v['vendor']}) same vendor as implement {target}")

    # G4 budget
    budget = args.budget_usd if args.budget_usd is not None else state.get("budget_usd")
    if budget is not None:
        total = sum(float(t.get("cost_usd") or 0) for t in tasks)
        if total > float(budget):
            violations.append(f"G4: total cost ${total:.2f} exceeds budget ${float(budget):.2f}")

    verdict = {"ok": not violations, "violations": violations,
               "counts": {"implement": len(impls), "verify": len(verifies)}}
    print(json.dumps(verdict, ensure_ascii=False))
    return 0 if not violations else 3


if __name__ == "__main__":
    raise SystemExit(main())
