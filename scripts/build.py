"""Henter markedsdata, beregner indikatorer og bygger dashboardet til mappen site/.

Kører hver time via GitHub Actions. Lokalt: `python scripts/build.py --demo` bygger med syntetiske data.
"""
import json
import math
import os
import random
import shutil
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
SITE = os.path.join(ROOT, "site")
PREV_URL = os.environ.get("PREV_DATA_URL", "")  # sidste publicerede data.json, bruges hvis en kilde fejler

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

ASSETS = {
    "btc": {"symbol": "BTC-USD", "name": "Bitcoin", "unit": "USD"},
    "eth": {"symbol": "ETH-USD", "name": "Ethereum", "unit": "USD"},
    "ndx": {"symbol": "^IXIC", "name": "Nasdaq Composite", "unit": "point"},
    "vix": {"symbol": "^VIX", "name": "VIX", "unit": "point"},
}


# ---------- datakilder ----------

def _clean(pairs):
    by_date = {}
    for d, c in pairs:
        if c is not None and math.isfinite(c) and c > 0:
            by_date[d] = float(c)
    dates = sorted(by_date)
    if len(dates) < 300:
        raise RuntimeError(f"for få datapunkter ({len(dates)})")
    return dates, [by_date[d] for d in dates]


def src_yfinance(symbol):
    import yfinance as yf
    df = yf.Ticker(symbol).history(period="10y", interval="1d", auto_adjust=False)
    return _clean((i.strftime("%Y-%m-%d"), float(c)) for i, c in zip(df.index, df["Close"]))


