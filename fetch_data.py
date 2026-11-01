"""Fetch every input of the Cross-Asset Regime Oscillator and the benchmark series from free sources.

Writes one CSV per series to data/raw/ and a manifest (data/SOURCES.md) with source, symbol, first and
last date, row count and SHA256. Re-running overwrites the files (downloads are deterministic up to
vendor revisions; the manifest records what was used).

Sources
  Yahoo Finance (via yfinance): HYG, IEF, XLI, XLU, ^VIX, DX-Y.NYB, ^SP500TR, SPY, VBMFX, ^GSPC
    Close = exchange close, split-adjusted, NOT dividend-adjusted (matches TradingView's default bars).
    Adj Close = dividend- and split-adjusted (total return proxy), used only for SPY/VBMFX/benchmarks.
  FRED (St. Louis Fed, CSV endpoint): DGS10, DGS3MO (constant-maturity Treasury yields, H.15, percent),
    DTB3 (3-month bill secondary market discount yield, percent), VIXCLS (CBOE VIX close, cross-check).

Usage: .venv/bin/python research/oscillator-paper/fetch_data.py
"""
from __future__ import annotations

import hashlib
import io
import sys
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import requests

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

YAHOO = {
    # file stem: (ticker, role)
    "HYG": ("HYG", "iShares iBoxx $ High Yield Corporate Bond ETF (credit numerator)"),
    "IEF": ("IEF", "iShares 7-10 Year Treasury Bond ETF (credit denominator)"),
    "XLI": ("XLI", "Industrial Select Sector SPDR (cyclical numerator)"),
    "XLU": ("XLU", "Utilities Select Sector SPDR (defensive denominator)"),
    "VIX": ("^VIX", "CBOE Volatility Index (equity volatility, inverted)"),
    "DXY": ("DX-Y.NYB", "ICE US Dollar Index (dollar, inverted)"),
    "SP500TR": ("^SP500TR", "S&P 500 Total Return index (forward returns, equity leg)"),
    "SPY": ("SPY", "SPDR S&P 500 ETF (investable cross-check)"),
    "VBMFX": ("VBMFX", "Vanguard Total Bond Market Index Fund (60/40 bond leg)"),
    "GSPC": ("^GSPC", "S&P 500 price index (US equity trading calendar)"),
}
FRED = {
    "DGS10": "10-Year Treasury constant maturity yield, percent (curve long end)",
    "DGS3MO": "3-Month Treasury constant maturity yield, percent (curve short end)",
    "DTB3": "3-Month Treasury bill secondary market rate, discount basis, percent (cash return)",
    "VIXCLS": "CBOE VIX close (cross-check of Yahoo ^VIX)",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_yahoo(stem: str, ticker: str) -> pd.DataFrame:
    import yfinance as yf

    d = yf.download(ticker, start="1960-01-01", progress=False, auto_adjust=False, threads=False)
    if d.empty:
        raise RuntimeError(f"empty download for {ticker}")
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    out = d[["Open", "High", "Low", "Close", "Adj Close", "Volume"]].copy()
    out.index = pd.to_datetime(out.index).tz_localize(None).normalize()
    out.index.name = "date"
    out = out.dropna(subset=["Close"])
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out.to_csv(RAW / f"{stem}.csv", float_format="%.6f")
    return out


def fetch_fred(series: str) -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text))
    d.columns = ["date", series]
    d["date"] = pd.to_datetime(d["date"])
    d[series] = pd.to_numeric(d[series], errors="coerce")  # FRED prints '.' on holidays
    d = d.set_index("date")
    d.to_csv(RAW / f"{series}.csv")
    return d


def main() -> int:
    rows = []
    for stem, (ticker, role) in YAHOO.items():
        d = fetch_yahoo(stem, ticker)
        p = RAW / f"{stem}.csv"
        rows.append(("Yahoo Finance", ticker, role, d.index[0].date(), d.index[-1].date(), len(d), p.name, sha256(p)))
        print(f"{stem:8s} {ticker:10s} {d.index[0].date()} -> {d.index[-1].date()} n={len(d)}")
    for series, role in FRED.items():
        d = fetch_fred(series)
        p = RAW / f"{series}.csv"
        valid = d[series].dropna()
        rows.append(("FRED", series, role, valid.index[0].date(), valid.index[-1].date(), len(valid), p.name, sha256(p)))
        print(f"{series:8s} {'FRED':10s} {valid.index[0].date()} -> {valid.index[-1].date()} n={len(valid)} (non-missing)")

    man = HERE / "data" / "SOURCES.md"
    with man.open("w") as f:
        f.write(f"# Data sources (fetched {date.today().isoformat()})\n\n")
        f.write("All series are free. Yahoo `Close` is the exchange close, split-adjusted but not dividend-adjusted, which is\n")
        f.write("what TradingView plots by default and therefore what the oscillator's ratios use. FRED yields are the H.15\n")
        f.write("constant-maturity series; FRED prints no value on bond-market holidays and those days are skipped, as a\n")
        f.write("TradingView daily bar would be. Row counts for FRED are non-missing observations.\n\n")
        f.write("| Source | Symbol | Role | First | Last | Rows | File | SHA256 |\n|---|---|---|---|---|---|---|---|\n")
        for src, sym, role, a, b, n, fn, h in rows:
            f.write(f"| {src} | `{sym}` | {role} | {a} | {b} | {n} | `data/raw/{fn}` | `{h[:16]}` |\n")
        f.write("\n## Mapping to the Pine script's symbols\n\n")
        f.write("| Pine symbol | Series used here | Note |\n|---|---|---|\n")
        f.write("| `AMEX:HYG/NASDAQ:IEF` | HYG Close / IEF Close, on days both traded | ratio of unadjusted closes, as TradingView builds a spread symbol |\n")
        f.write("| `CBOE:VIX` | ^VIX Close (Yahoo); FRED VIXCLS as a cross-check | same CBOE close |\n")
        f.write("| `AMEX:XLI/AMEX:XLU` | XLI Close / XLU Close | as above |\n")
        f.write("| `TVC:US10Y-TVC:US03MY` | FRED DGS10 minus DGS3MO, on days both are published | TradingView's TVC yields come from a different vendor and fixing time than the Fed's H.15 (about 3:30 pm ET); small level differences are expected and are the most likely source of any residual mismatch |\n")
        f.write("| `TVC:DXY` | DX-Y.NYB Close (ICE US Dollar Index) | same index; ICE close about 5 pm ET |\n")
        f.write("\nThe equity trading calendar (the chart symbol's bars) is taken from ^GSPC.\n")
    print("wrote", man)
    return 0


if __name__ == "__main__":
    sys.exit(main())
