import requests, json, time
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
def t(name, url, **kw):
    try:
        r=requests.get(url, headers={**UA, **kw.pop("headers",{})}, timeout=30, **kw)
        print(f"\n## {name}: {r.status_code} ACAO={r.headers.get('access-control-allow-origin')} len={len(r.text)}")
        print(r.text[:500].replace("\n"," | "))
    except Exception as e: print(f"\n## {name}: ERR {e}")
t("FRED FEDFUNDS","https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU&cosd=2024-01-01")
t("FRED CPI","https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL&cosd=2025-01-01")
t("DBnomics ISM","https://api.db.nomics.world/v22/series/ISM/pmi/pm?observations=1&format=json")
t("DBnomics ISM search","https://api.db.nomics.world/v22/datasets/ISM?limit=50")
t("CMC data-api FG","https://api.coinmarketcap.com/data-api/v3/fear-greed/chart?start=%d&end=%d"%(int(time.time())-86400*400,int(time.time())))
t("CMC data-api FG latest","https://api.coinmarketcap.com/data-api/v3/fear-greed/latest")
t("alternative.me","https://api.alternative.me/fng/?limit=3")
t("Binance","https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=1d&limit=2", headers={"Origin":"https://fraddykirk.github.io"})
t("Coinbase","https://api.exchange.coinbase.com/products/SOL-USD/candles?granularity=86400", headers={"Origin":"https://fraddykirk.github.io"})
t("SP500 list","https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv")
t("Wiki NDX","https://en.wikipedia.org/wiki/Nasdaq-100")
t("ISM site","https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/")
t("TradingEconomics","https://tradingeconomics.com/united-states/business-confidence")
import yfinance as yf
for s in ["ETH-USD","NOVO-B.CO","NVDA"]:
    df=yf.Ticker(s).history(period="10y"); print(f"\n## yf {s}: {len(df)} rows {df.index[0].date() if len(df) else ''} last {df['Close'].iloc[-1] if len(df) else ''}")
t0=time.time(); df=yf.download(["AAPL","MSFT","GOOGL","AMZN","META","TSLA","AVGO","ASML","AMD","NFLX"]*1, period="3y", progress=False, threads=True)["Close"]; print("\n## yf.download 10:", df.shape, round(time.time()-t0,1),"s")
