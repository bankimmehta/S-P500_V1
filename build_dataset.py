#!/usr/bin/env python3
"""
build_dataset.py — rebuild output/ from cache/, NO fetching. Use before committing
to GitHub or after a code change, without hitting Yahoo.

  python build_dataset.py
"""

import sys
import json

import config
import universe
import extract


def main():
    files = sorted(config.CACHE_DIR.glob("*.json")) if config.CACHE_DIR.exists() else []
    if not files:
        print(f"cache/ empty ({config.CACHE_DIR}). Run `python extract.py` first.")
        sys.exit(1)

    meta_by_ticker = {r["ticker"]: r for r in universe.load()}
    records, skipped = {}, []
    for f in files:
        try:
            rec = json.load(open(f, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            skipped.append((f.name, str(e))); continue
        if isinstance(rec, dict) and rec.get("info") and (rec.get("income") or rec.get("balance")):
            records[f.stem] = rec
        else:
            skipped.append((f.name, "not a valid record"))

    print(f"Found {len(files)} cache files -> {len(records)} valid records.")
    for name, why in skipped[:10]:
        print(f"  skipped {name}: {why}")
    if not records:
        print("Nothing to build."); sys.exit(1)

    extract.build_workbook(records, meta_by_ticker, print)
    print("\nCommit BOTH so the deployed app can read them:")
    print(f"  git add -f output/{config.DATA_JSON} output/{config.XLSX_NAME}")
    print("  git commit -m 'Update dataset' && git push")


if __name__ == "__main__":
    main()
