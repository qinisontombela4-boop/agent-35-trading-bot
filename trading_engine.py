import os, requests, random
from datetime import datetime

# ================= KEYS ROTATION =================
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
    "GBPAUD":"GBP/AUD","EURCAD":"EUR/CAD","GBPCAD":"GBP/CAD",
    "XAUUSD":"XAU/USD","XAGUSD":"XAG/USD",
    "US30":"DJI","NAS100":"NDX","SPX500":"SPX","GER40":"DAX","UK100":"FTSE","FRA40":"CAC",
    "BTCUSD":"BTC/USD","ETHUSD":"ETH/USD","SOLUSD":"SOL/USD","BNBUSD":"BNB/USD"
}

def get_next_key():
    global KEY_INDEX
    if not KEYS: return None
    key=KEYS[KEY_INDEX % len(KEYS)]
    KEY_INDEX+=1
    return key

def td_request(symbol, interval, outputsize=50):
    if not KEYS:
        return {"code":500,"message":"No API keys set"}
    td_symbol=SYMBOL_MAP.get(symbol,symbol)
    last_error=None
    for _ in range(len(KEYS)):
        key=get_next_key()
        url=f"https://api.twelvedata.com/time_series?symbol={td_symbol}&interval={interval}&outputsize={outputsize}&apikey={key}"
        try:
            r=requests.get(url,timeout=12).json()
            if "code" in r and r["code"]==429:
                last_error=r
                continue
            if "values" in r:
                return r
            last_error=r
        except Exception as e:
            last_error={"code":500,"message":str(e)}
            continue
    return last_error if last_error else {"code":500,"message":"All keys failed"}

def get_values(symbol, interval, outputsize=50):
    data=td_request(symbol, interval, outputsize)
    if "values" not in data:
        return None, data
    vals=data["values"]
    vals.reverse()
    candles=[]
    for v in vals:
        try:
            candles.append({
                "open":float(v["open"]),
                "high":float(v["high"]),
                "low":float(v["low"]),
                "close":float(v["close"]),
                "time":v.get("datetime","")
            })
        except:
            continue
    return candles, None

# ================= INDICATORS =================
def ema(candles, period):
    if len(candles)<period:
        return None
    closes=[c["close"] for c in candles]
    ema_val=sum(closes[:period])/period
    k=2/(period+1)
    for price in closes[period:]:
        ema_val=price*k + ema_val*(1-k)
    return ema_val

def rsi(candles, period=14):
    if len(candles)<period+1:
        return 50
    closes=[c["close"] for c in candles]
    gains=0
    losses=0
    for i in range(1,period+1):
        change=closes[i]-closes[i-1]
        if change>0:
            gains+=change
        else:
            losses+=-change
    if losses==0:
        return 100
    rs=gains/losses if losses!=0 else 0
    return 100 - (100/(1+rs))

def get_htf_bias(symbol):
    candles,_=get_values(symbol,"1day",50)
    if not candles or len(candles)<25:
        return "NEUTRAL",50,None
    ema5=ema(candles,5)
    ema20=ema(candles,20)
    if not ema5 or not ema20:
        return "NEUTRAL",50,candles
    bias="BULLISH" if ema5>ema20 else "BEARISH" if ema5<ema20 else "NEUTRAL"
    daily_high=max([c["high"] for c in candles[-20:]])
    daily_low=min([c["low"] for c in candles[-20:]])
    current=candles[-1]["close"]
    rng=daily_high-daily_low
    premium=((current-daily_low)/rng)*100 if rng!=0 else 50
    return bias,premium,candles

def check_4h_alignment(symbol, daily_bias):
    candles,_=get_values(symbol,"4h",50)
    if not candles or len(candles)<25:
        return False,"NEUTRAL"
    ema5=ema(candles,5)
    ema20=ema(candles,20)
    if not ema5 or not ema20:
        return False,"NEUTRAL"
    bias4h="BULLISH" if ema5>ema20 else "BEARISH" if ema5<ema20 else "NEUTRAL"
    aligned=(bias4h==daily_bias and daily_bias!="NEUTRAL")
    return aligned,bias4h

