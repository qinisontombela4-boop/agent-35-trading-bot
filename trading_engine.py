import os, requests, itertools, time
from datetime import datetime, timedelta
import json

API_KEYS = [k for k in [
    os.getenv("TWELVE_DATA_API_KEY"),
    os.getenv("TWELVE_DATA_API_KEY_2"),
    os.getenv("TWELVE_DATA_API_KEY_3"),
    os.getenv("TWELVE_DATA_API_KEY_4"),
] if k]

key_cycle = itertools.cycle(API_KEYS) if API_KEYS else None
def get_key(): return next(key_cycle) if key_cycle else None

SYMBOL_MAP = {
    "EURUSD":"EUR/USD","GBPUSD":"GBP/USD","USDJPY":"USD/JPY","USDCHF":"USD/CHF","AUDUSD":"AUD/USD","USDCAD":"USD/CAD","NZDUSD":"NZD/USD",
    "EURJPY":"EUR/JPY","GBPJPY":"GBP/JPY","EURGBP":"EUR/GBP","AUDJPY":"AUD/JPY","CADJPY":"CAD/JPY","CHFJPY":"CHF/JPY","EURCHF":"EUR/CHF",
    "GBPCHF":"GBP/CHF","AUDCHF":"AUD/CHF","EURAUD":"EUR/AUD","GBPAUD":"GBP/AUD","EURCAD":"EUR/CAD","GBPCAD":"GBP/CAD",
    "XAUUSD":"XAU/USD","XAGUSD":"XAG/USD","XAUJPY":"XAU/JPY",
    "US30":"DJI","NAS100":"NDX","SPX500":"SPX","GER40":"DAX","UK100":"FTSE","FRA40":"CAC",
    "BTCUSD":"BTC/USD","ETHUSD":"ETH/USD","SOLUSD":"SOL/USD","BNBUSD":"BNB/USD"
}

def td_request(symbol, interval):
    td_symbol = SYMBOL_MAP.get(symbol, symbol)
    url_base = f"https://api.twelvedata.com/time_series?symbol={td_symbol}&interval={interval}&outputsize=100"
    for _ in range(len(API_KEYS)*4 if API_KEYS else 1):
        key = get_key()
        if not key: return {"code":500,"message":"No keys"}
        try:
            r = requests.get(f"{url_base}&apikey={key}", timeout=15).json()
            if r.get("code")==429 or "exceeded" in str(r).lower() or "limit" in str(r).lower():
                time.sleep(0.6); continue
            if "values" in r: return r
        except: time.sleep(0.5); continue
    return {"code":429,"message":"All 4 keys 429"}

# === NEWS LOGIC FROM YOUR PHOTO ===
NEWS_FILE = "/data/news_cache.json" if os.path.exists("/data") else "news_cache.json"

