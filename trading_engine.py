import os, requests, itertools, time
from datetime import datetime

# V19.7 - 4 Keys Support + Extended Symbols
API_KEYS = [k for k in [
    os.getenv("TWELVE_DATA_API_KEY"),
    os.getenv("TWELVE_DATA_API_KEY_2"),
    os.getenv("TWELVE_DATA_API_KEY_3"),
    os.getenv("TWELVE_DATA_API_KEY_4"),
] if k]

key_cycle = itertools.cycle(API_KEYS) if API_KEYS else None
def get_key(): return next(key_cycle) if key_cycle else None

# EXTENDED MAP - 38 Symbols for diversity
SYMBOL_MAP = {
    "EURUSD":"EUR/USD","GBPUSD":"GBP/USD","USDJPY":"USD/JPY","USDCHF":"USD/CHF","AUDUSD":"AUD/USD","USDCAD":"USD/CAD","NZDUSD":"NZD/USD",
    "EURJPY":"EUR/JPY","GBPJPY":"GBP/JPY","EURGBP":"EUR/GBP","AUDJPY":"AUD/JPY","CADJPY":"CAD/JPY","CHFJPY":"CHF/JPY","EURCHF":"EUR/CHF",
    "GBPCHF":"GBP/CHF","AUDCHF":"AUD/CHF","EURAUD":"EUR/AUD","GBPAUD":"GBP/AUD","EURCAD":"EUR/CAD","GBPCAD":"GBP/CAD",
    "XAUUSD":"XAU/USD","XAGUSD":"XAG/USD","XAUJPY":"XAU/JPY",
    "US30":"DJI","NAS100":"NDX","SPX500":"SPX","GER40":"DAX","UK100":"FTSE","FRA40":"CAC","ESP35":"IBEX","ITA40":"FTSE MIB",
    "BTCUSD":"BTC/USD","ETHUSD":"ETH/USD","SOLUSD":"SOL/USD","BNBUSD":"BNB/USD"
}

def td_request(symbol, interval):
    td_symbol = SYMBOL_MAP.get(symbol, symbol)
    url_base = f"https://api.twelvedata.com/time_series?symbol={td_symbol}&interval={interval}&outputsize=100"
    for _ in range(len(API_KEYS)*4 if API_KEYS else 1):
        key = get_key()
        if not key: return {"code":500,"message":"No API keys"}
        try:
            r = requests.get(f"{url_base}&apikey={key}", timeout=15).json()
            if r.get("code")==429 or "exceeded" in str(r).lower() or "limit" in str(r).lower():
                time.sleep(0.6)
                continue
            if "values" in r: return r
        except:
            time.sleep(0.5)
            continue
    return {"code":429,"message":"All 4 keys 429 - resets 2am SAST"}

# === CANDLESTICK DETECTION ===
def detect_candle_patterns(vals):
    """Detect Hammer, Hanging Man, Doji, Engulfing"""
    if len(vals) < 3: return []
    patterns = []
    try:
        for i in range(1, min(5, len(vals))):
            c = vals[i-1] # Most recent closed candle
            prev = vals[i]
            o = float(c["open"]); h = float(c["high"]); l = float(c["low"]); cl = float(c["close"])
            po = float(prev["open"]); ph = float(prev["high"]); pl = float(prev["low"]); pcl = float(prev["close"])

            body = abs(cl - o)
            upper_wick = h - max(cl, o)
            lower_wick = min(cl, o) - l
            total_range = h - l
            if total_range == 0: continue

            # Doji - small body <10% of range
            if body <= total_range * 0.1:
                patterns.append({"type":"DOJI","bias":"REVERSAL","strength":2,"desc":f"Doji indecision"})

            # Hammer - bullish reversal at bottom - long lower wick, small body, small upper
            if lower_wick >= body * 2 and upper_wick <= body * 0.5 and body > 0:
                if total_range > 0 and lower_wick >= total_range * 0.6:
                    patterns.append({"type":"HAMMER","bias":"BULLISH","strength":3,"desc":f"Hammer bullish reversal"})

            # Hanging Man / Shooting Star - bearish reversal at top
            if upper_wick >= body * 2 and lower_wick <= body * 0.5 and body > 0:
                if total_range > 0 and upper_wick >= total_range * 0.6:
                    patterns.append({"type":"HANGING_MAN","bias":"BEARISH","strength":3,"desc":f"Hanging Man bearish reversal"})

            # Bullish Engulfing - current bullish engulfs previous bearish
            if cl > o and pcl < po and cl >= po and o <= pcl and body > abs(pcl - po):
                patterns.append({"type":"BULL_ENGULFING","bias":"BULLISH","strength":4,"desc":f"Bullish Engulfing strong"})

            # Bearish Engulfing
            if cl < o and pcl > po and cl <= po and o >= pcl and body > abs(pcl - po):
                patterns.append({"type":"BEAR_ENGULFING","bias":"BEARISH","strength":4,"desc":f"Bearish Engulfing strong"})
    except Exception as e:
        pass
    return patterns

