#!/usr/bin/env python3
"""Classify a task description into a bench domain + recommended requirements filter.

Rule-based (no network). Prints JSON:
  {"domain": "coding-implement", "requirements": ["coding-implement"], "kind": "implement"}
Domains mirror the benchmarks table in the ledger; kind is one of
implement / verify / research / docs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

RULES = [
    ("verify",     r"テスト|検証|verify|review|audit|check|監査|レビュー|テストして"),
    ("research",   r"調査|リサーチ|research|compare|比較|evaluate|評価"),
    ("docs",       r"文書|ドキュメント|docs|documentation|README|guide|ガイド|記事"),
    ("implement",  r"実装|作成|実行|build|implement|create|fix|修正|追加|add|refactor|リファクタ"),
]
DOMAIN_BY_KIND = {
    "implement": ("coding-implement", ["coding-implement"]),
    "verify":    ("coding-verify",    ["coding-verify", "coding-implement"]),
    "research":  ("coding-implement", []),
    "docs":      ("coding-implement", []),
}


def classify(text: str) -> dict:
    for kind, pattern in RULES:
        if re.search(pattern, text, re.IGNORECASE):
            domain, reqs = DOMAIN_BY_KIND[kind]
            return {"kind": kind, "domain": domain, "requirements": reqs}
    domain, reqs = DOMAIN_BY_KIND["implement"]
    return {"kind": "implement", "domain": domain, "requirements": reqs}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="+")
    args = parser.parse_args()
    print(json.dumps(classify(" ".join(args.text)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
