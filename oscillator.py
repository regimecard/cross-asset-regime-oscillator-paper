"""Python port of the TradingView "Cross-Asset Regime Oscillator" (regimecard, Pine v6).

Faithful to the published script, line for line:

  zClamped(src) = clamp((src - sma(src, 252)) / stdev(src, 252), -3, +3)       # stdev = POPULATION (Pine default)
  five signals, each z-scored on ITS OWN daily bar series:
      credit  = HYG/IEF          (+)
      vol     = VIX              (-)   sign flipped after z-scoring (identical to z-scoring -VIX)
      cycdef  = XLI/XLU          (+)
      curve   = US10Y - US03MY   (+)
      dollar  = DXY              (-)
  composite = mean of the signals that are not na (a signal is na until 252 bars exist or if stdev == 0)
  score     = clamp(50 + composite * 100/6, 0, 100)
  bands     = [0,20) RISK-OFF  [20,40) MILDLY OFF  [40,60) NEUTRAL  [60,80) MILDLY ON  [80,100] RISK-ON

Two timings are produced for every chart day D (equity trading day):

  score_raw[D]  : composite of each signal's LATEST bar with date <= D. This is the information set at the
                  close of day D (closes of D for every input that traded that day). Used for signals and
                  the "same close" execution.
  score_tv[D]   : what the TradingView chart PLOTS on bar D. The script requests zClamped(close)[1] inside
                  the "1D" security context with lookahead_on, so the plotted value is the z of each
                  signal's PREVIOUS confirmed daily bar. For an input that has a bar on D this is its bar
                  D-1. Numerically score_tv[D] == score_raw[previous bar] except around holidays of a
                  single input (FRED yields on bond-market holidays), where the [1] offset is taken on
                  that input's own calendar, exactly as Pine does.

Outputs data/oscillator_daily.csv with the per-signal clamped z-scores (raw timing), signal count,
composite, score, band, and the tv_ columns.

Usage: .venv/bin/python research/oscillator-paper/oscillator.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
LOOKBACK = 252          # Pine input default "Lookback (bars)"
CLAMP = 3.0             # Pine: math.max(-3, math.min(3, z))
BANDS = [(0, 20, "RISK-OFF"), (20, 40, "MILDLY OFF"), (40, 60, "NEUTRAL"), (60, 80, "MILDLY ON"), (80, 101, "RISK-ON")]
WEIGHTS = {"RISK-ON": 1.00, "MILDLY ON": 0.75, "NEUTRAL": 0.50, "MILDLY OFF": 0.25, "RISK-OFF": 0.00}
BAND_ORDER = ["RISK-OFF", "MILDLY OFF", "NEUTRAL", "MILDLY ON", "RISK-ON"]


def read_close(stem: str, col: str = "Close") -> pd.Series:
    d = pd.read_csv(RAW / f"{stem}.csv", parse_dates=["date"], index_col="date")
    s = pd.to_numeric(d[col], errors="coerce").dropna()
    s.name = stem
    return s.sort_index()


def read_fred(series: str) -> pd.Series:
    d = pd.read_csv(RAW / f"{series}.csv", parse_dates=["date"], index_col="date")
    return pd.to_numeric(d[series], errors="coerce").dropna().sort_index()


def z_clamped(src: pd.Series, length: int = LOOKBACK) -> pd.Series:
    """Pine zClamped on the series' own bars. ta.sma / ta.stdev (population) need `length` bars; na before."""
    m = src.rolling(length, min_periods=length).mean()
    s = src.rolling(length, min_periods=length).std(ddof=0)
    z = (src - m) / s
    z[~(s > 0)] = np.nan  # Pine: na when the deviation is zero (flat series)
    return z.clip(lower=-CLAMP, upper=CLAMP)


def band_of(score: float) -> str:
    if pd.isna(score):
        return "NO DATA"
    if score < 20:
        return "RISK-OFF"
    if score < 40:
        return "MILDLY OFF"
    if score < 60:
        return "NEUTRAL"
    if score < 80:
        return "MILDLY ON"
    return "RISK-ON"


