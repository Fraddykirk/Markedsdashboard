import requests, json, time
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
def t(name, url, n=400, **kw):
    try:
        r=requests.get(url, headers=UA, timeout=90, **kw)
        print(f"\n## {name}: {r.status_code} len={len(r.text)}"); print(r.text[:n].replace("\n"," | ")); return r
    except Exception as e: print(f"\n## {name}: ERR {e}")
r=t("DBn ISM pm","https://api.db.nomics.world/v22/series/ISM/pmi/pm?observations=1",50)
if r: s=r.json()["series"]["docs"][0]; print("ISM last:", s["period"][-3:], s["value"][-3:], len(s["period"]))
r=t("DBn BLS CPI","https://api.db.nomics.world/v22/series/BLS/cu/CUSR0000SA0?observations=1",50)
if r and r.ok: s=r.json()["series"]["docs"][0]; print("CPI last:", s["period"][-3:], s["value"][-3:])
r=t("DBn BLS core","https://api.db.nomics.world/v22/series/BLS/cu/CUSR0000SA0L1E?observations=1",50)
if r and r.ok: s=r.json()["series"]["docs"][0]; print("core last:", s["period"][-3:], s["value"][-3:])
t("BLS API","https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0",300)
t("NYFed EFFR","https://markets.newyorkfed.org/api/rates/unsecured/effr/last/2.json",500)
t("FRED 90s","https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU&cosd=2026-01-01",200)
t("FRED api.stlouisfed alt","https://api.stlouisfed.org/fred/series/observations?series_id=DFEDTARU&file_type=json",200)
import pandas as pd, io
try:
    h=requests.get("https://en.wikipedia.org/wiki/Nasdaq-100",headers=UA,timeout=30).text
    tabs=pd.read_html(io.StringIO(h)); nd=[x for x in tabs if "Ticker" in x.columns or "Symbol" in x.columns]; print("\nNDX tables:", [ (list(x.columns)[:3], len(x)) for x in nd])
    h=requests.get("https://en.wikipedia.org/wiki/OMX_Copenhagen_25",headers=UA,timeout=30).text
    tabs=pd.read_html(io.StringIO(h)); print("C25 tables:", [ (list(x.columns)[:4], len(x)) for x in tabs if len(x)>=20])
except Exception as e: print("wiki err", e)
