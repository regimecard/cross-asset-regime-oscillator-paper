"""Pre-registered tests for the Cross-Asset Regime Oscillator paper (PREREG.md, 2026-11-01).

Frozen with PREREG.md before any forward return was computed. Reads data/oscillator_daily.csv and the raw
benchmark files, writes results/*.csv, results/tables.md (every table in markdown) and paper/figures/*.png.
RESULTS.md and the paper are written by hand from those outputs.

Usage: .venv/bin/python research/oscillator-paper/analysis.py
"""
from __future__ import annotations

import json
import sys
import warnings
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.ticker
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)  # all-NaN slices for the empty RISK-ON band
HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
RES = HERE / "results"
FIG = HERE / "paper" / "figures"
RES.mkdir(exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

# ---------------- fixed parameters (PREREG.md) ----------------
HORIZONS = [5, 20, 60]
BANDS = ["RISK-OFF", "MILDLY OFF", "NEUTRAL", "MILDLY ON", "RISK-ON"]
WEIGHTS = {"RISK-ON": 1.00, "MILDLY ON": 0.75, "NEUTRAL": 0.50, "MILDLY OFF": 0.25, "RISK-OFF": 0.00}
PRIMARY_START = pd.Timestamp("2008-04-09")
IS_END = pd.Timestamp("2017-12-29")
OOS_START = pd.Timestamp("2018-01-02")
EXT_START, EXT_END = pd.Timestamp("1990-12-28"), pd.Timestamp("2008-04-08")
DECADES = [("2008-09", "2008-04-09", "2009-12-31"), ("2010s", "2010-01-01", "2019-12-31"), ("2020s", "2020-01-01", "2026-12-31")]
BOOT_N = 5000
BLOCK_LEN = 63
SEED = 20261101
COST_BPS = 5
COST_GRID = [0, 5, 10, 20]
THIN_WINDOWS = 10
CI = (5, 95)

# ---------------- chart conventions (dataviz reference palette) ----------------
INK, INK2, MUTED, GRID, BASE, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE, ORANGE, AQUA, YELLOW, VIOLET, RED = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6", "#e34948"
ORDINAL = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]  # five ordered bands, light -> dark blue
BAND_COLOR = dict(zip(BANDS, ORDINAL))
plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 9, "axes.edgecolor": BASE, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF, "axes.facecolor": SURF,
    "legend.frameon": False, "axes.axisbelow": True, "axes.titlecolor": INK, "axes.titlesize": 10, "axes.titleweight": "bold",
})


def savefig(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=150)
    plt.close(fig)


# ---------------- data ----------------
def load_frame() -> pd.DataFrame:
    o = pd.read_csv(HERE / "data" / "oscillator_daily.csv", parse_dates=["date"], index_col="date")
    tr = pd.read_csv(RAW / "SP500TR.csv", parse_dates=["date"], index_col="date")["Close"]
    vb = pd.read_csv(RAW / "VBMFX.csv", parse_dates=["date"], index_col="date")["Adj Close"]
    tb = pd.read_csv(RAW / "DTB3.csv", parse_dates=["date"], index_col="date")["DTB3"].dropna()
    df = o[["score", "band", "tv_score", "tv_band", "n_signals"]].copy()
    df["tr"] = tr.reindex(df.index)
    df = df[df["tr"].notna()]  # equity days with an index close (from 1988)
    df["r_eq"] = df["tr"].pct_change()
    df["r_bond"] = vb.reindex(df.index).ffill().pct_change()
    tb_asof = tb.reindex(tb.index.union(df.index)).ffill().reindex(df.index)
    df["r_cash"] = tb_asof.shift(1) / 100.0 / 252.0  # yield known as of the prior day
    for h in HORIZONS:
        df[f"r{h}"] = df["tr"].shift(-h) / df["tr"] - 1.0           # close t -> close t+h
        df[f"r{h}_next"] = df["tr"].shift(-h - 1) / df["tr"].shift(-1) - 1.0  # close t+1 -> close t+1+h
    df["w_signal"] = df["band"].map(WEIGHTS)
    return df


# ---------------- stationary block bootstrap ----------------
def stationary_indices(n: int, B: int, L: float, rng: np.random.Generator) -> np.ndarray:
    p = 1.0 / L
    starts = rng.integers(0, n, size=(B, n), dtype=np.int64)
    cont = rng.random((B, n)) >= p
    idx = np.empty((B, n), dtype=np.int64)
    idx[:, 0] = starts[:, 0]
    for j in range(1, n):
        idx[:, j] = np.where(cont[:, j], (idx[:, j - 1] + 1) % n, starts[:, j])
    return idx


