#!/usr/bin/env python3
"""
Build full history.csv (5 years, daily closes)
• Reads the current gaming_universe_fixed.xlsx
• Uses yfinance for primary quotes, falls back to Stooq daily closes
• Writes a brand-new history.csv covering every market day
"""
import json, csv, os, re, io, requests, pandas as pd, yfinance as yf
from datetime import datetime

SRC_XLSX  = "gaming_universe_fixed.xlsx"
OUT_CSV   = "history.csv"
YEARS     = 5                      # how far back
REGIONS   = ["All","North America","Europe","Asia-Pacific","Other"]

# ── universe ───────────────────────────────────────────────
u = pd.read_excel(SRC_XLSX).assign(Symbol=lambda d:d["Symbol"].astype(str).str.strip())
if "Weight" not in u.columns:
    u["Weight"] = 1/len(u)

region_map = {
    "NYSE":"North America","NASDAQ":"North America","OTCMKTS":"North America","TSE":"North America",
    "ASX":"Asia-Pacific","HKG":"Asia-Pacific","TYO":"Asia-Pacific","SGX":"Asia-Pacific",
    "LSE":"Europe","AMS":"Europe","EPA":"Europe","STO":"Europe","BIT":"Europe","FRA":"Europe"
}
if "Region" not in u.columns:
    u["Region"] = u["Market"].map(region_map).fillna("Other")

tickers = u["Symbol"].tolist()

# ── fetch bulk daily prices from yfinance ──────────────────
yf_hist = yf.download(tickers, period=f"{YEARS}y", interval="1d")["Adj Close"]

# ── Stooq helper ───────────────────────────────────────────
def stooq_hist(sym:str)->pd.Series|None:
    m=re.match(r"([^.]+)(?:\\.(\\w+))?",sym);base,suf=m.group(1),m.group(2) if m else (sym,None)
    code_map={None:f\"{base}.us\",\"AX\":f\"{base}.au\",\"HK\":f\"{base}.hk\",\"T\":f\"{base}.jp\",
              \"ST\":f\"{base}.se\",\"L\":f\"{base}.uk\",\"PA\":f\"{base}.fr\",\"F\":f\"{base}.de\",
              \"MI\":f\"{base}.it\",\"AS\":f\"{base}.nl\"}
    st=code_map.get(suf)
    if not st: return None
    url=f\"https://stooq.com/q/d/l/?s={st}&i=d\"
    try:
        df=pd.read_csv(url,parse_dates=['Date']).set_index('Date')
        return df['Close'].replace(0,pd.NA)
    except: return None

# ── merge yfinance & Stooq per ticker ──────────────────────
prices={}
for sym in tickers:
    s=yf_hist[sym]
    if s.isna().all():
        s2=stooq_hist(sym)
        if s2 is not None:
            s=s2.reindex_like(s)
    prices[sym]=s

# ── assemble dataframe of index levels ─────────────────────
df_idx=pd.DataFrame(index=yf_hist.index)
for region in REGIONS:
    vals=[]
    for dt in df_idx.index:
        tot=0
        for _,row in u.iterrows():
            if region!='All' and row['Region']!=region: continue
            px=prices[row['Symbol']].loc[dt]
            if pd.notna(px):
                tot+=px*row['Weight']
        vals.append(tot)
    df_idx[region]=vals

# drop rows where All == 0 (non-trading days)
df_idx=df_idx[df_idx['All']>0]

# ── write history.csv ──────────────────────────────────────
df_idx.reset_index().rename(columns={'Date':'timestamp'}).to_csv(OUT_CSV,index=False)
print("Wrote",OUT_CSV,"with",len(df_idx),"rows")