def src_yahoo(symbol):
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}"
    r = requests.get(url, params={"range": "10y", "interval": "1d"}, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    off = res["meta"].get("gmtoffset", 0)
    closes = res["indicators"]["quote"][0]["close"]
    return _clean((datetime.fromtimestamp(ts + off, tz=timezone.utc).strftime("%Y-%m-%d"), c)
                  for ts, c in zip(res["timestamp"], closes))


def src_cryptocompare(_):
    pairs, to_ts = [], None
    for _ in range(2):  # 2 x 2000 dage
        params = {"fsym": "BTC", "tsym": "USD", "limit": 2000}
        if to_ts:
            params["toTs"] = to_ts
        r = requests.get("https://min-api.cryptocompare.com/data/v2/histoday", params=params,
                         headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        rows = r.json()["Data"]["Data"]
        pairs += [(datetime.fromtimestamp(x["time"], tz=timezone.utc).strftime("%Y-%m-%d"), x["close"]) for x in rows]
        to_ts = rows[0]["time"] - 86400
    cutoff = (datetime.now(timezone.utc) - timedelta(days=3653)).strftime("%Y-%m-%d")
    return _clean(p for p in pairs if p[0] >= cutoff)


def src_fred(series):
    def go(_):
        start = (datetime.now(timezone.utc) - timedelta(days=3653)).strftime("%Y-%m-%d")
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series, "cosd": start},
                         headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        pairs = []
        for row in r.text.strip().splitlines()[1:]:
            d, v = row.split(",")[:2]
            try:
                pairs.append((d, float(v)))
            except ValueError:
                pass
        return _clean(pairs)
    return go


SOURCES = {
    "btc": [("Yahoo Finance", src_yfinance), ("CryptoCompare", src_cryptocompare), ("Yahoo Finance", src_yahoo), ("FRED (Coinbase)", src_fred("CBBTCUSD"))],
    "eth": [("Yahoo Finance", src_yfinance), ("Yahoo Finance", src_yahoo)],
    "ndx": [("Yahoo Finance", src_yfinance), ("Yahoo Finance", src_yahoo), ("FRED", src_fred("NASDAQCOM"))],
    "vix": [("Yahoo Finance", src_yfinance), ("Yahoo Finance", src_yahoo), ("FRED", src_fred("VIXCLS"))],
}


def fetch_prices(key, symbol):
    errs = []
    for name, fn in SOURCES[key]:
        try:
            dates, close = fn(symbol)
            print(f"{key}: {name} OK ({len(dates)} dage, sidste {dates[-1]})")
            return dates, close, name
        except Exception as e:
            errs.append(f"{name}: {str(e)[:120]}")
            print(f"{key}: {name} fejlede: {e}")
    raise RuntimeError(" | ".join(errs))


def fetch_fear_greed():
    start = (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%Y-%m-%d")
    url = f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start}"
    r = requests.get(url, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*",
        "Referer": "https://edition.cnn.com/", "Origin": "https://edition.cnn.com",
    }, timeout=30)
    r.raise_for_status()
    j = r.json()
    fg = j["fear_and_greed"]
    hist = {}
    for p in j.get("fear_and_greed_historical", {}).get("data", []):
        d = datetime.fromtimestamp(p["x"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        hist[d] = round(float(p["y"]), 1)
    return {
        "score": round(float(fg["score"]), 1),
        "rating": fg.get("rating", ""),
        "asOf": fg.get("timestamp"),
        "previousClose": _r(fg.get("previous_close")),
        "week": _r(fg.get("previous_1_week")),
        "month": _r(fg.get("previous_1_month")),
        "year": _r(fg.get("previous_1_year")),
        "history": [[d, hist[d]] for d in sorted(hist)],
    }


# ---------- CoinMarketCap Fear & Greed (krypto) ----------

def fetch_cmc_fng():
    now = int(datetime.now(timezone.utc).timestamp())
    r = requests.get("https://api.coinmarketcap.com/data-api/v3/fear-greed/chart",
                     params={"start": now - 86400 * 400, "end": now},
                     headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    rows = r.json()["data"]["dataList"]
    hist = {}
    for x in rows:
        d = datetime.fromtimestamp(int(x["timestamp"]), tz=timezone.utc).strftime("%Y-%m-%d")
        hist[d] = (float(x["score"]), x.get("name", ""))
    dates = sorted(hist)
    if not dates:
        raise RuntimeError("tom historik")
    def ago(n):
        return hist[dates[-1 - n]][0] if len(dates) > n else None
    return {
        "score": hist[dates[-1]][0], "rating": hist[dates[-1]][1], "asOf": dates[-1],
        "previousClose": ago(1), "week": ago(7), "month": ago(30), "year": ago(365),
        "history": [[d, hist[d][0]] for d in dates],
    }


# ---------- makro ----------

def _month_add(ym, n):
    y, m = map(int, ym.split("-"))
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def _valid_pmi(v):
    try:
        v = float(str(v).strip())
        return v if 25 <= v <= 80 else None
    except ValueError:
        return None


def fetch_ism(prev_series):
    """ISM Manufacturing PMI, månedlig. Historik bygges op fra Nasdaqs økonomiske kalender
    (kun manglende måneder hentes), suppleret med DBnomics og Trading Economics."""
    ser_ = dict(prev_series or {})
    if not ser_:
        try:
            r = requests.get("https://api.db.nomics.world/v22/series/ISM/pmi/pm?observations=1", timeout=60)
            doc = r.json()["series"]["docs"][0]
            for p, v in zip(doc["period"], doc["value"]):
                if p <= "2025-08" and _valid_pmi(v):
                    ser_[p] = float(v)
            print(f"ISM: {len(ser_)} måneder fra DBnomics")
        except Exception as e:
            print("ISM DBnomics fejlede:", e)
    # Seneste udgivelser fra Trading Economics
    try:
        import io
        import pandas as pd
        h = requests.get("https://tradingeconomics.com/united-states/business-confidence",
                         headers={"User-Agent": UA}, timeout=40).text
        for t in pd.read_html(io.StringIO(h)):
            if {"Calendar", "Actual", "Reference.1"} <= set(t.columns):
                for _, row in t.iterrows():
                    v = _valid_pmi(row["Actual"])
                    if v is None:
                        continue
                    rel = datetime.strptime(str(row["Calendar"])[:10], "%Y-%m-%d")
                    ref = datetime.strptime(str(row["Reference.1"])[:3], "%b").month
                    year = rel.year - (1 if ref > rel.month else 0)
                    ser_[f"{year:04d}-{ref:02d}"] = v
                    prv = _valid_pmi(row.get("Previous"))
                    if prv is not None:
                        ser_.setdefault(_month_add(f"{year:04d}-{ref:02d}", -1), prv)
    except Exception as e:
        print("ISM Trading Economics fejlede:", e)
    # Udfyld huller via Nasdaq-kalenderen (udgives første hverdag i måneden efter)
    today = datetime.now(timezone.utc)
    last_month = _month_add(today.strftime("%Y-%m"), -1)
    hdr = {"User-Agent": UA, "Accept": "application/json", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
    m, budget = "2016-01", 220
    while m <= last_month and budget > 0:
        if m not in ser_:
            rel = datetime.strptime(_month_add(m, 1) + "-01", "%Y-%m-%d")
            for k in range(6):
                d = rel + timedelta(days=k)
                if d.weekday() >= 5 or d > today.replace(tzinfo=None):
                    continue
                budget -= 1
                try:
                    j = requests.get("https://api.nasdaq.com/api/calendar/economicevents",
                                     params={"date": d.strftime("%Y-%m-%d")}, headers=hdr, timeout=20).json()
                    rows = (j.get("data") or {}).get("rows") or []
                except Exception:
                    rows = []
                hit = [x for x in rows if x.get("country") == "United States"
                       and (x.get("eventName") or "").strip().lower() in ("ism manufacturing pmi", "ism manufacturing index")]
                if hit:
                    v = _valid_pmi(hit[0].get("actual"))
                    if v is not None:
                        ser_[m] = v
                    pv = _valid_pmi(hit[0].get("previous"))
                    if pv is not None:
                        ser_.setdefault(_month_add(m, -1), pv)
                    break
        m = _month_add(m, 1)
    keys = sorted(k for k in ser_ if k >= "2016-01")
    if len(keys) < 12:
        raise RuntimeError(f"for få ISM-måneder ({len(keys)})")
    return {k: ser_[k] for k in keys}


def fetch_fed():
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r = requests.get("https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json",
                     params={"startDate": "2016-01-01", "endDate": end}, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    rows = sorted(r.json()["refRates"], key=lambda x: x["effectiveDate"])
    if len(rows) < 100:
        raise RuntimeError("for få datapunkter")
    return {
        "dates": [x["effectiveDate"] for x in rows],
        "effr": [x.get("percentRate") for x in rows],
        "lo": [x.get("targetRateFrom") for x in rows],
        "hi": [x.get("targetRateTo") for x in rows],
    }


def fetch_cpi():
    this_year = datetime.now(timezone.utc).year
    idx = {"CUUR0000SA0": {}, "CUUR0000SA0L1E": {}}
    for a, b in ((this_year - 11, this_year - 2), (this_year - 1, this_year)):
        r = requests.post("https://api.bls.gov/publicAPI/v1/timeseries/data/",
                          json={"seriesid": list(idx), "startyear": str(a), "endyear": str(b)},
                          headers={"User-Agent": UA}, timeout=60)
        j = r.json()
        if j.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS: {j.get('message')}")
        for s in j["Results"]["series"]:
            for x in s["data"]:
                if x["period"].startswith("M") and x["period"] != "M13" and x["value"] not in ("-", ""):
                    idx[s["seriesID"]][f'{x["year"]}-{x["period"][1:]}'] = float(x["value"])
    head, core = idx["CUUR0000SA0"], idx["CUUR0000SA0L1E"]
    months = sorted(m for m in head if _month_add(m, -12) in head and m >= f"{this_year - 10}-01")
    yoy = lambda d, m: round((d[m] / d[_month_add(m, -12)] - 1) * 100, 2) if m in d and _month_add(m, -12) in d else None
    mom = lambda d, m: round((d[m] / d[_month_add(m, -1)] - 1) * 100, 2) if m in d and _month_add(m, -1) in d else None
    if len(months) < 24:
        raise RuntimeError("for få CPI-måneder")
    return {"months": months, "headline": [yoy(head, m) for m in months], "core": [yoy(core, m) for m in months],
            "momNsa": mom(head, months[-1])}


def build_macro(prev, errors, now_iso):
    pm = (prev or {}).get("macro") or {}
    out = {}
    # ISM
    try:
        prev_ism = dict(zip(pm["ism"]["months"], pm["ism"]["values"])) if pm.get("ism") else {}
        s = fetch_ism(prev_ism)
        out["ism"] = {"months": list(s), "values": list(s.values()), "source": "ISM via Nasdaq / Trading Economics"}
    except Exception as e:
        print("FEJL ism:", e); errors["ism"] = str(e)[:200]
        if pm.get("ism"): out["ism"] = pm["ism"]
    # Fed
    try:
        out["fed"] = fetch_fed(); out["fed"]["source"] = "New York Fed"
    except Exception as e:
        print("FEJL fed:", e); errors["fed"] = str(e)[:200]
        if pm.get("fed"): out["fed"] = pm["fed"]
    # CPI – BLS tillader få kald pr. døgn uden nøgle, så vi henter højst hver 6. time
    fresh = pm.get("cpi") and pm["cpi"].get("fetched") and \
        datetime.now(timezone.utc) - datetime.fromisoformat(pm["cpi"]["fetched"]) < timedelta(hours=6)
    if fresh:
        out["cpi"] = pm["cpi"]
    else:
        try:
            out["cpi"] = fetch_cpi(); out["cpi"].update(source="U.S. Bureau of Labor Statistics", fetched=now_iso)
        except Exception as e:
            print("FEJL cpi:", e); errors["cpi"] = str(e)[:200]
            if pm.get("cpi"): out["cpi"] = pm["cpi"]
    return out


# ---------- aktieunivers til tickersøgning ----------

def stock_universe():
    names = {}
    hdr = {"User-Agent": UA, "Accept": "application/json"}
    try:
        rows = requests.get("https://api.nasdaq.com/api/quote/list-type/nasdaq100", headers=hdr, timeout=30).json()["data"]["data"]["rows"]
        for x in rows:
            names[x["symbol"].replace(".", "-")] = x["companyName"]
    except Exception as e:
        print("Nasdaq-100-liste fejlede:", e)
    try:
        import csv, io
        txt = requests.get("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv", timeout=30).text
        for row in csv.DictReader(io.StringIO(txt)):
            names.setdefault(row["Symbol"].replace(".", "-"), row["Security"])
    except Exception as e:
        print("S&P 500-liste fejlede:", e)
    try:
        import io
        import pandas as pd
        h = requests.get("https://en.wikipedia.org/wiki/OMX_Copenhagen_25", headers={"User-Agent": UA}, timeout=30).text
        for t in pd.read_html(io.StringIO(h)):
            if "Ticker symbol" in t.columns:
                for _, row in t.iterrows():
                    tk = str(row["Ticker symbol"]).strip().split(":")[-1].strip().replace(" ", "-")
                    tk = {"NDA": "NDA-DK"}.get(tk, tk)  # Yahoo-koder der afviger
                    if tk and tk != "nan":
                        names.setdefault(tk + ".CO", str(row["Company"]))
    except Exception as e:
        print("C25-liste fejlede:", e)
    wl = os.path.join(ROOT, "watchlist.txt")
    if os.path.exists(wl):
        for line in open(wl, encoding="utf-8"):
            line = line.split("#")[0].strip()
            if line:
                tk, _, nm = line.partition(" ")
                names[tk.upper()] = nm.strip() or tk.upper()
    return names


def build_stocks(site_dir, demo=False):
    out_dir = os.path.join(site_dir, "stocks")
    os.makedirs(out_dir, exist_ok=True)
    if demo:
        names = {"AAPL": "Apple Inc.", "NVDA": "NVIDIA Corp.", "NOVO-B.CO": "Novo Nordisk B"}
        closes = {}
        for i, t in enumerate(names):
            d, c = demo_series(100 + 50 * i, 0.0006, 0.018, 1100, True)
            closes[t] = (d, c)
    else:
        import yfinance as yf
        names = stock_universe()
        tickers = sorted(names)
        print(f"Aktieunivers: {len(tickers)} tickers")
        df = yf.download(tickers, period="3y", interval="1d", auto_adjust=False, threads=True, progress=False, group_by="column")["Close"]
        closes = {}
        for t in tickers:
            if t not in df.columns:
                continue
            s_ = df[t].dropna()
            if len(s_) >= 60:
                closes[t] = ([i.strftime("%Y-%m-%d") for i in s_.index], [float(v) for v in s_.values])
    index = []
    for t, (dates, c) in closes.items():
        ma = sma(c, 200)
        dg = 2 if c[-1] >= 1 else 5
        fn = t.replace("^", "_").replace("/", "_") + ".json"
        with open(os.path.join(out_dir, fn), "w") as f:
            json.dump({"t": t, "n": names.get(t, t), "dates": dates, "close": ser(c, dg), "sma200": ser(ma, dg)}, f, separators=(",", ":"))
        index.append([t, names.get(t, t), fn])
    index.sort()
    with open(os.path.join(out_dir, "index.json"), "w") as f:
        json.dump(index, f, separators=(",", ":"))
    print(f"Aktier gemt: {len(index)}")
    return len(index)


def _r(v, n=1):
    return None if v is None else round(float(v), n)


# ---------- indikatorer ----------

def sma(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def rolling_std(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        out[i] = x[i - n + 1:i + 1].std()  # populationsstd som i Bollingers definition
    return out


def rsi(x, n=14):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) <= n:
        return out
    d = np.diff(x)
    g, l = np.clip(d, 0, None), np.clip(-d, 0, None)
    ag, al = g[:n].mean(), l[:n].mean()
    for i in range(n, len(x)):
        if i > n:
            ag = (ag * (n - 1) + g[i - 1]) / n
            al = (al * (n - 1) + l[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def log_channel(dates, close):
    """Log-lineær trend: ln(pris) = a + b·år. Bånd = trend · e^(±kσ) af residualerne."""
    t0 = datetime.strptime(dates[0], "%Y-%m-%d")
    t = np.array([(datetime.strptime(d, "%Y-%m-%d") - t0).days / 365.25 for d in dates])
    y = np.log(np.asarray(close, float))
    b, a = np.polyfit(t, y, 1)
    resid = y - (a + b * t)
    s = resid.std()
    trend = np.exp(a + b * t)
    return trend, s, resid[-1] / s, math.exp(b) - 1


def ser(arr, digits):
    return [None if not np.isfinite(v) else round(float(v), digits) for v in arr]


def build_price_asset(dates, close, digits):
    trend, sigma, z, cagr = log_channel(dates, close)
    ma = sma(close, 200)
    rs = rsi(close, 14)
    last = close[-1]
    prev = close[-2] if len(close) > 1 else last
    return {
        "dates": dates,
        "close": ser(close, digits),
        "trend": ser(trend, digits),
        "sigma": round(float(sigma), 5),
        "sma200": ser(ma, digits),
        "rsi": ser(rs, 1),
        "stats": {
            "last": round(last, digits),
            "chg1d": round((last / prev - 1) * 100, 2),
            "sma200": round(float(ma[-1]), digits) if np.isfinite(ma[-1]) else None,
            "vsSma": round((last / ma[-1] - 1) * 100, 1) if np.isfinite(ma[-1]) else None,
            "rsi": round(float(rs[-1]), 1),
            "z": round(float(z), 2),
            "trendNow": round(float(trend[-1]), digits),
            "trendCagr": round(cagr * 100, 1),
        },
    }


def build_vix(dates, close):
    mid = sma(close, 20)
    sd = rolling_std(close, 20)
    up, lo = mid + 2 * sd, mid - 2 * sd
    last = close[-1]
    pctb = (last - lo[-1]) / (up[-1] - lo[-1]) if up[-1] != lo[-1] else 0.5
    return {
        "dates": dates,
        "close": ser(close, 2),
        "mid": ser(mid, 2), "upper": ser(up, 2), "lower": ser(lo, 2),
        "stats": {
            "last": round(last, 2),
            "chg1d": round((last / close[-2] - 1) * 100, 2),
            "upper": round(float(up[-1]), 2), "lower": round(float(lo[-1]), 2),
            "mid": round(float(mid[-1]), 2),
            "pctB": round(float(pctb), 2),
        },
    }


# ---------- demo-data til lokal test ----------

def demo_series(start_price, mu, vol, days, weekdays_only):
    random.seed(start_price)
    d = datetime.now(timezone.utc) - timedelta(days=days)
    p, dates, out = start_price, [], []
    while d <= datetime.now(timezone.utc):
        if not weekdays_only or d.weekday() < 5:
            p *= math.exp(random.gauss(mu, vol))
            dates.append(d.strftime("%Y-%m-%d"))
            out.append(p)
        d += timedelta(days=1)
    return dates, out


def demo_vix(days):
    random.seed(7)
    d = datetime.now(timezone.utc) - timedelta(days=days)
    v, dates, out = 16.0, [], []
    while d <= datetime.now(timezone.utc):
        if d.weekday() < 5:
            v = max(9, v + 0.06 * (17 - v) + random.gauss(0, 1.1) + (25 if random.random() < 0.002 else 0))
            dates.append(d.strftime("%Y-%m-%d"))
            out.append(v)
        d += timedelta(days=1)
    return dates, out


# ---------- main ----------

def load_prev():
    if not PREV_URL:
        return {}
    try:
        r = requests.get(PREV_URL, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Ingen tidligere data: {e}")
        return {}


def main():
    demo = "--demo" in sys.argv
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "demo": demo, "errors": {}}
    prev = load_prev() if not demo else {}

    for key, cfg in ASSETS.items():
        try:
            if demo:
                dates, close = {
                    "btc": lambda: demo_series(400, 0.0018, 0.035, 3650, False),
                    "eth": lambda: demo_series(300, 0.0012, 0.045, 3200, False),
                    "ndx": lambda: demo_series(4900, 0.0006, 0.013, 3650, True),
                    "vix": lambda: demo_vix(3650),
                }[key]()
                source = "Demo"
            else:
                dates, close, source = fetch_prices(key, cfg["symbol"])
            out[key] = build_vix(dates, close) if key == "vix" else build_price_asset(dates, close, 0 if key in ("btc", "ndx") else 1)
            out[key].update(name=cfg["name"], symbol=cfg["symbol"], updated=out["generated"], source=source)
        except Exception as e:
            print(f"FEJL {key}: {e}")
            out["errors"][key] = str(e)[:200]
            if key in prev:
                out[key] = prev[key]

    try:
        if demo:
            hist = []
            v = 50.0
            for i in range(365):
                v = min(98, max(3, v + random.gauss(0, 4)))
                hist.append([(datetime.now(timezone.utc) - timedelta(days=365 - i)).strftime("%Y-%m-%d"), round(v, 1)])
            out["fng"] = {"score": 38.0, "rating": "fear", "asOf": out["generated"], "previousClose": 41.2,
                          "week": 52.6, "month": 61.0, "year": 33.4, "history": hist}
        else:
            out["fng"] = fetch_fear_greed()
        out["fng"]["updated"] = out["generated"]
    except Exception as e:
        print(f"FEJL fng: {e}")
        out["errors"]["fng"] = str(e)[:200]
        if "fng" in prev:
            out["fng"] = prev["fng"]

    # CoinMarketCap Fear & Greed
    try:
        if demo:
            out["cmcFng"] = {"score": 31.0, "rating": "Fear", "asOf": out["generated"][:10], "previousClose": 34.0,
                             "week": 45.0, "month": 58.0, "year": 66.0,
                             "history": [[d, round(50 + 25 * math.sin(i / 20), 1)] for i, (d, _) in enumerate(out["fng"]["history"])]}
        else:
            out["cmcFng"] = fetch_cmc_fng()
        out["cmcFng"]["updated"] = out["generated"]
    except Exception as e:
        print(f"FEJL cmcFng: {e}")
        out["errors"]["cmcFng"] = str(e)[:200]
        if "cmcFng" in prev:
            out["cmcFng"] = prev["cmcFng"]

    # Makro
    if demo:
        months = [f"{y}-{m:02d}" for y in range(2016, 2027) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-10"]
        days = [(datetime(2016, 1, 4) + timedelta(days=7 * i)).strftime("%Y-%m-%d") for i in range(565)]
        out["macro"] = {
            "ism": {"months": months, "values": [round(51 + 5 * math.sin(i / 9), 1) for i in range(len(months))], "source": "Demo"},
            "fed": {"dates": days, "effr": [round(2 + 2 * math.sin(i / 90), 2) for i in range(len(days))],
                    "lo": [max(0, round(2 + 2 * math.sin(i / 90) - 0.13, 2)) for i in range(len(days))],
                    "hi": [round(2 + 2 * math.sin(i / 90) + 0.12, 2) for i in range(len(days))], "source": "Demo"},
            "cpi": {"months": months[12:], "headline": [round(3 + 2.5 * math.sin(i / 14), 2) for i in range(len(months) - 12)],
                    "core": [round(3 + 1.8 * math.sin(i / 14 - .5), 2) for i in range(len(months) - 12)], "momNsa": 0.2, "source": "Demo"},
        }
    else:
        out["macro"] = build_macro(prev, out["errors"], out["generated"])

    if all(k not in out for k in ("btc", "ndx", "vix", "fng")):
        sys.exit("Ingen data kunne hentes – afbryder uden at overskrive siden.")

    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    shutil.copytree(WEB, SITE)
    try:
        out["stocksCount"] = build_stocks(SITE, demo)
    except Exception as e:
        print(f"FEJL aktier: {e}")
        out["errors"]["stocks"] = str(e)[:200]
    with open(os.path.join(SITE, "data.json"), "w") as f:
        json.dump(out, f, separators=(",", ":"))
    mac = out.get("macro", {})
    print("Bygget:", {k: out[k]["stats"]["last"] for k in ("btc", "eth", "ndx", "vix") if k in out},
          "F&G:", out.get("fng", {}).get("score"), "CMC F&G:", out.get("cmcFng", {}).get("score"),
          "ISM:", (mac.get("ism") or {}).get("months", [None])[-1:], (mac.get("ism") or {}).get("values", [None])[-1:],
          f"({len((mac.get('ism') or {}).get('months', []))} mdr)",
          "Fed:", (mac.get("fed") or {}).get("hi", [None])[-1:], "CPI:", (mac.get("cpi") or {}).get("headline", [None])[-1:],
          "Aktier:", out.get("stocksCount"), "fejl:", out["errors"] or "ingen")


if __name__ == "__main__":
    main()
