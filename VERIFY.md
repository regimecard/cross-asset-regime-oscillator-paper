# Verification against TradingView

The port can only be called faithful once it matches the chart. Open any US equity 1D chart (SPY) on
TradingView, add the public **Cross-Asset Regime Oscillator** (regimecard) with the default 252 lookback,
hover each date below and read the plotted **Regime score** (one decimal). Enter it in the
`TradingView value` column and run `.venv/bin/python research/oscillator-paper/verify_tv.py`.

`tv_score` is the port's prediction of the PLOTTED value on that bar (the Pine request is
`zClamped(close)[1]` inside the 1D context, so the bar shows each input's previous confirmed daily
bar). `score` is the same-day-close value the paper uses as the signal at that close; on the chart it
appears on the NEXT bar. If your readings match `score` better than `tv_score`, say so: the check prints
which column fits.

Tolerance: 1.0 point on the 0 to 100 scale. Anything larger is a mismatch to be explained before the
paper's numbers are trusted. Expected sources of small differences: TradingView's `TVC:US10Y` and
`TVC:US03MY` come from a different vendor and fixing time than FRED's H.15 yields, and a handful of VIX
closes differ between Yahoo and FRED (listed at the bottom).

| Date | tv_score (plotted, port) | score (same-day close, port) | Band (plotted) | TradingView value |
|---|---|---|---|---|
| 2011-08-10 | 23.0 | 20.6 | MILDLY OFF | 24.1 |
| 2013-05-22 | 61.4 | 62.6 | MILDLY ON | 62.1 |
| 2015-08-25 | 20.0 | 23.2 | MILDLY OFF | 20.6 |
| 2017-10-05 | 62.9 | 64.1 | MILDLY ON | 63.0 |
| 2018-12-24 | 7.0 | 7.0 | RISK-OFF | 7.2 |
| 2020-03-16 | 26.2 | 26.5 | MILDLY OFF | 26.3 |
| 2020-11-09 | 62.9 | 65.2 | MILDLY ON | 62.9 |
| 2022-06-16 | 32.4 | 27.1 | MILDLY OFF | 32.9 |
| 2025-04-08 | 30.1 | 30.8 | MILDLY OFF | 29.9 |
| 2026-10-30 | 51.2 | 45.1 | NEUTRAL | 50.6 |

Per-signal clamped z-scores on the same dates (plotted timing), to localise any mismatch with the
"Show signal breakdown" option of the indicator:

| Date | Credit | Volatility | Cyclical/Defensive | Yield curve | Dollar | Composite |
|---|---|---|---|---|---|---|
| 2011-08-10 | -2.80 | -3.00 | -1.27 | -2.11 | +1.07 | -1.62 |
| 2013-05-22 | +1.54 | +0.88 | +1.30 | +1.50 | -1.80 | +0.68 |
| 2015-08-25 | -2.75 | -3.00 | -2.04 | -1.05 | -0.16 | -1.80 |
| 2017-10-05 | +0.70 | +1.14 | +1.49 | -0.87 | +1.41 | +0.77 |
| 2018-12-24 | -3.00 | -2.92 | -2.91 | -2.73 | -1.33 | -2.58 |
| 2020-03-16 | -3.00 | -3.00 | -2.76 | +2.97 | -1.36 | -1.43 |
| 2020-11-09 | -0.03 | +0.23 | +0.70 | +1.23 | +1.76 | +0.78 |
| 2022-06-16 | -0.13 | -1.41 | -1.46 | +0.15 | -2.45 | -1.06 |
| 2025-04-08 | -2.14 | -3.00 | -2.38 | +0.80 | +0.76 | -1.19 |
| 2026-10-30 | +0.50 | +0.25 | +0.42 | +1.09 | -1.89 | +0.07 |

## Known data caveats

- Yahoo `^VIX` and FRED `VIXCLS` disagree by more than 0.05 on 9 of 9,274 common days (largest: 2026-02-06,
  20.37 vs 17.76; 2014-10-15, 25.27 vs 26.25). The port uses Yahoo. A single-day VIX gap of 1 point moves
  the score by about 0.7 points (1 / stdev ~ 5 / 5 signals x 16.7).
- FRED yields have no value on bond-market holidays (Columbus Day, Veterans Day); the port skips those
  days for the curve signal exactly as a missing TradingView bar would be skipped.
- FRED publishes a day's yields the next business day, so the final row's `score` can change when FRED
  catches up; historical rows do not.

Status: READ 2026-11-01 (SPY 1D, default lookback, crosshair on each bar). 9 of 10 within the 1.0 tolerance;
2011-08-10 at +1.13. Mean absolute difference 0.42 against `tv_score`, 2.26 against `score`: the plotted-value
offset is confirmed. The "Show signal breakdown" table on the latest bar (2026-10-30) printed Credit +0.50,
Volatility +0.25, Cyclical/Defensive +0.42 (identical to the port), Yield curve about +0.7 and Dollar about -1.7
(port +1.09 and -1.89): the residual is entirely in the two TVC-sourced inputs. No band differs on any date.
The 2011-08-10 bar follows the 2011-08-09 FOMC statement, when the 10-year yield moved by tens of basis points
within the session; a different yield fixing time explains a 1-point score difference. `verify_tv.py` reports
the one date as MISMATCH by design; the tolerance was not changed.