def detect_candle(candles):
    if len(candles)<3:
        return [],0
    last=candles[-1]
    prev=candles[-2]
    patterns=[]
    score=0
    body=abs(last["close"]-last["open"])
    range_c=last["high"]-last["low"]
    if range_c==0:
        return [],0
    if prev["close"]<prev["open"] and last["close"]>last["open"] and last["close"]>prev["open"] and last["open"]<prev["close"]:
        patterns.append("Bull Engulf")
        score+=4
    if prev["close"]>prev["open"] and last["close"]<last["open"] and last["close"]<prev["open"] and last["open"]>prev["close"]:
        patterns.append("Bear Engulf")
        score+=4
    lower_wick=min(last["open"],last["close"])-last["low"]
    upper_wick=last["high"]-max(last["open"],last["close"])
    if lower_wick>body*2 and upper_wick<body*0.5 and range_c>0:
        patterns.append("Hammer")
        score+=3
    if upper_wick>body*2 and lower_wick<body*0.5:
        patterns.append("Hang Man")
        score+=3
    if body<range_c*0.1:
        patterns.append("Doji")
        score+=2
    return patterns,score

def detect_sweep(candles, bias):
    if len(candles)<12:
        return False,0
    recent=candles[-11:-1]
    last=candles[-1]
    if "BULLISH" in bias.upper():
        recent_low=min([c["low"] for c in recent])
        if last["low"]<recent_low and last["close"]>recent_low:
            return True,3
    if "BEARISH" in bias.upper():
        recent_high=max([c["high"] for c in recent])
        if last["high"]>recent_high and last["close"]<recent_high:
            return True,3
    return False,0

def detect_fvg(candles):
    if len(candles)<4:
        return False
    c1=candles[-3]
    c3=candles[-1]
    if c3["low"]>c1["high"]:
        return True
    if c3["high"]<c1["low"]:
        return True
    return False

def is_news_time(user_settings):
    trade_news=user_settings.get("trade_news",True)
    now=datetime.utcnow()
    weekday=now.weekday()
    is_nfp_day=weekday==4 and 1<=now.day<=7
    is_fomc=now.day in [29,30,31] and now.month in [1,3,5,6,7,9,11,12]
    is_cpi_week=10<=now.day<=15
    is_news=is_nfp_day or is_fomc or is_cpi_week
    if not trade_news and is_news:
        return True,"NEWS BLOCKED - Trade News OFF"
    return False,""

# ================= 5 TRADING METHODS =================

