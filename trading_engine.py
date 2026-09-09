import os, time, requests, random

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
    if not KEYS:
        return None
    return KEYS[current_key_idx % len(KEYS)]

def rotate_key():
    global current_key_idx
    current_key_idx += 1
    print(f"ROTATING to key {current_key_idx % len(KEYS) + 1}/{len(KEYS)}")
    return get_key()

def fetch_candles(symbol, interval="1h", limit=100):
    if not KEYS:
        return None
    key = f"{symbol}_{interval}_{limit}"
    now = time.time()
    if key in _cache and now - _cache_time.get(key,0) < 300:
        return _cache[key]

    sym = symbol.replace("XAU","GOLD").upper()
    if sym == "GOLDUSD":
        sym = "XAU/USD"
    elif "/" not in sym and len(sym) >= 6:
        sym = f"{sym[:3]}/{sym[3:]}"

    for attempt in range(len(KEYS)):
        api_key = get_key()
        url = f"https://api.twelvedata.com/time_series?symbol={sym}&interval={interval}&outputsize={limit}&apikey={api_key}"
        try:
            r = requests.get(url, timeout=15)
            data = r.json()
            if "values" not in data:
                msg = str(data)
                if "429" in msg or "credits" in msg.lower() or data.get("code")==429:
                    print(f"429 on key {current_key_idx+1}: {sym} {interval}")
                    rotate_key()
                    continue
                print(f"Twelve err {symbol} {data}")
                return None
            candles = list(reversed(data["values"]))
            result = []
            for c in candles:
                result.append({"open":float(c["open"]),"high":float(c["high"]),"low":float(c["low"]),"close":float(c["close"])})
            _cache[key]=result
            _cache_time[key]=now
            return result
        except Exception as e:
            print(f"fetch err {symbol} {e}")
            rotate_key()
            continue
    print(f"All keys exhausted for {symbol}")
    return None

def ema(values, period):
    if len(values)<period:
        return None
    k=2/(period+1)
    ema_val=sum(values[:period])/period
    for v in values[period:]:
        ema_val=v*k+ema_val*(1-k)
    return ema_val

def rsi(values, period=14):
    if len(values)<period+1:
        return 50
    gains=0
    losses=0
    for i in range(1, period+1):
        diff=values[i]-values[i-1]
        if diff>0:
            gains+=diff
        else:
            losses+=-diff
    if losses==0:
        return 70
    rs=gains/losses
    return 100-(100/(1+rs))

def get_bias(candles):
    closes=[c["close"] for c in candles]
    e50=ema(closes,50)
    e200=ema(closes,200)
    if not e50 or not e200:
        return "NEUTRAL",0
    last=closes[-1]
    if last>e50>e200:
        return "BULLISH",1
    if last<e50<e200:
        return "BEARISH",1
    return "NEUTRAL",0

def full_multi_tf_analysis(symbol, use_news_filter=True):
    c_1h=fetch_candles(symbol,"1h",100)
    c_15m=fetch_candles(symbol,"15m",100)
    if not c_1h or not c_15m:
        return {"signal":False,"reason":"No data / 429 / Cache wait 5min","score":0,"symbol":symbol}
    bias_1h,_=get_bias(c_1h)
    bias_15m,_=get_bias(c_15m)
    closes_15=[c["close"] for c in c_15m]
    r=rsi(closes_15)
    score=0
    direction=None
    conf=[]
    if bias_1h=="BULLISH":
        score+=2
        conf.append("1H Bull")
    elif bias_1h=="BEARISH":
        score+=2
        conf.append("1H Bear")
    if bias_15m==bias_1h and bias_1h!="NEUTRAL":
        score+=2
        conf.append("15M aligned")
    if bias_1h=="BULLISH" and r<70 and r>45:
        score+=1
        conf.append(f"RSI {r:.1f}")
        direction="BUY"
    elif bias_1h=="BEARISH" and r>30 and r<55:
        score+=1
        conf.append(f"RSI {r:.1f}")
        direction="SELL"
    last_close=closes_15[-1]
    atr=sum([c["high"]-c["low"] for c in c_15m[-14:]])/14 if len(c_15m)>=14 else last_close*0.005
    if bias_1h=="BULLISH":
        entry=last_close
        sl=entry-atr*1.5
        tp=entry+atr*3
        if not direction:
            direction="BUY"
    else:
        entry=last_close
        sl=entry+atr*1.5
        tp=entry-atr*3
        if not direction:
            direction="SELL"
    if bias_1h=="NEUTRAL" or score<4:
        return {"signal":False,"reason":f"Weak {bias_1h} {bias_15m} RSI {r:.1f}","score":score,"symbol":symbol,"bias":bias_1h}
    risk=abs(entry-sl)
    reward=abs(tp-entry)
    rr=reward/risk if risk else 0
    quality="A" if score>=6 else "B" if score>=5 else "C"
    return {"signal":True,"symbol":symbol,"direction":direction,"entry":entry,"sl":sl,"tp":tp,"bias":f"{bias_1h}/{bias_15m}","score":score,"rr":f"{rr:.1f}","quality":quality,"confluence":", ".join(conf),"reason":f"{bias_1h} {bias_15m} RSI {r:.1f}"}
