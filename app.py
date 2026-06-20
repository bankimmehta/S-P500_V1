#!/usr/bin/env python3
"""
app.py — Streamlit viewer for the S&P 500 dataset (yfinance). Mirror of the NSE app.

Robust loading: searches paths, falls back to cache/*.json, then a browser upload.
Read-only — never calls yfinance.

Run:  streamlit run app.py
"""

import json
from pathlib import Path

import streamlit as st
import pandas as pd

import config
import universe
import parse
import analysis

st.set_page_config(page_title="S&P 500 Fundamentals", layout="wide")
st.title("📈 S&P 500 Fundamentals — yfinance")
st.caption("USD · annual statements · read-only (no live calls)")

META = {r["ticker"]: r for r in universe.load()}


def _candidate_paths():
    return [config.OUTPUT_DIR / config.DATA_JSON, config.ROOT / config.DATA_JSON,
            Path.cwd() / "output" / config.DATA_JSON, Path.cwd() / config.DATA_JSON]


def load_dataset():
    for p in _candidate_paths():
        if p.exists():
            try:
                return json.load(open(p, encoding="utf-8")), f"file: {p}"
            except Exception:  # noqa: BLE001
                pass
    files = sorted(config.CACHE_DIR.glob("*.json")) if config.CACHE_DIR.exists() else []
    if files:
        out = {}
        for cf in files:
            try:
                rec = json.load(open(cf, encoding="utf-8"))
                if isinstance(rec, dict) and rec.get("info"):
                    out[cf.stem] = rec
            except Exception:  # noqa: BLE001
                continue
        if out:
            return out, f"cache/ ({len(out)} stocks)"
    return None, None


records, source = load_dataset()
if not records:
    st.warning("No dataset found. Upload your **sp500_data.json** to view it here.")
    ups = st.file_uploader("Upload JSON", type="json", accept_multiple_files=True)
    if ups:
        records = {}
        for u in ups:
            try:
                d = json.load(u)
                if isinstance(d, dict) and "info" in d and "ticker" in d:
                    records[d["ticker"]] = d
                elif isinstance(d, dict):
                    records.update({k: v for k, v in d.items() if isinstance(v, dict) and v.get("info")})
            except Exception as e:  # noqa: BLE001
                st.error(f"{u.name}: {e}")
        source = f"upload ({len(records)} stocks)"
    if not records:
        st.info("Tip: commit output/sp500_data.json to your repo, or upload it above.")
        st.stop()

st.caption(f"Loaded {len(records)} stocks · {source}")


@st.cache_data
def sec_med(keys):
    return analysis.sector_medians(records, META)


@st.cache_data
def overview_df(keys):
    return pd.DataFrame([parse.snapshot(records[k], META.get(k, {})) for k in keys])


@st.cache_data
def analysis_df(keys):
    sm = analysis.sector_medians(records, META)
    return pd.DataFrame([analysis.summary_row(records[k], k, META.get(k, {}), sm) for k in keys])


keys = list(records.keys())
ov = overview_df(keys)
an = analysis_df(keys)
SM = sec_med(keys)

tab_ov, tab_screen, tab_detail = st.tabs(["🏆 Overview", "🔬 Screener", "🔍 Stock detail"])

