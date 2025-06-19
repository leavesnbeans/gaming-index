#!/usr/bin/env python3
"""
backfill_history.py
──────────────────────────────────────────────────────────────
Creates a full multi-year history.csv (default 5y, daily closes).

• Reads gaming_universe_fixed.xlsx  (Symbol / Region / Weight)
• Fetches daily data with yfinance; if NaN, falls back to Stooq
• Writes/overwrites history.csv with index levels for:
  All, North America, Europe, Asia-Pacific, Other
"""

import csv, io, os, re, requests, pandas as pd, yfinance as yf
from datetime import datetime

# ── Config ─────────────────────────────────────────────────
SRC_XLSX = "gaming_universe_fixed.xlsx"
OUT_CSV  = "history.csv"
YEARS    = 5
REGIONS  = ["All", "North America", "Europe", "Asia-Pacific", "Other"]

# ── Load and prepare universe ──────────────────────────────
u = (
    pd.read_excel(SRC_XLSX)
      .dropna(subset=["Symbol"])
      .assign(Symbol=lambda d: d["Symbol"].astype(str).str.strip())
)

if "Weight" not in u.columns:
    u["Weight"] = 1 / len(u)

if "Region" not in u.columns:
    REGION_MAP = {
        "NYSE":"North America","NASDAQ":"North America","OTCMKTS":"North America","TSE":"North America",
        "ASX":"Asia-Pacific","HKG":"Asia-Pacific","TYO":"Asia-Pacific","SGX":"Asia-Pacific",
        "KRX":"Asia-Pacific","KLSE":"Asia-Pacific",
        "LSE":"Europe","AMS":"Europe","EPA":"Europe","STO":"Europe","BIT":"Europe","FRA":"Europe","ATH":"Europe",
    }
    u["Region"] = u["Market"].map(REGION_MAP).fillna("Other")

tickers = u["Symbol"].tolist()

# ── Bulk download daily closes from yfinance ───────────────
yf_hist = yf.download(tickers, period=f"{YEARS}y", interval="1d")["Adj Close"]

# ── Stooq helper: return Series of closes indexed by Date ──
def stooq_hist(sym: str) -> pd.Series | None:
    m = re.match(r"([^.]+)(?:\\.(\\w+))?", sym)
    if not m:
        return None
    base, suf = m.group(1), m.group(2)
    code_map = {
        None:  f"{base}.us",
        "AX":  f"{base}.au",
        "HK":  f"{base}.hk",
        "T":   f"{base}.jp",
        "ST":  f"{base}.se",
        "L":   f"{base}.uk",
        "PA":  f"{base}.fr",
        "F":   f"{base}.de",
        "MI":  f"{base}.it",
        "AS":  f"{base}.nl",
        "KS":  f"{base}.ks",
        "KL":  f"{base}.kl",
        "SI":  f"{base}.sg",
        "AT":  f"{base}.at",
    }
    code = code_map.get(suf)
    if not code:
        return None
    url = f"https://stooq.com/q/d/l/?s={code}&i=d"
    try:
        df = pd.read_csv(url, parse_dates=["Date"]).set_index("Date")
        return df["Close"].replace(0, pd.NA)
    except Exception:
        return None

# ── Merge yfinance & Stooq per ticker ──────────────────────
prices = {}
for sym in tickers:
    # if yfinance dropped the column, start with an all-NaN Series
    s = yf_hist[sym] if sym in yf_hist else pd.Series(index=yf_hist.index, dtype=float)

    # fall back to Stooq if entire Series is NaN
    if s.isna().all():
        s2 = stooq_hist(sym)
        if s2 is not None:
            s = s2.reindex_like(s)

    prices[sym] = s

# ── Build index dataframe ─────────────────────────────────-
df_idx = pd.DataFrame(index=yf_hist.index)

for region in REGIONS:
    vals = []
    for dt in df_idx.index:
        tot = 0.0
        for _, row in u.iterrows():
            if region != "All" and row["Region"] != region:
                continue
            px = prices[row["Symbol"]].loc[dt]
            if pd.notna(px):
                tot += px * row["Weight"]
        vals.append(tot)
    df_idx[region] = vals

# Keep only rows where the overall index > 0
df_idx = df_idx[df_idx["All"] > 0]

# ── Write history.csv ─────────────────────────────────────-
df_idx.reset_index().rename(columns={"Date": "timestamp"}).to_csv(OUT_CSV, index=False)

print(f"✓ Wrote {OUT_CSV} with {len(df_idx)} rows – up to {df_idx['timestamp'].iloc[-1].date()}")
