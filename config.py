"""
config.py — S&P 500 (yfinance) extractor. Sibling of nifty50_indianapi, same
shape and UX; source is yfinance, currency USD, universe the S&P 500.

Design priority: don't get blocked by Yahoo over ~500 names — permanent cache,
resumable runs, paced requests with backoff.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "cache"
OUTPUT_DIR = ROOT / "output"
LOG_DIR = ROOT / "logs"


def _resolve(*relpaths):
    """Return the first existing path among candidates; else the first (for writing).
    Lets files live either at the repo root (GUI uploads) or in subfolders."""
    cands = [ROOT / r for r in relpaths]
    for c in cands:
        if c.exists():
            return c
    return cands[0]


# Looks in the repo root first (where GitHub-GUI uploads land), then data/.
CONSTITUENTS_CSV = _resolve("sp500_constituents.csv", "data/sp500_constituents.csv")
CONSTITUENTS_URL = ("https://raw.githubusercontent.com/datasets/"
                    "s-and-p-500-companies/main/data/constituents.csv")

# anti-block knobs
REQUEST_DELAY = 1.5
REQUEST_JITTER = 1.0
MAX_RETRIES = 4
BACKOFF_BASE = 5.0
CACHE_PERMANENT = True

XLSX_NAME = "sp500_fundamentals.xlsx"
DATA_JSON = "sp500_data.json"
STATEMENT_YEARS = 5

# analysis thresholds (same philosophy as the NSE tool)
ROCE_GOOD = 15.0
ROE_GOOD = 15.0
DE_HIGH = 1.5
INT_COVER_MIN = 3.0
MIN_YEARS = 4          # US annual statements via yfinance are usually 4
