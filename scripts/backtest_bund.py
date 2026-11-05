import json, numpy as np, pandas as pd, requests, yfinance as yf
pd.set_option("display.width", 200)
def close(s, start="1990-01-01"):
    df = yf.Ticker(s).history(period="max", interval="1d", auto_adjust=False)
    x = df["Close"]; x.index = x.index.tz_localize(None).normalize(); return x[x.index >= start]
def rsi(x, n=14):
    d = x.diff(); g = d.clip(lower=0); l = -d.clip(upper=0)
    ag = g.ewm(alpha=1/n, adjust=False).mean(); al = l.ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + ag/al)
def evaluate(name, p, score, H, bottoms, ks, gap, labels, sig):
    p = p.dropna(); score = score.reindex(p.index).fillna(0)
    a = p.values; idx = p.index; N = len(a)
    print(f"\n==================== {name}: {idx[0].date()} – {idx[-1].date()} ====================")
    base = {h: a[h:]/a[:-h]-1 for h in H}
    print("Basis (alle dage): " + " | ".join(f"{h}d snit {base[h].mean()*100:+.1f}% pos {np.mean(base[h]>0)*100:.0f}%" for h in H))
    print("Andel af dagene hvor hvert signal er aktivt: " + ", ".join(f"{l} {sig[l].reindex(idx).fillna(False).mean()*100:.1f}%" for l in labels))
    for k in ks:
        m = (score >= k).values
        ev = [i for i in range(N) if m[i] and not m[max(0, i-gap):i].any()]
        print(f"\n--- Score >= {k}: {len(ev)} episoder (ny episode efter {gap} dage uden signal), aktiv {m.mean()*100:.1f}% af dagene")
        for h in H:
            r = np.array([a[i+h]/a[i]-1 for i in ev if i+h < N])
            if len(r): print(f"  {h:>3}d: n={len(r):>2} snit {r.mean()*100:+6.1f}% median {np.median(r)*100:+6.1f}% positiv {np.mean(r>0)*100:4.0f}%   (basis snit {base[h].mean()*100:+5.1f}%, pos {np.mean(base[h]>0)*100:.0f}%)")
        hmax = H[-1]
        print("  Episoder: dato | score | kurs | 6m | 12m | yderligere fald før bund (inden for 12m)")
        for i in ev:
            f6 = f"{(a[i+H[1]]/a[i]-1)*100:+.0f}%" if i+H[1] < N else "  –"
            f12 = f"{(a[i+hmax]/a[i]-1)*100:+.0f}%" if i+hmax < N else "  –"
            dd = (a[i:min(N, i+hmax+1)].min()/a[i]-1)*100
            print(f"    {idx[i].date()} | {int(score.iloc[i])} | {a[i]:,.0f} | {f6} | {f12} | {dd:+.0f}%")
    print("\nKendte bunde: højeste score inden for 60 dage før bunden, og første dag score>=3 i samme periode")
    for b in bottoms:
        bt = pd.Timestamp(b); win = score[(score.index >= bt - pd.Timedelta(days=90)) & (score.index <= bt + pd.Timedelta(days=5))]
        if not len(win): print(f"  {b}: ingen data"); continue
        f3 = win[win >= 3]; first = f3.index[0] if len(f3) else None
        pb = p[p.index <= bt].iloc[-1]
        extra = f", første score>=3 {first.date()} ved kurs {p[first]:,.0f} ({(pb/p[first]-1)*100:+.0f}% ned til bunden)" if first is not None else ""
        print(f"  {b}: maks score {int(win.max())} (af {len(labels)}){extra}, aktive ved bunden: {[l for l in labels if bool(sig[l].reindex([p.index[p.index<=bt][-1]]).fillna(False).iloc[0])]}")
    wk = pd.DataFrame({"p": p, "s": score}).resample("W-FRI").last().dropna()
    print("SERIES_" + name.split()[0] + " " + json.dumps([[d.strftime("%Y-%m-%d"), round(float(r.p), 2), int(r.s)] for d, r in wk.iterrows()], separators=(",", ":")))