def get_news_bias():
    """
    Photo logic:
    NFP Strong / CPI High / FOMC Rates Up / Unemployment Low = $ UP, Gold DOWN
    NFP Weak / CPI Low / FOMC Rates Down / Unemployment High = $ DOWN, Gold UP
    FOMC 29th July etc = high volatility
    """
    try:
        # Try fetch real calendar from forexfactory / investing - cache 1 hour
        if os.path.exists(NEWS_FILE):
            with open(NEWS_FILE,"r") as f:
                cache = json.load(f)
                if (datetime.now() - datetime.fromisoformat(cache["time"])).seconds < 3600:
                    return cache["data"]

        # Simple news check - in production use real API, for now logic based on upcoming high impact
        # We'll use current date to estimate risk window
        now = datetime.utcnow()
        news_risk = False
        news_bias = "NEUTRAL"
        reason = "No major news"

        # Check if today is high impact day (NFP first Friday, CPI mid-month, FOMC)
        # NFP = first Friday
        first_friday = 1 + (4 - datetime(now.year, now.month, 1).weekday()) % 7
        if now.day == first_friday and now.weekday() == 4:
            news_risk = True
            news_bias = "VOLATILE"
            reason = f"🔴 NFP TODAY - $ volatile - Gold inverse - Avoid or use photo logic: Strong NFP $ UP Gold DOWN"

        # FOMC dates 2026 (approx) - from your photo FOMC 29th July
        fomc_dates = ["2026-01-29","2026-03-19","2026-05-07","2026-06-18","2026-07-29","2026-09-17","2026-11-05","2026-12-17"]
        for d in fomc_dates:
            fomc_day = datetime.fromisoformat(d)
            if abs((now - fomc_day).days) <= 1:
                news_risk = True
                news_bias = "VOLATILE"
                reason = f"🔴 FOMC {d} - Rates UP = $ UP Gold DOWN, Rates DOWN = $ DOWN Gold UP - High volatility"

        # CPI week (around 10-15th)
        if 10 <= now.day <= 15:
            news_risk = True
            reason += " | CPI week possible - High CPI $ UP Gold DOWN"

        data = {"risk":news_risk,"bias":news_bias,"reason":reason,"usd_bias":"NEUTRAL","gold_bias":"NEUTRAL"}

        with open(NEWS_FILE,"w") as f:
            json.dump({"time":datetime.now().isoformat(),"data":data}, f)
        return data
    except:
        return {"risk":False,"bias":"NEUTRAL","reason":"News check error","usd_bias":"NEUTRAL","gold_bias":"NEUTRAL"}

def detect_candle_patterns(vals):
    if len(vals) < 3: return []
    patterns = []
    try:
        for i in range(1, min(5, len(vals))):
            c = vals[i-1]; prev = vals[i]
            o = float(c["open"]); h = float(c["high"]); l = float(c["low"]); cl = float(c["close"])
            po = float(prev["open"]); pcl = float(prev["close"])
            body = abs(cl - o); upper_wick = h - max(cl, o); lower_wick = min(cl, o) - l; total_range = h - l
            if total_range == 0: continue
            if body <= total_range * 0.1:
                patterns.append({"type":"DOJI","bias":"REVERSAL","strength":2,"desc":"Doji"})
            if lower_wick >= body * 2 and upper_wick <= body * 0.5 and lower_wick >= total_range * 0.6:
                patterns.append({"type":"HAMMER","bias":"BULLISH","strength":3,"desc":"Hammer bullish reversal"})
            if upper_wick >= body * 2 and lower_wick <= body * 0.5 and upper_wick >= total_range * 0.6:
                patterns.append({"type":"HANGING_MAN","bias":"BEARISH","strength":3,"desc":"Hanging Man bearish reversal"})
            if cl > o and pcl < po and cl >= po and o <= pcl and body > abs(pcl - po):
                patterns.append({"type":"BULL_ENGULFING","bias":"BULLISH","strength":4,"desc":"Bullish Engulfing strong"})
            if cl < o and pcl > po and cl <= po and o >= pcl and body > abs(pcl - po):
                patterns.append({"type":"BEAR_ENGULFING","bias":"BEARISH","strength":4,"desc":"Bearish Engulfing strong"})
    except: pass
    return patterns

def detect_liquidity_sweep(data):
    try:
        vals = data.get("values", [])[:20]
        if len(vals) < 10: return False, "No data", 0
        recent_high = max([float(v["high"]) for v in vals[1:11]])
        recent_low = min([float(v["low"]) for v in vals[1:11]])
        curr = vals[0]; h = float(curr["high"]); l = float(curr["low"]); cl = float(curr["close"])
        if l < recent_low and cl > recent_low:
            return True, f"Swept Low {recent_low:.5f} + Close Above - Liquidity Grab Bullish", recent_low - l
        if h > recent_high and cl < recent_high:
            return True, f"Swept High {recent_high:.5f} + Close Below - Liquidity Grab Bearish", h - recent_high
        return False, "No sweep", 0
    except: return False, "Error", 0

