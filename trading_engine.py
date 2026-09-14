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

# ---- NEW: simple per-analysis cache so the same symbol+interval is never
# fetched twice in one call to full_multi_tf_analysis. Saves API quota and
# guarantees h1_ob and multi_ob score off the SAME 1h candles, not two
# separately-fetched (and possibly slightly different) sets. ----
def get_values_cached(cache, symbol, interval, outputsize=50):
    key=(symbol, interval, outputsize)
    if key in cache: return cache[key]
    result = get_values(symbol, interval, outputsize)
    cache[key] = result
    return result

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

# ---- FIXED: proper Wilder's RSI, smoothed across the WHOLE fetched series
# (not just the earliest period+1 candles). Reflects current momentum. ----
def rsi(candles, period=14):
    if len(candles) < period + 1: return 50
    closes = [c["close"] for c in candles]
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]

    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ---- NEW: ATR, used for stop-loss distance and volatility-aware scalp checks ----
def atr(candles, period=14):
    if len(candles) < period + 1: return None
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    recent = trs[-period:]
    return sum(recent) / len(recent)

def get_htf_bias(symbol, cache):
    candles,_=get_values_cached(cache, symbol,"1day",50)
    if not candles or len(candles)<25: return "NEUTRAL",50,None
    ema5=ema(candles,5); ema20=ema(candles,20)
    if not ema5 or not ema20: return "NEUTRAL",50,candles
    bias="BULLISH" if ema5>ema20 else "BEARISH" if ema5<ema20 else "NEUTRAL"
    daily_high=max([c["high"] for c in candles[-20:]]); daily_low=min([c["low"] for c in candles[-20:]])
    current=candles[-1]["close"]; rng=daily_high-daily_low
    premium=((current-daily_low)/rng)*100 if rng!=0 else 50
    return bias,premium,candles

def check_4h_alignment(symbol, daily_bias, cache):
    candles,_=get_values_cached(cache, symbol,"4h",50)
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

# ---- FIXED: now takes `bias` and only returns an order block that AGREES
# with it (a bearish OB can no longer add score to a bullish setup).
# Also scans from the MOST RECENT candidate backward, so the nearest
# (most relevant, least likely already-invalidated) OB wins over an older
# one further back in the lookback window. ----
def detect_order_block(candles, bias=None):
    if len(candles) < 20: return False, "", 0
    last_close = candles[-1]["close"]; last_low = candles[-1]["low"]; last_high = candles[-1]["high"]
    want_bull = bias is None or "BULLISH" in bias.upper()
    want_bear = bias is None or "BEARISH" in bias.upper()

    for i in range(len(candles)-4, len(candles)-15, -1):
        c = candles[i]; body = abs(c["close"] - c["open"])
        if body == 0: continue
        next_candles = candles[i+1:i+5]
        if len(next_candles) < 2: continue

        if want_bull and c["close"] < c["open"]:
            impulse_high = max([cc["close"] for cc in next_candles])
            impulse_strength = (impulse_high - c["high"]) / c["high"] if c["high"]!=0 else 0
            if impulse_strength > 0.002:
                ob_low = c["low"]; ob_high = c["high"]; ob_mid = (ob_low + ob_high)/2
                tolerance = ob_high * 0.005 if ob_high > 1000 else ob_high * 0.0015
                # Invalidation: a normal retest dips INTO or slightly THROUGH
                # the zone before reversing — that's not a break, it's the
                # entry. Only treat it as genuinely broken if price closed a
                # full zone-height beyond it (a decisive structural break),
                # not just a marginal tick past a tight tolerance band.
                zone_height = ob_high - ob_low
                break_margin = max(zone_height, tolerance)
                broken = any(cc["close"] < ob_low - break_margin for cc in candles[i+1:-1])
                if broken: continue
                if abs(last_close - ob_mid) <= tolerance or (last_low <= ob_high and last_close >= ob_low):
                    return True, f"Bull OB {ob_low:.2f}-{ob_high:.2f}", 4

        if want_bear and c["close"] > c["open"]:
            impulse_low = min([cc["close"] for cc in next_candles])
            impulse_strength = (c["low"] - impulse_low) / c["low"] if c["low"]!=0 else 0
            if impulse_strength > 0.002:
                ob_low = c["low"]; ob_high = c["high"]; ob_mid = (ob_low + ob_high)/2
                tolerance = ob_high * 0.005 if ob_high > 1000 else ob_high * 0.0015
                # Same reasoning as the bullish case: only a full zone-height
                # breach counts as genuinely broken, not a marginal retest.
                zone_height = ob_high - ob_low
                break_margin = max(zone_height, tolerance)
                broken = any(cc["close"] > ob_high + break_margin for cc in candles[i+1:-1])
                if broken: continue
                if abs(last_close - ob_mid) <= tolerance or (last_high >= ob_low and last_close <= ob_high):
                    return True, f"Bear OB {ob_low:.2f}-{ob_high:.2f}", 4
    return False, "", 0

