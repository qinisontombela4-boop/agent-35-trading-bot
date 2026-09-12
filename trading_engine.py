import os, requests
from datetime import datetime

def get_keys():
    keys=[]
    for k in ["TWELVE_DATA_API_KEY","TWELVE_DATA_API_KEY_2","TWELVE_DATA_API_KEY_3","TWELVE_DATA_API_KEY_4"]:
        v=os.getenv(k)
        if v: keys.append(v)
    return keys

KEYS=get_keys()
KEY_INDEX=0

SYMBOL_MAP={
    "EURUSD":"EUR/USD","GBPUSD":"GBP/USD","USDJPY":"USD/JPY","USDCHF":"USD/CHF",
    "AUDUSD":"AUD/USD","USDCAD":"USD/CAD","NZDUSD":"NZD/USD","EURJPY":"EUR/JPY",
    "GBPJPY":"GBP/JPY","EURGBP":"EUR/GBP","AUDJPY":"AUD/JPY","CADJPY":"CAD/JPY",
    "CHFJPY":"CHF/JPY","EURCHF":"EUR/CHF","GBPCHF":"GBP/CHF","EURAUD":"EUR/AUD",
    "GBPAUD":"GBP/AUD","EURCAD":"EUR/CAD","GBPCAD":"GBP/CAD","EURNZD":"EUR/NZD",
    "GBPNZD":"GBP/NZD","AUDNZD":"AUD/NZD","AUDCAD":"AUD/CAD","NZDCAD":"NZD/CAD",
    "AUDCHF":"AUD/CHF","NZDJPY":"NZD/JPY",
    "XAUUSD":"XAU/USD","XAGUSD":"XAG/USD","XTIUSD":"WTI/USD","XBRUSD":"BRENT/USD",
    "US30":"DJI","NAS100":"NDX","SPX500":"SPX","GER40":"DAX","UK100":"FTSE",
    "FRA40":"CAC","ESP35":"IBEX","ITA40":"FTSE MIB","JPN225":"NIKKEI","AUS200":"ASX 200",
    "BTCUSD":"BTC/USD","ETHUSD":"ETH/USD","SOLUSD":"SOL/USD","BNBUSD":"BNB/USD",
    "XRPUSD":"XRP/USD","ADAUSD":"ADA/USD","DOGEUSD":"DOGE/USD","DOTUSD":"DOT/USD",
    "AVAXUSD":"AVAX/USD","LINKUSD":"LINK/USD","MATICUSD":"MATIC/USD","LTCUSD":"LTC/USD"
}

def get_next_key():
    global KEY_INDEX
    if not KEYS: return None
    key=KEYS[KEY_INDEX % len(KEYS)]; KEY_INDEX+=1; return key

def td_request(symbol, interval, outputsize=50):
    if not KEYS: return {"code":500,"message":"No keys"}
    td_symbol=SYMBOL_MAP.get(symbol,symbol); last_error=None
    for _ in range(len(KEYS)):
        key=get_next_key()
        url=f"https://api.twelvedata.com/time_series?symbol={td_symbol}&interval={interval}&outputsize={outputsize}&apikey={key}"
        try:
            r=requests.get(url,timeout=12).json()
            if "code" in r and r["code"]==429: last_error=r; continue
            if "values" in r: return r
            last_error=r
        except Exception as e: last_error={"code":500,"message":str(e)}; continue
    return last_error if last_error else {"code":500,"message":"fail"}

def get_values(symbol, interval, outputsize=50, cache=None):
    # FIX #4: Cache per analysis run
    cache_key = (symbol, interval, outputsize)
    if cache is not None and cache_key in cache:
        return cache[cache_key], None
    data=td_request(symbol, interval, outputsize)
    if "values" not in data:
        return None, data
    vals=data["values"]; vals.reverse(); candles=[]
    for v in vals:
        try: candles.append({"open":float(v["open"]),"high":float(v["high"]),"low":float(v["low"]),"close":float(v["close"]),"time":v.get("datetime","")})
        except: continue
    if cache is not None:
        cache[cache_key] = candles
    return candles, None

