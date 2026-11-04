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
    prev = None

    for key, cfg in ASSETS.items():
        try:
            if demo:
                dates, close = {
                    "btc": lambda: demo_series(400, 0.0018, 0.035, 3650, False),
                    "ndx": lambda: demo_series(4900, 0.0006, 0.013, 3650, True),
                    "vix": lambda: demo_vix(3650),
                }[key]()
                source = "Demo"
            else:
                dates, close, source = fetch_prices(key, cfg["symbol"])
            out[key] = build_vix(dates, close) if key == "vix" else build_price_asset(dates, close, 0 if key == "btc" else 1)
            out[key].update(name=cfg["name"], symbol=cfg["symbol"], updated=out["generated"], source=source)
        except Exception as e:
            print(f"FEJL {key}: {e}")
            out["errors"][key] = str(e)[:200]
            prev = prev if prev is not None else load_prev()
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
        prev = prev if prev is not None else load_prev()
        if "fng" in prev:
            out["fng"] = prev["fng"]

    if all(k not in out for k in ("btc", "ndx", "vix", "fng")):
        sys.exit("Ingen data kunne hentes – afbryder uden at overskrive siden.")

    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    shutil.copytree(WEB, SITE)
    with open(os.path.join(SITE, "data.json"), "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print("Bygget:", {k: out[k]["stats"]["last"] for k in ("btc", "ndx", "vix") if k in out},
          "F&G:", out.get("fng", {}).get("score"), "fejl:", out["errors"] or "ingen")


if __name__ == "__main__":
    main()
