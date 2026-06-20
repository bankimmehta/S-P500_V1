"""
client.py — yfinance fetcher built to NOT get blocked over ~500 stocks.

  * permanent per-ticker JSON cache (fetch once, ever)
  * paced requests + jitter, exponential backoff/retry on errors / HTTP 429
  * empty/invalid responses NOT cached (retry next run)
  * logging (console + file)

Cached record: {ticker, info{...}, income{item:{year:val}}, balance, cashflow, fetched}
"""

import os
import time
import json
import random
import logging

import pandas as pd

import config

for noisy in ("yfinance", "urllib3", "peewee"):
    logging.getLogger(noisy).setLevel(logging.CRITICAL)

config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("sp500")
_last_call = [0.0]
_n_calls = [0]

INFO_KEYS = [
    "symbol", "longName", "sector", "industry", "currentPrice",
    "regularMarketPrice", "marketCap", "trailingPE", "forwardPE", "priceToBook",
    "priceToSalesTrailing12Months", "pegRatio", "enterpriseToEbitda",
    "enterpriseToRevenue", "returnOnEquity", "returnOnAssets", "profitMargins",
    "operatingMargins", "grossMargins", "ebitdaMargins", "revenueGrowth",
    "earningsGrowth", "revenuePerShare", "totalRevenue", "ebitda",
    "freeCashflow", "operatingCashflow", "totalCash", "totalDebt",
    "debtToEquity", "currentRatio", "quickRatio", "beta", "dividendYield",
    "payoutRatio", "trailingEps", "forwardEps", "bookValue",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "fiftyDayAverage",
    "twoHundredDayAverage", "targetMeanPrice", "targetHighPrice",
    "targetLowPrice", "recommendationMean", "recommendationKey",
    "numberOfAnalystOpinions", "sharesOutstanding", "country",
]


def configure_logging(logfile=None, level=logging.INFO):
    log.setLevel(level)
    log.handlers.clear()
    cfmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    ch = logging.StreamHandler(); ch.setFormatter(cfmt); log.addHandler(ch)
    if logfile:
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        log.addHandler(fh)


def _cache_path(ticker):
    return config.CACHE_DIR / f"{ticker}.json"


def _cached(path):
    return path.exists() if config.CACHE_PERMANENT else False


def calls_made():
    return _n_calls[0]


def _stmt_to_dict(df, years=None):
    years = years or config.STATEMENT_YEARS
    if df is None or getattr(df, "empty", True):
        return {}
    df = df.iloc[:, :years]
    out = {}
    for item, row in df.iterrows():
        vals = {}
        for col, val in row.items():
            yr = col.year if hasattr(col, "year") else str(col)
            vals[str(yr)] = None if pd.isna(val) else float(val)
        out[str(item)] = vals
    return out


def is_valid(rec):
    if not isinstance(rec, dict):
        return False
    info = rec.get("info") or {}
    has_price = any(info.get(k) for k in ("currentPrice", "regularMarketPrice", "marketCap"))
    has_stmt = any(rec.get(g) for g in ("income", "balance", "cashflow"))
    return bool(info) and has_price and has_stmt


def _pace():
    dt = time.time() - _last_call[0]
    wait = config.REQUEST_DELAY + random.uniform(0, config.REQUEST_JITTER) - dt
    if wait > 0:
        time.sleep(wait)


def _fetch_raw(ticker):
    import yfinance as yf
    tk = yf.Ticker(ticker)
    info_full = tk.get_info() or {}
    info = {k: info_full.get(k) for k in INFO_KEYS if info_full.get(k) is not None}

    def safe(getter):
        try:
            return _stmt_to_dict(getter())
        except Exception:  # noqa: BLE001
            return {}

    return {
        "ticker": ticker,
        "info": info,
        "income": safe(lambda: tk.income_stmt),
        "balance": safe(lambda: tk.balance_sheet),
        "cashflow": safe(lambda: tk.cashflow),
        "fetched": time.strftime("%Y-%m-%d"),
    }


def get_stock(ticker, refresh=False):
    cache = _cache_path(ticker)
    if not refresh and _cached(cache):
        try:
            rec = json.load(open(cache, encoding="utf-8"))
            log.info("%-7s CACHE hit", ticker)
            return rec
        except Exception:  # noqa: BLE001
            pass

    last_err = None
    for attempt in range(config.MAX_RETRIES):
        _pace()
        t0 = time.time()
        try:
            rec = _fetch_raw(ticker)
            _last_call[0] = time.time(); _n_calls[0] += 1
            if is_valid(rec):
                json.dump(rec, open(cache, "w", encoding="utf-8"))
                log.info("%-7s OK  (%.1fs)  %s", ticker, time.time() - t0,
                         (rec["info"].get("longName") or "")[:34])
                return rec
            log.warning("%-7s empty/invalid (try %d): info=%d, inc/bal/cas=%d/%d/%d",
                        ticker, attempt + 1, len(rec.get("info", {})),
                        len(rec.get("income", {})), len(rec.get("balance", {})),
                        len(rec.get("cashflow", {})))
        except Exception as e:  # noqa: BLE001
            _last_call[0] = time.time(); _n_calls[0] += 1
            last_err = e
            rl = "429" in str(e) or "too many requests" in str(e).lower()
            log.warning("%-7s error (try %d): %s%s", ticker, attempt + 1,
                        str(e)[:90], "  [RATE-LIMITED]" if rl else "")
        if attempt < config.MAX_RETRIES - 1:
            nap = config.BACKOFF_BASE * (3 ** attempt)
            log.info("%-7s backing off %.0fs", ticker, nap)
            time.sleep(nap)

    log.error("%-7s GAVE UP after %d tries (%s). Not cached; retries next run.",
              ticker, config.MAX_RETRIES, str(last_err)[:50] if last_err else "empty")
    return None
