import os, time, requests, pandas as pd
from dotenv import load_dotenv
load_dotenv()

OANDA_ACCOUNT_ID=os.getenv("OANDA_ACCOUNT_ID","")
OANDA_API_TOKEN=os.getenv("OANDA_API_TOKEN","")
OANDA_ENVIRONMENT=os.getenv("OANDA_ENVIRONMENT","practice").lower()
OANDA_BASE="https://api-fxpractice.oanda.com" if OANDA_ENVIRONMENT=="practice" else "https://api-fxtrade.oanda.com"
CAP_API_KEY=os.getenv("CAPITAL_API_KEY","")
CAP_IDENTIFIER=os.getenv("CAPITAL_IDENTIFIER","")
CAP_PASSWORD=os.getenv("CAPITAL_PASSWORD","")
CAP_BASE="https://demo-api-capital.backend-capital.com" if os.getenv("CAPITAL_ENVIRONMENT","demo").lower()=="demo" else "https://api-capital.backend-capital.com"

TIMEFRAME={"15m":"M15","1h":"H1","4h":"H4"}
OANDA_SYMBOLS={
"EURUSD":"EUR_USD","GBPUSD":"GBP_USD","USDJPY":"USD_JPY","USDCHF":"USD_CHF",
"USDCAD":"USD_CAD","AUDUSD":"AUD_USD","NZDUSD":"NZD_USD","EURGBP":"EUR_GBP",
"EURJPY":"EUR_JPY","GBPJPY":"GBP_JPY","AUDJPY":"AUD_JPY","EURAUD":"EUR_AUD",
"GBPAUD":"GBP_AUD","EURCHF":"EUR_CHF","GBPCHF":"GBP_CHF","AUDNZD":"AUD_NZD",
"NZDJPY":"NZD_JPY","CADJPY":"CAD_JPY","CHFJPY":"CHF_JPY","XAUUSD":"XAU_USD","XAGUSD":"XAG_USD"}
CAP_SEARCH={"NAS100":"US Tech 100","SPX500":"US 500"}

def _oanda(symbol,tf,limit=300):
    if not OANDA_ACCOUNT_ID or not OANDA_API_TOKEN: raise RuntimeError("OANDA credentials missing")
    inst=OANDA_SYMBOLS[symbol]
    u=f"{OANDA_BASE}/v3/accounts/{OANDA_ACCOUNT_ID}/instruments/{inst}/candles"
    p={"granularity":TIMEFRAME[tf],"count":min(limit,5000),"price":"M"}
    r=requests.get(u,params=p,headers={"Authorization":f"Bearer {OANDA_API_TOKEN}"},timeout=15); r.raise_for_status()
    rows=[]
    for c in r.json()["candles"]:
        if not c.get("complete"): continue
        q=c["mid"]; rows.append({"time":c["time"],"open":q["o"],"high":q["h"],"low":q["l"],"close":q["c"],"volume":c["volume"]})
    return pd.DataFrame(rows)

_cap_session={"ts":0,"cst":None,"sec":None}
def _cap_auth():
    if not all([CAP_API_KEY,CAP_IDENTIFIER,CAP_PASSWORD]): raise RuntimeError("Capital.com credentials missing")
    if time.time()-_cap_session["ts"]<500 and _cap_session["cst"]: return _cap_session
    u=f"{CAP_BASE}/api/v1/session"
    r=requests.post(u,headers={"X-CAP-API-KEY":CAP_API_KEY,"Content-Type":"application/json"},
                    json={"identifier":CAP_IDENTIFIER,"password":CAP_PASSWORD,"encryptedPassword":False},timeout=15)
    r.raise_for_status()
    _cap_session={"ts":time.time(),"cst":r.headers["CST"],"sec":r.headers["X-SECURITY-TOKEN"]}; return _cap_session

def _cap_epic(symbol):
    # Resolve from the account's available market list instead of hard-coding a regional epic.
    s=_cap_auth(); q=requests.get(f"{CAP_BASE}/api/v1/markets",params={"searchTerm":CAP_SEARCH[symbol]},
        headers={"CST":s["cst"],"X-SECURITY-TOKEN":s["sec"]},timeout=15); q.raise_for_status()
    markets=q.json().get("markets",[])
    if not markets: raise RuntimeError(f"Capital.com market not found for {symbol}")
    return markets[0]["epic"]

def _capital(symbol,tf,limit=300):
    s=_cap_auth(); epic=_cap_epic(symbol)
    res={"15m":"MINUTE_15","1h":"HOUR","4h":"HOUR_4"}[tf]
    r=requests.get(f"{CAP_BASE}/api/v1/prices/{epic}",params={"resolution":res,"max":min(limit,1000)},
                   headers={"CST":s["cst"],"X-SECURITY-TOKEN":s["sec"]},timeout=15); r.raise_for_status()
    rows=[]
    for p in r.json().get("prices",[]):
        op,hi,lo,cl=p["openPrice"],p["highPrice"],p["lowPrice"],p["closePrice"]
        rows.append({"time":p["snapshotTimeUTC"],"open":(op["bid"]+op["ask"])/2,
                     "high":(hi["bid"]+hi["ask"])/2,"low":(lo["bid"]+lo["ask"])/2,
                     "close":(cl["bid"]+cl["ask"])/2,"volume":p.get("lastTradedVolume",0)})
    return pd.DataFrame(rows)

def get_ohlcv(symbol,tf,limit=300):
    symbol=symbol.replace("/","").replace("-","").upper()
    if symbol in OANDA_SYMBOLS: return _oanda(symbol,tf,limit)
    if symbol in CAP_SEARCH: return _capital(symbol,tf,limit)
    raise ValueError(f"Unsupported symbol: {symbol}")
