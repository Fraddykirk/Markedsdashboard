import numpy as np, pandas as pd, requests
rows, url = [], "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
params = {"assets": "btc", "metrics": "PriceUSD,CapMVRVCur,HashRate,IssTotUSD", "frequency": "1d", "page_size": 10000, "start_time": "2010-07-18"}
while url:
    j = requests.get(url, params=params, timeout=60).json(); rows += j["data"]; url = j.get("next_page_url"); params = None
cm = pd.DataFrame(rows); cm["time"] = pd.to_datetime(cm["time"]).dt.tz_localize(None).dt.normalize(); cm = cm.set_index("time")
for c in ["PriceUSD", "CapMVRVCur", "HashRate", "IssTotUSD"]: cm[c] = pd.to_numeric(cm.get(c), errors="coerce")
p = cm["PriceUSD"].dropna(); idx = p.index
fng = requests.get("https://api.alternative.me/fng/?limit=0&format=json", timeout=60).json()["data"]
fng = pd.Series({pd.Timestamp(int(x["timestamp"]), unit="s").normalize(): float(x["value"]) for x in fng}).sort_index()
hr = cm["HashRate"]; h30, h60 = hr.rolling(30).mean(), hr.rolling(60).mean()
below = (h30 < h60); cross_up = below.shift(1, fill_value=False) & ~below & below.rolling(20).sum().shift(1).ge(10)
ribbon = cross_up.astype(int).rolling(45, min_periods=1).max().astype(bool)
puell = cm["IssTotUSD"] / cm["IssTotUSD"].rolling(365).mean()
ma1400 = p.rolling(1400).mean()
wma = p.resample("W-SUN").last().rolling(200).mean()
mvrv = cm["CapMVRVCur"]; realized = p / mvrv
dd = p / p.cummax() - 1
sig = pd.DataFrame({
 "MVRV<1": (mvrv < 1), "Under 200-ugers MA": (p < ma1400), "Puell<0.5": (puell < 0.5),
 "Hash ribbon": ribbon, "-70% fra ATH": (dd <= -0.70), "F&G<=15": (fng <= 15).reindex(idx).fillna(False)}).reindex(idx).fillna(False)
score = sig.sum(axis=1)
last = idx[-1]
print(f"DATO {last.date()}  (CoinMetrics' seneste dag; F&G seneste {fng.index[-1].date()} = {fng.iloc[-1]:.0f})")
print(f"Kurs {p.iloc[-1]:,.0f}  ATH {p.cummax().iloc[-1]:,.0f} ({p.idxmax().date()})  fald fra ATH {dd.iloc[-1]*100:.1f}%")
m = mvrv.dropna(); print(f"MVRV {m.iloc[-1]:.2f}  realized price {realized.dropna().iloc[-1]:,.0f}")
print(f"200-ugers MA (1400 dage) {ma1400.iloc[-1]:,.0f}  | ugentlig 200W {wma.dropna().iloc[-1]:,.0f}  | kurs vs 1400d {(p.iloc[-1]/ma1400.iloc[-1]-1)*100:+.1f}%")
print(f"Puell {puell.dropna().iloc[-1]:.2f}")
print(f"Hashrate 30d vs 60d: {'30d UNDER 60d (minerne presset)' if h30.iloc[-1] < h60.iloc[-1] else '30d over 60d'}  ({(h30.iloc[-1]/h60.iloc[-1]-1)*100:+.1f}%), seneste ribbon-købssignal: {cross_up[cross_up].index[-1].date() if cross_up.any() else '-'}")
print("SIGNALER NU:", {c: bool(sig[c].iloc[-1]) for c in sig.columns}, "SCORE", int(score.iloc[-1]))
for k in (3, 4):
    hit = score[score >= k]; print(f"Sidste gang score>={k}: {hit.index[-1].date() if len(hit) else '-'} (kurs {p[hit.index[-1]]:,.0f})" if len(hit) else f"score>={k}: aldrig")
print("Maks score i 2026:", int(score[score.index >= "2026-01-01"].max()), "den", score[score.index >= "2026-01-01"].idxmax().date())
w = pd.DataFrame({"p": p, "s": score, "fng": fng.reindex(idx), "mvrv": mvrv, "puell": puell}).resample("W-SUN").last().tail(20)
print(w.round(2).to_string())
# historisk: værdier ved tidligere bunde
for b in ["2015-01-14", "2018-12-15", "2020-03-12", "2022-11-21"]:
    t = pd.Timestamp(b); print(f"Bund {b}: kurs {p[t]:,.0f} MVRV {mvrv[t]:.2f} kurs/200W {(p[t]/ma1400[t]-1)*100 if pd.notna(ma1400[t]) else float('nan'):+.0f}% Puell {puell[t]:.2f} fald fra ATH {dd[t]*100:.0f}% score {int(score[t])}")