def build_inputs() -> dict[str, tuple[pd.Series, float]]:
    """Return {signal: (daily series on its own calendar, sign)}, sign=+1 risk-on when higher, -1 when inverted."""
    hyg, ief = read_close("HYG"), read_close("IEF")
    xli, xlu = read_close("XLI"), read_close("XLU")
    vix = read_close("VIX")
    dxy = read_close("DXY")
    us10, us3m = read_fred("DGS10"), read_fred("DGS3MO")

    credit = (hyg / ief).dropna()            # bars only where both components traded (TradingView spread rule)
    cycdef = (xli / xlu).dropna()
    curve = (us10 - us3m).dropna()           # FRED prints nothing on bond-market holidays: no bar that day
    return {
        "credit": (credit.rename("credit"), +1.0),
        "vol": (vix.rename("vol"), -1.0),
        "cycdef": (cycdef.rename("cycdef"), +1.0),
        "curve": (curve.rename("curve"), +1.0),
        "dollar": (dxy.rename("dollar"), -1.0),
    }


def composite_from(zdf: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Pine: average of non-na signals; score = clamp(50 + comp*100/6, 0, 100)."""
    n = zdf.notna().sum(axis=1)
    comp = zdf.mean(axis=1, skipna=True)
    comp[n == 0] = np.nan
    score = (50.0 + comp * (100.0 / 6.0)).clip(lower=0.0, upper=100.0)
    return n, comp, score


def build() -> pd.DataFrame:
    chart_days = read_close("GSPC").index  # the chart symbol's daily bars: US equity trading days
    inputs = build_inputs()

    raw_cols, tv_cols = {}, {}
    for name, (series, sign) in inputs.items():
        z = sign * z_clamped(series)                           # on the input's own calendar
        z_prev = z.shift(1)                                    # Pine: zClamped(close)[1] inside the 1D context
        # as-of alignment to chart days: latest bar of the input with date <= chart day (lookahead_on semantics)
        raw_cols[f"z_{name}"] = z.reindex(z.index.union(chart_days)).ffill().reindex(chart_days)
        tv_cols[f"tvz_{name}"] = z_prev.reindex(z_prev.index.union(chart_days)).ffill().reindex(chart_days)
        # a chart day before the input's first bar must stay na (nothing to carry forward); ffill already does that

    out = pd.DataFrame(index=chart_days)
    out.index.name = "date"
    zraw = pd.DataFrame(raw_cols, index=chart_days)
    ztv = pd.DataFrame(tv_cols, index=chart_days)

    n, comp, score = composite_from(zraw)
    out = pd.concat([out, zraw], axis=1)
    out["n_signals"] = n
    out["composite"] = comp
    out["score"] = score
    out["band"] = out["score"].map(band_of)

    n2, comp2, score2 = composite_from(ztv)
    out = pd.concat([out, ztv], axis=1)
    out["tv_n_signals"] = n2
    out["tv_composite"] = comp2
    out["tv_score"] = score2
    out["tv_band"] = out["tv_score"].map(band_of)

    out = out[out["n_signals"] > 0]
    return out


def main() -> int:
    out = build()
    path = HERE / "data" / "oscillator_daily.csv"
    out.to_csv(path, float_format="%.6f")
    print("wrote", path, len(out), "rows", out.index[0].date(), "->", out.index[-1].date())

    first = {}
    for c in ["z_credit", "z_vol", "z_cycdef", "z_curve", "z_dollar"]:
        first[c] = out[c].first_valid_index().date()
    print("first non-na z by signal:", first)
    for k in [3, 4, 5]:
        d = out.index[out["n_signals"] >= k]
        print(f"first chart day with >= {k} signals: {d[0].date() if len(d) else None}")
    full = out[out["n_signals"] == 5]
    print("five-signal days:", len(full), full.index[0].date(), "->", full.index[-1].date())
    print("\nband counts (five-signal period, raw timing):")
    print(full["band"].value_counts().reindex(BAND_ORDER))
    print("\nlast 5 rows:")
    print(out[["z_credit", "z_vol", "z_cycdef", "z_curve", "z_dollar", "n_signals", "composite", "score", "band", "tv_score", "tv_band"]].tail(5).round(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
