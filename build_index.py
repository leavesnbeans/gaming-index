#!/usr/bin/env python3
"""
Gaming Index builder – yfinance + Stooq fallback (hist-CSV, last non-zero close)
"""
import io, json, csv, os, re, requests
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

# ─── Config ───────────────────────────────────────────────
SRC_XLSX  = "gaming_universe_fixed.xlsx"   # sheet with Symbol / Region / Weight
SNAPSHOT  = "latest.json"
HISTORY   = "history.csv"
PR_PERIOD = "1d"    # yfinance look-back
PR_STEP   = "1m"

# ─── Load & scrub universe ────────────────────────────────
u = (
    pd.read_excel(SRC_XLSX)
      .dropna(subset=["Symbol"])
      .assign(Symbol=lambda d: d["Symbol"].astype(str).str.strip())
)

if "Region" not in u.columns:
    REGION_MAP = {
        "NYSE":"North America","NASDAQ":"North America","OTCMKTS":"North America","TSE":"North America",
        "ASX":"Asia-Pacific","HKG":"Asia-Pacific","TYO":"Asia-Pacific","SGX":"Asia-Pacific",
        "LSE":"Europe","AMS":"Europe","EPA":"Europe","STO":"Europe","BIT":"Europe","FRA":"Europe"
    }
    u["Region"] = u["Market"].map(REGION_MAP).fillna("Other")

if "Weight" not in u.columns:
    u["Weight"] = 1 / len(u)

tickers = u["Symbol"].tolist()

# ─── Fetch prices via yfinance ─────────────────────────────
prices = yf.download(tickers, period=PR_PERIOD, interval=PR_STEP)["Adj Close"].iloc[-1]

# ─── Stooq fallback helper ────────────────────────────────
def stooq_price(sym: str) -> float | None:
    """
    Convert Yahoo-style symbol to Stooq code and return last non-zero close.
    """
    m = re.match(r"([^.]+)(?:\\.(\\w+))?", sym)
    if not m:
        return None
    base, suf = m.group(1), m.group(2)
    stooq_code = {
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
    }.get(suf, None)
    if not stooq_code:
        return None
    url = f"https://stooq.com/q/d/l/?s={stooq_code}&i=d"
    try:
        csv_bytes = requests.get(url, timeout=10).content
        df = pd.read_csv(io.BytesIO(csv_bytes))
        close_series = df["Close"][df["Close"] > 0]   # filter non-zero
        return float(close_series.iloc[-1]) if not close_series.empty else None
    except Exception:
        return None

# ─── Build component list ─────────────────────────────────
components, skipped = [], []
for _, row in u.iterrows():
    sym, reg, w = row["Symbol"], row["Region"], row["Weight"]
    px = prices.get(sym)
    if pd.isna(px):
        px = stooq_price(sym)
    if px and not pd.isna(px):
        components.append({
            "symbol": sym,
            "price" : float(px),
            "weight": float(w),
            "region": reg
        })
    else:
        skipped.append(sym)

if skipped:
    print(f"⚠️  Skipped {len(skipped)} symbols after Stooq fallback:", ', '.join(skipped))

# ─── Aggregate by region ──────────────────────────────────
def region_val(region: str) -> float:
    subset = components if region == "All" else [c for c in components if c["region"] == region]
    return sum(c["price"] * c["weight"] for c in subset)

now_iso = datetime.now(timezone.utc).isoformat()
values  = {r: region_val(r) for r in ["All","North America","Europe","Asia-Pacific","Other"]}

# ─── Write latest.json ────────────────────────────────────
with open(SNAPSHOT, "w") as f:
    json.dump({
        "last_updated": now_iso,
        "components" : components,
        "values"     : values
    }, f, indent=2)

# ─── Append history.csv ───────────────────────────────────
row    = [now_iso] + [values[k] for k in ["All","North America","Europe","Asia-Pacific","Other"]]
header = ["timestamp","All","North America","Europe","Asia-Pacific","Other"]
new_file = not os.path.exists(HISTORY)

with open(HISTORY, "a", newline="") as f:
    w = csv.writer(f)
    if new_file:
        w.writerow(header)
    w.writerow(row)

print("✓ Index updated", now_iso)
