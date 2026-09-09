import os, time, requests

KEYS = [
    os.environ.get('TWELVEDATA_API_KEY','').strip(),
    os.environ.get('TWELVEDATA_API_KEY_2','').strip(),
    os.environ.get('TWELVEDATA_API_KEY_3','').strip(),
]
KEYS = [k for k in KEYS if k]
current_key_idx = 0
_cache = {}
_cache_time = {}

def get_key():
    global current_key_idx
    if not KEYS: return None
    return KEYS[current_key_idx % len(KEYS)]

def rotate_key():
    global current_key_idx
    current_key_idx += 1
    return get_key()

def fetch_candles(symbol, interval="1d", limit=100, cache_min=5):
    if not KEYS: return None
    key = f"{symbol}_{interval}_{limit}"
    now = time.time()
    cache_sec = cache_min * 60
    if key in _cache and now - _cache_time.get(key,0) < cache_sec:
        return _cache[key]
    sym = symbol.replace("XAU","GOLD").upper()
    if sym == "GOLDUSD": sym = "XAU/USD"
    elif "/" not in sym and len(sym)>=6: sym = f"{sym[:3]}/{sym[3:]}"
    for _ in range(len(KEYS)):
        api = get_key()
        url = f"https://api.twelvedata.com/time_series?symbol={sym}&interval={interval}&outputsize={limit}&apikey={api}"
        try:
            r = requests.get(url, timeout=15)
            data = r.json()
            if "values" not in data:
                if "429" in str(data) or data.get("code")==429:
                    rotate_key(); continue
                return None
            c = list(reversed(data["values"]))
            res = [{"open":float(x["open"]),"high":float(x["high"]),"low":float(x["low"]),"close":float(x["close"])} for x in c]
            _cache[key]=res; _cache_time[key]=now
            return res
        except:
            rotate_key(); continue
    return None

def ema(vals, p):
    if len(vals)<p: return None
    k=2/(p+1); e=sum(vals[:p])/p
    for v in vals[p:]: e=v*k+e*(1-k)
    return e

def rsi(vals, p=14):
    if len(vals)<p+1: return 50
    g=l=0
    for i in range(1,p+1):
        d=vals[i]-vals[i-1]
        if d>0: g+=d
        else: l+=-d
    if l==0: return 70
    return 100-(100/(1+g/l))

def atr_calc(candles, p=14):
    if len(candles)<=p: return 0
    trs=[]
    for i in range(1,len(candles)):
        trs.append(max(candles[i]["high"]-candles[i]["low"], abs(candles[i]["high"]-candles[i-1]["close"]), abs(candles[i]["low"]-candles[i-1]["close"])))
    return sum(trs[-p:])/p if trs else 0

def get_bias(candles):
    if not candles or len(candles)<50: return "NEUTRAL",0,0
    closes=[c["close"] for c in candles]
    e50=ema(closes,50); e200=ema(closes,200)
    if not e50 or not e200: return "NEUTRAL",0,closes[-1]
    last=closes[-1]
    if last>e50>e200: return "BULLISH",1,last
    if last<e50<e200: return "BEARISH",-1,last
    return "NEUTRAL",0,last

def premium_discount(c1d):
    if len(c1d)<50: return "EQ",0.5,None,None
    h=max(c["high"] for c in c1d[-50:]); l=min(c["low"] for c in c1d[-50:])
    curr=c1d[-1]["close"]
    if h==l: return "EQ",0.5,h,l
    fib=(curr-l)/(h-l)
    if fib<=0.45: return "DISCOUNT",fib,h,l
    if fib>=0.55: return "PREMIUM",fib,h,l
    return "EQ",fib,h,l

def bos_choch(candles, swing_len=50):
    if len(candles)<=swing_len: return "NONE",None,None
    sh=max(c["high"] for c in candles[-swing_len:])
    sl=min(c["low"] for c in candles[-swing_len:])
    curr=candles[-1]["close"]; prev=candles[-2]["close"] if len(candles)>=2 else curr
    if curr>sh and prev<=sh: return "BOS_BULL",sh,sl
    if curr<sl and prev>=sl: return "BOS_BEAR",sh,sl
    return "NONE",sh,sl

def find_ob(candles, direction="BUY"):
    if len(candles)<20: return None
    avg=sum(c["high"]-c["low"] for c in candles[-20:])/20
    for i in range(len(candles)-3, len(candles)-15, -1):
        if (candles[i]["high"]-candles[i]["low"]) >= 2*avg: continue
        o=candles[i]["open"]; c=candles[i]["close"]
        if direction=="BUY" and o>c and candles[i+1]["close"]>candles[i+1]["open"]:
            return {"top":candles[i]["high"],"bottom":candles[i]["low"]}
        if direction=="SELL" and o<c and candles[i+1]["close"]<candles[i+1]["open"]:
            return {"top":candles[i]["high"],"bottom":candles[i]["low"]}
    return None

