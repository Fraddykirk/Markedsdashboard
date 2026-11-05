import requests, json, re, io
import pandas as pd
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
r=requests.get("https://api.db.nomics.world/v22/series/ISM/pmi?observations=1&limit=20",headers=UA,timeout=60).json()
for s in r["series"]["docs"]:
    print("DBN", s["series_code"], s.get("series_name"), s["period"][:2], s["period"][-2:], s["value"][-3:], len(s["period"]))
h=requests.get("https://tradingeconomics.com/united-states/business-confidence",headers=UA,timeout=60).text
tabs=pd.read_html(io.StringIO(h))
for x in tabs: print("\nTE table", list(x.columns)); print(x.head(15).to_string()[:2500])
h=requests.get("https://en.wikipedia.org/wiki/Nasdaq-100",headers=UA,timeout=30).text
for x in pd.read_html(io.StringIO(h)):
    if len(x)>90: print("\nNDX", list(x.columns), len(x), x.iloc[0].tolist())
r=requests.post("https://api.bls.gov/publicAPI/v1/timeseries/data/",json={"seriesid":["CUUR0000SA0","CUUR0000SA0L1E"],"startyear":"2015","endyear":"2026"},headers=UA,timeout=60).json()
print("\nBLS", r["status"], r.get("message"), [ (s["seriesID"], len(s["data"]), s["data"][0]["year"], s["data"][-1]["year"]) for s in r["Results"]["series"]])
r=requests.get("https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2016-01-01&endDate=2026-11-05",headers=UA,timeout=60).json()
print("EFFR", len(r["refRates"]), r["refRates"][-1]["effectiveDate"], r["refRates"][0]["effectiveDate"])
