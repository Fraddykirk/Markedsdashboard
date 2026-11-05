import numpy as np, pandas as pd, yfinance as yf
px = {}
for s in ["^VIX", "^IXIC", "^GSPC"]:
    df = yf.Ticker(s).history(period="max", interval="1d", auto_adjust=False)
    px[s] = df["Close"].tz_localize(None)
d = pd.concat(px, axis=1).dropna()
d = d[d.index >= "1990-01-01"]
v = d["^VIX"]
mid = v.rolling(20).mean(); sd = v.rolling(20).std(ddof=0)
up, lo = mid + 2*sd, mid - 2*sd
above = v > up; below = v < lo
sig = {
 "VIX lukker OVER øvre bånd": above & ~above.shift(1, fill_value=False),
 "VIX lukker tilbage UNDER øvre bånd (efter spike)": (~above) & above.shift(1, fill_value=False),
 "VIX lukker UNDER nedre bånd": below & ~below.shift(1, fill_value=False),
}
H = [5, 20, 60, 125, 250]
def declus(mask, gap=20):
    idx = np.where(mask.values)[0]; keep = []; last = -10**9
    for i in idx:
        if i - last >= gap: keep.append(i)
        last = i if i - last >= gap else last
    return keep
print(f"Periode: {d.index[0].date()} – {d.index[-1].date()}, {len(d)} handelsdage")
for idxname in ["^IXIC", "^GSPC"]:
    p = d[idxname].values
    print(f"\n===== {idxname} =====")
    base = {h: (p[h:]/p[:-h]-1) for h in H}
    print("Alle dage (basis):", " | ".join(f"{h}d: snit {base[h].mean()*100:+.1f}% / positiv {np.mean(base[h]>0)*100:.0f}%" for h in H))
    for name, m in sig.items():
        ev = declus(m)
        print(f"\n{name}: {len(ev)} signaler (min. 20 dage mellem)")
        for h in H:
            r = np.array([p[i+h]/p[i]-1 for i in ev if i+h < len(p)])
            if len(r)==0: continue
            dd = []
            for i in ev:
                if i+h < len(p): dd.append(p[i:i+h+1].min()/p[i]-1)
            print(f"  {h:>3}d: n={len(r):>3}  snit {r.mean()*100:+6.1f}%  median {np.median(r)*100:+6.1f}%  positiv {np.mean(r>0)*100:4.0f}%  vs basis snit {base[h].mean()*100:+5.1f}% pos {np.mean(base[h]>0)*100:3.0f}%  | snit værste fald undervejs {np.mean(dd)*100:+5.1f}%")
    # 2016+ (dashboardets periode)
    ev = [i for i in declus(sig["VIX lukker OVER øvre bånd"]) if d.index[i] >= pd.Timestamp("2016-01-01")]
    r = np.array([p[i+60]/p[i]-1 for i in ev if i+60 < len(p)])
    print(f"\nKun 2016+: OVER øvre bånd, 60d: n={len(r)} snit {r.mean()*100:+.1f}% positiv {np.mean(r>0)*100:.0f}%")
# største drawdowns: hvor mange signaler kom før bunden
p = d["^GSPC"]
print("\nEksempler (S&P 500) – signal OVER øvre bånd, efterfølgende 60d afkast:")
for i in declus(sig["VIX lukker OVER øvre bånd"]):
    if d.index[i].year in (2000,2001,2002,2007,2008,2020,2022,2025) and i+60 < len(p):
        print(f"  {d.index[i].date()}  VIX {v.iloc[i]:.1f}  S&P 60d {(p.iloc[i+60]/p.iloc[i]-1)*100:+.1f}%")
print("\nAktuelt:", d.index[-1].date(), f"VIX {v.iloc[-1]:.2f} øvre {up.iloc[-1]:.2f} nedre {lo.iloc[-1]:.2f}")
