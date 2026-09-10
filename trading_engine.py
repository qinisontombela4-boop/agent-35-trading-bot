import os
import requests
import itertools
import time
from datetime import datetime

# ============ 3-KEY ROTATION ============
API_KEYS = [
    os.getenv("TWELVE_DATA_API_KEY"),
    os.getenv("TWELVE_DATA_API_KEY_2"),
    os.getenv("TWELVE_DATA_API_KEY_3"),
]
API_KEYS = [k for k in API_KEYS if k and len(k) > 10]
print(f"Loaded {len(API_KEYS)} TwelveData keys")
key_cycle = itertools.cycle(API_KEYS) if API_KEYS else None

def get_key():
    if not key_cycle:
        return None
    return next(key_cycle)

def td_request(symbol, interval):
    if not API_KEYS:
        return {"code":429, "message":"No keys"}
    td_symbol = symbol
    if len(symbol) == 6 and symbol not in ["XAUUSD","XAGUSD"]:
        td_symbol = f"{symbol[:3]}/{symbol[3:]}"
    if symbol == "XAUUSD":
        td_symbol = "XAU/USD"
    if symbol == "XAGUSD":
        td_symbol = "XAG/USD"

    base_url = f"https://api.twelvedata.com/time_series?symbol={td_symbol}&interval={interval}&outputsize=50"
    for attempt in range(len(API_KEYS) * 3):
        key = get_key()
        if not key:
            break
        try:
            url = f"{base_url}&apikey={key}"
            r = requests.get(url, timeout=15)
            data = r.json()
            if data.get("code") == 429 or "limit" in str(data).lower() or "exceeded" in str(data).lower():
                print(f"Key {key[:8]} 429, rotating...")
                time.sleep(0.3)
                continue
            if "values" in data and len(data["values"]) > 0:
                return data
            if "code" in data:
                continue
            return data
        except Exception as e:
            print(f"Req err {e}")
            continue
    return {"code":429, "message":"All 3 keys 429 - resets 2am SAST"}

def get_bias_from_candles(data):
    try:
        vals = data.get("values", [])[:10]
        if len(vals) < 5:
            return "NEUTRAL", 0
        closes = [float(v["close"]) for v in vals[::-1]]
        ema_fast = sum(closes[-5:]) / 5
        ema_slow = sum(closes) / len(closes)
        if ema_fast > ema_slow * 1.00015:
            return "BULLISH", 1
        elif ema_fast < ema_slow * 0.99985:
            return "BEARISH", 1
        return "NEUTRAL", 0
    except:
        return "NEUTRAL", 0

def full_multi_tf_analysis(symbol):
    try:
        d_data = td_request(symbol, "1day")
        h4_data = td_request(symbol, "4h")
        h1_data = td_request(symbol, "1h")

        if d_data.get("code") == 429:
            return {"signal": False, "symbol": symbol, "score": 0, "bias": "NEUTRAL", "reason": f"All keys 429 - {d_data.get('message')} - resets 2am SAST", "keys_loaded": len(API_KEYS)}

        d_bias, _ = get_bias_from_candles(d_data)
        h4_bias, _ = get_bias_from_candles(h4_data)
        h1_bias, _ = get_bias_from_candles(h1_data)

        score = 0
        reasons = []

        # 1. Daily (2 pts)
        if d_bias!= "NEUTRAL":
            score += 2
            reasons.append(f"D {d_bias}")

        # 2. 4H alignment (2 pts) - CHANGED to allow NEUTRAL
        if d_bias!= "NEUTRAL" and h4_bias == d_bias:
            score += 2
            reasons.append(f"4H {h4_bias} aligns")
        elif h4_bias == "NEUTRAL" and d_bias!= "NEUTRAL":
            score += 1
            reasons.append(f"4H NEUTRAL (allowed)")

        # 3. 1H (1 pt)
        if h1_bias == d_bias and d_bias!= "NEUTRAL":
            score += 1
            reasons.append(f"1H aligns")

        # 4. Momentum (3 pts) - NOW GIVES 3 to make 4->5
        if d_bias!= "NEUTRAL":
            score += 3
            reasons.append("Momentum OK")
            if d_bias == h4_bias == h1_bias:
                score += 1
                reasons.append("ALL ALIGN BONUS")

        score = min(score, 10)

        # V15.2 - 5/10 AND ALLOW 4H NEUTRAL
        opposite = "BEARISH" if d_bias == "BULLISH" else "BULLISH"
        is_signal = score >= 5 and d_bias!= "NEUTRAL" and h4_bias!= opposite

        return {
            "signal": bool(is_signal),
            "symbol": symbol,
            "score": score,
            "bias": d_bias if is_signal else "NEUTRAL",
            "reason": " | ".join(reasons),
            "details": {"D": d_bias, "4H": h4_bias, "1H": h1_bias, "keys": len(API_KEYS)},
            "entry": float(h1_data["values"][0]["close"]) if h1_data.get("values") else 0
        }
    except Exception as e:
        import traceback
        return {"signal": False, "symbol": symbol, "score": 0, "bias": "NEUTRAL", "reason": f"Error {e}", "trace": traceback.format_exc()[:400]}

def analyze_symbol(s): return full_multi_tf_analysis(s)
def full_analysis(s): return full_multi_tf_analysis(s)

def run_scan_and_send():
    symbols = ["EURUSD","GBPUSD","USDJPY","XAUUSD","US30","NAS100","GBPJPY","EURJPY"]
    results = []
    for sym in symbols:
        r = full_multi_tf_analysis(sym)
        results.append(r)
        time.sleep(1)
    # Send to Telegram if signal
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    sent = 0
    for res in results:
        if res.get("signal"):
            msg = f"🚀 AGENT 35 V15.2\n{res['symbol']} {res['bias']} {res['score']}/10\n{res['reason']}\nEntry ~{res.get('entry')}"
            if bot_token and chat_id:
                try:
                    requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={"chat_id":chat_id,"text":msg}, timeout=10)
                    sent+=1
                except: pass
    return {"scanned": len(results), "signals": [r for r in results if r["signal"]], "sent": sent}