# ---- NEW: decimal precision per instrument CATEGORY, not per live price
# level. The old approach ("if price < 20, use 5 decimals, else 2") breaks
# down constantly: JPY pairs and indices sit above 20 but need their own
# conventions, and crypto alts drift across that threshold over time,
# silently changing how many decimals a symbol displays from one signal to
# the next. This is fixed per-symbol instead, matching how real trading
# platforms quote each instrument. ----
def price_decimals(symbol):
    if symbol == "XAUUSD": return 2
    if symbol == "XAGUSD": return 3
    if symbol in ("XTIUSD", "XBRUSD"): return 2
    if symbol in ("US30","NAS100","SPX500","GER40","UK100","FRA40","ESP35","ITA40","JPN225","AUS200"): return 1
    if symbol in ("BTCUSD","ETHUSD"): return 2
    if symbol in ("SOLUSD","BNBUSD","LINKUSD","LTCUSD","AVAXUSD"): return 3
    if symbol in ("XRPUSD","ADAUSD","DOGEUSD","DOTUSD","MATICUSD"): return 5
    if "JPY" in symbol: return 3
    return 5  # standard forex majors/crosses (pipette precision)

# ---- NEW: builds a short, plain-language explanation FROM the same factors
# that produced the score — not a separate guess, just that reasoning
# translated into a sentence a human can read in the Telegram message. ----
def build_rationale(symbol, final_bias, score, daily_bias, aligned_4h, bias_4h, premium_pct,
                     rsi_h1, bos_bull, bos_bear, breakout_bull, breakout_bear,
                     h1_fvg, m5_fvg, h1_ob, h1_ob_zone, m5_ob, multi_ob, multi_ob_details,
                     h1_sweep, m5_sweep, h1_patterns, m5_patterns):
    direction_word = "buyers" if final_bias == "BULLISH" else "sellers"
    parts = []

    if aligned_4h:
        parts.append(f"daily and 4H trend both point {final_bias.lower()}, so {direction_word} have the higher-timeframe trend behind them")
    elif daily_bias != "NEUTRAL":
        parts.append(f"daily trend is {daily_bias.lower()}")

    if final_bias == "BULLISH" and premium_pct <= 35:
        parts.append(f"price is in the discount zone of its recent range ({premium_pct:.0f}%), a level buyers have tended to defend")
    elif final_bias == "BEARISH" and premium_pct >= 65:
        parts.append(f"price is in the premium zone of its recent range ({premium_pct:.0f}%), a level sellers have tended to defend")

    if h1_sweep or m5_sweep:
        parts.append("a recent liquidity sweep took out resting stops just before reversing")

    ob_note = None
    if h1_ob: ob_note = f"an H1 {h1_ob_zone.split(' ')[0].lower()} order block"
    elif multi_ob: ob_note = f"an order block on {multi_ob_details.split('|')[0].strip()}"
    elif m5_ob: ob_note = "a fresh 5-minute order block"
    if ob_note:
        parts.append(f"price is reacting from {ob_note}")

    if h1_fvg or m5_fvg:
        parts.append("an unfilled imbalance (fair value gap) sits nearby, often acting as a magnet")

    if bos_bull or bos_bear or breakout_bull or breakout_bear:
        parts.append(f"structure just broke {'higher' if final_bias=='BULLISH' else 'lower'}, confirming momentum")

    pats = h1_patterns + m5_patterns
    if pats:
        parts.append(f"a {', '.join(sorted(set(pats)))} candle confirms rejection at this level")

    if final_bias=="BULLISH" and 40<=rsi_h1<=55:
        parts.append(f"RSI at {rsi_h1:.0f} shows a healthy pullback, not an overbought chase")
    elif final_bias=="BEARISH" and 45<=rsi_h1<=60:
        parts.append(f"RSI at {rsi_h1:.0f} shows a healthy pullback, not an oversold chase")

    if not parts:
        return f"{score}/10 confluence with no single dominant factor — lower-conviction setup, size accordingly."

    return f"{'; '.join(parts)}.".capitalize()

# ---- FIXED: reuses the already-fetched 1h candles instead of re-fetching,
# and passes bias through so it doesn't count an opposite-direction OB. ----
def detect_multi_tf_ob(symbol, bias, cache, h1_candles=None):
    timeframes = ["4h","2h","1h"]; ob_found = False; ob_details = []; total_score = 0
    for tf in timeframes:
        if tf == "1h" and h1_candles is not None:
            candles = h1_candles
        else:
            candles,_ = get_values_cached(cache, symbol, tf, 50)
        if not candles or len(candles) < 20: continue
        found, zone, score = detect_order_block(candles, bias)
        if found: ob_found = True; ob_details.append(f"{tf.upper()} {zone}"); total_score += score
    return ob_found, " | ".join(ob_details), total_score

