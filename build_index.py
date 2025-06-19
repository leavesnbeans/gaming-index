#!/usr/bin/env python3
"""
Gaming Index builder  –  yfinance + Stooq fallback
• Tries yfinance first (1-min intraday, ~15-min delay)
• For any missing/NaN price, fetches last close from Stooq CSV
• Writes latest.json  +  history.csv
"""

import json, csv, os, re, pandas as pd, yfinance as yf
from datetime import datetime, timezone

SRC_XLSX  = "gaming_universe_fixed.xlsx"   # your sheet name
SNAPSHOT  = "latest.json"
HISTORY   = "history.csv"
PR_PERIOD = "1d"
PR_STEP   = "1m"

# ─── load universe ──────────────────────────────────────────
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

# ─── fetch prices from Yahoo first ─────────────────────────
prices = yf.download(tickers, period=PR_PERIOD, interval=PR_STEP)["Adj Close"].iloc[-1]

# ─── helper: Stooq fallback ────────────────────────────────
def stooq_price(sym: str) -> float | None:
    """
    Map Yahoo-style symbol to Stooq code and return last close.
    """
    # split "6460.T" → base 6460, suf T
    m = re.match(r"([^.]+)(?:\\.(\\w+))?", sym)
    if not m: return None
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

    url = f"https://stooq.com/q/l/?s={stooq_code}&i=d"
    try:
        return float(pd.read_csv(url).iloc[0, 1])
    except Exception:
        return None

# ─── build component list ─────────────────────────────────
components, skipped = [], []
for _, row in u.iterrows():
    sym, reg, w = row["Symbol"], row["Region"], row["Weight"]
    px = prices.get(sym)

    if pd.isna(px):
        px = stooq_price(sym)  # try Stooq

    if px and not pd.isna(px):
        components.append({"symbol": sym,
                           "price":  float(px),
                           "weight": float(w),
                           "region": reg})
    else:
        skipped.append(sym)

if skipped:
    print(f"⚠️  Skipped {len(skipped)} symbols after Stooq fallback:", ', '.join(skipped))

# ─── aggregate by region ──────────────────────────────────
def region_val(region: str) -> float:
    subset = components if region == "All" else [c for c in components if c["region"] == region]
    return sum(c["price"] * c["weight"] for c in subset)

now_iso = datetime.now(timezone.utc).isoformat()
values  = {r: region_val(r) for r in ["All","North America","Europe","Asia-Pacific","Other"]}

# ─── write latest.json ─────────────────────────────────────
with open(SNAPSHOT, "w") as f:
    json.dump({"last_updated": now_iso,
               "components":  components,
               "values":      values}, f, indent=2)

# ─── append history.csv ───────────────────────────────────
row    = [now_iso] + [values[k] for k in ["All","North America","Europe","Asia-Pacific","Other"]]
header = ["timestamp","All","North America","Europe","Asia-Pacific","Other"]
new    = not os.path.exists(HISTORY)

with open(HISTORY, "a", newline="") as f:
    w = csv.writer(f)
    if new: w.writerow(header)
    w.writerow(row)

print("✓ Index updated", now_iso)
