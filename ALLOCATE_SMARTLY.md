# Cross-Asset Regime Oscillator allocation rule: replication specification

Written for Allocate Smartly's request for a fully specified rule with execution at the close. Everything
below is public and free. Backtest figures are from `RESULTS.md` and are **pending verification of the
indicator port against the TradingView chart** (`VERIFY.md`); treat them as provisional until that check is
reported as passed.

## 1. Summary

| Item | Value |
|---|---|
| Name | Cross-Asset Regime Oscillator rule (CARO) |
| Source | Open-source TradingView indicator "Cross-Asset Regime Oscillator" by regimecard, Pine v6: https://www.tradingview.com/script/uC4zb3i5-Cross-Asset-Regime-Oscillator/ |
| Assets traded | US large-cap equity (S&P 500 total return; SPY as the ETF) and 3-month T-bills (cash) |
| Signal frequency | daily, checked at every US equity close |
| Trade frequency | only on a band change: about 20 changes a year, 5.0 units of one-way turnover a year |
| Execution | at the close, on the previous day's signal (the value the TradingView chart shows that day); a same-close variant is reported separately |
| Equity weight | 100 / 75 / 50 / 25 / 0 percent by band, from RISK-ON down to RISK-OFF; remainder in T-bills |
| Parameters | the indicator's published defaults only; nothing tuned |
| History | five-signal signal from 2008-04-09 (HYG listed 2007-04-11, 252-day lookback); reduced-signal history back to 1991 with the script's own missing-data rule, reported but not recommended |

## 2. Data

| Input | Series | Free source used | Notes |
|---|---|---|---|
| Credit | HYG close / IEF close | Yahoo Finance, unadjusted close | ratio on days both trade |
| Volatility | VIX close | Yahoo ^VIX (CBOE) | enters inverted |
| Cyclical vs defensive | XLI close / XLU close | Yahoo Finance, unadjusted close | |
| Yield curve | 10-year minus 3-month constant maturity yield, percent | FRED DGS10 and DGS3MO | no value on bond-market holidays; the series simply has no bar that day. TradingView uses its own vendor (TVC:US10Y, TVC:US03MY); small level differences are expected |
| Dollar | ICE US Dollar Index close | Yahoo DX-Y.NYB | enters inverted |
| Equity leg | S&P 500 Total Return index | Yahoo ^SP500TR | SPY total return is the investable equivalent |
| Cash leg | 3-month T-bill | FRED DTB3 | daily accrual DTB3 / 100 / 252, yield as of the prior day |

Real-time availability: the VIX settles at 16:15 ET and the dollar index at about 17:00 ET, after the equity
close. FRED posts a day's yields the next business day; TradingView's yield feed is intraday. Trading on the
previous day's signal (section 4) removes every one of these timing problems.

## 3. Signal construction, step by step

1. For each of the five inputs, build the daily series on the input's own trading calendar:
   `credit = HYG/IEF`, `vol = VIX`, `cycdef = XLI/XLU`, `curve = DGS10 - DGS3MO`, `dollar = DXY`.
2. For each series x, on each of its bars t with at least 252 bars of history:
   `m = mean(x[t-251..t])`, `s = population std dev(x[t-251..t])` (divide by 252, not 251),
   `z = (x[t] - m) / s`, then clamp: `z = max(-3, min(3, z))`. If `s == 0` the signal is not available that day.
3. Orient: `z_credit = +z`, `z_vol = -z`, `z_cycdef = +z`, `z_curve = +z`, `z_dollar = -z`.
4. On each US equity trading day D, take for each input the z of its latest bar dated on or before D.
5. `composite = mean of the available oriented z's` (skip any that is not available; in the five-signal period
   all five are always available).
6. `score = max(0, min(100, 50 + composite x 100/6))`.
7. Band: `score < 20` RISK-OFF; `< 40` MILDLY OFF; `< 60` NEUTRAL; `< 80` MILDLY ON; `>= 80` RISK-ON.

Reference implementation: `oscillator.py` in this folder (pandas). Verification dates with expected values:
`VERIFY.md`.

Two facts about the score to know before building on it: in the five-signal period 2008 to 2026 the score
never reached 80, so RISK-ON never occurs and the rule's maximum equity weight is in practice 75%; and the
average equity weight over the period is 51%.

## 4. Trading rule

- At the close of each US equity trading day t, compute `score[t]` from closes through t and read the band.
- Target equity weight `w = {RISK-ON: 1.00, MILDLY ON: 0.75, NEUTRAL: 0.50, MILDLY OFF: 0.25, RISK-OFF: 0.00}`.
- **Headline execution (next close):** trade to the target at the close of t+1. This is identical to reading
  the TradingView chart's plotted value on day t+1 and trading at that day's close, because the chart plots
  the previous confirmed bar of every input.
