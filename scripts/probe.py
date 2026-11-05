import requests, io, pandas as pd
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0 Safari/537.36","Accept-Language":"en-US,en;q=0.9","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
r=requests.get("https://api.db.nomics.world/v22/series/ISM/pmi/pm?observations=1",timeout=60).json()["series"]["docs"][0]
print("DBN", list(zip(r["period"],r["value"]))[:6], list(zip(r["period"],r["value"]))[-6:])
for u in ["https://ycharts.com/indicators/us_pmi","https://www.ycharts.com/indicators/us_pmi","https://www.econdb.com/api/series/?search=ISM%20manufacturing&format=json",
          "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/pmi/october/",
          "https://www.forexfactory.com/calendar","https://www.marketwatch.com/economy-politics/calendar"]:
    try:
        x=requests.get(u,headers=UA,timeout=40); print("\nURL",u,x.status_code,len(x.text))
        if x.ok and "ycharts" in u:
            for t in pd.read_html(io.StringIO(x.text)): print(t.head(30).to_string()[:1800])
        if x.ok and "econdb" in u: print(x.text[:800])
        if x.ok and "ismworld" in u:
            import re; i=x.text.find("PMI®"); print(re.sub(r"<[^>]+>"," ",x.text[i:i+1500])[:800])
    except Exception as e: print("URL",u,"ERR",e)
