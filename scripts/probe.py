import requests, json
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0 Safari/537.36","Accept":"application/json, text/plain, */*"}
for eid in [173, 733, 168, 69]:
    try:
        r=requests.get(f"https://sbcharts.investing.com/events_charts/us/{eid}.json",headers=UA,timeout=40)
        print("INV",eid,r.status_code,len(r.text), r.text[:300])
        if r.ok:
            j=r.json(); d=j.get("data") or j.get("attr"); print(" keys", list(j.keys())[:10], "n", len(j.get("data",[])), j.get("data",[])[-2:] if j.get("data") else "")
    except Exception as e: print("INV",eid,"ERR",e)
r=requests.get("https://api.nasdaq.com/api/quote/list-type/nasdaq100",headers=UA,timeout=40)
print("NASDAQ", r.status_code, r.text[:300])
import io, pandas as pd
h=requests.get("https://en.wikipedia.org/wiki/Nasdaq-100",headers={"User-Agent":UA["User-Agent"]},timeout=30).text
tabs=pd.read_html(io.StringIO(h)); print("wiki tables", [(list(x.columns)[:3], len(x)) for x in tabs])