with tab_ov:
    st.subheader(f"{len(ov)} stocks")
    secs = sorted(x for x in ov["sector"].dropna().unique())
    psec = st.multiselect("Filter by sector", secs, default=[])
    view = ov[ov["sector"].isin(psec)] if psec else ov
    cols = ["ticker", "name", "sector", "price", "market_cap", "pe_ttm", "fwd_pe",
            "pb", "roe_pct", "net_margin_pct", "rev_growth_pct", "debt_to_equity",
            "div_yield_pct", "reco"]
    show = view[[c for c in cols if c in view.columns]]
    fmt = {"price": "{:.2f}", "market_cap": "{:,.0f}", "pe_ttm": "{:.1f}", "fwd_pe": "{:.1f}",
           "pb": "{:.2f}", "roe_pct": "{:.1f}%", "net_margin_pct": "{:.1f}%",
           "rev_growth_pct": "{:+.1f}%", "debt_to_equity": "{:.1f}", "div_yield_pct": "{:.2f}%"}
    st.dataframe(show.style.format({k: v for k, v in fmt.items() if k in show.columns}, na_rep="—"),
                 use_container_width=True, height=560)
    xlsx = config.OUTPUT_DIR / config.XLSX_NAME
    if xlsx.exists():
        st.download_button("⬇️ Download full Excel", open(xlsx, "rb").read(), config.XLSX_NAME,
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab_screen:
    st.subheader("Shortlist on your own rules")
    st.caption("Every criterion uses the FULL multi-year history. Filters AND together.")
    c1, c2, c3 = st.columns(3)
    with c1:
        min_rev = st.slider("Min revenue CAGR %", -10, 40, 8)
        min_roce = st.slider("Min avg ROCE %", 0, 50, 15)
    with c2:
        max_de = st.slider("Max Debt/Equity", 0.0, 5.0, 1.5, 0.1)
        min_pio = st.slider("Min Piotroski F", 0, 9, 5)
    with c3:
        no_red = st.checkbox("No red flags", value=False)
        incl_fin = st.checkbox("Include financials", value=True)

    st.markdown("**Three independent lenses** (never combined into one score):")
    L1, L2, L3, L4 = st.columns(4)
    g_fund = L1.checkbox("✅ Fundamentals strong", value=True)
    g_val = L2.checkbox("💰 Valuation not stretched", value=False)
    g_tech = L3.checkbox("📈 Technicals in uptrend", value=False)
    g_all = L4.checkbox("🎯 All three positive", value=False)

    df = an.copy()
    m = pd.Series(True, index=df.index)
    m &= df["rev_cagr_pct"].fillna(-999) >= min_rev
    m &= df["roce_avg_pct"].fillna(-999) >= min_roce
    m &= df["de_now"].fillna(999) <= max_de
    m &= df["piotroski_f"].fillna(-1) >= min_pio
    if no_red:
        m &= df["n_red_flags"] == 0
    if not incl_fin:
        m &= ~df["is_financial"]
    if g_fund:
        m &= df["fund_ok"]
    if g_val:
        m &= df["value_ok"]
    if g_tech:
        m &= df["tech_ok"]
    if g_all:
        m &= df["all_three_lenses"]

    hits = df[m]
    st.markdown(f"**{len(hits)} of {len(df)} stocks match.** Each lens shown separately.")
    scols = ["ticker", "company", "sector", "fund_checks", "value_checks", "tech_checks",
             "all_three_lenses", "roce_avg_pct", "rev_cagr_pct", "pe_ttm", "sector_pe",
             "peg", "pos_52w", "altman_zone"]
    st.dataframe(hits[[c for c in scols if c in hits.columns]]
                 .sort_values(["all_three_lenses", "roce_avg_pct"], ascending=False),
                 use_container_width=True, hide_index=True, height=440)
    st.download_button("⬇️ Download shortlist (CSV)", hits.to_csv(index=False).encode(),
                       "shortlist.csv", "text/csv")

with tab_detail:
    labels = {tk: f"{tk} — {(records[tk].get('info') or {}).get('longName','')}" for tk in keys}
    pick = st.selectbox("Stock", keys, format_func=lambda t: labels[t])
    rec = records[pick]
    meta = META.get(pick, {})
    a = analysis.analyze(rec, pick, meta, SM)
    s = a["summary"]
    snap = parse.snapshot(rec, meta)

    st.subheader(f"{snap['name']}  ·  {snap['sector']}")
    cc = st.columns(6)
    cc[0].metric("Price", f"${snap['price']:,.2f}" if snap['price'] else "—")
    cc[1].metric("Market cap", f"${snap['market_cap']/1e9:,.1f}B" if snap['market_cap'] else "—")
    cc[2].metric("P/E", f"{snap['pe_ttm']:.1f}" if snap['pe_ttm'] else "—")
    cc[3].metric("ROE", f"{snap['roe_pct']:.1f}%" if snap['roe_pct'] is not None else "—")
    cc[4].metric("Rev growth", f"{snap['rev_growth_pct']:+.1f}%" if snap['rev_growth_pct'] is not None else "—")
    cc[5].metric("Analysts", snap['reco'] or "—")

    st.markdown("#### Buy-readiness — three independent lenses")
    st.caption("Each judged on its own; deliberately NOT combined. Factual checks, not advice.")
    g1, g2, g3 = st.columns(3)
    g1.metric("✅ Fundamentals", s["fund_checks"], "strong" if s["fund_ok"] else "not yet")
    g2.metric("💰 Valuation", s["value_checks"], "ok" if s["value_ok"] else "stretched")
    g3.metric("📈 Technicals", s["tech_checks"], "uptrend" if s["tech_ok"] else "no")
    lc1, lc2, lc3 = st.columns(3)
    with lc1:
        st.markdown("**Fundamentals**")
        for nm, ok, d in a["fundamental_checks"]:
            st.markdown(f"{'🟢' if ok else '⚪'} {nm} — _{d}_")
    with lc2:
        st.markdown("**Valuation**")
        for nm, ok, d in a["valuation"]["checks"]:
            st.markdown(f"{'🟢' if ok else '⚪'} {nm} — _{d}_")
    with lc3:
        st.markdown("**Technicals**")
        for nm, ok, d in a["technical"]["checks"]:
            st.markdown(f"{'🟢' if ok else '⚪'} {nm} — _{d}_")
    if s["all_three_lenses"]:
        st.success("All three lenses independently positive — worth a closer look. "
                   "(Not a recommendation.)")

    stmts, _ = parse.statements(rec)
    st.markdown("#### Financial statements (USD, annual)")
    for name in ["Income", "Balance", "Cash Flow"]:
        df = stmts.get(name)
        if df is None or df.empty:
            continue
        with st.expander(name, expanded=(name == "Income")):
            show = df.copy()
            show.columns = [str(c) for c in show.columns]
            st.dataframe(show.style.format("{:,.0f}", na_rep="—"), use_container_width=True)

    st.markdown("#### Flags & ratios by year")
    fc1, fc2 = st.columns(2)
    with fc1:
        if a["red"]:
            st.markdown("**🔴 Red flags**")
            for nm, note in a["red"]:
                st.markdown(f"- **{nm}** — {note}")
        else:
            st.caption("No red flags.")
    with fc2:
        if a["green"]:
            st.markdown("**🟢 Green flags**")
            for nm, note in a["green"]:
                st.markdown(f"- **{nm}** — {note}")
        else:
            st.caption("No green flags.")
    rt = analysis.ratio_table(rec)
    rt.columns = [str(c) for c in rt.columns]
    st.dataframe(rt.style.format("{:,.1f}", na_rep="—"), use_container_width=True)