def method1_premium_sweep(symbol, user_settings):
    daily_bias,premium_pct,daily_candles=get_htf_bias(symbol)
    if daily_bias=="NEUTRAL":
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"premium_pct":premium_pct,"reason":"Daily NEUTRAL - Sideways","confluence":"Daily sideways no trend","details":{"news_blocked":False},"method":"method1_premium_sweep"}
    if daily_bias=="BULLISH" and premium_pct>65:
        entry_val=daily_candles[-1]["close"] if daily_candles else 0
        return {"symbol":symbol,"signal":False,"score":3,"bias":daily_bias,"entry":entry_val,"premium_pct":premium_pct,"reason":f"Wait Discount {premium_pct:.0f}% Premium zone","confluence":f"Daily {daily_bias} but {premium_pct:.0f}% Premium - wait 0-35% discount","details":{"premium":premium_pct},"method":"method1_premium_sweep"}
    if daily_bias=="BEARISH" and premium_pct<35:
        entry_val=daily_candles[-1]["close"] if daily_candles else 0
        return {"symbol":symbol,"signal":False,"score":3,"bias":daily_bias,"entry":entry_val,"premium_pct":premium_pct,"reason":f"Wait Premium {premium_pct:.0f}% Discount zone","confluence":f"Daily {daily_bias} but {premium_pct:.0f}% Discount - wait 65-100% premium","details":{"premium":premium_pct},"method":"method1_premium_sweep"}
    aligned_4h,bias_4h=check_4h_alignment(symbol,daily_bias)
    h1_candles,_=get_values(symbol,"1h",30)
    if not h1_candles or len(h1_candles)<12:
        return {"symbol":symbol,"signal":False,"score":0,"bias":daily_bias,"entry":0,"premium_pct":premium_pct,"reason":"No H1 data","confluence":"No H1 candles","details":{},"method":"method1_premium_sweep"}
    h1_patterns,h1_pat_score=detect_candle(h1_candles)
    h1_sweep,h1_sweep_score=detect_sweep(h1_candles,daily_bias)
    h1_fvg=detect_fvg(h1_candles)
    h1_entry=h1_candles[-1]["close"]
    m5_candles,_=get_values(symbol,"5min",30)
    m5_patterns=[]; m5_pat_score=0; m5_sweep=False; m5_sweep_score=0; m5_fvg=False; m5_entry=h1_entry
    if m5_candles and len(m5_candles)>=12:
        m5_patterns,m5_pat_score=detect_candle(m5_candles)
        m5_sweep,m5_sweep_score=detect_sweep(m5_candles,daily_bias)
        m5_fvg=detect_fvg(m5_candles)
        m5_entry=m5_candles[-1]["close"]
    score=0; parts=[]
    if daily_bias!="NEUTRAL": score+=2; parts.append(f"Daily {daily_bias}")
    if aligned_4h: score+=2; parts.append(f"4H {bias_4h} aligned")
    else: parts.append(f"4H {bias_4h} not aligned")
    if daily_bias=="BULLISH" and premium_pct<=35: score+=3; parts.append(f"Discount {premium_pct:.0f}% perfect BUY")
    elif daily_bias=="BEARISH" and premium_pct>=65: score+=3; parts.append(f"Premium {premium_pct:.0f}% perfect SELL")
    else: parts.append(f"{premium_pct:.0f}% zone")
    if h1_patterns: score+=h1_pat_score; parts.append(f"H1 {','.join(h1_patterns)} +{h1_pat_score}")
    if h1_sweep: score+=h1_sweep_score; parts.append(f"H1 Sweep +{h1_sweep_score}")
    if h1_fvg: score+=1; parts.append("H1 FVG +1")
    if m5_patterns: score+=m5_pat_score; parts.append(f"M5 {','.join(m5_patterns)} +{m5_pat_score}")
    if m5_sweep: score+=m5_sweep_score; parts.append(f"M5 Sweep +{m5_sweep_score}")
    if m5_fvg: score+=1; parts.append("M5 FVG +1")
    has_sweep=h1_sweep or m5_sweep
    has_strong=h1_pat_score>=3 or m5_pat_score>=3
    is_strong=score>=7 and has_sweep and has_strong
    if not is_strong:
        if score<7: reason=f"Score {score}/10 low - Need 7+"
        elif not has_sweep: reason=f"Score {score}/10 but no sweep - Waiting liquidity grab"
        elif not has_strong: reason=f"Score {score}/10 but no engulf/hammer - Waiting strong candle"
        else: reason=f"Score {score}/10 Wait"
    else: reason=f"Score {score}/10 STRONG - Premium+Sweep+Engulf"
    final_entry=m5_entry if m5_entry!=0 else h1_entry
    return {"symbol":symbol,"signal":is_strong,"score":score,"bias":daily_bias,"bias_4h":bias_4h,"entry":final_entry,"premium_pct":premium_pct,"reason":reason,"confluence":" | ".join(parts),"details":{"candles":h1_patterns+m5_patterns,"sweep":has_sweep,"fvg":h1_fvg or m5_fvg,"premium":premium_pct,"h1_entry":h1_entry,"m5_entry":m5_entry,"aligned_4h":aligned_4h},"method":"method1_premium_sweep"}

def method2_ema_rsi(symbol, user_settings):
    daily_bias,premium_pct,daily_candles=get_htf_bias(symbol)
    h1_candles,_=get_values(symbol,"1h",40)
    if not h1_candles or len(h1_candles)<20:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"premium_pct":premium_pct,"reason":"No H1 data","confluence":"No H1","details":{},"method":"method2_ema_rsi"}
    ema5=ema(h1_candles,5); ema20=ema(h1_candles,20); rsi_val=rsi(h1_candles,14)
    h1_entry=h1_candles[-1]["close"]
    if not ema5 or not ema20:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":h1_entry,"premium_pct":premium_pct,"reason":"No EMA","confluence":"No EMA","details":{},"method":"method2_ema_rsi"}
    bias="BULLISH" if ema5>ema20 else "BEARISH" if ema5<ema20 else "NEUTRAL"
    patterns,pat_score=detect_candle(h1_candles)
    score=0; parts=[]
    if bias=="BULLISH" and 40<=rsi_val<=55:
        score+=4; parts.append(f"RSI {rsi_val:.0f} pullback BUY zone 40-55")
    elif bias=="BEARISH" and 45<=rsi_val<=60:
        score+=4; parts.append(f"RSI {rsi_val:.0f} pullback SELL zone 45-60")
    else:
        parts.append(f"RSI {rsi_val:.0f} no pullback")
    if bias!="NEUTRAL": score+=2; parts.append(f"EMA5>20 {bias}")
    if patterns: score+=pat_score; parts.append(f"{','.join(patterns)} +{pat_score}")
    if bias=="BULLISH" and premium_pct<=50: score+=2; parts.append(f"Discount {premium_pct:.0f}%")
    if bias=="BEARISH" and premium_pct>=50: score+=2; parts.append(f"Premium {premium_pct:.0f}%")
    is_strong=score>=6 and (40<=rsi_val<=60) and pat_score>=2
    reason=f"EMA+RSI Score {score}/10 RSI {rsi_val:.0f} {bias} {'STRONG' if is_strong else 'Wait pullback'}"
    return {"symbol":symbol,"signal":is_strong,"score":score,"bias":bias,"entry":h1_entry,"premium_pct":premium_pct,"reason":reason,"confluence":" | ".join(parts),"details":{"rsi":rsi_val,"candles":patterns,"ema5":ema5,"ema20":ema20},"method":"method2_ema_rsi"}