def is_market_open(symbol):
    now_utc = datetime.utcnow(); weekday = now_utc.weekday(); hour = now_utc.hour
    crypto = ["BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD","ADAUSD","DOGEUSD","DOTUSD","AVAXUSD","LINKUSD","MATICUSD","LTCUSD"]
    if symbol in crypto: return True, ""
    if weekday==5: return False, "Closed - Saturday"
    if weekday==6 and hour<22: return False, "Closed - Sunday opens 22:00 UTC"
    if weekday==4 and hour>=22: return False, "Closed - Friday 22:00"
    return True, ""

def ema(candles, period):
    if len(candles)<period: return None
    closes=[c["close"] for c in candles]; ema_val=sum(closes[:period])/period; k=2/(period+1)
    for price in closes[period:]: ema_val=price*k + ema_val*(1-k)
    return ema_val

# FIX #1: Proper Wilder's RSI across whole series
def rsi(candles, period=14):
    if len(candles) < period + 1:
        return 50
    closes = [c["close"] for c in candles]
    gains = 0.0; losses = 0.0
    for i in range(1, period + 1):
        change = closes[i] - closes[i-1]
        if change > 0: gains += change
        else: losses += -change
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i-1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(candles, period=14):
    if len(candles) < period + 1: return None
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]; l = candles[i]["low"]; pc = candles[i-1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if len(trs) < period: return sum(trs) / len(trs) if trs else None
    atr_val = sum(trs[:period]) / period
    for tr in trs[period:]: atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val

def get_htf_bias(symbol, cache):
    candles,_=get_values(symbol,"1day",50, cache)
    if not candles or len(candles)<25: return "NEUTRAL",50,None
    ema5=ema(candles,5); ema20=ema(candles,20)
    if not ema5 or not ema20: return "NEUTRAL",50,candles
    bias="BULLISH" if ema5>ema20 else "BEARISH" if ema5<ema20 else "NEUTRAL"
    daily_high=max([c["high"] for c in candles[-20:]]); daily_low=min([c["low"] for c in candles[-20:]])
    current=candles[-1]["close"]; rng=daily_high-daily_low
    premium=((current-daily_low)/rng)*100 if rng!=0 else 50
    return bias,premium,candles

def check_4h_alignment(symbol, daily_bias, cache):
    candles,_=get_values(symbol,"4h",50, cache)
    if not candles or len(candles)<25: return False,"NEUTRAL"
    ema5=ema(candles,5); ema20=ema(candles,20)
    if not ema5 or not ema20: return False,"NEUTRAL"
    bias4h="BULLISH" if ema5>ema20 else "BEARISH" if ema5<ema20 else "NEUTRAL"
    aligned=(bias4h==daily_bias and daily_bias!="NEUTRAL"); return aligned,bias4h

def detect_candle(candles):
    if len(candles)<3: return [],0
    last=candles[-1]; prev=candles[-2]; patterns=[]; score=0
    body=abs(last["close"]-last["open"]); range_c=last["high"]-last["low"]
    if range_c==0: return [],0
    if prev["close"]<prev["open"] and last["close"]>last["open"] and last["close"]>prev["open"] and last["open"]<prev["close"]: patterns.append("Bull Engulf"); score+=4
    if prev["close"]>prev["open"] and last["close"]<last["open"] and last["close"]<prev["open"] and last["open"]>prev["close"]: patterns.append("Bear Engulf"); score+=4
    lower_wick=min(last["open"],last["close"])-last["low"]; upper_wick=last["high"]-max(last["open"],last["close"])
    if lower_wick>body*2 and upper_wick<body*0.5 and range_c>0: patterns.append("Hammer"); score+=3
    if upper_wick>body*2 and lower_wick<body*0.5: patterns.append("Hang Man"); score+=3
    if body<range_c*0.1: patterns.append("Doji"); score+=2
    return patterns,score

def detect_sweep(candles, bias):
    if len(candles)<12: return False,0
    recent=candles[-11:-1]; last=candles[-1]
    if "BULLISH" in bias.upper():
        recent_low=min([c["low"] for c in recent])
        if last["low"]<recent_low and last["close"]>recent_low: return True,3
    if "BEARISH" in bias.upper():
        recent_high=max([c["high"] for c in recent])
        if last["high"]>recent_high and last["close"]<recent_high: return True,3
    return False,0

def detect_fvg(candles):
    if len(candles)<4: return False
    c1=candles[-3]; c3=candles[-1]
    if c3["low"]>c1["high"]: return True
    if c3["high"]<c1["low"]: return True
    return False

# FIX #3: OB must match bias direction
def detect_order_block(candles, bias=None):
    if len(candles) < 20: return False, "", 0
    last_close = candles[-1]["close"]; last_low = candles[-1]["low"]; last_high = candles[-1]["high"]
    bias_upper = bias.upper() if bias else None
    for i in range(len(candles)-15, len(candles)-3):
        c = candles[i]; body = abs(c["close"] - c["open"])
        if body == 0: continue
        next_candles = candles[i+1:i+5]
        if len(next_candles) < 2: continue
        if c["close"] < c["open"]:
            if bias_upper == "BEARISH": continue
            impulse_high = max([cc["close"] for cc in next_candles])
            impulse_strength = (impulse_high - c["high"]) / c["high"] if c["high"]!=0 else 0
            if impulse_strength > 0.002:
                ob_low = c["low"]; ob_high = c["high"]; ob_mid = (ob_low + ob_high)/2
                tolerance = ob_high * 0.005 if ob_high > 1000 else ob_high * 0.0015
                if abs(last_close - ob_mid) <= tolerance or (last_low <= ob_high and last_close >= ob_low):
                    return True, f"Bull OB {ob_low:.2f}-{ob_high:.2f}", 4
        if c["close"] > c["open"]:
            if bias_upper == "BULLISH": continue
            impulse_low = min([cc["close"] for cc in next_candles])
            impulse_strength = (c["low"] - impulse_low) / c["low"] if c["low"]!=0 else 0
            if impulse_strength > 0.002:
                ob_low = c["low"]; ob_high = c["high"]; ob_mid = (ob_low + ob_high)/2
                tolerance = ob_high * 0.005 if ob_high > 1000 else ob_high * 0.0015
                if abs(last_close - ob_mid) <= tolerance or (last_high >= ob_low and last_close <= ob_high):
                    return True, f"Bear OB {ob_low:.2f}-{ob_high:.2f}", 4
    return False, "", 0

def detect_multi_tf_ob(symbol, cache, bias=None):
    timeframes = ["4h","2h","1h"]; ob_found = False; ob_details = []; total_score = 0
    for tf in timeframes:
        candles,_ = get_values(symbol, tf, 50, cache)
        if not candles or len(candles) < 20: continue
        found, zone, score = detect_order_block(candles, bias=bias)
        if found: ob_found = True; ob_details.append(f"{tf.upper()} {zone}"); total_score += score
    return ob_found, " | ".join(ob_details), total_score

def is_news_time(user_settings):
    """
    KNOWN LIMITATION - Heuristic news filter, NOT real calendar:
    Uses day-of-month ranges (10-15=CPI, 29-31=FOMC, 1-7+Friday=NFP)
    Will miss real events and block quiet days.
    TODO Real calendar:
    - Use TwelveData: GET /economic_calendar?date=today&importance=high
    - Or ForexFactory API
    - Filter high-impact USD/EUR/GBP within 60min of now
    - Example: events = requests.get(f"https://api.twelvedata.com/economic_calendar?apikey={KEY}&date={today}").json()
      for ev in events:
          if ev["importance"]=="high" and ev["currency"] in pair_currencies and abs(event_time-now)<60min: block
    - Make configurable: user_settings["news_block_minutes"]=60
    """
    trade_news=user_settings.get("trade_news",True); now=datetime.utcnow(); weekday=now.weekday()
    is_nfp_day=weekday==4 and 1<=now.day<=7; is_fomc=now.day in [29,30,31] and now.month in [1,3,5,6,7,9,11,12]; is_cpi_week=10<=now.day<=15; is_news=is_nfp_day or is_fomc or is_cpi_week
    if not trade_news and is_news: return True,"NEWS BLOCKED - heuristic (see code comment)"
    return False,""

def calculate_sl_tp_rr(symbol, entry, bias, candles_h1, candles_m5, mode, user_settings):
    # FIX #5: SL/TP/RR based on ATR + swing
    atr_h1 = atr(candles_h1, 14) if candles_h1 and len(candles_h1) >= 15 else None
    atr_m5 = atr(candles_m5, 14) if candles_m5 and len(candles_m5) >= 15 else None
    atr_val = atr_m5 if mode == "scalp" and atr_m5 else atr_h1
    if not atr_val: atr_val = entry * 0.002 if entry < 100 else entry * 0.005
    if candles_h1 and len(candles_h1) >= 20:
        recent_high = max([c["high"] for c in candles_h1[-20:-1]])
        recent_low = min([c["low"] for c in candles_h1[-20:-1]])
    else:
        recent_high = entry + atr_val * 2
        recent_low = entry - atr_val * 2
    target_rr = float(user_settings.get("rr_ratio", 2.5))
    min_rr = float(user_settings.get("min_rr", 1.5))
    is_bull = "BULLISH" in bias.upper()
    if is_bull:
        sl_struct = recent_low - atr_val * 0.25
        sl_atr = entry - atr_val * 1.5
        sl = max(sl_struct, sl_atr) if sl_struct < entry else sl_atr
        if entry - sl < atr_val * 0.6: sl = entry - atr_val * 0.8
        risk = entry - sl
        tp = entry + risk * target_rr
    else:
        sl_struct = recent_high + atr_val * 0.25
        sl_atr = entry + atr_val * 1.5
        sl = min(sl_struct, sl_atr) if sl_struct > entry else sl_atr
        if sl - entry < atr_val * 0.6: sl = entry + atr_val * 0.8
        risk = sl - entry
        tp = entry - risk * target_rr
    risk = abs(entry - sl); reward = abs(tp - entry)
    rr = reward / risk if risk!= 0 else 0
    rr_ok = rr >= min_rr
    return sl, tp, rr, risk, reward, atr_val, rr_ok, min_rr

def full_multi_tf_analysis(symbol, user_settings=None):
    if user_settings is None: user_settings={"trade_news":True,"trading_mode":"regular","currency":"ZAR","rr_ratio":2.5,"min_rr":1.5}
    cache = {}
    mode = user_settings.get("trading_mode","regular")
    is_open, closed_reason = is_market_open(symbol)
    if not is_open:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"sl":0,"tp":0,"rr":0,"premium_pct":50,"reason":closed_reason,"confluence":closed_reason,"details":{"market_closed":True},"mode":mode}
    blocked,reason=is_news_time(user_settings)
    if blocked:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"sl":0,"tp":0,"rr":0,"premium_pct":50,"reason":reason,"confluence":reason,"details":{"news_blocked":True},"mode":mode}
    daily_bias,premium_pct,daily_candles=get_htf_bias(symbol, cache)
    aligned_4h,bias_4h=check_4h_alignment(symbol,daily_bias, cache)
    h1_candles,_=get_values(symbol,"1h",40, cache)
    m5_candles,_=get_values(symbol,"5min",50, cache)
    if not h1_candles or len(h1_candles)<20:
        return {"symbol":symbol,"signal":False,"score":0,"bias":daily_bias,"entry":0,"sl":0,"tp":0,"rr":0,"premium_pct":premium_pct,"reason":"No H1 data","confluence":"No H1","details":{},"mode":mode}
    ema5_h1=ema(h1_candles,5); ema20_h1=ema(h1_candles,20); rsi_h1=rsi(h1_candles,14)
    h1_patterns,h1_pat_score=detect_candle(h1_candles)
    h1_sweep,h1_sweep_score=detect_sweep(h1_candles,daily_bias)
    h1_fvg=detect_fvg(h1_candles)
    h1_ob, h1_ob_zone, h1_ob_score = detect_order_block(h1_candles, bias=daily_bias if daily_bias!="NEUTRAL" else None)
    recent_high = max([c["high"] for c in h1_candles[-21:-1]]); recent_low = min([c["low"] for c in h1_candles[-21:-1]])
    last_h1=h1_candles[-1]
    bos_bull = last_h1["close"]>recent_high; bos_bear = last_h1["close"]<recent_low
    breakout_bull = last_h1["close"]>recent_high*1.0002; breakout_bear = last_h1["close"]<recent_low*0.9998
    m5_pat_score=0; m5_sweep=False; m5_sweep_score=0; m5_fvg=False; m5_ob=False; m5_ob_score=0; m5_patterns=[]; ema9_m5=None; ema21_m5=None; rsi_m5=50
    if m5_candles and len(m5_candles)>=20:
        ema9_m5=ema(m5_candles,9); ema21_m5=ema(m5_candles,21); rsi_m5=rsi(m5_candles,14)
        m5_patterns,m5_pat_score=detect_candle(m5_candles)
        m5_sweep,m5_sweep_score=detect_sweep(m5_candles,daily_bias)
        m5_fvg=detect_fvg(m5_candles)
        m5_ob, _, m5_ob_score = detect_order_block(m5_candles, bias=daily_bias if daily_bias!="NEUTRAL" else None)
    bias_votes = []
    if daily_bias!="NEUTRAL": bias_votes.append(daily_bias)
    if bias_4h!="NEUTRAL": bias_votes.append(bias_4h)
    if ema5_h1 and ema20_h1: bias_votes.append("BULLISH" if ema5_h1>ema20_h1 else "BEARISH")
    if ema9_m5 and ema21_m5: bias_votes.append("BULLISH" if ema9_m5>ema21_m5 else "BEARISH")
    if bos_bull or breakout_bull: bias_votes.append("BULLISH")
    if bos_bear or breakout_bear: bias_votes.append("BEARISH")
    if not bias_votes: final_bias="NEUTRAL"
    else: final_bias = max(set(bias_votes), key=bias_votes.count) if bias_votes else daily_bias
    if final_bias!= daily_bias:
        h1_ob, h1_ob_zone, h1_ob_score = detect_order_block(h1_candles, bias=final_bias)
        if m5_candles and len(m5_candles)>=20:
            m5_ob, _, m5_ob_score = detect_order_block(m5_candles, bias=final_bias)
    multi_ob, multi_ob_details, multi_ob_score = detect_multi_tf_ob(symbol, cache, bias=final_bias)
    score=0; parts=[]
    if daily_bias!="NEUTRAL": score+=2; parts.append(f"Daily {daily_bias}")
    if aligned_4h: score+=2; parts.append(f"4H {bias_4h} aligned")
    if daily_bias=="BULLISH" and premium_pct<=35: score+=3; parts.append(f"Discount {premium_pct:.0f}%")
    elif daily_bias=="BEARISH" and premium_pct>=65: score+=3; parts.append(f"Premium {premium_pct:.0f}%")
    elif 35 < premium_pct < 65: score+=1; parts.append(f"Mid {premium_pct:.0f}%")
    if ema5_h1 and ema20_h1:
        if final_bias=="BULLISH" and 40<=rsi_h1<=55: score+=2; parts.append(f"RSI {rsi_h1:.0f} BUY pullback")
        elif final_bias=="BEARISH" and 45<=rsi_h1<=60: score+=2; parts.append(f"RSI {rsi_h1:.0f} SELL pullback")
    if bos_bull or breakout_bull: score+=2; parts.append("BOS/Break High")
    if bos_bear or breakout_bear: score+=2; parts.append("BOS/Break Low")
    if h1_fvg: score+=2; parts.append("H1 FVG")
    if m5_fvg: score+=1; parts.append("M5 FVG")
    if h1_ob: score+=h1_ob_score; parts.append(f"H1 {h1_ob_zone}")
    if m5_ob: score+=m5_ob_score; parts.append(f"M5 OB")
    if multi_ob: score+=multi_ob_score; parts.append(f"MTF {multi_ob_details}")
    if h1_sweep: score+=h1_sweep_score; parts.append(f"H1 Sweep")
    if m5_sweep: score+=m5_sweep_score; parts.append(f"M5 Sweep")
    if h1_patterns: score+=h1_pat_score; parts.append(f"H1 {','.join(h1_patterns)}")
    if m5_patterns: score+=m5_pat_score; parts.append(f"M5 {','.join(m5_patterns)}")
    score = min(score, 10)
    entry = m5_candles[-1]["close"] if m5_candles and len(m5_candles)>0 else h1_candles[-1]["close"] if h1_candles else 0
    sl, tp, rr, risk_dist, reward_dist, atr_val, rr_ok, min_rr = calculate_sl_tp_rr(symbol, entry, final_bias, h1_candles, m5_candles, mode, user_settings)
    has_ob = h1_ob or m5_ob or multi_ob
    has_sweep = h1_sweep or m5_sweep
    has_pattern = h1_pat_score>=2 or m5_pat_score>=2
    if mode=="scalp":
        if ema9_m5 is None or ema21_m5 is None: m5_bias_ok = False
        else:
            if final_bias == "BULLISH": m5_bias_ok = ema9_m5 > ema21_m5
            elif final_bias == "BEARISH": m5_bias_ok = ema9_m5 < ema21_m5
            else: m5_bias_ok = False
        is_signal = score>=5 and has_pattern and m5_bias_ok and 20<=rsi_m5<=80 and rr_ok
        if not is_signal:
            if not rr_ok: reason=f"Scalp Score {score}/10 RR {rr:.2f} < min {min_rr} - reject"
            elif score<5: reason=f"Scalp Score {score}/10 - need 5+"
            elif not has_pattern: reason=f"Scalp Score {score}/10 no pattern"
            elif not m5_bias_ok: reason=f"Scalp Score {score}/10 EMA9/21 not aligned to {final_bias}"
            else: reason=f"Scalp Score {score}/10 Wait RSI {rsi_m5:.0f}"
        else: reason=f"Scalp {score}/10 STRONG {final_bias} RR {rr:.2f}"
    else:
        is_crypto = symbol in ["BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD","ADAUSD","DOGEUSD","DOTUSD","AVAXUSD","LINKUSD","MATICUSD","LTCUSD"]
        if is_crypto: is_signal = score>=5 and (has_ob or has_sweep or bos_bull or bos_bear or breakout_bull or breakout_bear) and has_pattern and rr_ok
        else: is_signal = score>=5 and (has_ob or has_sweep) and has_pattern and rr_ok
        if not is_signal:
            if not rr_ok: reason=f"Regular Score {score}/10 RR {rr:.2f} < min {min_rr} - reject"
            elif score<5: reason=f"Regular Score {score}/10 - need 5+"
            elif not (has_ob or has_sweep): reason=f"Regular {score}/10 no OB/Sweep (direction-filtered)"
            elif not has_pattern: reason=f"Regular {score}/10 no engulf/hammer"
            else: reason=f"Regular {score}/10 Wait"
        else:
            if score>=8: strength="🔥 8-10 A+"
            elif score>=7: strength="✅ 7 Strong"
            elif score>=6: strength="👍 6 Good"
            else: strength="⚡ 5 Takeable"
            reason=f"Regular {score}/10 {strength} {final_bias} RR {rr:.2f}"
    return {
        "symbol":symbol,
        "signal":is_signal,
        "score":score,
        "bias":final_bias,
        "bias_4h":bias_4h,
        "entry":entry,
        "sl": round(sl,5) if entry < 20 else round(sl,2),
        "tp": round(tp,5) if entry < 20 else round(tp,2),
        "rr": round(rr,2),
        "risk_dist": round(risk_dist,5) if entry < 20 else round(risk_dist,2),
        "reward_dist": round(reward_dist,5) if entry < 20 else round(reward_dist,2),
        "atr": round(atr_val,5) if atr_val and entry < 20 else round(atr_val,2) if atr_val else 0,
        "rr_ok": rr_ok,
        "min_rr_required": min_rr,
        "premium_pct":premium_pct,
        "reason":reason,
        "confluence":" | ".join(parts) if parts else "No confluence",
        "details":{"candles":h1_patterns+m5_patterns,"sweep":has_sweep,"fvg":h1_fvg or m5_fvg,"ob":has_ob,"ob_details":multi_ob_details,"rsi_h1":round(rsi_h1,1),"rsi_m5":round(rsi_m5,1),"bos":bos_bull or bos_bear,"breakout":breakout_bull or breakout_bear},
        "mode":mode
    }