def detect_fvg(data):
    try:
        vals = data.get("values", [])[:10]
        if len(vals) < 3: return False
        for i in range(1, len(vals)-1):
            if float(vals[i-1]["low"]) > float(vals[i+1]["high"]): return True
        return False
    except: return False

def get_htf_bias_and_zone(data):
    try:
        vals = data.get("values", [])[:40]
        if len(vals) < 15: return "NEUTRAL", 50, "No data", 0,0,0,0
        closes = [float(v["close"]) for v in vals[::-1]]
        highs = [float(v["high"]) for v in vals[::-1]]
        lows = [float(v["low"]) for v in vals[::-1]]
        htf_high = max(highs); htf_low = min(lows); htf_range = htf_high - htf_low
        if htf_range == 0: return "NEUTRAL", 50, "No range", 0,0,0,0
        current = closes[-1]
        premium_pct = ((current - htf_low) / htf_range) * 100
        ema_fast = sum(closes[-5:])/5; ema_slow = sum(closes[-20:])/20
        if ema_fast > ema_slow * 1.0003: return "BULLISH", premium_pct, f"HTF Uptrend {premium_pct:.0f}%", htf_high, htf_low, ema_fast, ema_slow
        elif ema_fast < ema_slow * 0.9997: return "BEARISH", premium_pct, f"HTF Downtrend {premium_pct:.0f}%", htf_high, htf_low, ema_fast, ema_slow
        else: return "NEUTRAL", premium_pct, f"HTF Sideways {premium_pct:.0f}%", htf_high, htf_low, ema_fast, ema_slow
    except: return "NEUTRAL", 50, "Error", 0,0,0,0

