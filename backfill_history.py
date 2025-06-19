#!/usr/bin/env python3
"""
Build full history.csv  (default: 5 years, daily closes)

• Reads gaming_universe_fixed.xlsx  (Symbol / Region / Weight)
• Pulls daily prices with yfinance; where NaN, falls back to Stooq
• Writes fresh history.csv covering every market day
"""
import csv, io, os, re, requests, pandas as pd, yfinance as yf
from datetime import datetime

SRC_XLSX = "gaming_universe_fixed.xlsx"   # universe sheet
OUT_CSV  = "history.csv"
YEARS    = 5                              # how far back
REGIONS  = ["All", "North America", "Europe", "Asia-Pacific", "Other"]

# ─── Load & prepare universe ──────────────────────────────────────────
u = (
    pd.read_excel(SRC_XLSX)
      .dropna(subset=["Symbol"])
      .assign(Symbol=lambda d: d["Symbol"].astype(str).str.strip())
)

if "Weight" not in u.columns:
    u["Weight"] = 1 / len(u)

if "Region" not in u.columns:
    REGION_MAP = {
        "NYSE": "North America", "NASDAQ": "North America", "OTCMKTS": "North America", "TSE": "North America",
        "ASX": "Asia-Pacific", "HKG": "Asia-Pacific", "TYO": "Asia-Pacific", "SGX": "Asia-Pacific",
        "KRX": "Asia-Pacific", "KLSE": "Asia-Pacific",
        "LSE": "Europe", "AMS": "Europe", "EPA": "Europe", "STO": "Europe",
        "BIT": "Europe", "FRA": "Europe", "ATH": "Europe",
    }
    u["Region"] = u["Market"].map(REGION_MAP).fillna("Other")

tickers = u["Symbol"].tolist()

# ─── Fetch bulk daily prices via yfinance ─────────────────────────────
yf_hist = yf.download(tickers, period=f"{YEARS}y", interval="1d")["Adj Close"]

# ─── Stooq helper (daily history) ────────────────────────────────────
def stooq_hist(sym: str) -> pd.Series | None:
    """
    Return a Series of daily closes indexed by Date from Stooq, or None.
    """
    m = re.match(r"([^.]+)(?:\\.(\\w+))?", sym)
    if not m:
        return None
    base, suf = m.group(1), m.group(2)

    code_map = {
        None:  f"{base}.us",   # default US
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
    stqx = code_map.get(suf)
    if not stqx:
        return None

    url = f"https://stooq.com/q/d/l/?s={stqx}&i=d"
    try:
        df = pd.read_csv(url, parse_dates=["Date"]).set_index("Date")
        return df["Close"].replace(0, pd.NA)     # treat 0 as missing
    except Exception:
        return None

# ─── Merge yfinance & Stooq per ticker ───────────────────────────────
prices = {}
for sym in tickers:
    s = yf_hist[sym]
    if s.isna().all():
        s2 = stooq_hist(sym)
        if s2 is not None:
            s = s2.reindex_like(s)
    prices[sym] = s

# ─── Assemble index dataframe ────────────────────────────────────────
df_idx = pd.DataFrame(index=yf_hist.index)

for region in REGIONS:
    vals = []
    for dt in df_idx.index:
        tot = 0
        for _, row in u.iterrows():
            if region != "All" and row["Region"] != region:
                continue
            px = prices[row["Symbol"]].loc[dt]
            if pd.notna(px):
                tot += px * row["Weight"]
        vals.append(tot)
    df_idx[region] = vals

# Drop non-trading days (All == 0)
df_idx = df_idx[df_idx["All"] > 0]

# ─── Write history.csv ───────────────────────────────────────────────
df_idx.reset_index().rename(columns={"Date": "timestamp"}).to_csv(OUT_CSV, index=False)
print(f"✓ Wrote {OUT_CSV} with {len(df_idx)} rows – up to {df_idx['timestamp'].iloc[-1].date()}")
