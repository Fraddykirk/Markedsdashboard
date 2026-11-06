import numpy as np, pandas as pd, yfinance as yf
def rsi(x, n=14):
    d = x.diff(); g = d.clip(lower=0); l = -d.clip(upper=0)
    return 100 - 100/(1 + g.ewm(alpha=1/n, adjust=False).mean()/l.ewm(alpha=1/n, adjust=False).mean())
p = yf.Ticker("^IXIC").history(period="max", auto_adjust=False)["Close"]; p.index = p.index.tz_localize(None)
p = p[p.index >= "1975-01-01"]
a = p.values; N = len(a); idx = p.index
r = rsi(p)
wk = p.resample("W-FRI").last(); wr = rsi(wk).reindex(idx, method="ffill")
ma200 = p.rolling(200).mean()
H = [21, 63, 126, 252]
base = {h: a[h:]/a[:-h]-1 for h in H}
print(f"Nasdaq Composite {idx[0].date()} – {idx[-1].date()}, {N} dage")
print("Basis: " + " | ".join(f"{h}d snit {base[h].mean()*100:+.1f}% median {np.median(base[h])*100:+.1f}% pos {np.mean(base[h]>0)*100:.0f}%" for h in H))
def run(name, mask, gap=20, show=False):
    m = mask.reindex(idx).fillna(False).values
    ev = [i for i in range(N) if m[i] and not m[max(0, i-gap):i].any()]
    print(f"\n--- {name}: {len(ev)} episoder")
    for h in H:
        rr = np.array([a[i+h]/a[i]-1 for i in ev if i+h < N])
        print(f"  {h:>3}d: snit {rr.mean()*100:+6.1f}%  median {np.median(rr)*100:+6.1f}%  positiv {np.mean(rr>0)*100:4.0f}%   (basis {base[h].mean()*100:+5.1f}% / {np.mean(base[h]>0)*100:.0f}%)")
    dd = np.array([a[i:min(N, i+127)].min()/a[i]-1 for i in ev])
    print(f"  Yderligere fald inden for 6 mdr: median {np.median(dd)*100:+.1f}%, værste {dd.min()*100:+.0f}%, faldt >10% videre i {np.mean(dd<-0.10)*100:.0f}% af tilfældene")
    if show:
        for i in ev[-15:]:
            f = lambda h: f"{(a[i+h]/a[i]-1)*100:+.0f}%" if i+h < N else "–"
            print(f"    {idx[i].date()} RSI {r.iloc[i]:.0f} | 1m {f(21)} | 6m {f(126)} | 12m {f(252)} | {'over' if a[i] > ma200.iloc[i] else 'under'} MA200")
    return ev
run("Daglig RSI <= 30", r <= 30, show=True)
run("Daglig RSI <= 25", r <= 25)
run("Daglig RSI <= 30 og kurs OVER MA200 (korrektion i optrend)", (r <= 30) & (p > ma200))
run("Daglig RSI <= 30 og kurs UNDER MA200 (i nedtrend)", (r <= 30) & (p < ma200))
run("Ugentlig RSI <= 30", wr <= 30, gap=60, show=True)
for per in [("1975", "1999"), ("2000", "2012"), ("2013", "2026")]:
    sub = (r <= 30) & (idx >= per[0]) & (idx <= per[1] + "-12-31")
    run(f"Daglig RSI <= 30, {per[0]}–{per[1]}", pd.Series(sub, index=idx))
print(f"\nNu: {idx[-1].date()} kurs {a[-1]:,.0f}, daglig RSI {r.iloc[-1]:.1f}, ugentlig RSI {wr.iloc[-1]:.1f}, {'over' if a[-1] > ma200.iloc[-1] else 'under'} MA200 ({(a[-1]/ma200.iloc[-1]-1)*100:+.1f}%)")
