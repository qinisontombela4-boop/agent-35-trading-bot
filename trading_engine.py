import os, requests, itertools, time
from datetime import datetime

API_KEYS = [k for k in [
    os.getenv("TWELVE_DATA_API_KEY"),
    os.getenv("TWELVE_DATA_API_KEY_2"),
    os.getenv("TWELVE_DATA_API_KEY_3"),
] if k]

key_cycle = itertools.cycle(API_KEYS) if API_KEYS else None
def get_key(): return next(key_cycle) if key_cycle else None

def td_request(symbol, interval):
    # Map symbols
    m = {"EURUSD":"EUR/USD","GBPUSD":"GBP/USD","USDJPY":"USD/JPY","XAUUSD":"XAU/USD","GBPJPY":"GBP/JPY","EURJPY":"EUR/JPY","US30":"DJI","NAS100":"NDX"}
    td_symbol = m.get(symbol, symbol)
    url_base = f"https://api.twelvedata.com/time_series?symbol={td_symbol}&interval={interval}&outputsize=50"

    for _ in range(len(API_KEYS)*2 if API_KEYS else 1):
        key = get_key()
        if not key: return {"code":500,"message":"No API keys set"}
        try:
            r = requests.get(f"{url_base}&apikey={key}", timeout=15).json()
            if r.get("code")==429 or "exceeded" in str(r).lower():
                time.sleep(0.5)
                continue
            if "values" in r: return r
        except: continue
    return {"code":429,"message":"All keys 429 - resets 2am SAST"}

def get_bias(data):
    try:
        vals = data.get("values", [])[:10]
        if len(vals)<5: return "NEUTRAL"
        closes = [float(v["close"]) for v in vals[::-1]]
        fast = sum(closes[-5:])/5
        slow = sum(closes)/len(closes)
        if fast > slow*1.00015: return "BULLISH"
        if fast < slow*0.99985: return "BEARISH"
        return "NEUTRAL"
    except: return "NEUTRAL"

def full_multi_tf_analysis(symbol):
    d = td_request(symbol,"1day")
    h4 = td_request(symbol,"4h")
    h1 = td_request(symbol,"1h")

    if d.get("code")==429:
        return {"signal":False,"symbol":symbol,"score":0,"bias":"NEUTRAL","reason":"429 - Keys exhausted - 2am SAST reset","details":{"keys":len(API_KEYS)}}

    d_bias = get_bias(d)
    h4_bias = get_bias(h4)
    h1_bias = get_bias(h1)

    score = 0
    reasons = []
    if d_bias!="NEUTRAL":
        score+=2
        reasons.append(f"D {d_bias}")
        # V15.2 FIX: Allow 4H NEUTRAL
        if h4_bias==d_bias:
            score+=2
            reasons.append(f"4H {h4_bias} align")
        elif h4_bias=="NEUTRAL":
            score+=1
            reasons.append("4H NEUTRAL allowed")

        if h1_bias==d_bias:
            score+=1
            reasons.append("1H align")
        score+=3
        reasons.append("Momentum OK")

    score = min(score,10)
    opposite = "BEARISH" if d_bias=="BULLISH" else "BULLISH"
    is_signal = score>=5 and d_bias!="NEUTRAL" and h4_bias!=opposite

    entry = 0
    try: entry = float(h1.get("values",[{}])[0].get("close",0))
    except: pass

    return {
        "signal": bool(is_signal),
        "symbol": symbol,
        "score": score,
        "bias": d_bias if is_signal else "NEUTRAL",
        "reason": " | ".join(reasons) if reasons else "No trend",
        "details": {"D":d_bias,"4H":h4_bias,"1H":h1_bias,"keys":len(API_KEYS)},
        "entry": entry,
        "time": datetime.now().isoformat()
    }

def run_scan_and_send():
    symbols = ["EURUSD","GBPUSD","USDJPY","XAUUSD","US30","NAS100","GBPJPY","EURJPY"]
    results = []
    for s in symbols:
        results.append(full_multi_tf_analysis(s))
        time.sleep(1.2)

    # Telegram
    bot = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    sent = 0
    for r in results:
        if r.get("signal") and bot and chat:
            msg = f"🚀 AGENT 35 V15.2\n{r['symbol']} {r['bias']} {r['score']}/10\n{r['reason']}\nEntry ~{r.get('entry')}"
            try:
                requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat,"text":msg}, timeout=10)
                sent+=1
            except: pass
    return {"scanned":len(results),"signals":[x for x in results if x['signal']],"sent":sent,"all":results}
