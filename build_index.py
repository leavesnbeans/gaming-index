#!/usr/bin/env python3
"""
Gaming Index builder  –  resilient to missing tickers
• Reads gaming_universe_fixed.xlsx
• Coerces Symbol to str, drops blanks
• Fetches prices via yfinance
• Skips any ticker that returns no price
• Writes latest.json and history.csv
"""
import json, csv, os, yfinance as yf, pandas as pd
from datetime import datetime, timezone

SRC_XLSX  = "gaming_universe_fixed.xlsx"
SNAPSHOT  = "latest.json"
HISTORY   = "history.csv"
PR_PERIOD = "1d"
PR_STEP   = "1m"

# ── load & scrub universe ──────────────────────────────────
u = pd.read_excel(SRC_XLSX).dropna(subset=["Symbol"])
u["Symbol"] = u["Symbol"].astype(str).str.strip()

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

# ── fetch prices ───────────────────────────────────────────
prices = yf.download(tickers, period=PR_PERIOD, interval=PR_STEP)["Adj Close"].iloc[-1]

# ── build component list (skip NaNs) ───────────────────────
components, skipped = [], []
for _, row in u.iterrows():
    sym, reg, w = row["Symbol"], row["Region"], row["Weight"]
    if sym in prices and pd.notna(prices[sym]):
        components.append({"symbol":sym,"price":float(prices[sym]),"weight":float(w),"region":reg})
    else:
        skipped.append(sym)

if skipped:
    print(f"⚠️  Skipped {len(skipped)} symbols with no price:", ", ".join(skipped))

# helper to sum by region
def region_val(region:str) -> float:
    subset = components if region == "All" else [c for c in components if c["region"] == region]
    return sum(c["price"] * c["weight"] for c in subset)

now_iso = datetime.now(timezone.utc).isoformat()
values  = {r: region_val(r) for r in ["All","North America","Europe","Asia-Pacific","Other"]}

# ── write latest.json ──────────────────────────────────────
with open(SNAPSHOT, "w") as f:
    json.dump({"last_updated":now_iso,"components":components,"values":values}, f, indent=2)

# ── append history.csv ─────────────────────────────────────
row    = [now_iso] + [values[k] for k in ["All","North America","Europe","Asia-Pacific","Other"]]
header = ["timestamp","All","North America","Europe","Asia-Pacific","Other"]
is_new = not os.path.exists(HISTORY)
with open(HISTORY, "a", newline="") as f:
    w = csv.writer(f)
    if is_new: w.writerow(header)
    w.writerow(row)

print("✓ Index updated", now_iso)
