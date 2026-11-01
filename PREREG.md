# Pre-registration: forward S&P 500 returns by band of the public Cross-Asset Regime Oscillator, and one allocation rule (2026-11-01)

Written and committed before any forward return was computed. What was looked at while writing this: the Pine
source of the indicator, the raw input files and their start dates (`data/SOURCES.md`), the oscillator series
produced by the port (`data/oscillator_daily.csv`): its score distribution, band counts, the pairwise
correlations of the five z-scores, and the values on the ten verification dates in `VERIFY.md`. No price series
was joined to the oscillator with any forward offset. The analysis script `analysis.py` is frozen with this
file; if a bug in it has to be fixed after the first run, the fix and its commit hash are listed in a
"changes after pre-registration" section of `RESULTS.md`. No parameter in this file changes after the run.

Scope rule: this study uses only the public TradingView indicator, as published. The indicator's own
defaults are the only parameters (252-bar lookback, +/-3 clamp, equal weights, bands at 20/40/60/80).
Nothing is tuned, and no alternative lookback, weight or band edge is tested.

## 0. Inputs (fixed)

- Oscillator: `data/oscillator_daily.csv` from `oscillator.py` (commit 5507674). Two timings per equity
  trading day D: `score` (closes through D: the information set at the close of D) and `tv_score` (the
  value TradingView plots on bar D, which is the previous confirmed bar of every input). `score[D]` equals
  `tv_score[next bar]` except around single-input holidays.
- Equity: S&P 500 Total Return index, Yahoo `^SP500TR`, daily close, from 1988-01-04. Buy-and-hold means
  holding this index with no cost.
- Cash: FRED `DTB3` (3-month bill, discount yield, percent). Daily cash return on trading day t =
  DTB3 (latest value as of t-1) / 100 / 252. Used both as the T-bill leg and as the risk-free rate in Sharpe.
- Bonds (60/40 only): Vanguard Total Bond Market Index Fund, Yahoo `VBMFX` adjusted close (total return).
- Calendar: US equity trading days (`^GSPC` bars). Horizons are counted in trading days on this calendar.

## 1. Samples

Structural fact known in advance: all five signals exist from **2008-04-09** (HYG, listed 2007-04-11, needs
252 bars). Before that, the indicator's own missing-data rule averages the signals that exist (four from
1999-12-21, three from 1990-12-28). Also known: in the five-signal period the score never reaches 80, so the
**RISK-ON band has zero days** and the allocation rule's 100 percent step is never used; the band counts are
RISK-OFF 153, MILDLY OFF 1,058, NEUTRAL 1,993, MILDLY ON 1,467, RISK-ON 0 (raw timing, 4,671 days to
2026-10-30).

- **Primary sample:** five-signal period, signal days 2008-04-09 to the last day with a complete forward
  window (for h = 60, about 2026-08-05).
- **In-sample (IS):** signal days 2008-04-09 to 2017-12-29. **Out-of-sample (OOS):** 2018-01-02 onward.
  Chronological split, fixed now, roughly halving the sample. The indicator was published in 2026 so there
  is no meaningful post-publication period; OOS here means "the second half, not looked at separately when
  reading the first half", and both halves are only ever computed together by the frozen script.
- **Extended check (reduced-signal composite):** 1990-12-28 to 2008-04-08, the oscillator as the script
  itself would compute it on a chart covering those years (three, then four signals). Reported with the
  label "reduced-signal", carries no headline verdict.
- **Decades:** 2008-04-09 to 2009-12-31; 2010 to 2019; 2020 to end. Reported, no verdict.

## 2. Band forward-return tests

