"""Check the Python port against readings taken from the TradingView chart.

VERIFY.md holds a table of 10 chart dates. For each, read the "Regime score" the indicator PLOTS on that
bar in TradingView (hover the bar on a 1D chart with the default 252 lookback) and put it in the
`TradingView value` column. Then run:

    .venv/bin/python research/oscillator-paper/verify_tv.py

Exit code 0 if every filled-in reading is within 1.0 point of the port's `tv_score` (the plotted value,
which uses the previous confirmed daily bar of each input, as the Pine `[1]` offset does); exit code 1
otherwise. Rows left blank are reported as PENDING and do not fail the check, but the check also fails
if fewer than 10 rows are filled in (so it cannot pass by omission).

The script also reports whether the readings match the port's `score` column (same-day closes) better than
`tv_score`; if so, the one-bar offset in the Pine request behaves differently from what the port assumes.

Usage: verify_tv.py [--write]   (--write regenerates the table in VERIFY.md from data/oscillator_daily.csv,
                                 keeping any TradingView values already entered)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
VERIFY = HERE / "VERIFY.md"
TOL = 1.0
DATES = [
    "2011-08-10",  # US downgrade week
    "2013-05-22",  # taper tantrum start, risk-on
    "2015-08-25",  # August 2015 selloff
    "2017-10-05",  # low-vol melt-up
    "2018-12-24",  # December 2018 low
    "2020-03-16",  # COVID crash
    "2020-11-09",  # vaccine day
    "2022-06-16",  # 2022 bear market
    "2025-04-08",  # tariff shock
    "2026-10-30",  # most recent close in the data
]
ROW_RE = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([-\d.]+)\s*\|\s*([-\d.]+)\s*\|\s*([A-Z\- ]+?)\s*\|\s*([-\d.]*)\s*\|")


def existing_readings() -> dict[str, float]:
    if not VERIFY.exists():
        return {}
    out = {}
    for line in VERIFY.read_text().splitlines():
        m = ROW_RE.match(line)
        if m and m.group(5).strip():
            out[m.group(1)] = float(m.group(5))
    return out


def write_table() -> None:
    o = pd.read_csv(HERE / "data" / "oscillator_daily.csv", parse_dates=["date"], index_col="date")
    keep = existing_readings()
    lines = [
        "# Verification against TradingView",
        "",
        "The port can only be called faithful once it matches the chart. Open any US equity 1D chart (SPY) on",
        "TradingView, add the public **Cross-Asset Regime Oscillator** (regimecard) with the default 252 lookback,",
        "hover each date below and read the plotted **Regime score** (one decimal). Enter it in the",
        "`TradingView value` column and run `.venv/bin/python research/oscillator-paper/verify_tv.py`.",
        "",
        "`tv_score` is the port's prediction of the PLOTTED value on that bar (the Pine request is",
        "`zClamped(close)[1]` inside the 1D context, so the bar shows each input's previous confirmed daily",
        "bar). `score` is the same-day-close value the paper uses as the signal at that close; on the chart it",
        "appears on the NEXT bar. If your readings match `score` better than `tv_score`, say so: the check prints",
        "which column fits.",
        "",
        f"Tolerance: {TOL:.1f} point on the 0 to 100 scale. Anything larger is a mismatch to be explained before the",
        "paper's numbers are trusted. Expected sources of small differences: TradingView's `TVC:US10Y` and",
        "`TVC:US03MY` come from a different vendor and fixing time than FRED's H.15 yields, and a handful of VIX",
        "closes differ between Yahoo and FRED (listed at the bottom).",
        "",
        "| Date | tv_score (plotted, port) | score (same-day close, port) | Band (plotted) | TradingView value |",
        "|---|---|---|---|---|",
    ]
    for d in DATES:
        ts = pd.Timestamp(d)
        if ts not in o.index:
            raise SystemExit(f"{d} is not a trading day in the data")
        r = o.loc[ts]
        tvv = f"{keep[d]:.1f}" if d in keep else ""
        lines.append(f"| {d} | {r.tv_score:.1f} | {r.score:.1f} | {r.tv_band} | {tvv} |")
    lines += [
        "",
        "Per-signal clamped z-scores on the same dates (plotted timing), to localise any mismatch with the",
        '"Show signal breakdown" option of the indicator:',
        "",
        "| Date | Credit | Volatility | Cyclical/Defensive | Yield curve | Dollar | Composite |",
        "|---|---|---|---|---|---|---|",
    ]
    for d in DATES:
        r = o.loc[pd.Timestamp(d)]
        lines.append(
            f"| {d} | {r.tvz_credit:+.2f} | {r.tvz_vol:+.2f} | {r.tvz_cycdef:+.2f} | {r.tvz_curve:+.2f} | {r.tvz_dollar:+.2f} | {r.tv_composite:+.2f} |"
        )
    lines += [
        "",
        "## Known data caveats",
        "",
        "- Yahoo `^VIX` and FRED `VIXCLS` disagree by more than 0.05 on 9 of 9,274 common days (largest: 2026-02-06,",
        "  20.37 vs 17.76; 2014-10-15, 25.27 vs 26.25). The port uses Yahoo. A single-day VIX gap of 1 point moves",
        "  the score by about 0.7 points (1 / stdev ~ 5 / 5 signals x 16.7).",
        "- FRED yields have no value on bond-market holidays (Columbus Day, Veterans Day); the port skips those",
        "  days for the curve signal exactly as a missing TradingView bar would be skipped.",
        "- FRED publishes a day's yields the next business day, so the final row's `score` can change when FRED",
        "  catches up; historical rows do not.",
        "",
        "Status: PENDING (no TradingView values entered yet)." if not keep else f"Status: {len(keep)} of {len(DATES)} readings entered.",
    ]
    VERIFY.write_text("\n".join(lines) + "\n")
    print("wrote", VERIFY)


def check() -> int:
    o = pd.read_csv(HERE / "data" / "oscillator_daily.csv", parse_dates=["date"], index_col="date")
    readings = existing_readings()
    fails, pending = 0, 0
    err_tv, err_raw = [], []
    print(f"{'date':12s} {'TV':>7s} {'tv_score':>9s} {'diff':>7s}   {'score':>7s} {'diff':>7s}  result")
    for d in DATES:
        r = o.loc[pd.Timestamp(d)]
        if d not in readings:
            pending += 1
            print(f"{d:12s} {'':>7s} {r.tv_score:9.2f} {'':>7s}   {r.score:7.2f} {'':>7s}  PENDING")
            continue
        v = readings[d]
        e1, e2 = v - r.tv_score, v - r.score
        err_tv.append(abs(e1)); err_raw.append(abs(e2))
        ok = abs(e1) <= TOL
        fails += 0 if ok else 1
        print(f"{d:12s} {v:7.2f} {r.tv_score:9.2f} {e1:+7.2f}   {r.score:7.2f} {e2:+7.2f}  {'ok' if ok else 'MISMATCH'}")
    if err_tv:
        print(f"\nmean |diff| vs tv_score: {sum(err_tv)/len(err_tv):.2f}   vs score: {sum(err_raw)/len(err_raw):.2f}")
        if sum(err_raw) < sum(err_tv):
            print("NOTE: readings fit the same-day `score` column better than `tv_score`; the assumed one-bar offset may be wrong.")
    if pending:
        print(f"\n{pending} of {len(DATES)} readings still PENDING; the check cannot pass until all are entered.")
        return 1
    if fails:
        print(f"\nFAIL: {fails} of {len(DATES)} readings differ by more than {TOL} point.")
        return 1
    print(f"\nPASS: all {len(DATES)} readings within {TOL} point.")
    return 0


if __name__ == "__main__":
    if "--write" in sys.argv:
        write_table()
        sys.exit(0)
    sys.exit(check())
