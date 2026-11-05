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
brk = above & ~above.shift(1, fill_value=False)
sig = {
 "Over øvre bånd, VIX < 20": brk & (v < 20),
 "Over øvre bånd, VIX 20-30": brk & (v >= 20) & (v < 30),
 "Over øvre bånd, VIX >= 30": brk & (v >= 30),
 "VIX >= 35 (uanset bånd)": (v >= 35) & ~(v.shift(1) >= 35),
 "VIX >= 25 OG S&P > 10% under top (kombineret)": (v >= 25) & (d["^GSPC"] / d["^GSPC"].cummax() < 0.9),
}
H = [5, 20, 60, 125, 250]
def declus(mask, gap=20):
    idx = np.where(mask.values)[0]; keep = []; last = -10**9
    for i in idx:
        if i - last >= gap: keep.append(i)
        last = i if i - last >= gap else last
    return keep
print(f"Periode: {d.index[0].date()} – {d.index[-1].date()}, {len(d)} handelsdage")
for idxname in ["^IXIC"]:
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

print("\nAktuelt:", d.index[-1].date(), f"VIX {v.iloc[-1]:.2f} øvre {up.iloc[-1]:.2f} nedre {lo.iloc[-1]:.2f}")