def method3_breakout_retest(symbol, user_settings):
    h1_candles,_=get_values(symbol,"1h",40)
    if not h1_candles or len(h1_candles)<25:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"premium_pct":50,"reason":"No H1 data","confluence":"No H1","details":{},"method":"method3_breakout_retest"}
    recent_high=max([c["high"] for c in h1_candles[-21:-1]])
    recent_low=min([c["low"] for c in h1_candles[-21:-1]])
    last=h1_candles[-1]; entry=last["close"]
    patterns,pat_score=detect_candle(h1_candles)
    score=0; parts=[]; bias="NEUTRAL"
    if last["close"]>recent_high*1.0002:
        bias="BULLISH"; score+=3; parts.append(f"Break High {recent_high:.5f}")
        if last["low"]<=recent_high*1.0005: score+=3; parts.append("Retest High +3")
    elif last["close"]<recent_low*0.9998:
        bias="BEARISH"; score+=3; parts.append(f"Break Low {recent_low:.5f}")
        if last["high"]>=recent_low*0.9995: score+=3; parts.append("Retest Low +3")
    else:
        parts.append(f"Inside {recent_low:.5f}-{recent_high:.5f}")
    if patterns: score+=pat_score; parts.append(f"{','.join(patterns)} +{pat_score}")
    is_strong=score>=6 and bias!="NEUTRAL" and pat_score>=2
    reason=f"Breakout Score {score}/10 {bias} {'STRONG breakout+retest' if is_strong else 'Wait breakout'}"
    return {"symbol":symbol,"signal":is_strong,"score":score,"bias":bias,"entry":entry,"premium_pct":50,"reason":reason,"confluence":" | ".join(parts),"details":{"break_high":recent_high,"break_low":recent_low,"candles":patterns},"method":"method3_breakout_retest"}

def method4_scalp_m5(symbol, user_settings):
    m5_candles,_=get_values(symbol,"5min",50)
    if not m5_candles or len(m5_candles)<25:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"premium_pct":50,"reason":"No M5 data","confluence":"No M5","details":{},"method":"method4_scalp_m5"}
    ema9=ema(m5_candles,9); ema21=ema(m5_candles,21); rsi_val=rsi(m5_candles,14); entry=m5_candles[-1]["close"]
    patterns,pat_score=detect_candle(m5_candles)
    if not ema9 or not ema21:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":entry,"premium_pct":50,"reason":"No EMA9/21","confluence":"No EMA","details":{},"method":"method4_scalp_m5"}
    bias="BULLISH" if ema9>ema21 else "BEARISH" if ema9<ema21 else "NEUTRAL"
    sweep,sweep_score=detect_sweep(m5_candles,bias)
    score=0; parts=[]
    if bias=="BULLISH" and rsi_val<70 and rsi_val>30: score+=3; parts.append(f"EMA9>21 BUY RSI {rsi_val:.0f}")
    elif bias=="BEARISH" and rsi_val>30 and rsi_val<70: score+=3; parts.append(f"EMA9<21 SELL RSI {rsi_val:.0f}")
    else: parts.append(f"RSI {rsi_val:.0f} extreme")
    if patterns: score+=pat_score; parts.append(f"{','.join(patterns)} +{pat_score}")
    if sweep: score+=2; parts.append(f"M5 Sweep +{sweep_score}")
    is_strong=score>=5 and bias!="NEUTRAL" and 30<=rsi_val<=70
    reason=f"Scalp M5 Score {score}/10 RSI {rsi_val:.0f} {bias} {'STRONG' if is_strong else 'Wait EMA cross'}"
    return {"symbol":symbol,"signal":is_strong,"score":score,"bias":bias,"entry":entry,"premium_pct":50,"reason":reason,"confluence":" | ".join(parts),"details":{"rsi":rsi_val,"candles":patterns,"sweep":sweep,"ema9":ema9,"ema21":ema21},"method":"method4_scalp_m5"}

