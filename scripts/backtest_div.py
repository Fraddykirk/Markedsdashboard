import numpy as np, pandas as pd, requests, yfinance as yf
def rsi(x, n):
    d = x.diff(); g = d.clip(lower=0); l = -d.clip(upper=0)
    return 100 - 100/(1 + g.ewm(alpha=1/n, adjust=False).mean()/l.ewm(alpha=1/n, adjust=False).mean())
# BTC-daglukkekurser: CoinMetrics (2010+), ellers Yahoo (2014+)
try:
    rows, url = [], "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    params = {"assets": "btc", "metrics": "PriceUSD", "frequency": "1d", "page_size": 10000, "start_time": "2011-01-01"}
    while url:
        j = requests.get(url, params=params, timeout=60).json(); rows += j["data"]; url = j.get("next_page_url"); params = None
    p = pd.Series({pd.Timestamp(x["time"][:10]): float(x["PriceUSD"]) for x in rows}).sort_index(); src = "CoinMetrics"
except Exception as e:
    p = yf.Ticker("BTC-USD").history(period="max")["Close"]; p.index = p.index.tz_localize(None).normalize(); src = "Yahoo"
p = p[p.index >= "2013-01-01"]
a = p.values; N = len(a); idx = p.index; r4 = rsi(p, 4).values
H = [3, 7, 14, 30]
print(f"BTC {src}: {idx[0].date()} – {idx[-1].date()}, {N} dage")
def stats(name, ev):
    ev = [i for i in ev if i + max(H) < N]
    if not ev: print(f"\n{name}: ingen"); return
    out = [f"\n{name}: n={len(ev)}"]
    for h in H:
        rr = np.array([a[i+h]/a[i]-1 for i in ev])
        up = np.array([a[i+1:i+h+1].max()/a[i]-1 for i in ev])
        out.append(f"  {h:>2}d: afkast snit {rr.mean()*100:+5.1f}% median {np.median(rr)*100:+5.1f}% op {np.mean(rr>0)*100:3.0f}% | max-stigning undervejs ≥5%: {np.mean(up>=.05)*100:3.0f}%, ≥10%: {np.mean(up>=.10)*100:3.0f}%")
    print("\n".join(out))
def declus(mask, gap):
    ev, last = [], -10**9
    for i in np.where(mask)[0]:
        if i - last >= gap: ev.append(i)
        last = i if i - last >= gap else last
    return ev
alld = list(range(30, N))
down = (pd.Series(a, index=idx) < pd.Series(a, index=idx).rolling(20).mean()).values & (a < np.roll(a, 14))
print("\n######## SAMMENLIGNINGSGRUNDLAG ########")
stats("Alle dage", alld)
stats("Alle dage i nedtrend (under 20d-gennemsnit og lavere end for 14 dage siden)", [i for i in alld if down[i]])

print("\n######## METODE 1: klassisk divergens på bundpunkter ########")
# bundpunkt i dag i = laveste lukkekurs i [i-k, i+k]; bekræftes først k dage senere (ingen kig ind i fremtiden)
for k in (2, 3):
    piv = [i for i in range(k, N-k) if a[i] == a[i-k:i+k+1].min()]
    div, ll_only, div_os = [], [], []
    for j in range(1, len(piv)):
        i1, i2 = piv[j-1], piv[j]
        if not (4 <= i2 - i1 <= 45) or not a[i2] < a[i1]: continue
        entry = i2 + k
        if r4[i2] > r4[i1]:
            div.append(entry)
            if r4[i1] < 20: div_os.append(entry)
        else: ll_only.append(entry)
    stats(f"[k={k}] Lavere bund i kurs + HØJERE bund i RSI(4) = divergens", div)
    stats(f"[k={k}]   heraf første RSI-bund under 20 (udsolgt)", div_os)
    stats(f"[k={k}] Kontrol: lavere bund i kurs UDEN divergens", ll_only)
print("\n######## METODE 2: hældning over en periode ########")
for n in (7, 14, 21):
    t = np.arange(n); t = t - t.mean()
    sl_p = np.full(N, np.nan); sl_r = np.full(N, np.nan)
    lp = np.log(a)
    for i in range(n, N):
        sl_p[i] = (t * lp[i-n+1:i+1]).sum() / (t*t).sum()
        sl_r[i] = (t * r4[i-n+1:i+1]).sum() / (t*t).sum()
    m = (sl_p < 0) & (sl_r > 0)
    stats(f"[{n} dage] Kurs faldende, RSI(4) stigende (første dag, min. {n} dage mellem)", declus(m, n))
    stats(f"[{n} dage] Kontrol: kurs faldende, RSI(4) også faldende", declus((sl_p < 0) & (sl_r < 0), n))
print("\n######## PERIODER (metode 1, k=3) ########")
piv = [i for i in range(3, N-3) if a[i] == a[i-3:i+4].min()]
div = [piv[j]+3 for j in range(1, len(piv)) if 4 <= piv[j]-piv[j-1] <= 45 and a[piv[j]] < a[piv[j-1]] and r4[piv[j]] > r4[piv[j-1]]]
for y0, y1 in [("2013", "2017"), ("2018", "2021"), ("2022", "2026")]:
    stats(f"Divergens {y0}–{y1}", [i for i in div if y0 <= str(idx[i].year) <= y1])
print("\nSeneste 10 signaler (metode 1, k=3):")
for i in div[-10:]:
    f = lambda h: f"{(a[i+h]/a[i]-1)*100:+.0f}%" if i+h < N else "–"
    print(f"  {idx[i].date()} kurs {a[i]:,.0f} | 7d {f(7)} | 14d {f(14)} | 30d {f(30)}")
t = np.arange(14) - 6.5
print(f"\nNu: {idx[-1].date()} kurs {a[-1]:,.0f}, RSI(4) {r4[-1]:.1f}, hældning 14d kurs {'faldende' if (t*np.log(a[-14:])).sum() < 0 else 'stigende'}, RSI {'stigende' if (t*r4[-14:]).sum() > 0 else 'faldende'}")
print("Seneste 10 dage RSI(4):", [round(x) for x in r4[-10:]], "kurs:", [round(x) for x in a[-10:]])