def detect_liquidity_sweep(data):
    """Detect liquidity sweep - wick beyond recent high/low then close back inside"""
    try:
        vals = data.get("values", [])[:20]
        if len(vals) < 10: return False, "No data", 0
        recent_high = max([float(v["high"]) for v in vals[1:11]])
        recent_low = min([float(v["low"]) for v in vals[1:11]])
        curr = vals[0]
        h = float(curr["high"]); l = float(curr["low"]); cl = float(curr["close"])

        # Bullish sweep - swept recent low then closed above
        if l < recent_low and cl > recent_low:
            sweep_dist = recent_low - l
            return True, f"Swept Low {recent_low:.5f} + Closed Above - Liquidity Grab Bullish", sweep_dist
        # Bearish sweep - swept recent high then closed below
        if h > recent_high and cl < recent_high:
            sweep_dist = h - recent_high
            return True, f"Swept High {recent_high:.5f} + Closed Below - Liquidity Grab Bearish", sweep_dist

        return False, "No sweep", 0
    except:
        return False, "Sweep error", 0

def detect_fvg(data):
    try:
        vals = data.get("values", [])[:10]
        if len(vals) < 3: return False
        for i in range(1, len(vals)-1):
            prev_high = float(vals[i+1]["high"])
            next_low = float(vals[i-1]["low"])
            if next_low > prev_high: return True
        return False
    except: return False

def get_htf_bias_and_zone(data):
    try:
        vals = data.get("values", [])[:40]
        if len(vals) < 15: return "NEUTRAL", 50, "No data", 0, 0, 0, 0
        closes = [float(v["close"]) for v in vals[::-1]]
        highs = [float(v["high"]) for v in vals[::-1]]
        lows = [float(v["low"]) for v in vals[::-1]]
        htf_high = max(highs)
        htf_low = min(lows)
        htf_range = htf_high - htf_low
        if htf_range == 0: return "NEUTRAL", 50, "No range", 0,0,0,0
        current = closes[-1]
        premium_pct = ((current - htf_low) / htf_range) * 100
        ema_fast = sum(closes[-5:])/5
        ema_slow = sum(closes[-20:])/20

        if ema_fast > ema_slow * 1.0003:
            return "BULLISH", premium_pct, f"HTF Uptrend {premium_pct:.0f}%", htf_high, htf_low, ema_fast, ema_slow
        elif ema_fast < ema_slow * 0.9997:
            return "BEARISH", premium_pct, f"HTF Downtrend {premium_pct:.0f}%", htf_high, htf_low, ema_fast, ema_slow
        else:
            return "NEUTRAL", premium_pct, f"HTF Sideways {premium_pct:.0f}%", htf_high, htf_low, ema_fast, ema_slow
    except Exception as e:
        return "NEUTRAL", 50, f"Error {e}", 0,0,0,0