- **Same-close variant:** trade to the target at the close of t. Requires the VIX and dollar closes before the
  equity close, so it is slightly optimistic; reported for completeness.
- Trade only when the target changes. Let positions drift between trades (the backtest does this; daily
  rebalancing to target gives almost identical numbers).
- Costs: 5 basis points of the traded equity amount at every trade. The cash leg is treated as free.
- Pseudocode:

```
w_target = NaN
for each trading day t (chronological):
    grow equity by r_equity[t], cash by r_cash[t]
    if execution == "next close": b = band(score[t-1]) else: b = band(score[t])
    w_new = weight_map[b]
    if w_new != w_target:
        trade equity to w_new x portfolio value; pay 0.0005 x |traded amount|
        w_target = w_new
```

## 5. Benchmarks used

- Buy and hold S&P 500 total return, no cost.
- 60/40: 60% S&P 500 TR, 40% Vanguard Total Bond Market Index (VBMFX adjusted close), rebalanced at month end,
  5 bp on the traded amount.
- Exposure-matched constant mix: 51% S&P 500 TR, 49% T-bills, rebalanced at month end, 5 bp. This is the
  benchmark that separates timing from exposure.

## 6. Backtest figures to replicate against (2008-04-09 to 2026-10-30, 5 bp per side) [pending verification]

| Strategy | CAGR % | Vol % | Sharpe | Sortino | Max DD % | Worst year % | Turnover /yr | Mean eq. weight |
|---|---|---|---|---|---|---|---|---|
| Rule, next close | 6.85 | 8.0 | 0.69 | 0.96 | -19.6 | -12.5 (2008) | 5.04 | 0.51 |
| Rule, same close | 7.12 | 7.9 | 0.73 | 1.01 | -19.0 | -11.4 (2008) | 5.05 | 0.51 |
| Buy and hold | 11.79 | 19.7 | 0.59 | 0.83 | -51.5 | -32.6 (2008) | | 1.00 |
| 60/40 monthly | 8.31 | 11.5 | 0.63 | 0.88 | -34.1 | -19.6 (2008) | 0.10 | |
| Constant mix 51/49 | 6.91 | 9.8 | 0.59 | 0.81 | -29.9 | -17.3 (2008) | 0.11 | 0.51 |

Out of sample (2018-01-02 to 2026-10-30): rule next close CAGR 8.90%, vol 8.4%, Sharpe 0.74, max DD -15.2%;
buy and hold 14.37%, 19.1%, 0.66, -33.8%.

Calendar years (rule next close / buy and hold, %): 2008 -12.5 / -32.6 (from April), 2009 18.3 / 26.5, 2010 8.2 /
15.1, 2011 -2.2 / 2.1, 2012 4.3 / 16.0, 2013 18.8 / 32.4, 2014 2.4 / 13.7, 2015 -2.3 / 1.4, 2016 4.4 / 12.0, 2017
13.6 / 21.8, 2018 -0.9 / -4.4, 2019 9.7 / 31.5, 2020 19.2 / 18.4, 2021 17.4 / 28.7, 2022 -12.4 / -18.1, 2023 14.8 /
26.3, 2024 13.7 / 25.0, 2025 12.1 / 17.9, 2026 8.7 / 11.8 (to October).

Daily series for a tie-out: `results/daily_returns_primary_5bp.csv` (daily returns of every strategy) and
`results/held_weights_primary.csv` (the equity weight held each day).

## 7. What the evidence says (read before listing it)

The pre-registered tests did not establish an edge. The rule's Sharpe advantage over buy and hold (+0.10) and
over the exposure-matched constant mix (+0.11) has a 90% block-bootstrap interval that includes zero, comes
from 2008 and 2020 to 2022, is absent in 2010 to 2019 (rule 0.78 against 0.90 for the constant mix) and
reverses on the reduced-signal history before 2008 (rule 0.23 against 0.48 for buy and hold, interval
excluding zero). The band with the best forward returns is RISK-OFF, where the rule holds no equity. The
drawdown reduction (20% against 52% for buy and hold) is real but a static 51/49 mix delivers 30%. Full
tables and the verdict are in `RESULTS.md`.

## 8. Things that will differ between implementations

- Yield source: TradingView's TVC yields versus FRED's H.15 can differ by a few basis points on a given day,
  which can move the score by up to about half a point and occasionally flip a band near an edge.
- VIX source: nine days since 1990 on which Yahoo and FRED disagree (largest 2026-02-06).
- Calendar alignment: an input with no bar on an equity trading day (FRED yields on Columbus Day and Veterans
  Day) carries its last value; TradingView does the same.
- Drift versus daily rebalancing: immaterial.
- Cash return: any T-bill or money-market proxy; the rule's relative results do not depend on it.