def boot_band_stats(r: np.ndarray, band: np.ndarray, idx: np.ndarray, bands=BANDS, chunk=500):
    """Per-resample mean and median of r within each band. Returns dict band -> (means[B], medians[B])."""
    B = idx.shape[0]
    out = {b: (np.full(B, np.nan), np.full(B, np.nan)) for b in bands}
    for s in range(0, B, chunk):
        ii = idx[s:s + chunk]
        rr = r[ii]
        bb = band[ii]
        for b in bands:
            m = bb == b
            cnt = m.sum(axis=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                means = np.where(cnt > 0, (rr * m).sum(axis=1) / cnt, np.nan)
            med = np.nanmedian(np.where(m, rr, np.nan), axis=1) if m.any() else np.full(len(ii), np.nan)
            out[b][0][s:s + chunk] = means
            out[b][1][s:s + chunk] = med
    return out


def nonoverlap_windows(dates_pos: np.ndarray, h: int) -> int:
    n, last = 0, -10**9
    for p in dates_pos:
        if p >= last + h:
            n += 1
            last = p
    return n


def pct(x, k=2):
    return f"{100 * x:.{k}f}"


def ci_str(lo, hi, k=2):
    return f"[{100 * lo:.{k}f}, {100 * hi:.{k}f}]"


# ---------------- band tables ----------------
def band_table(sub: pd.DataFrame, label: str, rng_seed_offset: int, timing="", do_boot=True):
    """Full band table for one sample. Returns (rows DataFrame, boot dict by horizon)."""
    rows, boots = [], {}
    pos = np.arange(len(sub))
    for h in HORIZONS:
        col = f"r{h}{timing}"
        d = sub[[col, "band"]].dropna()
        r = d[col].to_numpy()
        band = d["band"].to_numpy()
        p = pos[: len(d)] if len(d) == len(sub) else np.arange(len(d))
        bs = None
        if do_boot and len(d) > BLOCK_LEN:
            rng = np.random.default_rng(SEED + rng_seed_offset + h)
            idx = stationary_indices(len(d), BOOT_N, BLOCK_LEN, rng)
            bs = boot_band_stats(r, band, idx)
            boots[h] = (bs, r, band)
        allmean = r.mean()
        for b in BANDS:
            m = band == b
            n = int(m.sum())
            win = nonoverlap_windows(p[m], h) if n else 0
            row = dict(sample=label, timing=timing or "same", h=h, band=b, days=n, windows=win,
                       thin=(win < THIN_WINDOWS), mean=np.nan, median=np.nan, winrate=np.nan, lo=np.nan, hi=np.nan, allmean=allmean)
            if n:
                row.update(mean=r[m].mean(), median=np.median(r[m]), winrate=(r[m] > 0).mean())
                if bs is not None:
                    v = bs[b][0]
                    v = v[~np.isnan(v)]
                    if len(v):
                        row.update(lo=np.percentile(v, CI[0]), hi=np.percentile(v, CI[1]), valid=len(v))
            rows.append(row)
    return pd.DataFrame(rows), boots


def md_band_table(tab: pd.DataFrame) -> str:
    out = []
    for h in HORIZONS:
        t = tab[tab.h == h]
        out.append(f"\n**h = {h} trading days** (all-days mean {pct(t.allmean.iloc[0])}%)\n")
        out.append("| Band | Days | Non-overlapping windows | Mean % | 90% CI (mean) | Median % | Win rate % |")
        out.append("|---|---|---|---|---|---|---|")
        for _, r in t.iterrows():
            if r.days == 0:
                out.append(f"| {r.band} | 0 | 0 | | | | |")
                continue
            flag = " THIN" if r.thin else ""
            ci = ci_str(r.lo, r.hi) if not np.isnan(r.lo) else "n/a"
            out.append(f"| {r.band} | {r.days} | {r.windows}{flag} | {pct(r['mean'])} | {ci} | {pct(r['median'])} | {100 * r.winrate:.1f} |")
    return "\n".join(out)


def h1_h2(boots, sub: pd.DataFrame, label: str):
    """H1 (upper minus lower bands) and H2 (dead zone D) point estimates and intervals per horizon."""
    rows = []
    for h in HORIZONS:
        bs, r, band = boots[h]
        upper = np.isin(band, ["MILDLY ON", "RISK-ON"])
        lower = np.isin(band, ["RISK-OFF", "MILDLY OFF"])
        h1_pt = r[upper].mean() - r[lower].mean()
        # bootstrap of grouped means needs grouped resampling: recompute from the per-band means weighted by counts is
        # not exact, so redo with a 2-group label on the same indices (same seed -> same idx)
        rng = np.random.default_rng(SEED + (0 if label == "primary" else 1000) + h)
        idx = stationary_indices(len(r), BOOT_N, BLOCK_LEN, rng)
        grp = np.where(upper, "U", np.where(lower, "L", "N"))
        g = boot_band_stats(r, grp, idx, bands=["U", "L", "N"])
        h1_b = g["U"][0] - g["L"][0]
        h1_b = h1_b[~np.isnan(h1_b)]
        # H2
        mo, ro, ne = bs["MILDLY OFF"], bs["RISK-OFF"], bs["NEUTRAL"]
        d_both = np.minimum(ro[0], ne[0]) - mo[0]
        d_neut = ne[0] - mo[0]
        d_med_both = np.minimum(ro[1], ne[1]) - mo[1]
        pt_mo = r[band == "MILDLY OFF"].mean()
        pt_ro = r[band == "RISK-OFF"].mean() if (band == "RISK-OFF").any() else np.nan
        pt_ne = r[band == "NEUTRAL"].mean()
        medpt = np.median(r[band == "MILDLY OFF"])
        med_ro = np.median(r[band == "RISK-OFF"]) if (band == "RISK-OFF").any() else np.nan
        med_ne = np.median(r[band == "NEUTRAL"])
        rows.append(dict(
            sample=label, h=h,
            h1_point=h1_pt, h1_lo=np.percentile(h1_b, CI[0]), h1_hi=np.percentile(h1_b, CI[1]), h1_valid=len(h1_b),
            d_both_point=np.nanmin([pt_ro, pt_ne]) - pt_mo, d_both_lo=np.nanpercentile(d_both, CI[0]), d_both_hi=np.nanpercentile(d_both, CI[1]),
            d_both_valid=int((~np.isnan(d_both)).sum()),
            d_neut_point=pt_ne - pt_mo, d_neut_lo=np.nanpercentile(d_neut, CI[0]), d_neut_hi=np.nanpercentile(d_neut, CI[1]),
            d_med_point=np.nanmin([med_ro, med_ne]) - medpt, d_med_lo=np.nanpercentile(d_med_both, CI[0]), d_med_hi=np.nanpercentile(d_med_both, CI[1]),
            mean_ro=pt_ro, mean_mo=pt_mo, mean_ne=pt_ne,
        ))
    return pd.DataFrame(rows)


def score_bins(sub: pd.DataFrame, label: str):
    d = sub[["r60", "score"]].dropna()
    edges = list(range(0, 90, 10))
    lab = [f"{a}-{a + 10}" for a in edges[:-1]]
    d = d.assign(bin=pd.cut(d["score"], bins=edges, labels=lab, right=False, include_lowest=True).astype(str))
    r, b = d["r60"].to_numpy(), d["bin"].to_numpy()
    rng = np.random.default_rng(SEED + 777)
    idx = stationary_indices(len(d), BOOT_N, BLOCK_LEN, rng)
    bs = boot_band_stats(r, b, idx, bands=lab)
    rows = []
    for k in lab:
        m = b == k
        v = bs[k][0]
        v = v[~np.isnan(v)]
        rows.append(dict(sample=label, bin=k, days=int(m.sum()), mean=r[m].mean() if m.any() else np.nan,
                         median=np.median(r[m]) if m.any() else np.nan, winrate=(r[m] > 0).mean() if m.any() else np.nan,
                         lo=np.percentile(v, CI[0]) if len(v) else np.nan, hi=np.percentile(v, CI[1]) if len(v) else np.nan))
    return pd.DataFrame(rows)


# ---------------- allocation simulator ----------------
def simulate(r_risky: np.ndarray, r_safe: np.ndarray, target: np.ndarray, rebalance: np.ndarray, cost: float, w0: float | None = None):
    """Two-asset portfolio with drift. Positions held during day t were set at the close of t-1.
    target[t], rebalance[t]: at the close of day t (after that day's returns) trade to target[t] if rebalance[t].
    Returns daily portfolio returns, held weight during each day, traded amount (fraction of wealth) per day."""
    n = len(r_risky)
    ret = np.zeros(n)
    held = np.zeros(n)
    traded = np.zeros(n)
    if w0 is None:  # benchmarks start at their target; signal-driven rules pass w0=0 (cash until the first signal)
        w0 = target[0] if not np.isnan(target[0]) else 0.0
    E, S = w0, 1.0 - w0
    for t in range(n):
        V0 = E + S
        held[t] = E / V0 if V0 > 0 else 0.0
        E *= 1.0 + (r_risky[t] if not np.isnan(r_risky[t]) else 0.0)
        S *= 1.0 + (r_safe[t] if not np.isnan(r_safe[t]) else 0.0)
        V = E + S
        if rebalance[t] and not np.isnan(target[t]):
            trade = abs(target[t] * V - E)
            fee = cost * trade
            V -= fee
            E = target[t] * V
            S = V - E
            traded[t] = trade / (V + fee)
        ret[t] = V / V0 - 1.0
    return ret, held, traded


def metrics(ret: pd.Series, cash: pd.Series, held: pd.Series | None = None, traded: pd.Series | None = None) -> dict:
    ret = ret.dropna()
    n = len(ret)
    years = n / 252.0
    growth = (1 + ret).prod()
    cagr = growth ** (1 / years) - 1 if years > 0 else np.nan
    vol = ret.std(ddof=1) * np.sqrt(252)
    ex = ret - cash.reindex(ret.index).fillna(0.0)
    sharpe = ex.mean() * 252 / vol if vol > 0 else np.nan
    dd_ex = ex[ex < 0]
    ddev = np.sqrt((dd_ex ** 2).sum() / n) * np.sqrt(252)
    sortino = ex.mean() * 252 / ddev if ddev > 0 else np.nan
    curve = (1 + ret).cumprod()
    mdd = (curve / curve.cummax() - 1).min()
    yr = (1 + ret).groupby(ret.index.year).prod() - 1
    worst_year = yr.min()
    worst_year_label = str(yr.idxmin())
    out = dict(cagr=cagr, vol=vol, sharpe=sharpe, sortino=sortino, maxdd=mdd, worst_year=worst_year, worst_year_label=worst_year_label, years=years)
    if held is not None:
        hh = held.reindex(ret.index)
        out.update(mean_weight=hh.mean(), pct_in=(hh > 1e-9).mean(), pct_max=(hh >= hh.max() - 1e-9).mean())
    if traded is not None:
        out.update(turnover=traded.reindex(ret.index).sum() / years)
    return out


def month_end_mask(index: pd.DatetimeIndex) -> np.ndarray:
    nxt = pd.Series(index).shift(-1)
    return ((nxt.dt.month != pd.Series(index).dt.month) | nxt.isna()).to_numpy()


def run_portfolios(sub: pd.DataFrame, cost_bps: int, const_weight: float | None = None):
    """Rule A, rule B, buy-and-hold, 60/40, constant mix on one sample. Returns (returns DataFrame, held, traded, const_weight)."""
    cost = cost_bps / 10000.0
    r_eq, r_cash, r_bond = sub["r_eq"].to_numpy(), sub["r_cash"].to_numpy(), sub["r_bond"].to_numpy()
    out, held_d, traded_d = {}, {}, {}
    # Execution A: target at close t = w(score[t])
    tA = sub["w_signal"].to_numpy()
    rebA = np.r_[True, tA[1:] != tA[:-1]]
    out["rule_A"], held_d["rule_A"], traded_d["rule_A"] = simulate(r_eq, r_cash, tA, rebA, cost, w0=0.0)
    # Execution B: target at close t = w(score[t-1])
    tB = np.r_[np.nan, tA[:-1]]
    rebB = np.r_[False, True, tB[2:] != tB[1:-1]]
    out["rule_B"], held_d["rule_B"], traded_d["rule_B"] = simulate(r_eq, r_cash, tB, rebB, cost, w0=0.0)
    # buy and hold
    out["buy_hold"] = np.nan_to_num(r_eq)
    # 60/40 monthly
    me = month_end_mask(sub.index)
    t6040 = np.full(len(sub), 0.6)
    reb = me.copy(); reb[0] = True
    out["sixty_forty"], _, traded_d["sixty_forty"] = simulate(r_eq, r_bond, t6040, reb, cost)
    # exposure-matched constant mix
    if const_weight is None:
        const_weight = float(np.nanmean(held_d["rule_B"][2:]))
    tc = np.full(len(sub), const_weight)
    out["const_mix"], held_d["const_mix"], traded_d["const_mix"] = simulate(r_eq, r_cash, tc, reb, cost)
    R = pd.DataFrame(out, index=sub.index)
    H = pd.DataFrame({k: v for k, v in held_d.items()}, index=sub.index)
    T = pd.DataFrame({k: v for k, v in traded_d.items()}, index=sub.index)
    return R, H, T, const_weight


def sharpe_boot(R: pd.DataFrame, cash: pd.Series, a: str, b: str, seed_off: int) -> tuple[float, float, float, int]:
    ex = (R[[a, b]].sub(cash.reindex(R.index).fillna(0.0), axis=0)).dropna().to_numpy()
    n = len(ex)
    rng = np.random.default_rng(SEED + 5000 + seed_off)
    idx = stationary_indices(n, BOOT_N, BLOCK_LEN, rng)
    diffs = np.empty(BOOT_N)
    for s in range(0, BOOT_N, 500):
        x = ex[idx[s:s + 500]]  # (chunk, n, 2)
        mu = x.mean(axis=1)
        sd = x.std(axis=1, ddof=1)
        sh = mu / sd * np.sqrt(252)
        diffs[s:s + 500] = sh[:, 0] - sh[:, 1]
    pt = (ex[:, 0].mean() / ex[:, 0].std(ddof=1) - ex[:, 1].mean() / ex[:, 1].std(ddof=1)) * np.sqrt(252)
    return pt, np.percentile(diffs, CI[0]), np.percentile(diffs, CI[1]), n


def metrics_table(R: pd.DataFrame, H: pd.DataFrame, T: pd.DataFrame, cash: pd.Series, label: str, lo=None, hi=None) -> pd.DataFrame:
    rows = []
    Rs = R.loc[lo:hi] if lo is not None else R
    for k in R.columns:
        m = metrics(Rs[k], cash, H[k] if k in H else None, T[k] if k in T else None)
        m.update(sample=label, strategy=k)
        rows.append(m)
    return pd.DataFrame(rows)


NAMES = {"rule_A": "Rule, same close (A)", "rule_B": "Rule, next close (B)", "buy_hold": "Buy and hold", "sixty_forty": "60/40 monthly", "const_mix": "Constant mix (exposure matched)"}


def md_metrics(t: pd.DataFrame) -> str:
    out = ["| Strategy | CAGR % | Vol % | Sharpe | Sortino | Max DD % | Worst year % | Turnover /yr | Mean eq. weight | Days in market % |", "|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in t.iterrows():
        to = f"{r.turnover:.2f}" if not pd.isna(r.get("turnover", np.nan)) else ""
        mw = f"{r.mean_weight:.2f}" if not pd.isna(r.get("mean_weight", np.nan)) else ("1.00" if r.strategy == "buy_hold" else "")
        pin = f"{100 * r.pct_in:.0f}" if not pd.isna(r.get("pct_in", np.nan)) else ("100" if r.strategy == "buy_hold" else "")
        out.append(f"| {NAMES[r.strategy]} | {pct(r.cagr)} | {pct(r.vol, 1)} | {r.sharpe:.2f} | {r.sortino:.2f} | {pct(r.maxdd, 1)} | {pct(r.worst_year, 1)} ({r.worst_year_label}) | {to} | {mw} | {pin} |")
    return "\n".join(out)


# ---------------- figures ----------------
def fig_oscillator(df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(10, 3.8))
    d = df.loc[EXT_START:]
    for lo, hi, b in [(0, 20, "RISK-OFF"), (20, 40, "MILDLY OFF"), (40, 60, "NEUTRAL"), (60, 80, "MILDLY ON"), (80, 100, "RISK-ON")]:
        ax.axhspan(lo, hi, color=BAND_COLOR[b], alpha=0.10, lw=0)
        ax.text(d.index[-1] + pd.Timedelta(days=120), (lo + hi) / 2, b, va="center", fontsize=7, color=INK2)
    ax.plot(d.index, d["score"], color=BLUE, lw=0.9)
    ax.axvline(PRIMARY_START, color=MUTED, lw=0.8)
    ax.text(PRIMARY_START, 97, " five signals from 2008-04-09", fontsize=7, color=INK2, va="top")
    ax.text(d.index[0], 97, " three, then four signals (reduced-signal composite)", fontsize=7, color=INK2, va="top")
    ax.set_ylim(0, 100); ax.set_ylabel("Regime score (0 to 100)")
    ax.set_title("Cross-Asset Regime Oscillator, daily, published parameters")
    ax.set_xlim(d.index[0], d.index[-1] + pd.Timedelta(days=900))
    savefig(fig, "fig1_oscillator.png")


def fig_signals(df_osc: pd.DataFrame):
    o = pd.read_csv(HERE / "data" / "oscillator_daily.csv", parse_dates=["date"], index_col="date").loc[PRIMARY_START:]
    names = [("z_credit", "Credit: HYG/IEF"), ("z_vol", "Volatility: VIX (inverted)"), ("z_cycdef", "Cyclical/defensive: XLI/XLU"),
             ("z_curve", "Yield curve: 10y minus 3m"), ("z_dollar", "Dollar: DXY (inverted)")]
    fig, axes = plt.subplots(5, 1, figsize=(10, 7.5), sharex=True)
    for ax, (c, t) in zip(axes, names):
        ax.plot(o.index, o[c], color=BLUE, lw=0.7)
        ax.axhline(0, color=BASE, lw=0.8)
        ax.set_ylim(-3.2, 3.2); ax.set_yticks([-3, 0, 3])
        ax.set_title(t, loc="left", fontsize=9)
    axes[-1].set_xlabel("")
    fig.suptitle("The five clamped z-scores (252-day lookback), oriented so higher = risk-on", x=0.01, ha="left", fontsize=10, fontweight="bold", color=INK)
    savefig(fig, "fig2_signals.png")


def fig_band_returns(tab: pd.DataFrame, name: str, title: str):
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.6), sharey=False)
    for ax, h in zip(axes, HORIZONS):
        t = tab[(tab.h == h)].set_index("band").reindex(BANDS)
        x = np.arange(len(BANDS))
        vals = 100 * t["mean"].to_numpy()
        lo, hi = 100 * t["lo"].to_numpy(), 100 * t["hi"].to_numpy()
        colors = [BAND_COLOR[b] for b in BANDS]
        ax.bar(x, np.nan_to_num(vals), color=colors, width=0.62)
        ok = ~np.isnan(lo)
        ax.errorbar(x[ok], vals[ok], yerr=[vals[ok] - lo[ok], hi[ok] - vals[ok]], fmt="none", ecolor=INK2, elinewidth=1, capsize=3)
        ax.axhline(100 * t["allmean"].iloc[0], color=MUTED, lw=0.8)
        ax.axhline(0, color=BASE, lw=0.8)
        ax.set_xticks(x); ax.set_xticklabels(["Risk-off", "Mildly off", "Neutral", "Mildly on", "Risk-on"], rotation=30, ha="right", fontsize=8)
        ax.set_title(f"{h} trading days ahead", fontsize=9)
        for i, (b, r) in enumerate(t.iterrows()):
            if r.days == 0:
                ax.text(i, 0.1, "no days", ha="center", fontsize=7, color=MUTED, rotation=90, va="bottom")
            elif r.thin:
                ax.text(i, vals[i] if vals[i] > 0 else 0, " thin", ha="center", fontsize=7, color=INK2, va="bottom")
    axes[0].set_ylabel("Mean forward total return, %")
    fig.suptitle(title, x=0.01, ha="left", fontsize=10, fontweight="bold", color=INK)
    fig.text(0.01, 0.005, "Bars: mean. Whiskers: 90% stationary block-bootstrap interval. Grey line: all-days mean.", fontsize=7.5, color=INK2)
    fig.subplots_adjust(bottom=0.3)
    savefig(fig, name)