def full_multi_tf_analysis(symbol):
    d = td_request(symbol,"1day")
    h4 = td_request(symbol,"4h")
    h1 = td_request(symbol,"1h")
    m5 = td_request(symbol,"5min")

    if d.get("code")==429:
        return {"signal":False,"symbol":symbol,"score":0,"bias":"NEUTRAL","reason":"429 All 4 keys exhausted - 2am SAST reset","details":{"keys":len(API_KEYS)},"entry":0,"time":datetime.now().isoformat()}

    d_bias, d_premium, d_reason, d_high, d_low, d_ef, d_es = get_htf_bias_and_zone(d)
    h4_bias, h4_premium, h4_reason, h4_high, h4_low, h4_ef, h4_es = get_htf_bias_and_zone(h4)
    h1_bias, h1_premium, h1_reason, h1_high, h1_low, h1_ef, h1_es = get_htf_bias_and_zone(h1)

    # LTF analysis for reversal candles
    m5_patterns = detect_candle_patterns(m5.get("values", [])) if m5.get("values") else []
    h1_patterns = detect_candle_patterns(h1.get("values", [])) if h1.get("values") else []

    # Liquidity sweep
    h1_sweep, h1_sweep_desc, h1_sweep_dist = detect_liquidity_sweep(h1)
    m5_sweep, m5_sweep_desc, m5_sweep_dist = detect_liquidity_sweep(m5)

    fvg_h1 = detect_fvg(h1)
    fvg_m5 = detect_fvg(m5)

    score = 0
    reasons = []
    bullish_confluence = 0
    bearish_confluence = 0

    # === HTF DIRECTION FILTER ===
    if d_bias == "NEUTRAL":
        return {"signal":False,"symbol":symbol,"score":0,"bias":"NEUTRAL","reason":f"No HTF bias - {d_reason}","confluence":f"HTF Sideways {d_premium:.0f}% - Waiting","details":{"D":d_bias,"4H":h4_bias,"1H":h1_bias,"D_premium":f"{d_premium:.0f}%","keys":len(API_KEYS)},"entry":float(h1.get("values",[{}])[0].get("close",0)) if h1.get("values") else 0,"premium_pct":d_premium,"time":datetime.now().isoformat()}

    # Score HTF
    if d_bias!= "NEUTRAL":
        score += 2
        reasons.append(f"D {d_bias} {d_premium:.0f}%")

    # 4H must align
    if h4_bias == d_bias:
        score += 2
        reasons.append(f"4H {h4_bias} aligned")
        if d_bias == "BULLISH": bullish_confluence += 2
        else: bearish_confluence += 2
    elif h4_bias == "NEUTRAL":
        score += 0
        reasons.append(f"4H NEUTRAL - waiting")
    else:
        score -= 3
        reasons.append(f"4H {h4_bias} vs D {d_bias} conflict - NO SIGNAL")

    # === PREMIUM/DISCOUNT ZONE FILTER - CRITICAL ===
    if d_bias == "BULLISH":
        if d_premium < 35:
            score += 3
            bullish_confluence += 3
            reasons.append(f"✅ DISCOUNT {d_premium:.0f}% perfect BUY zone")
        elif d_premium > 60:
            # Block BUY in premium
            return {"signal":False,"symbol":symbol,"score":score,"bias":"NEUTRAL","reason":f"🚫 BLOCKED BUY - Premium {d_premium:.0f}% don't buy high - {d_reason}","confluence":f"🚫 Premium {d_premium:.0f}% - Waiting for Discount","details":{"D":d_bias,"4H":h4_bias,"1H":h1_bias,"D_premium":f"{d_premium:.0f}%","keys":len(API_KEYS)},"entry":float(h1.get("values",[{}])[0].get("close",0)) if h1.get("values") else 0,"premium_pct":d_premium,"time":datetime.now().isoformat()}
    else: # BEARISH
        if d_premium > 65:
            score += 3
            bearish_confluence += 3
            reasons.append(f"✅ PREMIUM {d_premium:.0f}% perfect SELL zone")
        elif d_premium < 40:
            return {"signal":False,"symbol":symbol,"score":score,"bias":"NEUTRAL","reason":f"🚫 BLOCKED SELL - Discount {d_premium:.0f}% don't sell low - {d_reason}","confluence":f"🚫 Discount {d_premium:.0f}% - Waiting for Premium","details":{"D":d_bias,"4H":h4_bias,"1H":h1_bias,"D_premium":f"{d_premium:.0f}%","keys":len(API_KEYS)},"entry":float(h1.get("values",[{}])[0].get("close",0)) if h1.get("values") else 0,"premium_pct":d_premium,"time":datetime.now().isoformat()}

    # === LTF REVERSAL CANDLES IN ZONE ===
    all_patterns = m5_patterns + h1_patterns
    for pat in all_patterns:
        if d_bias == "BULLISH" and pat["bias"] == "BULLISH":
            score += pat["strength"]
            bullish_confluence += pat["strength"]
            reasons.append(f"🕯️ {pat['type']} {pat['desc']} +{pat['strength']}")
        elif d_bias == "BEARISH" and pat["bias"] == "BEARISH":
            score += pat["strength"]
            bearish_confluence += pat["strength"]
            reasons.append(f"🕯️ {pat['type']} {pat['desc']} +{pat['strength']}")

    # === LIQUIDITY SWEEP ===
    if h1_sweep:
        if d_bias == "BULLISH" and "Bullish" in h1_sweep_desc:
            score += 3
            bullish_confluence += 3
            reasons.append(f"💧 {h1_sweep_desc}")
        elif d_bias == "BEARISH" and "Bearish" in h1_sweep_desc:
            score += 3
            bearish_confluence += 3
            reasons.append(f"💧 {h1_sweep_desc}")

    if m5_sweep:
        if d_bias == "BULLISH" and "Bullish" in m5_sweep_desc:
            score += 2
            bullish_confluence += 2
            reasons.append(f"💧 M5 {m5_sweep_desc}")
        elif d_bias == "BEARISH" and "Bearish" in m5_sweep_desc:
            score += 2
            bearish_confluence += 2
            reasons.append(f"💧 M5 {m5_sweep_desc}")

    # === FVG ===
    if fvg_h1:
        score += 1
        reasons.append("📦 H1 FVG imbalance")

    # === FINAL STRONG ONLY FILTER - Avoid weak SL hits ===
    # Require at least: HTF alignment + Zone + 1 reversal pattern + 1 sweep OR engulfing
    has_strong_pattern = any(p["type"] in ["BULL_ENGULFING","BEAR_ENGULFING","HAMMER","HANGING_MAN"] for p in all_patterns)
    has_sweep = h1_sweep or m5_sweep

    min_confluence = 5
    if d_bias == "BULLISH":
        if bullish_confluence < min_confluence:
            reasons.append(f"⚠️ Weak BUY confluence {bullish_confluence}/{min_confluence} - Need candle + sweep")
            is_signal = False
        else:
            is_signal = score >= 7 and has_strong_pattern and has_sweep
    else:
        if bearish_confluence < min_confluence:
            reasons.append(f"⚠️ Weak SELL confluence {bearish_confluence}/{min_confluence} - Need candle + sweep")
            is_signal = False
        else:
            is_signal = score >= 7 and has_strong_pattern and has_sweep

    # Block if opposite
    if h4_bias!= "NEUTRAL" and h4_bias!= d_bias:
        is_signal = False

    score = max(0, min(score, 10))
    entry = 0
    try:
        entry = float(h1.get("values",[{}])[0].get("close",0))
        if entry == 0:
            entry = float(m5.get("values",[{}])[0].get("close",0))
    except: pass

    # Build confluence for Telegram
    confluence_lines = []
    zone_name = "PREMIUM" if d_premium > 50 else "DISCOUNT"
    confluence_lines.append(f"· HTF: Daily {d_premium:.0f}% {zone_name} | 4H {h4_premium:.0f}% | D {d_bias}")
    if d_bias == "BULLISH" and d_premium < 35:
        confluence_lines.append(f"· ✅ DISCOUNT {d_premium:.0f}% perfect BUY zone")
    elif d_bias == "BEARISH" and d_premium > 65:
        confluence_lines.append(f"· ✅ PREMIUM {d_premium:.0f}% perfect SELL zone")
    if has_sweep:
        confluence_lines.append(f"· 💧 Liquidity Sweep: {h1_sweep_desc if h1_sweep else m5_sweep_desc}")
    for pat in all_patterns[:2]:
        confluence_lines.append(f"· 🕯️ {pat['type']} {pat['desc']}")
    if fvg_h1: confluence_lines.append("· 📦 FVG imbalance filled")
    confluence_lines.append(f"· 🔥 Confluence: {bullish_confluence if d_bias=='BULLISH' else bearish_confluence}/10 Strong")

    return {
        "signal": bool(is_signal),
        "symbol": symbol,
        "score": score,
        "bias": d_bias if is_signal else "NEUTRAL",
        "reason": " | ".join(reasons),
        "confluence": "\n".join(confluence_lines),
        "details": {"D":d_bias,"4H":h4_bias,"1H":h1_bias,"D_premium":f"{d_premium:.0f}%","4H_premium":f"{h4_premium:.0f}%","candles":[p["type"] for p in all_patterns],"sweep":bool(has_sweep),"keys":len(API_KEYS)},
        "entry": entry,
        "premium_pct": d_premium,
        "time": datetime.now().isoformat()
    }

def run_scan_and_send():
    symbols = list(SYMBOL_MAP.keys())[:25]
    results = []
    for s in symbols:
        results.append(full_multi_tf_analysis(s))
        time.sleep(0.8)
    bot = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    sent = 0
    for r in results:
        if r.get("signal") and bot and chat:
            msg = f"🚀 AGENT 35 V19.7 STRONG\n{r['symbol']} {r['bias']} {r['score']}/10\n{r['reason']}\nEntry ~{r.get('entry')}"
            try:
                requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat,"text":msg}, timeout=10)
                sent+=1
            except: pass
    return {"scanned":len(results),"signals":[x for x in results if x['signal']],"sent":sent,"all":results}