def fvg(candles):
    if len(candles)<3: return None
    c1,c2,c3=candles[-3],candles[-2],candles[-1]
    if c3["low"]>c1["high"]: return {"type":"BULL_FVG","top":c3["low"],"bottom":c1["high"]}
    if c3["high"]<c1["low"]: return {"type":"BEAR_FVG","top":c1["low"],"bottom":c3["high"]}
    return None

def eqh_eql(candles):
    if len(candles)<10: return None
    a=atr_calc(candles)
    if a==0: return None
    h=[c["high"] for c in candles[-3:]]; l=[c["low"] for c in candles[-3:]]
    if max(h)-min(h)<0.1*a: return "EQH"
    if max(l)-min(l)<0.1*a: return "EQL"
    return None

def is_doji(c):
    body=abs(c["close"]-c["open"]); rng=c["high"]-c["low"]
    return rng>0 and body<=0.15*rng

def is_hammer(c):
    body=abs(c["close"]-c["open"]); rng=c["high"]-c["low"]
    lw=min(c["close"],c["open"])-c["low"]
    uw=c["high"]-max(c["close"],c["open"])
    if rng==0: return False
    return body<0.3*rng and lw>2*body and uw<0.3*body

def is_engulfing(p,c,d):
    if d=="BUY":
        return p["close"]<p["open"] and c["close"]>c["open"] and c["close"]>p["open"] and c["open"]<p["close"]
    else:
        return p["close"]>p["open"] and c["close"]<c["open"] and c["close"]<p["open"] and c["open"]>p["close"]

