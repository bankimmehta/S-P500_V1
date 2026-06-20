"""
analysis.py — multi-year fundamental analysis for the S&P 500 (yfinance).

Same philosophy as the NSE tool: nothing judged on a single year; every metric
read across the full statement window. Factual flags + three INDEPENDENT lenses
(fundamentals / valuation / technicals), never merged into one buy score.

Differences from the NSE version (source-specific, by necessity):
  * statement line-item labels are yfinance's ("Total Revenue", "Stockholders
    Equity", "Operating Cash Flow", "Free Cash Flow", ...)
  * the VALUATION lens compares each stock to its GICS-SECTOR MEDIAN P/E and P/B
    computed across the loaded universe (no per-stock sector number from yfinance)
  * the TECHNICAL lens uses yfinance's 50- & 200-day averages and 52-week range
"""

import numpy as np
import pandas as pd

import config

FIN_HINTS = ["financ", "bank", "insurance", "capital market", "asset manage"]
ROCE_GOOD, ROE_GOOD = config.ROCE_GOOD, config.ROE_GOOD
DE_HIGH, INT_COVER_MIN, MIN_YEARS = config.DE_HIGH, config.INT_COVER_MIN, config.MIN_YEARS

# yfinance statement labels (first match wins)
L_REV = ("Total Revenue", "Operating Revenue")
L_GP = ("Gross Profit",)
L_EBIT = ("Operating Income", "EBIT")
L_NI = ("Net Income", "Net Income Common Stockholders")
L_EPS = ("Diluted EPS", "Basic EPS")
L_INT = ("Interest Expense",)
L_TA = ("Total Assets",)
L_TL = ("Total Liabilities Net Minority Interest", "Total Liabilities")
L_EQ = ("Stockholders Equity", "Common Stock Equity")
L_DEBT = ("Total Debt",)
L_CASH = ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")
L_CA = ("Current Assets",)
L_CL = ("Current Liabilities",)
L_RE = ("Retained Earnings",)
L_OCF = ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
L_CAPEX = ("Capital Expenditure",)
L_FCF = ("Free Cash Flow",)


