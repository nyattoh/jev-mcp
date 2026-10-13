#!/usr/bin/env python3
"""Rank live-catalogue candidates by performance and cost using the bench ledger.

Reads the SQLite bench ledger and a capabilities JSON (T3 orchestrator_capabilities
shape: {"providers": [{"providerInstanceId", "displayName", "models": [{"id",
"label", "options": [...]}]}]}). Returns ALL live models with effort options;
models present in the ledger carry benchmark evidence, the rest are marked
unknown. Ranking: known candidates first by score/cost efficiency (measured
beats external), unknown candidates after, preserving catalogue order.
Read-only: the ledger is never modified.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

LEDGER_DEFAULT = r"D:/develop/works/bench-ledger-engine/bench_ledger.db"

EFFORT_KEYS = ("effort", "reasoningEffort", "reasoning_effort", "thinking", "reasoning")


def load_ledger(db_path: str) -> dict[str, dict]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT slug, vendor, in_price, out_price, notes FROM models").fetchall()
        scores = conn.execute(
            "SELECT model, bench, score, source, recorded_at FROM scores").fetchall()
        domains = conn.execute("SELECT name, domain FROM benchmarks").fetchall()
    finally:
        conn.close()
    ledger = {r[0]: {"vendor": r[1], "in_price": r[2], "out_price": r[3],
                     "notes": r[4], "scores": []} for r in rows}
    for model, bench, score, source, recorded_at in scores:
        if model in ledger:
            ledger[model]["scores"].append(
                {"bench": bench, "score": score, "source": source, "recorded_at": recorded_at})
    return ledger, {r[0]: r[1] for r in domains}


def extract_efforts(model: dict) -> list[str]:
    for option in model.get("options") or []:
        if not isinstance(option, dict):
            continue
        if option.get("id") in EFFORT_KEYS and option.get("type") == "select":
            return [o["id"] for o in option.get("options", []) if isinstance(o, dict) and o.get("id")]
    # effort list given directly (common shorthand)
    if isinstance(model.get("efforts"), list):
        return [e for e in model["efforts"] if isinstance(e, str)]
    # single-choice style values
    values = model.get("values") or model.get("choices")
    if isinstance(values, list):
        return [v["id"] for v in values if isinstance(v, dict) and v.get("id")]
    return []


def load_live_models(capabilities) -> list[dict]:
    if isinstance(capabilities, list):
        providers = [p for p in capabilities if isinstance(p, dict)]
    elif isinstance(capabilities, dict):
        raw = capabilities.get("providers")
        if raw is None:
            raw = capabilities.get("capabilities")
        if raw is None and isinstance(capabilities.get("models"), list):
            raw = [{"providerInstanceId": "unknown", "models": capabilities["models"]}]
        providers = raw if isinstance(raw, list) else []
    else:
        providers = []
    live = []
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        instance = provider.get("providerInstanceId") or provider.get("id") or provider.get("name")
        if not instance:
            continue
        display = provider.get("displayName") or provider.get("name") or instance
        for model in provider.get("models") or []:
            if isinstance(model, str):
                model = {"id": model}
            if not isinstance(model, dict):
                continue
            model_id = model.get("id") or model.get("model") or model.get("name")
            if not model_id:
                continue
            efforts = extract_efforts(model)
            if not efforts:
                efforts = ["default"]
            live.append({"providerInstanceId": instance, "provider": display,
                         "model": model_id, "label": model.get("label") or model_id,
                         "efforts": efforts})
    return live


def evidence(row: dict | None, requirements: list[str], domains: dict[str, str]) -> dict | None:
    if row is None:
        return None
    def matches(s: dict) -> bool:
        if not requirements:
            return True
        return s["bench"] in requirements or domains.get(s["bench"]) in requirements
    scores = [s for s in row["scores"] if matches(s)]
    if requirements and not scores:
        return None
    ordered = sorted(scores or row["scores"],
                     key=lambda s: (s["source"] != "measured", -(s["score"] or 0)))
    best = ordered[0] if ordered else None
    return {"best_score": best["score"] if best else None,
            "best_source": best["source"] if best else None,
            "scores": ordered}


def rank(candidates: list[dict]) -> list[dict]:
    def efficiency(c: dict) -> tuple:
        bench, cost = c.get("benchmark"), c["cost"]["output"]
        if bench is None or bench.get("best_score") is None:
            return (0, 0.0, 0.0)          # unknown evidence ranks after known
        score = float(bench["best_score"])
        value = score / float(cost) if cost and cost > 0 else score
        measured_bonus = 1.0 if bench.get("best_source") == "measured" else 0.0
        return (1, value + measured_bonus, score)
    candidates.sort(key=efficiency, reverse=True)
    for index, c in enumerate(candidates, start=1):
        c["rank"] = index
    return candidates


def build(ledger: dict, domains: dict[str, str], live: list[dict],
          requirements: list[str]) -> list[dict]:
    out = []
    for entry in live:
        row = ledger.get(entry["model"])
        ev = evidence(row, requirements, domains)
        known = ev is not None
        out.append({"providerInstanceId": entry["providerInstanceId"], "provider": entry["provider"],
                    "model": entry["model"], "label": entry["label"], "efforts": entry["efforts"],
                    "cost": {"input": row["in_price"] if row else None,
                             "output": row["out_price"] if row else None},
                    "benchmark": ev if known else None,
                    "evidence": "ledger" if known else "unknown",
                    "vendor": row["vendor"] if row else None,
                    "notes": row["notes"] if row else None})
    return rank(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capabilities", nargs="?", help="capabilities JSON file path; '-' reads stdin")
    parser.add_argument("--ledger", default=LEDGER_DEFAULT)
    parser.add_argument("--requirements", nargs="*", default=[])
    parser.add_argument("--max-results", type=int, default=20)
    args = parser.parse_args()
    try:
        if args.capabilities in (None, "-"):
            capabilities = json.load(sys.stdin)
        else:
            capabilities = json.loads(Path(args.capabilities).read_text(encoding="utf-8"))
        ledger, domains = load_ledger(args.ledger)
        candidates = build(ledger, domains, load_live_models(capabilities), args.requirements)
        if not candidates:
            print(json.dumps({"error": "no_live_models_with_effort"}, ensure_ascii=False))
            return 2
        print(json.dumps({"candidates": candidates[:args.max_results],
                          "count": min(len(candidates), args.max_results),
                          "policy": "performance-max cost-min; ledger evidence ranks before unknown"},
                         ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