# ================= AKTIER (Nasdaq Composite) =================
ixic = close("^IXIC"); vix = close("^VIX"); vix3m = close("^VIX3M")
sectors = {s: close(s) for s in ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]}
hyg = close("HYG"); ief = close("IEF")
idx = ixic.index[ixic.index >= "1999-12-01"]
above = pd.DataFrame({s: (x > x.rolling(200).mean()).where(x.rolling(200).mean().notna()) for s, x in sectors.items()}).reindex(idx).ffill()
nabove = above.sum(axis=1).where(above.notna().all(axis=1))
wk = ixic.resample("W-FRI").last(); wr = rsi(wk).reindex(idx, method="ffill")
ratio = (hyg / ief).dropna()
sigE = {
    "VIX>=30": (vix >= 30).reindex(idx).fillna(False),
    "VIX>VIX3M": ((vix / vix3m) > 1.0).reindex(idx).fillna(False),
    "Sektorer<=2/9 over MA200": (nabove <= 2).fillna(False),
    "Nasdaq -20% fra 1-års top": (ixic / ixic.rolling(252, min_periods=60).max() - 1 <= -0.20).reindex(idx).fillna(False),
    "Ugentlig RSI<30": (wr < 30).fillna(False),
    "Kredit: HYG/IEF >5% under MA200": (ratio / ratio.rolling(200).mean() - 1 <= -0.05).reindex(idx).fillna(False),
}
labelsE = list(sigE)
scoreE = sum(sigE[l].astype(int) for l in labelsE)
evaluate("Nasdaq Composite", ixic.reindex(idx), scoreE, [63, 126, 252], ["2001-04-04", "2001-09-21", "2002-10-09", "2009-03-09", "2011-10-03", "2018-12-24", "2020-03-23", "2022-12-28"], [2, 3, 4], 30, labelsE, sigE)
idx8 = idx[idx >= "2008-01-01"]
evaluate("Nasdaq (2008+, alle 6 signaler tilgængelige)", ixic.reindex(idx8), scoreE.reindex(idx8), [63, 126, 252], [], [3, 4], 30, labelsE, sigE)

# ================= BITCOIN =================
rows, url = [], "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
params = {"assets": "btc", "metrics": "PriceUSD,CapMVRVCur,HashRate,IssTotUSD", "frequency": "1d", "page_size": 10000, "start_time": "2010-07-18"}
while url:
    j = requests.get(url, params=params, timeout=60).json()
    if "error" in j: print("CoinMetrics fejl:", j["error"]); break
    rows += j["data"]; url = j.get("next_page_url"); params = None
cm = pd.DataFrame(rows); cm["time"] = pd.to_datetime(cm["time"]).dt.tz_localize(None).dt.normalize(); cm = cm.set_index("time")
for c in ["PriceUSD", "CapMVRVCur", "HashRate", "IssTotUSD"]:
    cm[c] = pd.to_numeric(cm.get(c), errors="coerce")
print("CoinMetrics kolonner med data:", {c: int(cm[c].notna().sum()) for c in ["PriceUSD", "CapMVRVCur", "HashRate", "IssTotUSD"]})
p = cm["PriceUSD"].dropna()
fng = requests.get("https://api.alternative.me/fng/?limit=0&format=json", timeout=60).json()["data"]
fng = pd.Series({pd.Timestamp(int(x["timestamp"]), unit="s").normalize(): float(x["value"]) for x in fng}).sort_index()
hr = cm["HashRate"]; h30, h60 = hr.rolling(30).mean(), hr.rolling(60).mean()
below = (h30 < h60); cross_up = below.shift(1, fill_value=False) & ~below & below.rolling(20).sum().shift(1).ge(10)
ribbon = cross_up.astype(int).rolling(45, min_periods=1).max().astype(bool)
puell = cm["IssTotUSD"] / cm["IssTotUSD"].rolling(365).mean()
bidx = p.index[p.index >= "2014-06-01"]
sigB = {
    "MVRV<1 (under realized price)": (cm["CapMVRVCur"] < 1).reindex(bidx).fillna(False),
    "Under 200-ugers MA": (p < p.rolling(1400).mean()).reindex(bidx).fillna(False),
    "Puell<0.5": (puell < 0.5).reindex(bidx).fillna(False),
    "Hash ribbon købssignal (45 dage)": ribbon.reindex(bidx).fillna(False),
    "-70% fra ATH": (p / p.cummax() - 1 <= -0.70).reindex(bidx).fillna(False),
    "Krypto F&G<=15 (alternative.me)": (fng <= 15).reindex(bidx).fillna(False),
}
labelsB = list(sigB)
scoreB = sum(sigB[l].astype(int) for l in labelsB)
evaluate("Bitcoin", p.reindex(bidx), scoreB, [90, 180, 365], ["2015-01-14", "2018-12-15", "2020-03-12", "2022-11-21"], [2, 3, 4], 30, labelsB, sigB)
print("\nAktuelt Nasdaq:", idx[-1].date(), {l: bool(sigE[l].iloc[-1]) for l in labelsE}, "score", int(scoreE.iloc[-1]))
print("Aktuelt BTC:", bidx[-1].date(), {l: bool(sigB[l].iloc[-1]) for l in labelsB}, "score", int(scoreB.iloc[-1]))
print("Nasdaq sektorer over MA200 nu:", nabove.iloc[-1], " VIX/VIX3M:", round(float((vix / vix3m).dropna().iloc[-1]), 3), " MVRV:", round(float(cm['CapMVRVCur'].dropna().iloc[-1]), 2), " Puell:", round(float(puell.dropna().iloc[-1]), 2))