def method5_smc_ob_bos(symbol, user_settings):
    daily_bias,premium_pct,daily_candles=get_htf_bias(symbol)
    h1_candles,_=get_values(symbol,"1h",40)
    if not h1_candles or len(h1_candles)<25:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"premium_pct":premium_pct,"reason":"No H1 data","confluence":"No H1","details":{},"method":"method5_smc_ob_bos"}
    recent_high=max([c["high"] for c in h1_candles[-11:-1]])
    recent_low=min([c["low"] for c in h1_candles[-11:-1]])
    last=h1_candles[-1]
    bos_bull=last["close"]>recent_high
    bos_bear=last["close"]<recent_low
    fvg=detect_fvg(h1_candles)
    patterns,pat_score=detect_candle(h1_candles)
    entry=last["close"]
    score=0; parts=[]; bias="NEUTRAL"
    if bos_bull: bias="BULLISH"; score+=4; parts.append(f"BOS Bull break {recent_high:.5f} +4")
    if bos_bear: bias="BEARISH"; score+=4; parts.append(f"BOS Bear break {recent_low:.5f} +4")
    if not bos_bull and not bos_bear: parts.append(f"No BOS inside {recent_low:.5f}-{recent_high:.5f}")
    if fvg: score+=3; parts.append("FVG +3")
    else: parts.append("No FVG")
    if patterns: score+=pat_score; parts.append(f"{','.join(patterns)} +{pat_score}")
    if daily_bias==bias and bias!="NEUTRAL": score+=2; parts.append(f"Daily {daily_bias} aligned +2")
    is_strong=score>=7 and (bos_bull or bos_bear) and fvg
    reason=f"SMC OB+BOS Score {score}/10 BOS:{bos_bull or bos_bear} FVG:{fvg} {'STRONG' if is_strong else 'Wait BOS+FVG'}"
    return {"symbol":symbol,"signal":is_strong,"score":score,"bias":bias,"entry":entry,"premium_pct":premium_pct,"reason":reason,"confluence":" | ".join(parts),"details":{"bos_bull":bos_bull,"bos_bear":bos_bear,"fvg":fvg,"candles":patterns,"break_high":recent_high,"break_low":recent_low},"method":"method5_smc_ob_bos"}

# ================= DISPATCHER =================
def full_multi_tf_analysis(symbol, user_settings=None):
    if user_settings is None:
        user_settings={"trade_news":True,"trading_method":"method1_premium_sweep","currency":"ZAR","spread_forex":0.7,"spread_gold":0.35}
    blocked,reason=is_news_time(user_settings)
    if blocked:
        return {
            "symbol":symbol,
            "signal":False,
            "score":0,
            "bias":"NEUTRAL",
            "entry":0,
            "premium_pct":50,
            "reason":reason,
            "confluence":reason,
            "details":{"news_blocked":True},
            "method":user_settings.get("trading_method","method1_premium_sweep")
        }
    method=user_settings.get("trading_method","method1_premium_sweep")
    if method=="method1_premium_sweep":
        return method1_premium_sweep(symbol, user_settings)
    elif method=="method2_ema_rsi":
        return method2_ema_rsi(symbol, user_settings)
    elif method=="method3_breakout_retest":
        return method3_breakout_retest(symbol, user_settings)
    elif method=="method4_scalp_m5":
        return method4_scalp_m5(symbol, user_settings)
    elif method=="method5_smc_ob_bos":
        return method5_smc_ob_bos(symbol, user_settings)
    else:
        return method1_premium_sweep(symbol, user_settings)

def run_scan_and_send(all_symbols, user_settings):
    results=[]
    for sym in all_symbols:
        try:
            r=full_multi_tf_analysis(sym, user_settings)
            results.append(r)
        except Exception as e:
            results.append({"symbol":sym,"signal":False,"score":0,"bias":"ERROR","entry":0,"reason":str(e),"confluence":str(e),"details":{},"method":user_settings.get("trading_method","method1_premium_sweep")})
    return results
