# Data sources (fetched 2026-11-01)

All series are free. Yahoo `Close` is the exchange close, split-adjusted but not dividend-adjusted, which is
what TradingView plots by default and therefore what the oscillator's ratios use. FRED yields are the H.15
constant-maturity series; FRED prints no value on bond-market holidays and those days are skipped, as a
TradingView daily bar would be. Row counts for FRED are non-missing observations.

| Source | Symbol | Role | First | Last | Rows | File | SHA256 |
|---|---|---|---|---|---|---|---|
| Yahoo Finance | `HYG` | iShares iBoxx $ High Yield Corporate Bond ETF (credit numerator) | 2007-04-11 | 2026-10-30 | 4922 | `data/raw/HYG.csv` | `ce92e9fe118c1c75` |
| Yahoo Finance | `IEF` | iShares 7-10 Year Treasury Bond ETF (credit denominator) | 2002-07-30 | 2026-10-30 | 6104 | `data/raw/IEF.csv` | `602cc5aaee76cf20` |
| Yahoo Finance | `XLI` | Industrial Select Sector SPDR (cyclical numerator) | 1998-12-22 | 2026-10-30 | 7007 | `data/raw/XLI.csv` | `8d6f83309297b36b` |
| Yahoo Finance | `XLU` | Utilities Select Sector SPDR (defensive denominator) | 1998-12-22 | 2026-10-30 | 7007 | `data/raw/XLU.csv` | `070279ba24b7fb2e` |
| Yahoo Finance | `^VIX` | CBOE Volatility Index (equity volatility, inverted) | 1990-01-02 | 2026-10-30 | 9278 | `data/raw/VIX.csv` | `52fcb8338c83fc54` |
| Yahoo Finance | `DX-Y.NYB` | ICE US Dollar Index (dollar, inverted) | 1971-01-04 | 2026-10-30 | 14176 | `data/raw/DXY.csv` | `489e5b60fcba79fb` |
| Yahoo Finance | `^SP500TR` | S&P 500 Total Return index (forward returns, equity leg) | 1988-01-04 | 2026-10-30 | 9781 | `data/raw/SP500TR.csv` | `f906e623fdaedaba` |
| Yahoo Finance | `SPY` | SPDR S&P 500 ETF (investable cross-check) | 1993-01-29 | 2026-10-30 | 8497 | `data/raw/SPY.csv` | `9dff3eb94ef923e0` |
| Yahoo Finance | `VBMFX` | Vanguard Total Bond Market Index Fund (60/40 bond leg) | 1986-12-11 | 2026-10-30 | 10048 | `data/raw/VBMFX.csv` | `65ad2201b5faae27` |
| Yahoo Finance | `^GSPC` | S&P 500 price index (US equity trading calendar) | 1960-01-04 | 2026-10-30 | 16819 | `data/raw/GSPC.csv` | `40287774c63f1b7e` |
| FRED | `DGS10` | 10-Year Treasury constant maturity yield, percent (curve long end) | 1962-01-02 | 2026-10-29 | 16192 | `data/raw/DGS10.csv` | `99ea198f869dbbea` |
| FRED | `DGS3MO` | 3-Month Treasury constant maturity yield, percent (curve short end) | 1981-09-01 | 2026-10-29 | 11290 | `data/raw/DGS3MO.csv` | `449c4329b7749cda` |
| FRED | `DTB3` | 3-Month Treasury bill secondary market rate, discount basis, percent (cash return) | 1954-01-04 | 2026-10-29 | 18198 | `data/raw/DTB3.csv` | `7c98f425b430bec7` |
| FRED | `VIXCLS` | CBOE VIX close (cross-check of Yahoo ^VIX) | 1990-01-02 | 2026-10-29 | 9306 | `data/raw/VIXCLS.csv` | `8c44a9b40106c5cf` |

## Mapping to the Pine script's symbols

| Pine symbol | Series used here | Note |
|---|---|---|
| `AMEX:HYG/NASDAQ:IEF` | HYG Close / IEF Close, on days both traded | ratio of unadjusted closes, as TradingView builds a spread symbol |
| `CBOE:VIX` | ^VIX Close (Yahoo); FRED VIXCLS as a cross-check | same CBOE close |
| `AMEX:XLI/AMEX:XLU` | XLI Close / XLU Close | as above |
| `TVC:US10Y-TVC:US03MY` | FRED DGS10 minus DGS3MO, on days both are published | TradingView's TVC yields come from a different vendor and fixing time than the Fed's H.15 (about 3:30 pm ET); small level differences are expected and are the most likely source of any residual mismatch |
| `TVC:DXY` | DX-Y.NYB Close (ICE US Dollar Index) | same index; ICE close about 5 pm ET |

The equity trading calendar (the chart symbol's bars) is taken from ^GSPC.
