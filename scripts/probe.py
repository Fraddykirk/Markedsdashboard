import requests, json
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0 Safari/537.36","Accept":"application/json, text/plain, */*","Origin":"https://www.nasdaq.com","Referer":"https://www.nasdaq.com/"}
for d in ["2026-02-02","2026-06-01","2025-10-01","2021-03-01","2016-12-01"]:
    try:
        r=requests.get(f"https://api.nasdaq.com/api/calendar/economicevents?date={d}",headers=UA,timeout=40)
        j=r.json(); rows=(j.get("data") or {}).get("rows") or []
        print(d, r.status_code, len(rows), [x for x in rows if "ISM" in (x.get("eventName") or "") or "PMI" in (x.get("eventName") or "")][:3])
    except Exception as e: print(d,"ERR",e)