def fig_score_bins(sb: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 3.6))
    x = np.arange(len(sb))
    vals = 100 * sb["mean"].to_numpy(); lo = 100 * sb["lo"].to_numpy(); hi = 100 * sb["hi"].to_numpy()
    ax.bar(x, np.nan_to_num(vals), color=BLUE, width=0.62)
    ok = ~np.isnan(lo)
    ax.errorbar(x[ok], vals[ok], yerr=[vals[ok] - lo[ok], hi[ok] - vals[ok]], fmt="none", ecolor=INK2, elinewidth=1, capsize=3)
    ax.axhline(0, color=BASE, lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(sb["bin"])
    for i, r in sb.iterrows():
        ax.text(i, min(0, np.nan_to_num(vals[i])) - 0.6, f"n={r.days}", ha="center", fontsize=7, color=MUTED, va="top")
    ax.set_xlabel("Score bin"); ax.set_ylabel("Mean 60-day forward total return, %")
    ax.set_title("Forward 60-day return by 10-point score bin, five-signal period (90% intervals)")
    savefig(fig, "fig4_score_bins.png")


def fig_curves(R: pd.DataFrame, H: pd.DataFrame, df: pd.DataFrame):
    fig, axes = plt.subplots(3, 1, figsize=(10, 8.5), sharex=True, gridspec_kw={"height_ratios": [3, 1.6, 1.2]})
    cols = [("buy_hold", INK2, "Buy and hold"), ("sixty_forty", ORANGE, "60/40"), ("const_mix", AQUA, "Constant mix"), ("rule_B", BLUE, "Rule, next close, 5 bp")]
    ax = axes[0]
    for k, c, lab in cols:
        g = (1 + R[k].fillna(0)).cumprod()
        ax.plot(g.index, g, color=c, lw=1.4 if k == "rule_B" else 1.0, label=f"{lab}: {g.iloc[-1]:.2f}x")
    ax.set_yscale("log"); ax.set_ylabel("Growth of 1 (log scale)"); ax.legend(loc="upper left", fontsize=8)
    ax.yaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter()); ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_yticks([1, 2, 3, 5, 8, 12]); ax.set_yticklabels(["1", "2", "3", "5", "8", "12"])
    ax.set_title("Allocation rule versus benchmarks, five-signal period")
    ax = axes[1]
    for k, c, lab in cols:
        g = (1 + R[k].fillna(0)).cumprod()
        ax.plot(g.index, 100 * (g / g.cummax() - 1), color=c, lw=1.0 if k == "rule_B" else 0.8)
    ax.set_ylabel("Drawdown, %")
    ax = axes[2]
    ax.fill_between(H.index, 0, 100 * H["rule_B"], color=BLUE, alpha=0.35, lw=0, step="post")
    ax.set_ylabel("Equity weight, %"); ax.set_ylim(0, 100)
    ax.set_xlim(R.index[0], R.index[-1] + pd.Timedelta(days=60))
    savefig(fig, "fig5_rule_vs_benchmarks.png")


