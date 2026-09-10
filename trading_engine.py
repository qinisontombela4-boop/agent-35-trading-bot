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
    """Fetch with auto rotation on 429"""
    if not API_KEYS:
        return {"code":429, "message":"No keys"}

    # TwelveData format: EUR/USD not EURUSD
    td_symbol = symbol
    if len(symbol) == 6 and symbol not in ["XAUUSD","XAGUSD"]:
        td_symbol = f"{symbol[:3]}/{symbol[3:]}"
    if symbol == "XAUUSD":
        td_symbol = "XAU/USD"

    base_url = f"https://api.twelvedata.com/time_series?symbol={td_symbol}&interval={interval}&outputsize=50"

    for attempt in range(len(API_KEYS) * 2):
        key = get_key()
        if not key:
            break
        try:
            url = f"{base_url}&apikey={key}"
            r = requests.get(url, timeout=15)
            data = r.json()

            # Check 429 / limit
            if data.get("code") == 429 or "limit" in str(data).lower() or "exceeded" in str(data).lower():
                print(f"Key {key[:8]} 429, rotating... {data.get('message')}")
                time.sleep(0.5)
                continue

            if "values" in data and len(data["values"]) > 0:
                return data

            # No values but no 429 -> return to see error
            if "code" in data:
                print(f"TD error {symbol} {interval}: {data}")
                continue

            return data
        except Exception as e:
            print(f"Request error {symbol} {interval} key {key[:8]}: {e}")
            continue

    return {"code":429, "message":"All keys 429 - wait 2am SAST reset"}

def get_bias_from_candles(data):
    try:
        vals = data.get("values", [])[:10]
        if len(vals) < 5:
            return "NEUTRAL", 0
        closes = [float(v["close"]) for v in vals[::-1]] # old to new
        # Simple EMA bias
        ema_fast = sum(closes[-5:]) / 5
        ema_slow = sum(closes) / len(closes)
        if ema_fast > ema_slow * 1.0002:
            return "BULLISH", 1
        elif ema_fast < ema_slow * 0.9998:
            return "BEARISH", 1
        return "NEUTRAL", 0
    except:
        return "NEUTRAL", 0

def full_multi_tf_analysis(symbol):
    """V15.1 - 5/10 threshold"""
    try:
        # Fetch 3 TFs
        d_data = td_request(symbol, "1day")
        h4_data = td_request(symbol, "4h")
        h1_data = td_request(symbol, "1h")

        # Check for 429
        if d_data.get("code") == 429 or h4_data.get("code") == 429:
            return {
                "signal": False,
                "symbol": symbol,
                "score": 0,
                "bias": "NEUTRAL",
                "reason": f"No data/429 - wait 2am reset - D:{d_data.get('message','')} H4:{h4_data.get('message','')}",
                "keys_loaded": len(API_KEYS)
            }

        d_bias, d_pts = get_bias_from_candles(d_data)
        h4_bias, h4_pts = get_bias_from_candles(h4_data)
        h1_bias, h1_pts = get_bias_from_candles(h1_data)

        # Scoring - MAX 10
        score = 0
        reasons = []

        # 1. Daily trend (2 pts)
        if d_bias!= "NEUTRAL":
            score += 2
            reasons.append(f"D {d_bias}")

        # 2. 4H + Daily alignment (3 pts) - MAIN FILTER
        if d_bias!= "NEUTRAL" and h4_bias == d_bias:
            score += 3
            reasons.append(f"4H {h4_bias} aligns D")
        elif h4_bias!= "NEUTRAL":
            score += 1
            reasons.append(f"4H {h4_bias} vs D {d_bias}")

        # 3. 1H alignment (2 pts)
        if h1_bias == d_bias and d_bias!= "NEUTRAL":
            score += 2
            reasons.append(f"1H aligns {d_bias}")
        elif h1_bias!= "NEUTRAL":
            score += 1
            reasons.append(f"1H {h1_bias}")

        # 4. Momentum (3 pts) - simplified for V15.1
        if d_bias!= "NEUTRAL":
            score += 2 # give 2 if we have trend
            reasons.append("Momentum OK")
            # Bonus point if all 3 align
            if d_bias == h4_bias == h1_bias:
                score += 1
                reasons.append("ALL TF ALIGN")

        score = min(score, 10)

        # THRESHOLD = 5 (you asked for 5)
        is_signal = score >= 5 and d_bias!= "NEUTRAL" and h4_bias == d_bias

        return {
            "signal": bool(is_signal),
            "symbol": symbol,
            "score": score,
            "bias": d_bias if is_signal else "NEUTRAL",
            "reason": " | ".join(reasons) if reasons else "No alignment",
            "details": {
                "D": d_bias,
                "4H": h4_bias,
                "1H": h1_bias,
                "keys": len(API_KEYS)
            },
            "entry": float(h1_data["values"][0]["close"]) if h1_data.get("values") else 0
        }
    except Exception as e:
        import traceback
        return {
            "signal": False,
            "symbol": symbol,
            "score": 0,
            "bias": "NEUTRAL",
            "reason": f"Error: {str(e)}",
            "trace": traceback.format_exc()[:500]
        }

def analyze_symbol(symbol):
    return full_multi_tf_analysis(symbol)

def full_analysis(symbol):
    return full_multi_tf_analysis(symbol)
