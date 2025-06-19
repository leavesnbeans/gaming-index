#!/usr/bin/env python3
"""
Gaming Index builder  –  v2025-06-19
• Reads gaming_universe_prepared.xlsx
• Ensures all symbols are strings (avoids int→ISIN error)
• Pulls delayed prices via yfinance
• Saves snapshot  → latest.json
• Appends a row   → history.csv
"""
import json, csv, os, yfinance as yf, pandas as pd
from datetime import datetime, timezone

# ─── filenames ───────────────────────────────────────────────
SRC_XLSX   = "gaming_universe_prepared.xlsx"   # adjust if you renamed it
SNAP_JSON  = "latest.json"
HIST_CSV   = "history.csv"

# ─── yfinance look-back ──────────────────────────────────────
PR_PERIOD  = "1d"   # today
PR_STEP    = "1m"   # 1-minute bars (~15-min delayed)

# ─── load & scrub universe ──────────────────────────────────
u = pd.read_excel(SRC_XLSX)

# drop completely blank symbol cells
u = u.dropna(subset=["Symbol"])

# coerce every symbol to a trimmed string
u["Symbol"] = u["Symbol"].astype(str).str.strip()

# add Region if missing
if "Region" not in u.columns:
    REGION_MAP = {
        "NYSE":"North America","NASDAQ":"North America","OTCMKTS":"North America","TSE":"North America",
        "ASX":"Asia-Pacific","HKG":"Asia-Pacific","TYO":"Asia-Pacific","SGX":"Asia-Pacific",
        "LSE":"Europe","AMS":"Europe","EPA":"Europe","STO":"Europe","BIT":"Europe","FRA":"Europe"
    }
    u["Region"] = u["Market"].map(REGION_MAP).fillna("Other")

# add equal Weight if missing
if "Weight" not in u.columns:
    u["Weight"] = 1 / len(u)

tickers = u["Symbol"].tolist()

# ─── fetch prices ────────────────────────────────────────────
prices = yf.download(tickers,
                     period   = PR_PERIOD,
                     interval = PR_STEP)["Adj Close"].iloc[-1]

# ─── build component list ────────────────────────────────────
components = []
for _, row in u.iterrows():
    sym, reg, w = row["Symbol"], row["Region"], row["Weight"]
    components.append({
        "symbol": sym,
        "price" : float(prices[sym]),
        "weight": float(w),
        "region": reg
    })

# helper to sum by region
def region_val(region:str) -> float:
    subset = components if region == "All" else [c for c in components if c["region"] == region]
    return sum(c["price"] * c["weight"] for c in subset)

now_iso = datetime.now(timezone.utc).isoformat()
values  = {r: region_val(r) for r in ["All","North America","Europe","Asia-Pacific","Other"]}

# ─── write latest.json ───────────────────────────────────────
with open(SNAP_JSON, "w") as f:
    json.dump({
        "last_updated": now_iso,
        "components"  : components,
        "values"      : values
    }, f, indent=2)

# ─── append history.csv ─────────────────────────────────────
row    = [now_iso] + [values[k] for k in ["All","North America","Europe","Asia-Pacific","Other"]]
header = ["timestamp","All","North America","Europe","Asia-Pacific","Other"]
is_new = not os.path.exists(HIST_CSV)

with open(HIST_CSV, "a", newline="") as f:
    w = csv.writer(f)
    if is_new:
        w.writerow(header)
    w.writerow(row)

print("✓ Index updated", now_iso)
