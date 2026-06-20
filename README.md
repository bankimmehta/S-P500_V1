# S&P 500 Fundamentals — yfinance

Sibling of the NIFTY 50 / indianapi tool, same shape and UX (Overview · Analysis ·
Flags · statements · KeyMetrics, plus a 3-lens Screener), sourced from yfinance in USD.

## Install & run
```bash
pip install -r requirements.txt
python extract.py --limit 25      # TEST first — confirm yfinance is happy
python extract.py                 # full S&P 500 (~503; first run ~15-25 min)
streamlit run app.py              # browse + download Excel (no live calls)
```
Outputs: output/sp500_fundamentals.xlsx + output/sp500_data.json (the app reads this).

## Not getting blocked by Yahoo
- **Permanent cache**: each ticker fetched once -> cache/<TICKER>.json; re-runs reuse it.
- **Resumable**: interrupted run continues; failed/empty names aren't cached, so they retry.
- **Paced + backoff**: ~1.5-2.5s/stock jittered, 5/15/45s backoff on errors/429.
- Always `python extract.py --limit 25` first; `python extract.py --rebuild` makes the
  Excel from cache with no fetching.

## Analysis (parity with the NSE tool) — three independent lenses, never merged
- **Fundamentals (/6)**: multi-year avg ROCE/ROE, consistent profitability, revenue CAGR,
  FCF reliability, leverage, Altman (non-financials). Plus red/green flags with notes.
- **Valuation (/5)**: P/E & P/B vs the stock's **GICS-sector median computed across the
  loaded universe**, forward vs trailing P/E, PEG, EV/EBITDA.
- **Technicals (/4)**: price vs 50- & 200-day MA, golden-cross alignment, 52-week position.

Excel tabs: ReadMe, Overview, **Analysis**, **Flags**, Income, Balance, Cash Flow, KeyMetrics.
App: **Screener** (filter on each lens independently) + **Stock detail** (3 checklists,
flags, by-year ratios). Nothing is advice — facts surfaced for your judgment.

## Deploy (GitHub + Streamlit Cloud)
```bash
python build_dataset.py     # cache -> output/, NO fetching
git add -A && git add -f output/sp500_data.json output/sp500_fundamentals.xlsx
git commit -m "data + analysis" && git push
```
The app finds output/sp500_data.json (or falls back to cache/, or an upload box).

## Files
config.py · universe.py · client.py · parse.py · analysis.py · extract.py ·
build_dataset.py · app.py · data/sp500_constituents.csv