def fig_is_oos(tab_is: pd.DataFrame, tab_oos: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, (tab, lab) in zip(axes, [(tab_is, "In sample 2008-04 to 2017-12"), (tab_oos, "Out of sample 2018-01 to 2026")]):
        t = tab[tab.h == 60].set_index("band").reindex(BANDS)
        x = np.arange(len(BANDS))
        vals = 100 * t["mean"].to_numpy(); lo = 100 * t["lo"].to_numpy(); hi = 100 * t["hi"].to_numpy()
        ax.bar(x, np.nan_to_num(vals), color=[BAND_COLOR[b] for b in BANDS], width=0.62)
        ok = ~np.isnan(lo)
        ax.errorbar(x[ok], vals[ok], yerr=[vals[ok] - lo[ok], hi[ok] - vals[ok]], fmt="none", ecolor=INK2, elinewidth=1, capsize=3)
        ax.axhline(100 * t["allmean"].iloc[0], color=MUTED, lw=0.8); ax.axhline(0, color=BASE, lw=0.8)
        ax.set_xticks(x); ax.set_xticklabels(["Risk-off", "Mildly off", "Neutral", "Mildly on", "Risk-on"], rotation=30, ha="right", fontsize=8)
        ax.set_title(lab, fontsize=9)
        for i, (b, r) in enumerate(t.iterrows()):
            if r.days == 0:
                ax.text(i, 0.1, "no days", ha="center", fontsize=7, color=MUTED, rotation=90, va="bottom")
            elif r.thin:
                ax.text(i, max(vals[i], 0), " thin", ha="center", fontsize=7, color=INK2, va="bottom")
    axes[0].set_ylabel("Mean 60-day forward return, %")
    fig.suptitle("Forward 60-day return by band, in and out of sample", x=0.01, ha="left", fontsize=10, fontweight="bold", color=INK)
    fig.text(0.01, 0.005, "Bars: mean. Whiskers: 90% block-bootstrap interval. Grey line: sample mean.", fontsize=7.5, color=INK2)
    fig.subplots_adjust(bottom=0.3)
    savefig(fig, "fig6_is_oos.png")


def fig_decades(dec_tab: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 3.4))
    labs = [d[0] for d in DECADES]
    strategies = [("rule_B", BLUE, "Rule, next close"), ("buy_hold", INK2, "Buy and hold"), ("sixty_forty", ORANGE, "60/40")]
    x = np.arange(len(labs)); w = 0.26
    for j, (k, c, lab) in enumerate(strategies):
        v = [dec_tab[(dec_tab["sample"] == d) & (dec_tab.strategy == k)].sharpe.iloc[0] for d in labs]
        ax.bar(x + (j - 1) * w, v, width=w - 0.02, color=c, label=lab)
    ax.axhline(0, color=BASE, lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(["2008-04 to 2009", "2010 to 2019", "2020 to 2026-10"])
    ax.set_ylabel("Sharpe ratio"); ax.legend(fontsize=8)
    ax.set_title("Sharpe ratio by decade, after 5 bp costs")
    savefig(fig, "fig7_decades.png")


# ---------------- main ----------------
def main() -> int:
    t0 = time.time()
    df = load_frame()
    cash = df["r_cash"]
    md = []
    md.append("# Results tables (generated by analysis.py)\n")
    md.append(f"Generated {pd.Timestamp.today().date()}. Bootstrap: stationary block, E[len]={BLOCK_LEN}, {BOOT_N} resamples, seed {SEED}. Intervals 5th to 95th percentile.\n")

    # ---- samples
    prim = df.loc[PRIMARY_START:]
    prim = prim[prim.n_signals == 5]
    is_ = prim.loc[:IS_END]
    oos = prim.loc[OOS_START:]
    ext = df.loc[EXT_START:EXT_END]
    ext = ext[ext.n_signals >= 3]
    print(f"primary {prim.index[0].date()} -> {prim.index[-1].date()} n={len(prim)}; IS n={len(is_)}; OOS n={len(oos)}; ext n={len(ext)}")
    md.append(f"Samples: primary {prim.index[0].date()} to {prim.index[-1].date()} ({len(prim)} signal days; forward windows truncate the usable end by h days); IS to {IS_END.date()} ({len(is_)}); OOS from {OOS_START.date()} ({len(oos)}); extended reduced-signal {ext.index[0].date()} to {ext.index[-1].date()} ({len(ext)}).\n")

    # ---- band tables
    all_tabs = []
    tab_p, boots_p = band_table(prim, "primary", 0)
    tab_pn, _ = band_table(prim, "primary", 100, timing="_next")
    tab_is, boots_is = band_table(is_, "IS", 200)
    tab_oos, boots_oos = band_table(oos, "OOS", 300)
    tab_ext, boots_ext = band_table(ext, "extended", 400)
    all_tabs += [tab_p, tab_pn, tab_is, tab_oos, tab_ext]
    dec_band = []
    for lab, a, b in DECADES:
        sub = prim.loc[a:b]
        t, _ = band_table(sub, lab, 500 + 10 * DECADES.index((lab, a, b)))
        dec_band.append(t); all_tabs.append(t)
    pd.concat(all_tabs).to_csv(RES / "band_tables.csv", index=False)

    md.append("## 1. Forward returns by band, primary sample (signal at close t, window t to t+h)\n" + md_band_table(tab_p))
    md.append("\n## 1b. Same, window starting one day later (t+1 to t+1+h: act on the plotted value at the next close)\n" + md_band_table(tab_pn))
    md.append("\n## 1c. In sample (2008-04-09 to 2017-12-29)\n" + md_band_table(tab_is))
    md.append("\n## 1d. Out of sample (2018-01-02 onward)\n" + md_band_table(tab_oos))
    md.append("\n## 1e. Extended reduced-signal history (1990-12-28 to 2008-04-08; three, then four signals)\n" + md_band_table(tab_ext))
    for (lab, a, b), t in zip(DECADES, dec_band):
        md.append(f"\n## 1f. Decade {lab} ({a} to {b})\n" + md_band_table(t))

    # ---- H1 / H2
    hh = pd.concat([h1_h2(boots_p, prim, "primary"), h1_h2(boots_is, is_, "IS"), h1_h2(boots_oos, oos, "OOS"), h1_h2(boots_ext, ext, "extended")])
    hh.to_csv(RES / "h1_h2.csv", index=False)
    md.append("\n## 2. H1 (upper two bands minus lower two bands, mean forward return) and H2 (dead zone D)\n")
    md.append("| Sample | h | H1 diff % | 90% CI | D(min of neighbours) % | 90% CI | D(vs NEUTRAL) % | 90% CI | D on medians % | 90% CI | mean RISK-OFF | mean MILDLY OFF | mean NEUTRAL |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for _, r in hh.iterrows():
        md.append(f"| {r['sample']} | {r.h} | {pct(r.h1_point)} | {ci_str(r.h1_lo, r.h1_hi)} | {pct(r.d_both_point)} | {ci_str(r.d_both_lo, r.d_both_hi)} | {pct(r.d_neut_point)} | {ci_str(r.d_neut_lo, r.d_neut_hi)} | {pct(r.d_med_point)} | {ci_str(r.d_med_lo, r.d_med_hi)} | {pct(r.mean_ro)} | {pct(r.mean_mo)} | {pct(r.mean_ne)} |")

    # verdict lines H1, H2 (primary)
    p = hh[hh["sample"] == "primary"].set_index("h")
    o = hh[hh["sample"] == "OOS"].set_index("h")
    h1_sup = all(p.loc[h, "h1_lo"] > 0 for h in (20, 60)) and o.loc[60, "h1_point"] > 0 and o.loc[20, "h1_point"] > 0
    h1_con = all(p.loc[h, "h1_hi"] < 0 for h in (20, 60))
    h1_verdict = "SUPPORTED" if h1_sup else ("CONTRARY" if h1_con else "NULL")
    ro_thin = bool(tab_p[(tab_p.h == 60) & (tab_p.band == "RISK-OFF")].thin.iloc[0])
    if ro_thin:
        d_pt, d_lo = p.loc[60, "d_neut_point"], p.loc[60, "d_neut_lo"]
        comparator = "NEUTRAL only (RISK-OFF is THIN at h=60)"
    else:
        d_pt, d_lo = p.loc[60, "d_both_point"], p.loc[60, "d_both_lo"]
        comparator = "min(RISK-OFF, NEUTRAL)"
    h2_verdict = "DIP IS REAL" if (d_pt > 0 and d_lo > 0) else ("NO DIP" if d_pt <= 0 else "UNCLEAR")
    md.append(f"\n**H1 verdict (pre-registered rule): {h1_verdict}.** Primary h=20 CI {ci_str(p.loc[20, 'h1_lo'], p.loc[20, 'h1_hi'])}, h=60 CI {ci_str(p.loc[60, 'h1_lo'], p.loc[60, 'h1_hi'])}; OOS point h=20 {pct(o.loc[20, 'h1_point'])}%, h=60 {pct(o.loc[60, 'h1_point'])}%.")
    md.append(f"\n**H2 verdict (pre-registered rule): {h2_verdict}.** Comparator {comparator}; D at h=60 = {pct(d_pt)}%, 5th percentile {pct(d_lo)}%.")

    # ---- score bins
    sb = score_bins(prim, "primary")
    sb.to_csv(RES / "score_bins.csv", index=False)
    md.append("\n## 3. Mean 60-day forward return by 10-point score bin (primary, descriptive)\n")
    md.append("| Bin | Days | Mean % | 90% CI | Median % | Win rate % |\n|---|---|---|---|---|---|")
    for _, r in sb.iterrows():
        if r.days == 0:
            md.append(f"| {r.bin} | 0 | | | | |")
        else:
            md.append(f"| {r.bin} | {r.days} | {pct(r['mean'])} | {ci_str(r.lo, r.hi)} | {pct(r['median'])} | {100 * r.winrate:.1f} |")

    # ---- allocation
    R, H, T, cw = run_portfolios(prim, COST_BPS)
    R.to_csv(RES / "daily_returns_primary_5bp.csv"); H.to_csv(RES / "held_weights_primary.csv")
    met_rows = [metrics_table(R, H, T, cash, "primary"), metrics_table(R, H, T, cash, "IS", None, IS_END).assign(sample="IS"),
                metrics_table(R, H, T, cash, "OOS", OOS_START, None).assign(sample="OOS")]
    met_rows[1] = metrics_table(R.loc[:IS_END], H, T, cash, "IS")
    met_rows[2] = metrics_table(R.loc[OOS_START:], H, T, cash, "OOS")
    for lab, a, b in DECADES:
        met_rows.append(metrics_table(R.loc[a:b], H, T, cash, lab))
    met = pd.concat(met_rows)
    md.append(f"\n## 4. Allocation rule, primary sample, 5 bp per side (constant-mix weight = rule B mean weight = {cw:.3f})\n" + md_metrics(met[met['sample'] == 'primary']))
    md.append("\n### 4a. In sample\n" + md_metrics(met[met['sample'] == 'IS']))
    md.append("\n### 4b. Out of sample\n" + md_metrics(met[met['sample'] == 'OOS']))
    for lab, a, b in DECADES:
        md.append(f"\n### 4c. Decade {lab}\n" + md_metrics(met[met['sample'] == lab]))

    # cost sensitivity
    cost_rows = []
    for c in COST_GRID:
        Rc, Hc, Tc, _ = run_portfolios(prim, c, const_weight=cw)
        for k in ["rule_A", "rule_B"]:
            m = metrics(Rc[k], cash, Hc[k], Tc[k]); m.update(cost_bps=c, strategy=k, sample="primary"); cost_rows.append(m)
            m2 = metrics(Rc[k].loc[OOS_START:], cash, Hc[k], Tc[k]); m2.update(cost_bps=c, strategy=k, sample="OOS"); cost_rows.append(m2)
    cost_tab = pd.DataFrame(cost_rows)
    md.append("\n## 5. Cost sensitivity (CAGR % / Sharpe)\n\n| Cost bp per side | Rule A primary | Rule B primary | Rule A OOS | Rule B OOS |\n|---|---|---|---|---|")
    for c in COST_GRID:
        cells = []
        for s in ["primary", "OOS"]:
            for k in ["rule_A", "rule_B"]:
                r = cost_tab[(cost_tab.cost_bps == c) & (cost_tab.strategy == k) & (cost_tab["sample"] == s)].iloc[0]
                cells.append(f"{pct(r.cagr)} / {r.sharpe:.2f}")
        md.append(f"| {c} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |")

    # H3: Sharpe difference bootstrap
    h3_rows = []
    for samp, Rs in [("primary", R), ("IS", R.loc[:IS_END]), ("OOS", R.loc[OOS_START:])]:
        for k in ["rule_B", "rule_A"]:
            for bench in ["buy_hold", "sixty_forty", "const_mix"]:
                pt, lo, hi, n = sharpe_boot(Rs.iloc[2:], cash, k, bench, len(h3_rows))
                h3_rows.append(dict(sample=samp, strategy=k, benchmark=bench, sharpe_diff=pt, lo=lo, hi=hi, n=n))
    h3 = pd.DataFrame(h3_rows)
    md.append("\n## 6. H3: Sharpe difference, rule minus benchmark (90% block-bootstrap interval, paired)\n\n| Sample | Rule | Benchmark | Sharpe diff | 90% CI | Days |\n|---|---|---|---|---|---|")
    for _, r in h3.iterrows():
        md.append(f"| {r['sample']} | {NAMES[r.strategy]} | {NAMES[r.benchmark]} | {r.sharpe_diff:+.3f} | [{r.lo:+.3f}, {r.hi:+.3f}] | {r.n} |")
    hb = h3[(h3.strategy == "rule_B") & (h3.benchmark == "buy_hold")].set_index("sample")
    ha = h3[(h3.strategy == "rule_A") & (h3.benchmark == "buy_hold")].set_index("sample")
    h3_sup = hb.loc["primary", "lo"] > 0 and hb.loc["OOS", "sharpe_diff"] > 0
    h3_con = hb.loc["primary", "hi"] < 0
    h3_verdict = "SUPPORTED" if h3_sup else ("CONTRARY" if h3_con else "NULL")
    h3a_sup = ha.loc["primary", "lo"] > 0 and ha.loc["OOS", "sharpe_diff"] > 0
    md.append(f"\n**H3 verdict (pre-registered rule, Execution B, 5 bp, vs buy and hold): {h3_verdict}.** Primary diff {hb.loc['primary', 'sharpe_diff']:+.3f} CI [{hb.loc['primary', 'lo']:+.3f}, {hb.loc['primary', 'hi']:+.3f}]; IS {hb.loc['IS', 'sharpe_diff']:+.3f}; OOS {hb.loc['OOS', 'sharpe_diff']:+.3f} CI [{hb.loc['OOS', 'lo']:+.3f}, {hb.loc['OOS', 'hi']:+.3f}]. Execution A would be {'SUPPORTED' if h3a_sup else 'not supported'} (diff {ha.loc['primary', 'sharpe_diff']:+.3f}).")

    # overall verdict
    if h3_verdict == "SUPPORTED" and (h1_verdict == "SUPPORTED" or h2_verdict == "DIP IS REAL"):
        overall = "EDGE IS REAL"
    elif (h3_verdict == "NULL" and hb.loc["IS", "sharpe_diff"] > 0 and hb.loc["OOS", "sharpe_diff"] > 0) or (h3_verdict == "SUPPORTED"):
        overall = "SUGGESTIVE"
    else:
        overall = "NO EDGE"
    md.append(f"\n## 7. Overall verdict by the pre-registered rule: **{overall}** (H1 {h1_verdict}; H2 {h2_verdict}; H3 {h3_verdict})\n")

    # extended history allocation
    Re, He, Te, cwe = run_portfolios(ext, COST_BPS)
    met_ext = metrics_table(Re, He, Te, cash, "extended")
    md.append(f"\n## 8. Extended reduced-signal history (1990-12-28 to 2008-04-08), allocation rule, 5 bp (constant-mix weight {cwe:.3f})\n" + md_metrics(met_ext))
    pt, lo, hi, n = sharpe_boot(Re.iloc[2:], cash, "rule_B", "buy_hold", 99)
    md.append(f"\nSharpe difference rule B minus buy and hold, extended: {pt:+.3f} [{lo:+.3f}, {hi:+.3f}].")
    pd.concat([met, met_ext]).to_csv(RES / "metrics.csv", index=False)
    cost_tab.to_csv(RES / "cost_sensitivity.csv", index=False)
    h3.to_csv(RES / "h3_sharpe.csv", index=False)

    # band time share and transitions (descriptive)
    md.append("\n## 9. Band occupancy and changes, primary sample\n")
    vc = prim["band"].value_counts().reindex(BANDS).fillna(0).astype(int)
    changes = int((prim["band"] != prim["band"].shift(1)).sum() - 1)
    years = len(prim) / 252
    md.append("| Band | Days | Share % |\n|---|---|---|")
    for b in BANDS:
        md.append(f"| {b} | {vc[b]} | {100 * vc[b] / len(prim):.1f} |")
    md.append(f"\nBand changes: {changes} over {years:.1f} years ({changes / years:.1f} per year). Rule B one-way turnover is in section 4.")
    yearly = (1 + R).groupby(R.index.year).prod() - 1
    md.append("\n## 10. Calendar-year returns, primary sample (first and last years partial)\n\n| Year | " + " | ".join(NAMES[k] for k in R.columns) + " |\n|---|" + "---|" * len(R.columns))
    for y, r in yearly.iterrows():
        md.append(f"| {y} | " + " | ".join(pct(v, 1) for v in r) + " |")
    yearly.to_csv(RES / "calendar_years.csv")

    (RES / "tables.md").write_text("\n".join(md) + "\n")
    json.dump(dict(h1=h1_verdict, h2=h2_verdict, h3=h3_verdict, overall=overall, const_weight=cw), open(RES / "verdicts.json", "w"), indent=1)

    # ---- figures
    fig_oscillator(df)
    fig_signals(df)
    fig_band_returns(tab_p, "fig3_band_returns.png", "Forward S&P 500 total return by band, five-signal period 2008 to 2026")
    fig_score_bins(sb)
    fig_curves(R, H, prim)
    fig_is_oos(tab_is, tab_oos)
    fig_decades(met)
    fig_band_returns(tab_ext, "fig8_band_returns_extended.png", "Forward return by band, reduced-signal history 1990 to 2008")
    print("done in %.0fs; verdicts:" % (time.time() - t0), h1_verdict, h2_verdict, h3_verdict, overall)
    return 0


if __name__ == "__main__":
    sys.exit(main())
