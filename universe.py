"""universe.py — load the S&P 500 list (bundled CSV; --refresh to update)."""

import sys
import csv
import urllib.request

import config


def load() -> list[dict]:
    out = []
    if not config.CONSTITUENTS_CSV.exists():
        print(f"[universe] constituents CSV not found at {config.CONSTITUENTS_CSV} "
              "(checked repo root and data/). Sector will fall back to yfinance's field.")
        return out
    with open(config.CONSTITUENTS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sym = (row.get("Symbol") or "").strip()
            if not sym:
                continue
            out.append({
                "ticker": sym.replace(".", "-"),     # BRK.B -> BRK-B for yfinance
                "name": (row.get("Security") or "").strip(),
                "sector": (row.get("GICS Sector") or "").strip(),
                "industry": (row.get("GICS Sub-Industry") or "").strip(),
            })
    return out


def refresh():
    data = urllib.request.urlopen(config.CONSTITUENTS_URL, timeout=30).read().decode()
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    open(config.CONSTITUENTS_CSV, "w", encoding="utf-8").write(data)
    print(f"Refreshed ({data.count(chr(10))} lines)")


if __name__ == "__main__":
    if "--refresh" in sys.argv:
        refresh()
    rows = load()
    print(f"{len(rows)} constituents. First 5:", [r["ticker"] for r in rows[:5]])
