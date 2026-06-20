"""parse.py — turn one cached yfinance record into clean tables (USD)."""

import numpy as np
import pandas as pd

FIN_SECTOR = "Financial Services"


def _stmt_df(d):
    if not d:
        return pd.DataFrame()
    df = pd.DataFrame(d).T
    try:
        cols = sorted(df.columns, key=lambda c: int(c))
    except (ValueError, TypeError):
        cols = list(df.columns)
    df = df[cols]
    df.index.name = "Line Item"
    return df.sort_index()


def statements(rec):
    inc = _stmt_df(rec.get("income"))
    out = {"Income": inc, "Balance": _stmt_df(rec.get("balance")),
           "Cash Flow": _stmt_df(rec.get("cashflow"))}
    years = [int(c) for c in inc.columns] if not inc.empty else []
    return out, years


def _rev_series(rec):
    inc = rec.get("income") or {}
    for k in ("Total Revenue", "TotalRevenue", "Operating Revenue"):
        if k in inc:
            return {int(y): v for y, v in inc[k].items() if v is not None}
    return {}


def _stmt_item(rec, group, *keys):
    g = rec.get(group) or {}
    for k in keys:
        row = g.get(k)
        if row:
            ys = sorted(int(y) for y, v in row.items() if v is not None)
            if ys:
                return row[str(ys[-1])]
    return None


def snapshot(rec, meta=None):
    meta = meta or {}
    info = rec.get("info") or {}
    rev = _rev_series(rec)
    ys = sorted(rev)
    latest_fy = ys[-1] if ys else None
    rev_latest = rev.get(latest_fy) if latest_fy else None
    rev_prev = rev.get(ys[-2]) if len(ys) >= 2 else None
    rev_growth = (rev_latest / rev_prev - 1) if (rev_latest and rev_prev and rev_prev > 0) else None
    sector = meta.get("sector") or info.get("sector")

    def pct(x):
        return round(x * 100, 1) if isinstance(x, (int, float)) else None

    ps = info.get("priceToSalesTrailing12Months")
    if sector == FIN_SECTOR:
        ps = None

    dy = info.get("dividendYield")
    return {
        "ticker": rec.get("ticker"),
        "name": meta.get("name") or info.get("longName"),
        "sector": sector,
        "industry": meta.get("industry") or info.get("industry"),
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "market_cap": info.get("marketCap"),
        "pe_ttm": info.get("trailingPE"),
        "fwd_pe": info.get("forwardPE"),
        "pb": info.get("priceToBook"),
        "ps": ps,
        "peg": info.get("pegRatio"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "roe_pct": pct(info.get("returnOnEquity")),
        "roa_pct": pct(info.get("returnOnAssets")),
        "gross_margin_pct": pct(info.get("grossMargins")),
        "op_margin_pct": pct(info.get("operatingMargins")),
        "net_margin_pct": pct(info.get("profitMargins")),
        "rev_growth_pct": round(rev_growth * 100, 1) if rev_growth is not None else None,
        "debt_to_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "fcf": info.get("freeCashflow"),
        "beta": info.get("beta"),
        "div_yield_pct": (pct(dy) if (dy or 0) < 1 else round(dy, 2)) if dy is not None else None,
        "eps_ttm": info.get("trailingEps"),
        "revenue_latest": rev_latest,
        "net_income_latest": _stmt_item(rec, "income", "Net Income"),
        "latest_fy": latest_fy,
        "target_mean": info.get("targetMeanPrice"),
        "reco": info.get("recommendationKey"),
        "n_analysts": info.get("numberOfAnalystOpinions"),
        "wk52_high": info.get("fiftyTwoWeekHigh"),
        "wk52_low": info.get("fiftyTwoWeekLow"),
    }


def metrics_long(rec):
    info = rec.get("info") or {}
    return pd.DataFrame([{"ticker": rec.get("ticker"), "metric": k, "value": v}
                         for k, v in info.items()])
