# Cross-Asset Regime Oscillator: does the public TradingView indicator carry an allocation edge?

Research build on the open-source TradingView "Cross-Asset Regime Oscillator" published by the regimecard
account (https://www.tradingview.com/script/uC4zb3i5-Cross-Asset-Regime-Oscillator/). Only the public
indicator is studied; nothing else published by that author is used or discussed.

Run order (all from the repo root with `.venv/bin/python`):

1. `fetch_data.py`      pulls every input and benchmark from Yahoo Finance and FRED into `data/raw/`, writes `data/SOURCES.md`
2. `oscillator.py`      the Python port, writes `data/oscillator_daily.csv`
3. `verify_tv.py`       compares the port with readings taken from TradingView (see `VERIFY.md`); fails if off by more than 1 point
4. `PREREG.md`          hypotheses, horizons, statistics, split and the allocation rule, committed before step 5 was run
5. `analysis.py`        the pre-registered tests; writes `RESULTS.md`, `results/*.csv` and `paper/figures/*.png`

Deliverables: `RESULTS.md` (tables, charts, verdict), `paper/paper.md` (SSRN-style draft), `ALLOCATE_SMARTLY.md`
(the allocation rule as a replication spec).
