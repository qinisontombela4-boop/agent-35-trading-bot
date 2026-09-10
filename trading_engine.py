import os
import time
import requests
import pandas as pd

# ========== 3 KEYS ROTATION ==========
API_KEYS = [
    os.getenv("TWELVE_DATA_API_KEY"),
    os.getenv("TWELVE_DATA_API_KEY_2"),
    os.getenv("TWELVE_DATA_API_KEY_3"),
]
API_KEYS = [k for k in API_KEYS if k]
if not API_KEYS:
    API_KEYS = [os.getenv("TWELVEDATA_API_KEY")] # fallback old name

CACHE = {}
KEY_INDEX = 0

def fetch_candles(symbol, interval, outputsize=100, cache_min=5):
    global KEY_INDEX
    cache_key = f"{symbol}_{interval}"
    now = time.time()
    if cache_key in CACHE:
        data, ts = CACHE[cache_key]
        if now - ts < cache_min*60:
            return data

    # Rotate keys on 429
    for _ in range(len(API_KEYS)):
        key = API_KEYS[KEY_INDEX]
        try:
            url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={key}"
            r = requests.get(url, timeout=15)
            j = r.json()
            if "values" in j:
                df = pd.DataFrame(j["values"])
                df = df.iloc[::-1]
                df["close"] = df["close"].astype(float)
                df["open"] = df["open"].astype(float)
                df["high"] = df["high"].astype(float)
                df["low"] = df["low"].astype(float)
                CACHE[cache_key] = (df, now)
                return df
            if j.get("code")==429 or "429" in str(j):
                KEY_INDEX = (KEY_INDEX+1) % len(API_KEYS)
                continue
        except Exception as e:
            KEY_INDEX = (KEY_INDEX+1) % len(API_KEYS)
            continue
    return None

def ema_trend(df):
    if df is None or len(df)<50: return "NEUTRAL",0
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()
    c = df["close"].iloc[-1]
    e50 = df["ema50"].iloc[-1]
    e200 = df["ema200"].iloc[-1]
    if c>e50>e200: return "BULLISH", 2
    if c<e50<e200: return "BEARISH", 2
    if c>e50: return "BULLISH", 1
    if c<e50: return "BEARISH", 1
    return "NEUTRAL",0

def premium_discount(daily_df):
    if daily_df is None or len(daily_df)<50:
        return "EQ",0.5,0
    high = daily_df["high"].tail(50).max()
    low = daily_df["low"].tail(50).min()
    curr = daily_df["close"].iloc[-1]
    rng = high-low
    if rng==0: return "EQ",0.5,0
    fib = (curr-low)/rng
    if fib<0.4: return f"DISC {fib:.2f}", fib, 3
    if fib>0.6: return f"PREM {fib:.2f}", fib, 3
    return f"EQ {fib:.2f}", fib, 0

def detect_5m_entry(df5m):
    if df5m is None or len(df5m)<10:
        return "NONE",0
    last = df5m.iloc[-1]
    body = abs(last["close"]-last["open"])
    rng = last["high"]-last["low"]
    score=0
    reasons=[]
    # Doji
    if rng>0 and body/rng<0.2:
        reasons.append("Doji"); score+=1
    # Hammer / Hanging
    if rng>0:
        lower_wick = min(last["open"],last["close"])-last["low"]
        upper_wick = last["high"]-max(last["open"],last["close"])
        if lower_wick > body*1.5:
            reasons.append("Hammer"); score+=1
        if upper_wick > body*1.5:
            reasons.append("Hanging"); score+=1
    # Simple OB/FVG proxy - close near high/low + engulfing
    prev = df5m.iloc[-2]
    if last["close"]>prev["high"]: reasons.append("BOS"); score+=1
    if last["close"]<prev["low"]: reasons.append("BOS"); score+=1

    if not reasons:
        return "NONE",0
    return "+".join(reasons), min(score,2)

def full_multi_tf_analysis(symbol, use_news_filter=True):
    # Caching: Daily 60min, 4H 30min, 1H 15min, 15M 10min, 5M 5min
    daily = fetch_candles(symbol, "1day", 60, cache_min=60)
    h4 = fetch_candles(symbol, "4h", 60, cache_min=30)
    h1 = fetch_candles(symbol, "1h", 80, cache_min=15)
    m15 = fetch_candles(symbol, "15min", 80, cache_min=10)
    m5 = fetch_candles(symbol, "5min", 80, cache_min=5)

    if daily is None or h4 is None or h1 is None:
        return {"signal":False,"symbol":symbol,"reason":"No data/429 - wait 2am reset","score":0,"bias":"NEUTRAL"}

    d_trend, d_pts = ema_trend(daily)
    h4_trend, h4_pts = ema_trend(h4)
    h1_trend, h1_pts = ema_trend(h1)

    pd_label, fib, pd_pts = premium_discount(daily)

    entry_label, entry_pts = detect_5m_entry(m5)

    # Bias
    bias = d_trend

    # Score
    score = 0
    score += d_pts
    reason_parts = [f"D {d_trend}"]

    if h4_trend == d_trend:
        score += 2
        reason_parts.append(f"4H {h4_trend}")
    else:
        reason_parts.append(f"4H {h4_trend} vs D {d_trend} - no align")
        return {"signal":False,"symbol":symbol,"reason":" ".join(reason_parts),"score":score,"bias":bias,"fib":fib,"pd":pd_label}

    if h1_trend == d_trend:
        score += h1_pts
        reason_parts.append(f"1H {h1_trend}")

    # Premium/Discount alignment
    if d_trend=="BULLISH" and fib<0.5:
        score+=pd_pts
        reason_parts.append(pd_label)
    elif d_trend=="BEARISH" and fib>0.5:
        score+=pd_pts
        reason_parts.append(pd_label)
    else:
        reason_parts.append(pd_label)

    reason_parts.append(entry_label)
    score+=entry_pts

    # Final
    reason = " ".join(reason_parts)

    # *** THRESHOLD 5 - PERMANENT ***
    if score<5:
        return {"signal":False,"symbol":symbol,"reason":f"Weak {reason}","score":score,"bias":bias,"fib":fib,"pd":pd_label,"entry":entry_label}

    # Build entry
    if m5 is None:
        return {"signal":False,"symbol":symbol,"reason":reason,"score":score,"bias":bias}

    price = m5["close"].iloc[-1]
    if d_trend=="BULLISH":
        sl = m5["low"].tail(10).min()
        tp = price + (price-sl)*2.5
        direction="BUY"
    else:
        sl = m5["high"].tail(10).max()
        tp = price - (sl-price)*2.5
        direction="SELL"

    return {
        "signal":True,
        "symbol":symbol,
        "direction":direction,
        "bias":bias,
        "entry":price,
        "sl":sl,
        "tp":tp,
        "score":score,
        "reason":reason,
        "pd":pd_label,
        "fib":fib
    }