def full_multi_tf_analysis(symbol, use_news_filter=True):
    # TOP-DOWN: Daily 60min cache, 4H 30min, 1H/15M/5M 5min
    c1d=fetch_candles(symbol,"1day",100,60)
    c4h=fetch_candles(symbol,"4h",100,30)
    c1h=fetch_candles(symbol,"1h",100,5)
    c15m=fetch_candles(symbol,"15m",100,5)
    c5m=fetch_candles(symbol,"5m",100,5) or c15m
    if not c1d or not c1h:
        return {"signal":False,"reason":"No data/cache","score":0,"symbol":symbol}

    dbias,_,_ = get_bias(c1d)
    b4h,_,_ = get_bias(c4h) if c4h else (dbias,0,0)
    b1h,_,_ = get_bias(c1h)
    b15m,_,_ = get_bias(c15m) if c15m else (b1h,0,0)

    closes5=[c["close"] for c in c5m] if c5m else []
    r=rsi(closes5) if closes5 else 50
    pd_zone,fib,top,bottom = premium_discount(c1d)
    bos_1d,_,_ = bos_choch(c1d,50)
    bos_4h,_,_ = bos_choch(c4h,50) if c4h else ("NONE",None,None)
    bos_1h,_,_ = bos_choch(c1h,20)
    bos_5m,_,_ = bos_choch(c5m,20) if c5m else ("NONE",None,None)

    ob_buy=find_ob(c15m,"BUY") if c15m else None
    ob_sell=find_ob(c15m,"SELL") if c15m else None
    fvg_5m=fvg(c5m)
    eql=eqh_eql(c5m)

    curr=c5m[-1]["close"] if c5m else c1h[-1]["close"]
    in_bu_ob = ob_buy and ob_buy["bottom"]<=curr<=ob_buy["top"]
    in_be_ob = ob_sell and ob_sell["bottom"]<=curr<=ob_sell["top"]
    in_bull_fvg = fvg_5m and fvg_5m["type"]=="BULL_FVG" and fvg_5m["bottom"]<=curr<=fvg_5m["top"]
    in_bear_fvg = fvg_5m and fvg_5m["type"]=="BEAR_FVG" and fvg_5m["bottom"]<=curr<=fvg_5m["top"]

    shift_bull = bos_5m=="BOS_BULL" and dbias=="BEARISH"
    shift_bear = bos_5m=="BOS_BEAR" and dbias=="BULLISH"

    doji = is_doji(c5m[-1]) if c5m else False
    hammer = is_hammer(c5m[-1]) if c5m else False
    eng_b = is_engulfing(c5m[-2],c5m[-1],"BUY") if c5m and len(c5m)>=2 else False
    eng_s = is_engulfing(c5m[-2],c5m[-1],"SELL") if c5m and len(c5m)>=2 else False

    score=0; direction=None; conf=[]

    # Daily bias must align
    if dbias=="BULLISH": score+=2; conf.append("D Bull")
    elif dbias=="BEARISH": score+=2; conf.append("D Bear")
    else: conf.append("D Neutral")

    if b4h==dbias and dbias!="NEUTRAL": score+=2; conf.append(f"4H {b4h}")
    else: conf.append(f"4H {b4h} vs D {dbias}")

    if b1h==dbias and dbias!="NEUTRAL": score+=2; conf.append("1H align")
    else: conf.append(f"1H {b1h}")

    if dbias=="BULLISH" and pd_zone=="DISCOUNT": score+=3; conf.append(f"DISC {fib:.2f}")
    elif dbias=="BEARISH" and pd_zone=="PREMIUM": score+=3; conf.append(f"PREM {fib:.2f}")
    else: conf.append(f"{pd_zone} {fib:.2f}")

    if bos_1h!="NONE": score+=1; conf.append(f"1H {bos_1h}")
    if bos_5m!="NONE": conf.append(f"5M {bos_5m}")

    if shift_bull or shift_bear: score+=2; conf.append("5M SHIFT")

    if in_bu_ob and dbias=="BULLISH": score+=2; conf.append("Bu-OB")
    if in_be_ob and dbias=="BEARISH": score+=2; conf.append("Be-OB")
    if in_bull_fvg and dbias=="BULLISH": score+=1; conf.append("Bull FVG")
    if in_bear_fvg and dbias=="BEARISH": score+=1; conf.append("Bear FVG")
    if eql=="EQL" and dbias=="BULLISH": score+=1; conf.append("EQL Sweep")
    if eql=="EQH" and dbias=="BEARISH": score+=1; conf.append("EQH Sweep")

    if dbias=="BULLISH":
        if doji: score+=1; conf.append("Doji"); direction="BUY"
        if hammer: score+=2; conf.append("Hammer/HM"); direction="BUY"
        if eng_b: score+=2; conf.append("Bull Engulf"); direction="BUY"
    elif dbias=="BEARISH":
        if doji: score+=1; conf.append("Doji"); direction="SELL"
        if hammer: score+=2; conf.append("Hanging Man"); direction="SELL"
        if eng_s: score+=2; conf.append("Bear Engulf"); direction="SELL"

    if r<70 and r>45 and dbias=="BULLISH": score+=1; conf.append(f"RSI {r:.1f}"); direction="BUY" if not direction else direction
    elif r>30 and r<55 and dbias=="BEARISH": score+=1; conf.append(f"RSI {r:.1f}"); direction="SELL" if not direction else direction

    last_close=c5m[-1]["close"] if c5m else c1h[-1]["close"]
    atr=atr_calc(c15m,14) if c15m else atr_calc(c1h,14)
    if atr==0: atr=last_close*0.005

    if dbias=="BULLISH":
        entry=last_close; sl=entry-atr*1.5; tp=entry+atr*3
        if not direction: direction="BUY"
    else:
        entry=last_close; sl=entry+atr*1.5; tp=entry-atr*3
        if not direction: direction="SELL"

    # HARD FILTER: Daily + 4H must align
    if dbias=="NEUTRAL" or (b4h!=dbias and dbias!="NEUTRAL"):
        return {"signal":False,"reason":f"D {dbias} vs 4H {b4h} - no align","score":score,"symbol":symbol,"bias":dbias}

    if score<7:
        return {"signal":False,"reason":f"Weak {dbias}/{b1h}/{b4h} {pd_zone} {fib:.2f} {bos_5m} RSI {r:.1f}","score":score,"symbol":symbol,"bias":dbias}

    rr=abs(tp-entry)/abs(entry-sl) if entry!=sl else 0
    quality="A+" if score>=10 else "A" if score>=8 else "B"

    return {
        "signal":True,
        "symbol":symbol,
        "direction":direction,
        "entry":entry,
        "sl":sl,
        "tp":tp,
        "bias":f"{dbias}/{b1h}/{b4h} {pd_zone} {bos_5m}",
        "score":score,
        "rr":f"{rr:.1f}",
        "quality":quality,
        "confluence":", ".join(conf),
        "reason":f"{pd_zone} {fib:.2f} {bos_5m} {'OB' if in_bu_ob or in_be_ob else ''} {'FVG' if fvg_5m else ''} Doji:{doji} HM:{hammer} Engulf:{eng_b or eng_s}"
    }