For every signal day t in the sample, band b(t) from `score[t]` and forward total return
r_h(t) = TR[t+h] / TR[t] - 1 for **h = 5, 20, 60** trading days. Per band and horizon, report: days,
non-overlapping windows (greedy on the band's own dates: take a day, skip h trading days, repeat), mean,
median, win rate (share of r_h > 0), and a 90 percent block-bootstrap interval for the mean. Also the
all-days mean for reference and the same table with the forward window starting one day later
(t+1 to t+1+h), which is the return an investor who acts on the plotted TradingView value at the next close
would earn.

**Bootstrap (all tests):** stationary block bootstrap (Politis and Romano) on the day series, geometric
block length with expected length **63 trading days**, circular wrap, **5,000 resamples**, numpy
`default_rng(20261101)`. Every resample recomputes every band jointly, so differences between bands have
their own intervals. Intervals are 5th to 95th percentile. A resample where a compared band is empty is
dropped and the valid count reported. A band with fewer than **10 non-overlapping windows** at a horizon is
flagged THIN and carries no verdict at that horizon (RISK-OFF at h = 60 is at risk: 153 days).

**H1 (band ordering).** Risk-on readings precede higher returns than risk-off readings. Statistic:
mean r_h over the upper bands (MILDLY ON and RISK-ON) minus mean r_h over the lower bands (RISK-OFF and
MILDLY OFF). **Supported** if the 90 percent interval of the difference lies above zero at **both h = 20 and
h = 60** in the primary sample and the point estimate is positive in OOS on its own. **Contrary** if the
interval lies below zero at both horizons. **Null** otherwise. The h = 5 result and the monotonicity of
the four occupied bands are reported, no verdict.

**H2 (dead zone).** The MILDLY OFF band (20 to 40) has a lower mean forward return than both of its
neighbours, RISK-OFF and NEUTRAL. Statistic at **h = 60** (headline): D = min(mean_RISKOFF, mean_NEUTRAL)
minus mean_MILDLYOFF, recomputed in every resample. **Dip is real** if D > 0 at the point estimate and the
5th percentile of D is above zero. **No dip** if D <= 0 at the point estimate. **Unclear** otherwise. If
RISK-OFF is THIN at h = 60, the headline uses NEUTRAL alone as the comparator (D = mean_NEUTRAL minus
mean_MILDLYOFF) and says so. Reported as checks, no verdict: the same D at h = 20 and h = 5, D on medians,
and D in IS and OOS separately. Descriptive, no verdict: mean r_60 by 10-point score bin with intervals.

## 3. The allocation rule (fixed now)

- **Check** at every US equity close. Band from `score[t]` (closes through t, including the VIX 16:15 ET and
  dollar-index 17:00 ET closes and the day's Treasury yields).
- **Equity weight by band:** RISK-ON 100 percent, MILDLY ON 75, NEUTRAL 50, MILDLY OFF 25, RISK-OFF 0.
  The remainder in T-bills. Equity = S&P 500 total return index. One rule, no variants.
- **Execution A (same close):** the weight set from `score[t]` earns the index return from the close of t
  to the close of t+1. This is slightly optimistic because two inputs close after 16:00 ET.
- **Execution B (next close):** the weight set from `score[t]` earns the return from the close of t+1 to
  the close of t+2. This is exactly "act at the close on the value the TradingView chart shows that day"
  and is the headline execution.
- **Costs:** 5 basis points of the traded equity amount at every weight change (|w_new - w_old| x 0.0005),
  charged on the execution day. The T-bill side is treated as free. Sensitivity at 0, 10 and 20 basis points
  is reported.
- **Benchmarks:** (i) buy and hold the index, no cost; (ii) 60/40 index and VBMFX, rebalanced to target at
  the last trading day of each month, 5 basis points on the traded amount; (iii) exposure-matched constant
  mix: equity weight equal to the rule's realised mean weight over the primary sample (Execution B),
  remainder in T-bills, rebalanced at month end with the same cost.
- **Metrics:** CAGR, annualised volatility (sqrt 252), Sharpe (mean daily excess over cash x 252 / annualised
  volatility), Sortino (same numerator over annualised downside deviation of excess returns below zero),
  maximum drawdown, worst calendar year (partial first and last years marked), one-way turnover per year
  (sum of |weight changes| / years), time in market (mean equity weight; share of days with weight above
  zero; share of days at the maximum weight observed).

**H3 (allocation edge).** Statistic: Sharpe(rule, Execution B, 5 bp) minus Sharpe(buy and hold), with a 90
percent interval from the same stationary block bootstrap applied jointly to the paired daily return series
(blocks of days, so both series are resampled together). Sharpe is the right comparison because mixing an
asset with cash leaves its Sharpe unchanged; a positive difference is timing skill, not just lower
exposure. **Supported** if the interval lies above zero in the primary sample and the OOS point estimate is
positive. **Contrary** if the interval lies below zero. **Null** otherwise. Reported, no verdict: the same
versus 60/40 and versus the constant mix; CAGR and maximum drawdown versus all three; Execution A; the cost
sensitivity; IS and OOS and decade tables; the extended reduced-signal history.

## 4. Verdict rule (fixed now)

- **Edge is real:** H3 supported, and at least one of H1 or H2 supported (a mechanism behind the rule).
- **Suggestive:** H3 Null with positive point estimates in both IS and OOS, or H3 supported with neither
  H1 nor H2 supported.
- **No edge:** anything else, including H3 Contrary.
The verdict is stated for Execution B after 5 basis points. Execution A is reported beside it; if A passes
and B fails, the headline is "no edge, and the apparent edge depends on trading before two inputs close".

## 5. Multiple looks

Three horizons, two timings for the forward windows, five bands, four samples (full, IS, OOS, extended),
three decades, two executions, four cost levels, three benchmarks. Only H1 (h = 20 and 60, primary sample),
H2 (h = 60, primary sample) and H3 (Execution B, 5 bp, primary sample with the OOS sign check) carry
verdicts. Everything else is labelled a check, a sensitivity or descriptive, and is reported in full
whichever way it comes out.

## 6. Outputs

- `analysis.py` (frozen with this file), `RESULTS.md`, `results/*.csv`, `paper/figures/*.png`.
- Everything in `RESULTS.md` and the paper that depends on the port being right is marked "pending
  TradingView verification" until `verify_tv.py` passes.