def _num(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return np.nan


def is_financial(rec, meta=None):
    sec = ((meta or {}).get("sector") or (rec.get("info") or {}).get("sector") or "").lower()
    return any(h in sec for h in FIN_HINTS)


def _series(rec, group, labels):
    g = rec.get(group) or {}
    for lab in labels:
        if lab in g:
            return {int(y): v for y, v in g[lab].items() if v is not None}
    return {}


def _ratio(num, den, pct=True):
    out = {}
    for y in sorted(set(num) & set(den)):
        n, d = num.get(y), den.get(y)
        if n is not None and d not in (None, 0) and not (isinstance(d, float) and np.isnan(d)):
            out[y] = (n / d) * (100 if pct else 1)
    return out


def _clean(series):
    return [(y, v) for y, v in sorted(series.items())
            if v is not None and not (isinstance(v, float) and np.isnan(v))]


def cagr(series):
    it = _clean(series)
    if len(it) < 2:
        return np.nan
    (y0, v0), (yn, vn) = it[0], it[-1]
    n = yn - y0
    if v0 is None or v0 <= 0 or vn is None or vn <= 0 or n <= 0:
        return np.nan
    return ((vn / v0) ** (1 / n) - 1) * 100


def trend(series, rel_tol=0.03, pp_tol=0.5, is_pct=False):
    it = _clean(series)
    if len(it) < 3:
        return "n/a"
    ys = np.array([y for y, _ in it], float)
    vs = np.array([v for _, v in it], float)
    slope = np.polyfit(ys - ys[0], vs, 1)[0]
    if is_pct:
        return "rising" if slope > pp_tol else ("falling" if slope < -pp_tol else "stable")
    mean = np.mean(np.abs(vs)) or 1.0
    return "rising" if slope / mean > rel_tol else ("falling" if slope / mean < -rel_tol else "stable")


def count_years(series, pred):
    it = _clean(series)
    return sum(1 for _, v in it if pred(v)), len(it)


def latest(series):
    it = _clean(series)
    return it[-1][1] if it else np.nan


def avg(series):
    it = _clean(series)
    return float(np.mean([v for _, v in it])) if it else np.nan


def ratios(rec):
    rev = _series(rec, "income", L_REV)
    gp = _series(rec, "income", L_GP)
    ebit = _series(rec, "income", L_EBIT)
    ni = _series(rec, "income", L_NI)
    eps = _series(rec, "income", L_EPS)
    interest = {y: abs(v) for y, v in _series(rec, "income", L_INT).items() if v is not None}

    ta = _series(rec, "balance", L_TA)
    teq = _series(rec, "balance", L_EQ)
    tl = _series(rec, "balance", L_TL)
    debt = _series(rec, "balance", L_DEBT)
    cash = _series(rec, "balance", L_CASH)
    tca = _series(rec, "balance", L_CA)
    tcl = _series(rec, "balance", L_CL)
    re = _series(rec, "balance", L_RE)

    ocf = _series(rec, "cashflow", L_OCF)
    capex = _series(rec, "cashflow", L_CAPEX)
    fcf_direct = _series(rec, "cashflow", L_FCF)
    fcf = fcf_direct or {y: ocf[y] + capex.get(y, 0) for y in ocf if ocf.get(y) is not None}

    cap_emp = {y: ta[y] - tcl.get(y, 0) for y in ta if ta.get(y) is not None}

    return {
        "revenue": rev, "gross_profit": gp, "ebit": ebit, "net_income": ni, "eps": eps,
        "gross_margin": _ratio(gp, rev), "op_margin": _ratio(ebit, rev), "net_margin": _ratio(ni, rev),
        "roe": _ratio(ni, teq), "roa": _ratio(ni, ta), "roce": _ratio(ebit, cap_emp),
        "debt_equity": _ratio(debt, teq, pct=False),
        "interest_cover": _ratio(ebit, interest, pct=False),
        "current_ratio": _ratio(tca, tcl, pct=False),
        "ocf": ocf, "fcf": fcf, "cash_conversion": _ratio(ocf, ni),
        "net_debt": {y: debt.get(y, 0) - cash.get(y, 0) for y in debt},
        "_raw": {"ta": ta, "teq": teq, "tl": tl, "tca": tca, "tcl": tcl, "re": re,
                 "ebit": ebit, "rev": rev, "ni": ni, "ocf": ocf, "debt": debt},
    }


def altman_z_private(r):
    R = r["_raw"]
    if not R["ta"]:
        return np.nan, "n/a"
    y = max(R["ta"])
    try:
        ta = R["ta"][y]
        wc = R["tca"][y] - R["tcl"][y]
        z = (0.717 * (wc / ta) + 0.847 * (R["re"][y] / ta) + 3.107 * (R["ebit"][y] / ta) +
             0.420 * (R["teq"][y] / R["tl"][y]) + 0.998 * (R["rev"][y] / ta))
    except (KeyError, ZeroDivisionError, TypeError):
        return np.nan, "n/a"
    return round(z, 2), ("safe" if z > 2.9 else ("grey" if z >= 1.23 else "distress"))


def piotroski_f(r):
    R = r["_raw"]
    yrs = sorted(R["ta"])
    if len(yrs) < 2:
        return np.nan
    y, yp = yrs[-1], yrs[-2]
    s = 0
    try:
        s += R["ni"][y] > 0
        s += R["ocf"][y] > 0
        s += (R["ni"][y] / R["ta"][y]) > (R["ni"][yp] / R["ta"][yp])
        s += R["ocf"][y] > R["ni"][y]
        s += (R["debt"][y] / R["ta"][y]) < (R["debt"][yp] / R["ta"][yp])
        s += (R["tca"][y] / R["tcl"][y]) > (R["tca"][yp] / R["tcl"][yp])
        s += r["gross_margin"].get(y, 0) > r["gross_margin"].get(yp, 0)
        s += (R["rev"][y] / R["ta"][y]) > (R["rev"][yp] / R["ta"][yp])
        s += 1
    except (KeyError, ZeroDivisionError, TypeError):
        return np.nan
    return int(s)


# ---------------------------------------------------------------------------
# sector medians (computed across the whole loaded universe) for valuation
# ---------------------------------------------------------------------------
def sector_medians(records, meta_by_ticker=None):
    meta_by_ticker = meta_by_ticker or {}
    rows = {}
    for tk, rec in records.items():
        info = rec.get("info") or {}
        sec = (meta_by_ticker.get(tk, {}).get("sector") or info.get("sector") or "Unknown")
        rows.setdefault(sec, {"pe": [], "pb": []})
        pe, pb = info.get("trailingPE"), info.get("priceToBook")
        if isinstance(pe, (int, float)) and pe > 0:
            rows[sec]["pe"].append(pe)
        if isinstance(pb, (int, float)) and pb > 0:
            rows[sec]["pb"].append(pb)
    import statistics
    return {sec: {"pe": (statistics.median(v["pe"]) if v["pe"] else np.nan),
                  "pb": (statistics.median(v["pb"]) if v["pb"] else np.nan)}
            for sec, v in rows.items()}


def valuation(rec, meta=None, sec_med=None):
    info = rec.get("info") or {}
    meta = meta or {}
    sec = meta.get("sector") or info.get("sector") or "Unknown"
    med = (sec_med or {}).get(sec, {})
    pe = info.get("trailingPE")
    fpe = info.get("forwardPE")
    pb = info.get("priceToBook")
    peg = info.get("pegRatio")
    ev = info.get("enterpriseToEbitda")
    med_pe, med_pb = med.get("pe", np.nan), med.get("pb", np.nan)

    def ok(x):
        return isinstance(x, (int, float)) and not (isinstance(x, float) and np.isnan(x))

    checks = [
        ("P/E below sector median", (ok(pe) and ok(med_pe) and pe < med_pe),
         f"P/E {pe:.1f} vs sector {med_pe:.1f}" if ok(pe) and ok(med_pe) else "n/a"),
        ("P/B below sector median", (ok(pb) and ok(med_pb) and pb < med_pb),
         f"P/B {pb:.2f} vs sector {med_pb:.2f}" if ok(pb) and ok(med_pb) else "n/a"),
        ("Forward P/E below trailing (earnings expected up)",
         (ok(pe) and ok(fpe) and 0 < fpe < pe), f"fwd {fpe:.1f} vs ttm {pe:.1f}" if ok(fpe) and ok(pe) else "n/a"),
        ("PEG <= 2", (ok(peg) and 0 < peg <= 2), f"PEG {peg:.2f}" if ok(peg) else "n/a"),
        ("EV/EBITDA <= 15", (ok(ev) and 0 < ev <= 15), f"EV/EBITDA {ev:.1f}" if ok(ev) else "n/a"),
    ]
    npass = sum(1 for _, o, _ in checks if o)
    return {"pe": pe if ok(pe) else None, "sector_pe": None if not ok(med_pe) else round(med_pe, 1),
            "pb": pb if ok(pb) else None, "peg": peg if ok(peg) else None,
            "checks": checks, "pass": npass, "total": len(checks)}


def technical(rec):
    info = rec.get("info") or {}
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    ma50 = info.get("fiftyDayAverage")
    ma200 = info.get("twoHundredDayAverage")
    hi, lo = info.get("fiftyTwoWeekHigh"), info.get("fiftyTwoWeekLow")

    def ok(x):
        return isinstance(x, (int, float)) and not (isinstance(x, float) and np.isnan(x))

    pos52 = ((price - lo) / (hi - lo)) if (ok(price) and ok(hi) and ok(lo) and hi > lo) else np.nan
    golden = ok(ma50) and ok(ma200) and ma50 > ma200
    checks = [
        ("Price above 50-day MA", (ok(price) and ok(ma50) and price >= ma50),
         f"${price:.0f} vs 50DMA ${ma50:.0f}" if ok(price) and ok(ma50) else "n/a"),
        ("Price above 200-day MA", (ok(price) and ok(ma200) and price >= ma200),
         f"${price:.0f} vs 200DMA ${ma200:.0f}" if ok(price) and ok(ma200) else "n/a"),
        ("50-day above 200-day (golden alignment)", golden,
         "50>200" if golden else "not aligned"),
        ("In healthy 52-week zone (30-95%)", (ok(pos52) and 0.30 <= pos52 <= 0.95),
         f"{pos52:.0%} of range" if ok(pos52) else "n/a"),
    ]
    npass = sum(1 for _, o, _ in checks if o)
    return {"price": price if ok(price) else None,
            "ma50": ma50 if ok(ma50) else None, "ma200": ma200 if ok(ma200) else None,
            "pos_52w": None if not ok(pos52) else round(pos52, 2),
            "golden": golden, "checks": checks, "pass": npass, "total": len(checks)}


def fundamental_checks(rec, r, fin):
    rev_c = cagr(r["revenue"])
    roce_avg, roe_avg = avg(r["roce"]), avg(r["roe"])
    de = latest(r["debt_equity"])
    n_fcf, n = count_years(r["fcf"], lambda v: v > 0)
    n_prof, npy = count_years(r["net_income"], lambda v: v > 0)
    z, zone = altman_z_private(r) if not fin else (np.nan, "n/a")
    qual = roe_avg if fin else roce_avg
    qlabel = "avg ROE" if fin else "avg ROCE"
    checks = [
        (f"Quality: {qlabel} >= {ROCE_GOOD:.0f}%", (not np.isnan(qual) and qual >= ROCE_GOOD),
         f"{qual:.1f}%" if not np.isnan(qual) else "n/a"),
        ("Consistently profitable", (npy > 0 and n_prof == npy), f"{n_prof}/{npy} yrs"),
        ("Revenue CAGR >= 8%", (not np.isnan(rev_c) and rev_c >= 8), f"{rev_c:.1f}%" if not np.isnan(rev_c) else "n/a"),
        ("FCF positive in majority of years", (n > 0 and n_fcf > n / 2), f"{n_fcf}/{n} yrs"),
        ("Leverage in check (D/E <= 1.5)" if not fin else "Leverage (n/a for financials)",
         (fin or (not np.isnan(de) and de <= DE_HIGH)),
         "financial" if fin else (f"D/E {de:.2f}" if not np.isnan(de) else "n/a")),
        ("Not in Altman distress" if not fin else "Altman (n/a for financials)",
         (fin or zone in ("safe", "grey")),
         "financial" if fin else (f"Z'={z} ({zone})" if zone != "n/a" else "n/a")),
    ]
    return checks, sum(1 for _, o, _ in checks if o), len(checks)


def flags(rec, r, fin):
    red, green = [], []
    ni, ocf = r["net_income"], r["ocf"]
    bad = [y for y in sorted(set(ni) & set(ocf))
           if (ni.get(y) or 0) > 0 and (ocf.get(y) or 0) < (ni.get(y) or 0) * 0.5]
    if len(bad) >= 2:
        red.append(("Weak cash conversion", f"OCF well below net income in {len(bad)} years."))
    n_prof, n = count_years(ni, lambda v: v > 0)
    if n and n_prof == n:
        green.append(("Consistently profitable", f"Positive net income all {n} years."))
    elif n and n_prof <= n - 2:
        red.append(("Loss-making years", f"Net loss in {n - n_prof} of {n} years."))
    if not fin and r["roce"]:
        ng, nn = count_years(r["roce"], lambda v: v >= ROCE_GOOD)
        if nn and ng >= nn - 1:
            green.append(("Strong ROCE", f"ROCE >= {ROCE_GOOD:.0f}% in {ng}/{nn} yrs (avg {avg(r['roce']):.1f}%)."))
        elif nn and ng == 0:
            red.append(("Low ROCE", f"ROCE never reached {ROCE_GOOD:.0f}% (avg {avg(r['roce']):.1f}%)."))
    gm = trend(r["gross_margin"], is_pct=True)
    if gm == "falling":
        red.append(("Margins compressing", "Gross margin trending down."))
    elif gm == "rising":
        green.append(("Margins expanding", "Gross margin trending up."))
    if not fin and r["debt_equity"]:
        de = latest(r["debt_equity"])
        if not np.isnan(de) and de > DE_HIGH and trend(r["debt_equity"]) == "rising":
            red.append(("Rising leverage", f"D/E {de:.2f} and climbing."))
        nd = latest(r["net_debt"])
        if not np.isnan(nd) and nd < 0:
            green.append(("Net cash", "Cash exceeds total debt."))
    if not fin and r["interest_cover"]:
        ic = latest(r["interest_cover"])
        if not np.isnan(ic) and ic < INT_COVER_MIN:
            red.append(("Thin interest cover", f"EBIT covers interest {ic:.1f}x."))
    if r["fcf"]:
        npos, n = count_years(r["fcf"], lambda v: v > 0)
        if n and npos == n:
            green.append(("Reliable free cash flow", f"Positive FCF all {n} years."))
        elif n and npos <= n // 2:
            red.append(("Weak free cash flow", f"Negative FCF in {n - npos} of {n} years."))
    rc = cagr(r["revenue"])
    if not np.isnan(rc):
        if rc >= 10:
            green.append(("Healthy growth", f"Revenue CAGR {rc:.1f}%."))
        elif rc < 0:
            red.append(("Shrinking revenue", f"Revenue CAGR {rc:.1f}%."))
    if not fin:
        z, zone = altman_z_private(r)
        if zone == "distress":
            red.append(("Altman distress zone", f"Altman Z' = {z}."))
        elif zone == "safe":
            green.append(("Altman safe zone", f"Altman Z' = {z}."))
    return red, green


def analyze(rec, ticker=None, meta=None, sec_med=None):
    ticker = ticker or rec.get("ticker")
    r = ratios(rec)
    fin = is_financial(rec, meta)
    red, green = flags(rec, r, fin)
    z, zone = altman_z_private(r) if not fin else (np.nan, "n/a")
    n_years = len(_clean(r["revenue"]))
    severe = [f for f in red if f[0] in
              ("Weak cash conversion", "Loss-making years", "Altman distress zone",
               "Rising leverage", "Shrinking revenue")]
    investigate = (n_years >= MIN_YEARS) and (len(severe) == 0)

    val = valuation(rec, meta, sec_med)
    tech = technical(rec)
    fchecks, fpass, ftot = fundamental_checks(rec, r, fin)
    fund_ok = (fpass >= 4) and investigate
    value_ok = val["pass"] >= 3
    tech_ok = tech["pass"] >= 3
    all_three = fund_ok and value_ok and tech_ok

    def rnd(x, n=1):
        if x is None or not isinstance(x, (int, float)) or (isinstance(x, float) and np.isnan(x)):
            return None
        return round(x, n)

    summary = {
        "ticker": ticker, "company": (rec.get("info") or {}).get("longName"),
        "sector": (meta or {}).get("sector") or (rec.get("info") or {}).get("sector"),
        "is_financial": fin, "years": n_years,
        "rev_cagr_pct": rnd(cagr(r["revenue"])), "ni_cagr_pct": rnd(cagr(r["net_income"])),
        "roce_avg_pct": rnd(avg(r["roce"])), "roe_avg_pct": rnd(avg(r["roe"])),
        "gross_margin_trend": trend(r["gross_margin"], is_pct=True),
        "net_margin_trend": trend(r["net_margin"], is_pct=True),
        "de_now": rnd(latest(r["debt_equity"]), 2),
        "fcf_positive_years": f"{count_years(r['fcf'], lambda v: v>0)[0]}/{count_years(r['fcf'], lambda v: v>0)[1]}",
        "piotroski_f": piotroski_f(r), "altman_z": z if not (isinstance(z, float) and np.isnan(z)) else None,
        "altman_zone": zone, "n_red_flags": len(red), "n_green_flags": len(green),
        "investigate": investigate,
        "fund_checks": f"{fpass}/{ftot}", "fund_ok": fund_ok,
        "pe_ttm": rnd(val["pe"]), "sector_pe": val["sector_pe"], "peg": rnd(val["peg"], 2),
        "value_checks": f"{val['pass']}/{val['total']}", "value_ok": value_ok,
        "price": tech["price"], "pos_52w": tech["pos_52w"], "golden_cross": tech["golden"],
        "tech_checks": f"{tech['pass']}/{tech['total']}", "tech_ok": tech_ok,
        "all_three_lenses": all_three,
    }
    return {"summary": summary, "ratios": r, "red": red, "green": green,
            "valuation": val, "technical": tech, "fundamental_checks": fchecks}


def summary_row(rec, ticker=None, meta=None, sec_med=None):
    return analyze(rec, ticker, meta, sec_med)["summary"]


def flags_long(rec, ticker=None, meta=None):
    a = analyze(rec, ticker, meta)
    rows = []
    for kind, items in (("RED", a["red"]), ("GREEN", a["green"])):
        for nm, note in items:
            rows.append({"ticker": ticker or rec.get("ticker"), "type": kind, "flag": nm, "note": note})
    return rows


def ratio_table(rec, keys=("gross_margin", "op_margin", "net_margin", "roe", "roce",
                           "debt_equity", "interest_cover", "current_ratio", "fcf")):
    r = ratios(rec)
    rows = {k: {int(y): v for y, v in r.get(k, {}).items()} for k in keys}
    df = pd.DataFrame(rows).T
    df = df.reindex(columns=sorted(df.columns))
    df.index.name = "metric"
    return df
