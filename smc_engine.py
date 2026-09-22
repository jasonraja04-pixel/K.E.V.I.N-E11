"""SMC/ICT top-down market-structure analysis.
Analysis only: no order placement and no trade execution.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

def _prep(df):
    x = df.copy()
    x.columns = [str(c).lower() for c in x.columns]
    if "time" not in x:
        if isinstance(x.index, pd.DatetimeIndex):
            x["time"] = x.index
        else:
            raise ValueError("OHLCV data must contain a time column")
    x["time"] = pd.to_datetime(x["time"], utc=True)
    for c in ["open","high","low","close","volume"]:
        if c not in x:
            x[c] = 0.0
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.dropna(subset=["open","high","low","close"]).sort_values("time").drop_duplicates("time")
    return x.reset_index(drop=True)

def detect_swings(df, left=2, right=2):
    x = _prep(df)
    x["swing_high"] = np.nan
    x["swing_low"] = np.nan
    for i in range(left, len(x)-right):
        hs = x["high"].iloc[i-left:i+right+1].to_numpy()
        ls = x["low"].iloc[i-left:i+right+1].to_numpy()
        if hs[left] == hs.max() and np.argmax(hs) == left:
            x.loc[i, "swing_high"] = x.loc[i, "high"]
        if ls[left] == ls.min() and np.argmin(ls) == left:
            x.loc[i, "swing_low"] = x.loc[i, "low"]
    return x

def _swing_list(x):
    out=[]
    for i,r in x.iterrows():
        if pd.notna(r["swing_high"]):
            out.append({"type":"high","price":float(r["swing_high"]),"time":r["time"].isoformat(),"index":int(i)})
        if pd.notna(r["swing_low"]):
            out.append({"type":"low","price":float(r["swing_low"]),"time":r["time"].isoformat(),"index":int(i)})
    return sorted(out,key=lambda z:z["index"])

def detect_structure(df):
    x = detect_swings(df)
    swings = _swing_list(x)
    highs=[s for s in swings if s["type"]=="high"]
    lows=[s for s in swings if s["type"]=="low"]
    result={"trend":"Undetermined","last_event":"Not enough swing data",
            "swings":swings[-12:],"last_swing_high":None,"last_swing_low":None,
            "break_time":None,"break_price":None}
    if len(highs)>=2 and len(lows)>=2:
        hh=highs[-1]["price"]>highs[-2]["price"]
        hl=lows[-1]["price"]>lows[-2]["price"]
        lh=highs[-1]["price"]<highs[-2]["price"]
        ll=lows[-1]["price"]<lows[-2]["price"]
        if hh and hl: trend="Bullish"
        elif lh and ll: trend="Bearish"
        else: trend="Ranging"
        result.update(trend=trend,last_swing_high=highs[-1]["price"],last_swing_low=lows[-1]["price"])
        close=float(x["close"].iloc[-1])
        # Most recent confirmed swing break, using only candles after that swing.
        events=[]
        for s in highs[-6:]:
            if x["close"].iloc[s["index"]+1:].gt(s["price"]).any():
                j=x["close"].iloc[s["index"]+1:].gt(s["price"]).idxmax()
                events.append((int(j),"bull",s["price"]))
        for s in lows[-6:]:
            if x["close"].iloc[s["index"]+1:].lt(s["price"]).any():
                j=x["close"].iloc[s["index"]+1:].lt(s["price"]).idxmax()
                events.append((int(j),"bear",s["price"]))
        if events:
            j,d,p=max(events,key=lambda z:z[0])
            prior = None
            prior_events=[e for e in events if e[0] < j]
            if prior_events: prior=prior_events[-1][1]
            if prior is None:
                event="BOS (Bullish)" if d=="bull" else "BOS (Bearish)"
            elif prior==d:
                event="BOS (Bullish)" if d=="bull" else "BOS (Bearish)"
            else:
                event="CHoCH (Bullish)" if d=="bull" else "CHoCH (Bearish)"
            result.update(last_event=event,break_time=x["time"].iloc[j].isoformat(),
                          break_price=float(p))
    return x,result

def detect_fvgs(df, lookback=80):
    x=_prep(df); start=max(2,len(x)-lookback); gaps=[]
    for i in range(start,len(x)):
        a,b,c=x.iloc[i-2],x.iloc[i-1],x.iloc[i]
        if a["high"] < c["low"]:
            lo,hi=float(a["high"]),float(c["low"])
            mitigated=bool((x["low"].iloc[i+1:]<=lo).any()) if i+1<len(x) else False
            gaps.append({"type":"bullish","low":lo,"high":hi,"time":b["time"].isoformat(),"mitigated":mitigated})
        if a["low"] > c["high"]:
            lo,hi=float(c["high"]),float(a["low"])
            mitigated=bool((x["high"].iloc[i+1:]>=hi).any()) if i+1<len(x) else False
            gaps.append({"type":"bearish","low":lo,"high":hi,"time":b["time"].isoformat(),"mitigated":mitigated})
    return [g for g in gaps if not g["mitigated"]]

def atr(df,n=14):
    x=_prep(df); pc=x["close"].shift(1)
    tr=pd.concat([(x["high"]-x["low"]).abs(),(x["high"]-pc).abs(),(x["low"]-pc).abs()],axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1]) if len(x)>=n else 0.0

def detect_displacement(df, direction, atr_mult=1.2):
    x=_prep(df)
    if len(x)<20: return None
    a=atr(x,14)
    r=x.iloc[-1]; body=abs(float(r["close"]-r["open"]))
    if a<=0 or body<a*atr_mult: return None
    if direction=="Bullish" and r["close"]>r["open"]:
        return {"time":r["time"].isoformat(),"body":body,"atr":a}
    if direction=="Bearish" and r["close"]<r["open"]:
        return {"time":r["time"].isoformat(),"body":body,"atr":a}
    return None

def detect_sweep(df, structure):
    x=_prep(df)
    hi=structure.get("last_swing_high"); lo=structure.get("last_swing_low")
    if hi is not None and float(x["high"].iloc[-1])>hi and float(x["close"].iloc[-1])<hi:
        return {"type":"BSL raid","level":hi,"time":x["time"].iloc[-1].isoformat()}
    if lo is not None and float(x["low"].iloc[-1])<lo and float(x["close"].iloc[-1])>lo:
        return {"type":"SSL raid","level":lo,"time":x["time"].iloc[-1].isoformat()}
    return None

def detect_order_blocks(df, direction, lookback=60):
    x=_prep(df); start=max(1,len(x)-lookback)
    candidates=[]
    for i in range(start,len(x)-1):
        r=x.iloc[i]; nxt=x.iloc[i+1:]
        if direction=="Bullish" and r["close"]<r["open"]:
            # Valid only if a later close breaks above this candle's high.
            hits=nxt.index[nxt["close"]>r["high"]]
            if len(hits): candidates.append((int(hits[0]),{"type":"Bullish Order Block","low":float(r["low"]),"high":float(r["high"]),"time":r["time"].isoformat()}))
        if direction=="Bearish" and r["close"]>r["open"]:
            hits=nxt.index[nxt["close"]<r["low"]]
            if len(hits): candidates.append((int(hits[0]),{"type":"Bearish Order Block","low":float(r["low"]),"high":float(r["high"]),"time":r["time"].isoformat()}))
    return max(candidates,key=lambda z:z[0])[1] if candidates else None

def compute_ote(structure):
    hi=structure.get("last_swing_high"); lo=structure.get("last_swing_low")
    if hi is None or lo is None or hi<=lo: return None
    d=hi-lo
    if structure["trend"]=="Bullish":
        return {"low":round(hi-d*.786,8),"high":round(hi-d*.618,8)}
    if structure["trend"]=="Bearish":
        return {"low":round(lo+d*.618,8),"high":round(lo+d*.786,8)}
    return None

def in_zone(price,z):
    return z is not None and float(z["low"])<=price<=float(z["high"])

def analyze_timeframe(df):
    x,structure=detect_structure(df)
    fvgs=detect_fvgs(x)
    sweep=detect_sweep(x,structure)
    ob=detect_order_blocks(x,structure["trend"]) if structure["trend"] in ("Bullish","Bearish") else None
    disp=detect_displacement(x,structure["trend"]) if structure["trend"] in ("Bullish","Bearish") else None
    return {"structure":structure,"fvg_zones":fvgs[-5:],"liquidity_sweep":sweep,
            "order_block":ob,"ote_zone":compute_ote(structure),
            "displacement":disp,"last_close":float(x["close"].iloc[-1]),
            "last_time":x["time"].iloc[-1].isoformat()}

def build_reference_levels(tf):
    """Return non-executable structural reference levels for the dashboard."""
    h4, h1, m15 = tf["4h"], tf["1h"], tf["15m"]
    bias = h4["structure"]["trend"]
    poi = []
    # Prefer the 1H POIs that agree with the 4H bias.
    if bias in ("Bullish", "Bearish"):
        for z in h1["fvg_zones"]:
            if z.get("type", "").startswith(bias.lower()):
                poi.append({"type": "FVG", "low": z["low"], "high": z["high"], "time": z.get("time")})
        ob = h1.get("order_block")
        if ob and ob.get("type", "").startswith(bias):
            poi.append({"type": "Order Block", "low": ob["low"], "high": ob["high"], "time": ob.get("time")})
        ote = h1.get("ote_zone")
        if ote:
            poi.append({"type": "OTE", "low": ote["low"], "high": ote["high"]})

    entry_zone = poi[0] if poi else None
    inv = None
    if bias == "Bullish":
        inv = h1["structure"].get("last_swing_low") or h4["structure"].get("last_swing_low")
    elif bias == "Bearish":
        inv = h1["structure"].get("last_swing_high") or h4["structure"].get("last_swing_high")

    levels = []
    # Recent structural liquidity references: nearest confirmed swing levels.
    swings = m15["structure"].get("swings", [])
    for sw in reversed(swings):
        price = sw.get("price")
        if price is None or price == inv:
            continue
        if not any(abs(float(price) - float(x["price"])) < 1e-12 for x in levels):
            levels.append({"price": float(price), "type": "Swing liquidity reference", "swing": sw["type"], "time": sw.get("time")})
        if len(levels) == 3:
            break

    sweep = m15.get("liquidity_sweep")
    if sweep and sweep.get("level") is not None:
        levels.insert(0, {"price": float(sweep["level"]), "type": "Recent sweep reference", "swing": sweep.get("type"), "time": sweep.get("time")})
        dedup=[]
        for x in levels:
            if not any(abs(x["price"]-y["price"]) < 1e-12 for y in dedup):
                dedup.append(x)
        levels=dedup[:3]

    return {
        "potential_entry_zone": entry_zone,
        "invalidation_reference": inv,
        "liquidity_references": levels,
        "note": "Structural references for analysis only; not executable entry, stop-loss or take-profit instructions."
    }

def generate_topdown(tf):
    h4,h1,m15=tf["4h"],tf["1h"],tf["15m"]
    bias=h4["structure"]["trend"]
    reasons=[]
    if bias not in ("Bullish","Bearish"):
        state="No clear HTF bias"
    else:
        reasons.append(f"4H bias: {bias} via {h4['structure']['last_event']}")
        if h1["structure"]["trend"]==bias:
            reasons.append("1H structure agrees with 4H")
        else:
            reasons.append("1H structure is not aligned with 4H")
        poi=[]
        for z in h1["fvg_zones"]:
            if z["type"].startswith(bias.lower()): poi.append(("FVG",z))
        if h1["order_block"] and h1["order_block"]["type"].startswith(bias):
            poi.append(("Order Block",h1["order_block"]))
        if h1["ote_zone"]: poi.append(("OTE",h1["ote_zone"]))
        current=h1["last_close"]
        touched=[name for name,z in poi if in_zone(current,z)]
        if touched: reasons.append("1H POI currently in/near: "+", ".join(touched))
        sweep=m15["liquidity_sweep"]
        disp=m15["displacement"]
        trigger = ((bias=="Bullish" and sweep and sweep["type"]=="SSL raid") or
                   (bias=="Bearish" and sweep and sweep["type"]=="BSL raid"))
        if trigger: reasons.append("15M liquidity raid matches HTF direction")
        if disp: reasons.append("15M displacement detected")
        event=m15["structure"]["last_event"]
        if (bias=="Bullish" and "Bullish" in event) or (bias=="Bearish" and "Bearish" in event):
            reasons.append("15M structure event agrees with HTF")
        confluence=sum([h1["structure"]["trend"]==bias, bool(touched), bool(trigger), bool(disp),
                        ((bias=="Bullish" and "Bullish" in event) or (bias=="Bearish" and "Bearish" in event))])
        state = "High confluence" if confluence>=4 else "Developing" if confluence>=2 else "No complete setup"
    refs = build_reference_levels(tf)
    return {"bias":bias,"state":state,"confluence_score":confluence if bias in ("Bullish","Bearish") else 0,
            "reasons":reasons,
            "references":refs,
            "note":"Analysis only; no executable entry, stop-loss or take-profit is generated."}