def full_multi_tf_analysis(symbol, user_settings=None):
    # user_settings = {"trade_news":True/False}
    if user_settings is None: user_settings = {}
    trade_news = user_settings.get("trade_news", True)

    d = td_request(symbol,"1day"); h4 = td_request(symbol,"4h"); h1 = td_request(symbol,"1h"); m5 = td_request(symbol,"5min")
    if d.get("code")==429:
        return {"signal":False,"symbol":symbol,"score":0,"bias":"NEUTRAL","reason":"429 All 4 keys exhausted - 2am SAST reset","details":{"keys":len(API_KEYS)},"entry":0,"time":datetime.now().isoformat()}

    # News check
    news = get_news_bias()
    if news["risk"] and not trade_news:
        return {"signal":False,"symbol":symbol,"score":0,"bias":"NEUTRAL","reason":f"🚫 NEWS FILTER - {news['reason']} - User disabled news trading","confluence":f"🚫 News: {news['reason']}","details":{"D":"NEUTRAL","news_blocked":True,"keys":len(API_KEYS)},"entry":float(h1.get("values",[{}])[0].get("close",0)) if h1.get("values") else 0,"premium_pct":50,"time":datetime.now().isoformat()}

    d_bias, d_premium, d_reason, d_high, d_low, d_ef, d_es = get_htf_bias_and_zone(d)
    h4_bias, h4_premium, h4_reason, h4_high, h4_low, h4_ef, h4_es = get_htf_bias_and_zone(h4)
    h1_bias, h1_premium, h1_reason, h1_high, h1_low, h1_ef, h1_es = get_htf_bias_and_zone(h1)

    m5_patterns = detect_candle_patterns(m5.get("values", [])) if m5.get("values") else []
    h1_patterns = detect_candle_patterns(h1.get("values", [])) if h1.get("values") else []
    h1_sweep, h1_sweep_desc, _ = detect_liquidity_sweep(h1)
    m5_sweep, m5_sweep_desc, _ = detect_liquidity_sweep(m5)
    fvg_h1 = detect_fvg(h1)

    score = 0; reasons = []; bullish_confluence = 0; bearish_confluence = 0

    if d_bias == "NEUTRAL":
        return {"signal":False,"symbol":symbol,"score":0,"bias":"NEUTRAL","reason":f"No HTF bias - {d_reason}","confluence":f"HTF Sideways {d_premium:.0f}%","details":{"D":d_bias,"4H":h4_bias,"1H":h1_bias,"D_premium":f"{d_premium:.0f}%","keys":len(API_KEYS)},"entry":float(h1.get("values",[{}])[0].get("close",0)) if h1.get("values") else 0,"premium_pct":d_premium,"time":datetime.now().isoformat()}

    score += 2; reasons.append(f"D {d_bias} {d_premium:.0f}%")
    if h4_bias == d_bias:
        score += 2; reasons.append(f"4H {h4_bias} aligned")
        if d_bias == "BULLISH": bullish_confluence += 2
        else: bearish_confluence += 2
    elif h4_bias!= "NEUTRAL":
        score -= 3; reasons.append(f"4H {h4_bias} vs D {d_bias} conflict")
    if d_bias == "BULLISH":
        if d_premium < 35:
            score += 3; bullish_confluence += 3; reasons.append(f"✅ DISCOUNT {d_premium:.0f}% perfect BUY")
        elif d_premium > 60:
            return {"signal":False,"symbol":symbol,"score":score,"bias":"NEUTRAL","reason":f"🚫 BLOCKED BUY - Premium {d_premium:.0f}%","confluence":f"🚫 Premium {d_premium:.0f}% - Waiting Discount","details":{"D":d_bias,"D_premium":f"{d_premium:.0f}%","keys":len(API_KEYS)},"entry":float(h1.get("values",[{}])[0].get("close",0)) if h1.get("values") else 0,"premium_pct":d_premium,"time":datetime.now().isoformat()}
    else:
        if d_premium > 65:
            score += 3; bearish_confluence += 3; reasons.append(f"✅ PREMIUM {d_premium:.0f}% perfect SELL")
        elif d_premium < 40:
            return {"signal":False,"symbol":symbol,"score":score,"bias":"NEUTRAL","reason":f"🚫 BLOCKED SELL - Discount {d_premium:.0f}%","confluence":f"🚫 Discount {d_premium:.0f}% - Waiting Premium","details":{"D":d_bias,"D_premium":f"{d_premium:.0f}%","keys":len(API_KEYS)},"entry":float(h1.get("values",[{}])[0].get("close",0)) if h1.get("values") else 0,"premium_pct":d_premium,"time":datetime.now().isoformat()}

    all_patterns = m5_patterns + h1_patterns
    for pat in all_patterns:
        if d_bias == "BULLISH" and pat["bias"] == "BULLISH":
            score += pat["strength"]; bullish_confluence += pat["strength"]; reasons.append(f"🕯️ {pat['type']} +{pat['strength']}")
        elif d_bias == "BEARISH" and pat["bias"] == "BEARISH":
            score += pat["strength"]; bearish_confluence += pat["strength"]; reasons.append(f"🕯️ {pat['type']} +{pat['strength']}")

    if h1_sweep:
        if d_bias == "BULLISH" and "Bullish" in h1_sweep_desc: score += 3; bullish_confluence += 3; reasons.append(f"💧 {h1_sweep_desc}")
        elif d_bias == "BEARISH" and "Bearish" in h1_sweep_desc: score += 3; bearish_confluence += 3; reasons.append(f"💧 {h1_sweep_desc}")
    if m5_sweep:
        if d_bias == "BULLISH" and "Bullish" in m5_sweep_desc: score += 2; bullish_confluence += 2; reasons.append(f"💧 M5 {m5_sweep_desc}")
        elif d_bias == "BEARISH" and "Bearish" in m5_sweep_desc: score += 2; bearish_confluence += 2; reasons.append(f"💧 M5 {m5_sweep_desc}")
    if fvg_h1: score += 1; reasons.append("📦 FVG")

    # News bonus if aligns with photo logic
    if news["risk"]:
        reasons.append(f"⚠️ NEWS: {news['reason']}")
        if "XAU" in symbol or "Gold" in symbol:
            # Gold inverse to USD per photo
            if d_bias == "BEARISH" and "Gold - Down" in news["reason"]: score += 1
            if d_bias == "BULLISH" and "Gold - Up" in news["reason"]: score += 1

    has_strong_pattern = any(p["type"] in ["BULL_ENGULFING","BEAR_ENGULFING","HAMMER","HANGING_MAN"] for p in all_patterns)
    has_sweep = h1_sweep or m5_sweep
    min_confluence = 5
    if d_bias == "BULLISH":
        is_signal = bullish_confluence >= min_confluence and score >= 7 and has_strong_pattern and has_sweep
    else:
        is_signal = bearish_confluence >= min_confluence and score >= 7 and has_strong_pattern and has_sweep
    if h4_bias!= "NEUTRAL" and h4_bias!= d_bias: is_signal = False

    score = max(0, min(score, 10))
    entry = 0
    try:
        entry = float(h1.get("values",[{}])[0].get("close",0))
        if entry == 0: entry = float(m5.get("values",[{}])[0].get("close",0))
    except: pass

    confluence_lines = []
    zone_name = "PREMIUM" if d_premium > 50 else "DISCOUNT"
    confluence_lines.append(f"· HTF: Daily {d_premium:.0f}% {zone_name} | 4H {h4_premium:.0f}% | D {d_bias}")
    if d_bias == "BULLISH" and d_premium < 35: confluence_lines.append(f"· ✅ DISCOUNT {d_premium:.0f}% perfect BUY zone")
    elif d_bias == "BEARISH" and d_premium > 65: confluence_lines.append(f"· ✅ PREMIUM {d_premium:.0f}% perfect SELL zone")
    if has_sweep: confluence_lines.append(f"· 💧 Sweep: {h1_sweep_desc if h1_sweep else m5_sweep_desc}")
    for pat in all_patterns[:2]: confluence_lines.append(f"· 🕯️ {pat['type']} {pat['desc']}")
    if fvg_h1: confluence_lines.append("· 📦 FVG")
    if news["risk"]: confluence_lines.append(f"· 📰 News: {news['reason'][:80]}")
    confluence_lines.append(f"· 🔥 Confluence: {bullish_confluence if d_bias=='BULLISH' else bearish_confluence}/10 STRONG")

    return {
        "signal": bool(is_signal),
        "symbol": symbol,
        "score": score,
        "bias": d_bias if is_signal else "NEUTRAL",
        "reason": " | ".join(reasons),
        "confluence": "\n".join(confluence_lines),
        "details": {"D":d_bias,"4H":h4_bias,"1H":h1_bias,"D_premium":f"{d_premium:.0f}%","candles":[p["type"] for p in all_patterns],"sweep":bool(has_sweep),"news":news,"keys":len(API_KEYS)},
        "entry": entry,
        "premium_pct": d_premium,
        "time": datetime.now().isoformat()
    }

def run_scan_and_send():
    symbols = list(SYMBOL_MAP.keys())[:20]
    results = []
    for s in symbols:
        results.append(full_multi_tf_analysis(s))
        time.sleep(0.8)
    bot = os.getenv("TELEGRAM_BOT_TOKEN"); chat = os.getenv("TELEGRAM_CHAT_ID"); sent=0
    for r in results:
        if r.get("signal") and bot and chat:
            msg = f"🚀 V19.8 STRONG\n{r['symbol']} {r['bias']} {r['score']}/10\n{r['reason']}\nEntry {r.get('entry')}"
            try: requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat,"text":msg}, timeout=10); sent+=1
            except: pass
    return {"scanned":len(results),"signals":[x for x in results if x['signal']],"sent":sent,"all":results}
