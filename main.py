import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from data_feed import get_ohlcv
from smc_engine import analyze_timeframe, generate_topdown

app=FastAPI(title="SMC/ICT Top-Down Analysis API")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])

SUPPORTED_SYMBOLS=[
"EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD","EURGBP","EURJPY",
"GBPJPY","AUDJPY","EURAUD","GBPAUD","EURCHF","GBPCHF","AUDNZD","NZDJPY","CADJPY",
"CHFJPY","XAUUSD","XAGUSD","NAS100","SPX500"]
TIMEFRAMES=["4h","1h","15m"]
_cache={}; TTL=30

def norm(s): return s.replace("/","").replace("-","").upper()

@app.get("/api/symbols")
def symbols(): return {"symbols":SUPPORTED_SYMBOLS,"timeframes":TIMEFRAMES}

@app.get("/api/timeframe/{symbol}/{tf}")
def timeframe(symbol:str,tf:str):
    s=norm(symbol)
    if s not in SUPPORTED_SYMBOLS or tf not in TIMEFRAMES: raise HTTPException(400,"Unsupported symbol/timeframe")
    try: return analyze_timeframe(get_ohlcv(s,tf))
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/api/signal/{symbol}")
def signal(symbol:str):
    s=norm(symbol)
    if s not in SUPPORTED_SYMBOLS: raise HTTPException(404,f"{s} not supported")
    now=time.time()
    if s in _cache and now-_cache[s][0]<TTL: return _cache[s][1]
    try:
        tf={t:analyze_timeframe(get_ohlcv(s,t)) for t in TIMEFRAMES}
        top=generate_topdown(tf)
        response={"symbol":s,"generated_at":time.time(),"signal":top,
                  "timeframes":{t:{
                    "trend":tf[t]["structure"]["trend"],
                    "last_event":tf[t]["structure"]["last_event"],
                    "last_close":tf[t]["last_close"],
                    "fvg_zones":tf[t]["fvg_zones"],
                    "liquidity_sweep":tf[t]["liquidity_sweep"],
                    "order_block":tf[t]["order_block"],
                    "ote_zone":tf[t]["ote_zone"],
                    "displacement":tf[t]["displacement"],
                    "last_time":tf[t]["last_time"]} for t in TIMEFRAMES}}
        _cache[s]=(now,response); return response
    except Exception as e: raise HTTPException(502,f"Data fetch/analysis failed for {s}: {e}")
