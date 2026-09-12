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

def get_values(symbol, interval, outputsize=50):
    data=td_request(symbol, interval, outputsize)
    if "values" not in data: return None, data
    vals=data["values"]; vals.reverse(); candles=[]
    for v in vals:
        try: candles.append({"open":float(v["open"]),"high":float(v["high"]),"low":float(v["low"]),"close":float(v["close"]),"time":v.get("datetime","")})
        except: continue
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

def rsi(candles, period=14):
    if len(candles)<period+1: return 50
    closes=[c["close"] for c in candles]; gains=0; losses=0
    for i in range(1,period+1):
        change=closes[i]-closes[i-1]
        if change>0: gains+=change
        else: losses+=-change
    if losses==0: return 100
    rs=gains/losses if losses!=0 else 0; return 100 - (100/(1+rs))

def get_htf_bias(symbol):
    candles,_=get_values(symbol,"1day",50)
    if not candles or len(candles)<25: return "NEUTRAL",50,None
    ema5=ema(candles,5); ema20=ema(candles,20)
    if not ema5 or not ema20: return "NEUTRAL",50,candles
    bias="BULLISH" if ema5>ema20 else "BEARISH" if ema5<ema20 else "NEUTRAL"
    daily_high=max([c["high"] for c in candles[-20:]]); daily_low=min([c["low"] for c in candles[-20:]])
    current=candles[-1]["close"]; rng=daily_high-daily_low
    premium=((current-daily_low)/rng)*100 if rng!=0 else 50
    return bias,premium,candles

def check_4h_alignment(symbol, daily_bias):
    candles,_=get_values(symbol,"4h",50)
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

def detect_order_block(candles):
    if len(candles) < 20: return False, "", 0
    last_close = candles[-1]["close"]; last_low = candles[-1]["low"]; last_high = candles[-1]["high"]
    for i in range(len(candles)-15, len(candles)-3):
        c = candles[i]; body = abs(c["close"] - c["open"])
        if body == 0: continue
        next_candles = candles[i+1:i+5]
        if len(next_candles) < 2: continue
        if c["close"] < c["open"]:
            impulse_high = max([cc["close"] for cc in next_candles])
            impulse_strength = (impulse_high - c["high"]) / c["high"] if c["high"]!=0 else 0
            if impulse_strength > 0.002:
                ob_low = c["low"]; ob_high = c["high"]; ob_mid = (ob_low + ob_high)/2
                tolerance = ob_high * 0.005 if ob_high > 1000 else ob_high * 0.0015
                if abs(last_close - ob_mid) <= tolerance or (last_low <= ob_high and last_close >= ob_low):
                    return True, f"Bull OB {ob_low:.2f}-{ob_high:.2f}", 4
        if c["close"] > c["open"]:
            impulse_low = min([cc["close"] for cc in next_candles])
            impulse_strength = (c["low"] - impulse_low) / c["low"] if c["low"]!=0 else 0
            if impulse_strength > 0.002:
                ob_low = c["low"]; ob_high = c["high"]; ob_mid = (ob_low + ob_high)/2
                tolerance = ob_high * 0.005 if ob_high > 1000 else ob_high * 0.0015
                if abs(last_close - ob_mid) <= tolerance or (last_high >= ob_low and last_close <= ob_high):
                    return True, f"Bear OB {ob_low:.2f}-{ob_high:.2f}", 4
    return False, "", 0

def detect_multi_tf_ob(symbol):
    timeframes = ["4h","2h","1h"]; ob_found = False; ob_details = []; total_score = 0
    for tf in timeframes:
        candles,_ = get_values(symbol, tf, 50)
        if not candles or len(candles) < 20: continue
        found, zone, score = detect_order_block(candles)
        if found: ob_found = True; ob_details.append(f"{tf.upper()} {zone}"); total_score += score
    return ob_found, " | ".join(ob_details), total_score

def is_news_time(user_settings):
    trade_news=user_settings.get("trade_news",True); now=datetime.utcnow(); weekday=now.weekday()
    is_nfp_day=weekday==4 and 1<=now.day<=7; is_fomc=now.day in [29,30,31] and now.month in [1,3,5,6,7,9,11,12]; is_cpi_week=10<=now.day<=15; is_news=is_nfp_day or is_fomc or is_cpi_week
    if not trade_news and is_news: return True,"NEWS BLOCKED - Trade News OFF"
    return False,""