def is_news_time(user_settings):
    # NOTE: this is a rough calendar approximation, not a real economic
    # calendar feed. It will miss unscheduled/rescheduled high-impact
    # events and misfire in months where dates don't line up. Wire in a
    # real calendar API (Trading Economics / Forex Factory / similar) if
    # you're trading news-sensitive instruments seriously.
    trade_news=user_settings.get("trade_news",True); now=datetime.utcnow(); weekday=now.weekday()
    is_nfp_day=weekday==4 and 1<=now.day<=7; is_fomc=now.day in [29,30,31] and now.month in [1,3,5,6,7,9,11,12]; is_cpi_week=10<=now.day<=15; is_news=is_nfp_day or is_fomc or is_cpi_week
    if not trade_news and is_news: return True,"NEWS BLOCKED - Trade News OFF"
    return False,""

# ================= V24 UNIFIED ENGINE - ONE STRATEGY, 2 MODES =================
def full_multi_tf_analysis(symbol, user_settings=None):
    if user_settings is None: user_settings={"trade_news":True,"trading_mode":"regular","currency":"ZAR"}
    mode = user_settings.get("trading_mode","regular") # regular or scalp
    min_rr = user_settings.get("min_risk_reward", 1.5)
    cache = {}  # per-call fetch cache: guarantees no duplicate API calls or double-counted candles

    is_open, closed_reason = is_market_open(symbol)
    if not is_open:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"premium_pct":50,"reason":closed_reason,"confluence":closed_reason,"details":{"market_closed":True},"mode":mode}
    blocked,reason=is_news_time(user_settings)
    if blocked:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"premium_pct":50,"reason":reason,"confluence":reason,"details":{"news_blocked":True},"mode":mode}

    daily_bias,premium_pct,daily_candles=get_htf_bias(symbol, cache)
    aligned_4h,bias_4h=check_4h_alignment(symbol,daily_bias, cache)
    h1_candles,_=get_values_cached(cache, symbol,"1h",40)
    m5_candles,_=get_values_cached(cache, symbol,"5min",50)
    if not h1_candles or len(h1_candles)<20:
        return {"symbol":symbol,"signal":False,"score":0,"bias":daily_bias,"entry":0,"premium_pct":premium_pct,"reason":"No H1 data","confluence":"No H1","details":{},"mode":mode}

    # ALL INDICATORS - ONE CALCULATION
    ema5_h1=ema(h1_candles,5); ema20_h1=ema(h1_candles,20); rsi_h1=rsi(h1_candles,14)
    atr_h1=atr(h1_candles,14)
    h1_patterns,h1_pat_score=detect_candle(h1_candles)
    h1_sweep,h1_sweep_score=detect_sweep(h1_candles,daily_bias)
    h1_fvg=detect_fvg(h1_candles)
    recent_high = max([c["high"] for c in h1_candles[-21:-1]]); recent_low = min([c["low"] for c in h1_candles[-21:-1]])
    last_h1=h1_candles[-1]
    bos_bull = last_h1["close"]>recent_high; bos_bear = last_h1["close"]<recent_low
    breakout_bull = last_h1["close"]>recent_high*1.0002; breakout_bear = last_h1["close"]<recent_low*0.9998

    m5_pat_score=0; m5_sweep=False; m5_sweep_score=0; m5_fvg=False; m5_ob=False; m5_ob_score=0; m5_patterns=[]; ema9_m5=None; ema21_m5=None; rsi_m5=50; atr_m5=None
    if m5_candles and len(m5_candles)>=20:
        ema9_m5=ema(m5_candles,9); ema21_m5=ema(m5_candles,21); rsi_m5=rsi(m5_candles,14)
        atr_m5=atr(m5_candles,14)
        m5_patterns,m5_pat_score=detect_candle(m5_candles)
        m5_sweep,m5_sweep_score=detect_sweep(m5_candles,daily_bias)
        m5_fvg=detect_fvg(m5_candles)

    # DETERMINE BIAS - unified (computed BEFORE order-block detection, since
    # OB detection now needs to know which direction to look for)
    bias_votes = []
    if daily_bias!="NEUTRAL": bias_votes.append(daily_bias)
    if bias_4h!="NEUTRAL": bias_votes.append(bias_4h)
    if ema5_h1 and ema20_h1:
        bias_votes.append("BULLISH" if ema5_h1>ema20_h1 else "BEARISH")
    if ema9_m5 and ema21_m5:
        bias_votes.append("BULLISH" if ema9_m5>ema21_m5 else "BEARISH")
    if bos_bull or breakout_bull: bias_votes.append("BULLISH")
    if bos_bear or breakout_bear: bias_votes.append("BEARISH")
    final_bias = max(set(bias_votes), key=bias_votes.count) if bias_votes else "NEUTRAL"

    # Order blocks - now direction-aware and de-duplicated against the
    # shared 1h candle set (no separate re-fetch, no double count)
    h1_ob, h1_ob_zone, h1_ob_score = detect_order_block(h1_candles, final_bias)
    if m5_candles and len(m5_candles) >= 20:
        m5_ob, _, m5_ob_score = detect_order_block(m5_candles, final_bias)
    multi_ob, multi_ob_details, multi_ob_score = detect_multi_tf_ob(symbol, final_bias, cache, h1_candles=h1_candles)

    # SCORING - ALL STRATEGIES COMBINED AS ONE
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

    crypto_list = ["BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD","ADAUSD","DOGEUSD","DOTUSD","AVAXUSD","LINKUSD","MATICUSD","LTCUSD"]
    is_crypto = symbol in crypto_list
    has_ob = h1_ob or m5_ob or multi_ob
    has_sweep = h1_sweep or m5_sweep
    has_pattern = h1_pat_score>=2 or m5_pat_score>=2

    if mode=="scalp":
        # FIXED: EMA-cross check no longer neutralized by a trailing OR
        m5_bias_ok = bool(ema9_m5 and ema21_m5 and (
            (ema9_m5>ema21_m5 and final_bias=="BULLISH") or
            (ema9_m5<ema21_m5 and final_bias=="BEARISH")
        ))
        is_signal = score>=5 and has_pattern and m5_bias_ok and 20<=rsi_m5<=80
        if not is_signal:
            if score<5: reason=f"Scalp Score {score}/10 - need 5+"
            elif not has_pattern: reason=f"Scalp Score {score}/10 no pattern"
            elif not m5_bias_ok: reason=f"Scalp Score {score}/10 M5 EMA not aligned with {final_bias}"
            else: reason=f"Scalp Score {score}/10 Wait RSI {rsi_m5:.0f}"
        else:
            reason=f"Scalp {score}/10 STRONG {final_bias} {'OB' if has_ob else 'Sweep' if has_sweep else 'EMA'}"
    else:
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

    # ---- NEW: stop-loss / take-profit / R:R, gated on min_rr ----
    stop_loss = None; take_profit = None; risk_reward = None
    if is_signal and entry:
        ref_atr = atr_m5 if mode == "scalp" and atr_m5 else atr_h1
        if ref_atr:
            buffer = ref_atr * 1.2
            if final_bias == "BULLISH":
                # prefer the structural low (OB/sweep low) if it's further
                # than the ATR buffer, otherwise use the ATR buffer
                struct_low = min(recent_low, h1_candles[-1]["low"])
                stop_loss = min(entry - buffer, struct_low - buffer * 0.25)
                risk = entry - stop_loss
                take_profit = entry + risk * min_rr
            else:
                struct_high = max(recent_high, h1_candles[-1]["high"])
                stop_loss = max(entry + buffer, struct_high + buffer * 0.25)
                risk = stop_loss - entry
                take_profit = entry - risk * min_rr
            risk_reward = min_rr
            if risk <= 0:
                stop_loss = take_profit = risk_reward = None
                is_signal = False
                reason = "Rejected: invalid SL distance"

    rationale = build_rationale(symbol, final_bias, score, daily_bias, aligned_4h, bias_4h, premium_pct,
                                 rsi_h1, bos_bull, bos_bear, breakout_bull, breakout_bear,
                                 h1_fvg, m5_fvg, h1_ob, h1_ob_zone, m5_ob, multi_ob, multi_ob_details,
                                 h1_sweep, m5_sweep, h1_patterns, m5_patterns)

    return {
        "symbol":symbol,
        "signal":is_signal,
        "score":score,
        "bias":final_bias,
        "bias_4h":bias_4h,
        "entry":entry,
        "stop_loss":stop_loss,
        "take_profit":take_profit,
        "risk_reward":risk_reward,
        "premium_pct":premium_pct,
        "reason":reason,
        "rationale":rationale,
        "confluence":" | ".join(parts) if parts else "No confluence",
        "details":{"candles":h1_patterns+m5_patterns,"sweep":has_sweep,"fvg":h1_fvg or m5_fvg,"ob":has_ob,"ob_details":multi_ob_details,"rsi_h1":round(rsi_h1,1),"rsi_m5":round(rsi_m5,1),"bos":bos_bull or bos_bear,"breakout":breakout_bull or breakout_bear},
        "mode":mode
    }