# ================= V23 UNIFIED ENGINE - ONE STRATEGY, 2 MODES =================
def full_multi_tf_analysis(symbol, user_settings=None):
    if user_settings is None: user_settings={"trade_news":True,"trading_mode":"regular","currency":"ZAR"}
    mode = user_settings.get("trading_mode","regular") # regular or scalp
    is_open, closed_reason = is_market_open(symbol)
    if not is_open:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"premium_pct":50,"reason":closed_reason,"confluence":closed_reason,"details":{"market_closed":True},"mode":mode}
    blocked,reason=is_news_time(user_settings)
    if blocked:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"premium_pct":50,"reason":reason,"confluence":reason,"details":{"news_blocked":True},"mode":mode}

    daily_bias,premium_pct,daily_candles=get_htf_bias(symbol)
    aligned_4h,bias_4h=check_4h_alignment(symbol,daily_bias)
    h1_candles,_=get_values(symbol,"1h",40)
    m5_candles,_=get_values(symbol,"5min",50)
    if not h1_candles or len(h1_candles)<20:
        return {"symbol":symbol,"signal":False,"score":0,"bias":daily_bias,"entry":0,"premium_pct":premium_pct,"reason":"No H1 data","confluence":"No H1","details":{},"mode":mode}

    # ALL INDICATORS - ONE CALCULATION
    ema5_h1=ema(h1_candles,5); ema20_h1=ema(h1_candles,20); rsi_h1=rsi(h1_candles,14)
    h1_patterns,h1_pat_score=detect_candle(h1_candles)
    h1_sweep,h1_sweep_score=detect_sweep(h1_candles,daily_bias)
    h1_fvg=detect_fvg(h1_candles)
    h1_ob, h1_ob_zone, h1_ob_score = detect_order_block(h1_candles)
    recent_high = max([c["high"] for c in h1_candles[-21:-1]]); recent_low = min([c["low"] for c in h1_candles[-21:-1]])
    last_h1=h1_candles[-1]
    bos_bull = last_h1["close"]>recent_high; bos_bear = last_h1["close"]<recent_low
    breakout_bull = last_h1["close"]>recent_high*1.0002; breakout_bear = last_h1["close"]<recent_low*0.9998
    multi_ob, multi_ob_details, multi_ob_score = detect_multi_tf_ob(symbol)

    m5_pat_score=0; m5_sweep=False; m5_sweep_score=0; m5_fvg=False; m5_ob=False; m5_ob_score=0; m5_patterns=[]; ema9_m5=None; ema21_m5=None; rsi_m5=50
    if m5_candles and len(m5_candles)>=20:
        ema9_m5=ema(m5_candles,9); ema21_m5=ema(m5_candles,21); rsi_m5=rsi(m5_candles,14)
        m5_patterns,m5_pat_score=detect_candle(m5_candles)
        m5_sweep,m5_sweep_score=detect_sweep(m5_candles,daily_bias)
        m5_fvg=detect_fvg(m5_candles)
        m5_ob, _, m5_ob_score = detect_order_block(m5_candles)

    # DETERMINE BIAS - unified
    bias_votes = []
    if daily_bias!="NEUTRAL": bias_votes.append(daily_bias)
    if bias_4h!="NEUTRAL": bias_votes.append(bias_4h)
    if ema5_h1 and ema20_h1:
        bias_votes.append("BULLISH" if ema5_h1>ema20_h1 else "BEARISH")
    if ema9_m5 and ema21_m5:
        bias_votes.append("BULLISH" if ema9_m5>ema21_m5 else "BEARISH")
    if bos_bull or breakout_bull: bias_votes.append("BULLISH")
    if bos_bear or breakout_bear: bias_votes.append("BEARISH")
    if not bias_votes: final_bias="NEUTRAL"
    else: final_bias = max(set(bias_votes), key=bias_votes.count) if bias_votes else daily_bias

    # SCORING - ALL STRATEGIES COMBINED AS ONE
    score=0; parts=[]

    # HTF
    if daily_bias!="NEUTRAL": score+=2; parts.append(f"Daily {daily_bias}")
    if aligned_4h: score+=2; parts.append(f"4H {bias_4h} aligned")
    # Premium/Discount
    if daily_bias=="BULLISH" and premium_pct<=35: score+=3; parts.append(f"Discount {premium_pct:.0f}%")
    elif daily_bias=="BEARISH" and premium_pct>=65: score+=3; parts.append(f"Premium {premium_pct:.0f}%")
    elif 35 < premium_pct < 65: score+=1; parts.append(f"Mid {premium_pct:.0f}%")
    # EMA + RSI (method2)
    if ema5_h1 and ema20_h1:
        if final_bias=="BULLISH" and 40<=rsi_h1<=55: score+=2; parts.append(f"RSI {rsi_h1:.0f} BUY pullback")
        elif final_bias=="BEARISH" and 45<=rsi_h1<=60: score+=2; parts.append(f"RSI {rsi_h1:.0f} SELL pullback")
    # Breakout + BOS (method3 + method5)
    if bos_bull or breakout_bull: score+=2; parts.append("BOS/Break High")
    if bos_bear or breakout_bear: score+=2; parts.append("BOS/Break Low")
    # FVG
    if h1_fvg: score+=2; parts.append("H1 FVG")
    if m5_fvg: score+=1; parts.append("M5 FVG")
    # Order Block - BTC case (method5)
    if h1_ob: score+=h1_ob_score; parts.append(f"H1 {h1_ob_zone}")
    if m5_ob: score+=m5_ob_score; parts.append(f"M5 OB")
    if multi_ob: score+=multi_ob_score; parts.append(f"MTF {multi_ob_details}")
    # Sweep (method1)
    if h1_sweep: score+=h1_sweep_score; parts.append(f"H1 Sweep")
    if m5_sweep: score+=m5_sweep_score; parts.append(f"M5 Sweep")
    # Candle patterns
    if h1_patterns: score+=h1_pat_score; parts.append(f"H1 {','.join(h1_patterns)}")
    if m5_patterns: score+=m5_pat_score; parts.append(f"M5 {','.join(m5_patterns)}")

    # Cap score 0-10
    score = min(score, 10)

    # ENTRY - best available
    entry = m5_candles[-1]["close"] if m5_candles and len(m5_candles)>0 else h1_candles[-1]["close"] if h1_candles else 0

    # MODE LOGIC - REGULAR vs SCALP
    crypto_list = ["BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD","ADAUSD","DOGEUSD","DOTUSD","AVAXUSD","LINKUSD","MATICUSD","LTCUSD"]
    is_crypto = symbol in crypto_list
    has_ob = h1_ob or m5_ob or multi_ob
    has_sweep = h1_sweep or m5_sweep
    has_pattern = h1_pat_score>=2 or m5_pat_score>=2

    if mode=="scalp":
        # SCALP MODE: M5 only, faster, lower threshold, 30-70 RSI, need EMA cross + pattern
        m5_bias_ok = ema9_m5 and ema21_m5 and ((ema9_m5>ema21_m5 and final_bias=="BULLISH") or (ema9_m5<ema21_m5 and final_bias=="BEARISH") or final_bias!="NEUTRAL")
        is_signal = score>=5 and has_pattern and m5_bias_ok and 20<=rsi_m5<=80
        if not is_signal:
            if score<5: reason=f"Scalp Score {score}/10 - need 5+"
            elif not has_pattern: reason=f"Scalp Score {score}/10 no pattern"
            else: reason=f"Scalp Score {score}/10 Wait RSI {rsi_m5:.0f}"
        else:
            reason=f"Scalp {score}/10 STRONG {final_bias} {'OB' if has_ob else 'Sweep' if has_sweep else 'EMA'}"
    else:
        # REGULAR MODE: Combined all swing strategies, need OB or Sweep + pattern for quality
        if is_crypto:
            is_signal = score>=5 and (has_ob or has_sweep or bos_bull or bos_bear or breakout_bull or breakout_bear) and has_pattern
        else:
            is_signal = score>=5 and (has_ob or has_sweep) and has_pattern
        if not is_signal:
            if score<5: reason=f"Regular Score {score}/10 - need 5+"
            elif not (has_ob or has_sweep): reason=f"Regular {score}/10 no OB/Sweep"
            elif not has_pattern: reason=f"Regular {score}/10 no engulf/hammer"
            else: reason=f"Regular {score}/10 Wait"
        else:
            if score>=8: strength="🔥 8-10 A+ Setup"
            elif score>=7: strength="✅ 7 Strong"
            elif score>=6: strength="👍 6 Good"
            else: strength="⚡ 5 Takeable"
            reason=f"Regular {score}/10 {strength} {final_bias} {'OB Respect' if has_ob and not has_sweep else 'Sweep+Engulf'}"

    return {
        "symbol":symbol,
        "signal":is_signal,
        "score":score,
        "bias":final_bias,
        "bias_4h":bias_4h,
        "entry":entry,
        "premium_pct":premium_pct,
        "reason":reason,
        "confluence":" | ".join(parts) if parts else "No confluence",
        "details":{"candles":h1_patterns+m5_patterns,"sweep":has_sweep,"fvg":h1_fvg or m5_fvg,"ob":has_ob,"ob_details":multi_ob_details,"rsi_h1":rsi_h1,"rsi_m5":rsi_m5,"bos":bos_bull or bos_bear,"breakout":breakout_bull or breakout_bear},
        "mode":mode
    }
