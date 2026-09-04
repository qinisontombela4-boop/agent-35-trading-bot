"""
Agent 35 - V12.5 SHIFT HUNTER - TwelveData Edition
- No more Yahoo blocking
- Premium/Discount + OB/MB + FVG + BOS/CHoCH Shift in 5m
"""

import os
import time
import random
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# ========== CONFIG ==========
TD_API_KEY = os.environ.get('TWELVEDATA_API_KEY', 'demo')
TD_BASE = "https://api.twelvedata.com"

# TwelveData symbols (different format than Yahoo)
TD_MAP = {
    "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY", "EURJPY": "EUR/JPY",
    "GBPJPY": "GBP/JPY", "USDZAR": "USD/ZAR", "EURZAR": "EUR/ZAR", "GBPZAR": "GBP/ZAR",
    "ZARJPY": "ZAR/JPY", "USDCHF": "USD/CHF",
    "XAUUSD": "XAU/USD", "GOLD": "XAU/USD", "XAGUSD": "XAG/USD",
    "BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD", "SOLUSD": "SOL/USD",
    "NAS100": "NDX", "US30": "DJI", "SPX500": "SPX", "GER40": "DAX", "UK100": "FTSE", "JP225": "NIKKEI",
    "USOIL": "WTI/USD", "UKOIL": "BRENT/USD", "AAPL": "AAPL", "TSLA": "TSLA", "NVDA": "NVDA", "MSFT": "MSFT"
}

# Interval map Yahoo -> TwelveData
INTERVAL_MAP = {
    "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1day",
    "5min": "5min", "15min": "15min", "1day": "1day"
}

def get_data(symbol, period="5d", interval="5m"):
    """
    TwelveData time_series with retry
    period: 5d, 10d, 1mo, 3mo, 6mo -> converted to outputsize
    """
    td_symbol = TD_MAP.get(symbol.upper(), symbol.upper())
    td_interval = INTERVAL_MAP.get(interval, "5min")

    # period -> outputsize
    size_map = {"5d": "500", "10d": "500", "1mo": "500", "3mo": "500", "6mo": "500"}
    outputsize = size_map.get(period, "500")

    # Special for 4h: TwelveData uses 4h, but need more data
    if td_interval == "4h":
        outputsize = "300"

    for attempt in range(3):
        try:
            # Random sleep to avoid rate limit (free = 8/min)
            time.sleep(random.uniform(0.8, 1.5))

            url = f"{TD_BASE}/time_series"
            params = {
                "symbol": td_symbol,
                "interval": td_interval,
                "outputsize": outputsize,
                "apikey": TD_API_KEY,
                "format": "JSON"
            }

            r = requests.get(url, params=params, timeout=15)
            data = r.json()

            if "values" not in data:
                # Check error
                msg = data.get("message", "") or data.get("code", "")
                print(f"TD Error {symbol} {td_symbol} {td_interval}: {msg} | {data}")
                if "limit" in str(msg).lower() or "429" in str(msg):
                    print("Rate limited, waiting 60s...")
                    time.sleep(60)
                    continue
                # Try fallback: if symbol not found, try with /USD
                time.sleep(2)
                continue

            values = data["values"]
            if not values:
                return None

            # Convert to DataFrame like yfinance
            df = pd.DataFrame(values)
            # TD returns newest first, reverse
            df = df.iloc[::-1]
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
            # Rename columns
            df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
            for col in ["Open", "High", "Low", "Close"]:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df.dropna(inplace=True)

            if len(df) < 20:
                return None

            return df

        except Exception as e:
            print(f"TD get_data error {symbol} attempt {attempt+1}: {e}")
            time.sleep(2 + attempt*2)
            continue

    print(f"TD Failed to get {symbol} after 3 attempts")
    return None

def calc_atr(df, p=14):
    try:
        high = df['High']
        low = df['Low']
        close = df['Close']
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        return tr.rolling(p).mean().iloc[-1]
    except:
        return 0

# ========== LUXALGO SMC LOGIC ==========

def get_swing_structure(df, length=10):
    if df is None or len(df) < length * 3:
        return None
    try:
        highs = df['High'].rolling(window=length*2+1, center=True).max()
        lows = df['Low'].rolling(window=length*2+1, center=True).min()
        is_sh = df['High'] == highs
        is_sl = df['Low'] == lows
        sh = df[is_sh].tail(3)
        sl = df[is_sl].tail(3)
        if len(sh) < 2 or len(sl) < 2:
            return None
        return {
            "last_high": sh['High'].iloc[-1],
            "prev_high": sh['High'].iloc[-2],
            "last_low": sl['Low'].iloc[-1],
            "prev_low": sl['Low'].iloc[-2],
            "hh": sh['High'].iloc[-1] > sh['High'].iloc[-2],
            "hl": sl['Low'].iloc[-1] > sl['Low'].iloc[-2],
            "ll": sl['Low'].iloc[-1] < sl['Low'].iloc[-2],
            "lh": sh['High'].iloc[-1] < sh['High'].iloc[-2]
        }
    except:
        return None

def detect_bos_choch(df, length=10):
    st = get_swing_structure(df, length)
    if not st:
        return {"trend": "NEUTRAL", "signal": None, "is_shift": False, "last_high": 0, "last_low": 0}
    close = df['Close'].iloc[-1]
    try:
        if close > st['last_high']:
            if st['last_high'] > st['prev_high']:
                return {"trend": "BULL", "signal": "BULL_BOS", "is_shift": False, "last_high": st['last_high'], "last_low": st['last_low']}
            else:
                return {"trend": "BULL", "signal": "BULL_CHOCH", "is_shift": True, "last_high": st['last_high'], "last_low": st['last_low']}
        if close < st['last_low']:
            if st['last_low'] < st['prev_low']:
                return {"trend": "BEAR", "signal": "BEAR_BOS", "is_shift": False, "last_high": st['last_high'], "last_low": st['last_low']}
            else:
                return {"trend": "BEAR", "signal": "BEAR_CHOCH", "is_shift": True, "last_high": st['last_high'], "last_low": st['last_low']}
        if st['hh'] and st['hl']:
            return {"trend": "BULL", "signal": None, "is_shift": False, "last_high": st['last_high'], "last_low": st['last_low']}
        if st['ll'] and st['lh']:
            return {"trend": "BEAR", "signal": None, "is_shift": False, "last_high": st['last_high'], "last_low": st['last_low']}
        return {"trend": "NEUTRAL", "signal": None, "is_shift": False, "last_high": st['last_high'], "last_low": st['last_low']}
    except:
        return {"trend": "NEUTRAL", "signal": None, "is_shift": False, "last_high": 0, "last_low": 0}

def detect_ob(df):
    if df is None or len(df) < 25:
        return None
    try:
        for i in range(len(df) - 6, len(df) - 20, -1):
            c = df.iloc[i]
            if c['Close'] < c['Open']:
                future = df.iloc[i+1:i+4]
                if len(future) < 3: continue
                impulse = future['Close'].max() > c['High'] * 1.0008
                if impulse:
                    after = df.iloc[i+4:]
                    mitigated = (after['Low'].min() <= c['High']) if len(after) > 0 else False
                    ob_type = "BULL_MB_BREAKER" if mitigated else "BULL_OB"
                    return {"type": ob_type, "high": float(c['High']), "low": float(c['Low']), "mitigated": mitigated, "idx": i}
            if c['Close'] > c['Open']:
                future = df.iloc[i+1:i+4]
                if len(future) < 3: continue
                impulse = future['Close'].min() < c['Low'] * 0.9992
                if impulse:
                    after = df.iloc[i+4:]
                    mitigated = (after['High'].max() >= c['Low']) if len(after) > 0 else False
                    ob_type = "BEAR_MB_BREAKER" if mitigated else "BEAR_OB"
                    return {"type": ob_type, "high": float(c['High']), "low": float(c['Low']), "mitigated": mitigated, "idx": i}
        return None
    except:
        return None

def detect_fvg(df, min_atr_pct=0.12):
    if df is None or len(df) < 5:
        return None
    try:
        atr = calc_atr(df, 14)
        if atr == 0 or pd.isna(atr): return None
        low = df['Low'].iloc[-1]
        high = df['High'].iloc[-1]
        high_2 = df['High'].iloc[-3]
        low_2 = df['Low'].iloc[-3]
        close = df['Close'].iloc[-1]
        bull_fvg = low > high_2
        bear_fvg = high < low_2
        bull_size = (low - high_2) / atr * 100 if atr!=0 else 0
        bear_size = (low_2 - high) / atr * 100 if atr!=0 else 0
        if bull_fvg and bull_size > min_atr_pct:
            sl = low_2 - 0.0005
            risk = close - sl
            return {"type": "BULL_FVG", "entry": float(close), "sl": float(sl), "risk": float(risk), "top": float(low), "bottom": float(high_2), "size": float(bull_size)}
        if bear_fvg and bear_size > min_atr_pct:
            sl = high_2 + 0.0005
            risk = sl - close
            return {"type": "BEAR_FVG", "entry": float(close), "sl": float(sl), "risk": float(risk), "top": float(low_2), "bottom": float(high), "size": float(bear_size)}
        return None
    except:
        return None

def get_premium_discount(df_htf):
    if df_htf is None or len(df_htf) < 50:
        return "EQUILIBRIUM", 0.5, 0, 0
    try:
        hi = df_htf['High'].tail(50).max()
        lo = df_htf['Low'].tail(50).min()
        close = df_htf['Close'].iloc[-1]
        if hi == lo: return "EQUILIBRIUM", 0.5, hi, lo
        pct = (close - lo) / (hi - lo)
        eq = (hi + lo) / 2
        if pct >= 0.7: return "PREMIUM", pct, eq, hi
        elif pct <= 0.3: return "DISCOUNT", pct, eq, lo
        else: return "EQUILIBRIUM", pct, eq, (hi+lo)/2
    except:
        return "EQUILIBRIUM", 0.5, 0, 0

def get_rsi(df, period=14):
    try:
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = -delta.where(delta < 0, 0).rolling(period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
    except:
        return 50.0

# ========== MAIN V12.5 ==========

def full_multi_tf_analysis(symbol, use_news_filter=True, rr_target=2.5):
    try:
        # Load MTF with TwelveData - add delays to respect 8/min limit
        df_5m = get_data(symbol, period="5d", interval="5m")
        if df_5m is None:
            return {"signal": False, "symbol": symbol, "reason": "No 5m data from TwelveData", "score": 0}

        df_15m = get_data(symbol, period="10d", interval="15m")
        df_1h = get_data(symbol, period="1mo", interval="1h")
        df_4h = get_data(symbol, period="3mo", interval="4h")
        df_daily = get_data(symbol, period="6mo", interval="1d")

        zone_daily, pct_daily, eq_daily, level_daily = get_premium_discount(df_daily if df_daily is not None else df_4h)
        zone_4h, pct_4h, eq_4h, level_4h = get_premium_discount(df_4h if df_4h is not None else df_1h)

        struct_4h = detect_bos_choch(df_4h, 10) if df_4h is not None else {"trend": "NEUTRAL", "signal": None, "is_shift": False}
        struct_1h = detect_bos_choch(df_1h, 10) if df_1h is not None else {"trend": "NEUTRAL", "signal": None, "is_shift": False}
        struct_15m = detect_bos_choch(df_15m, 10) if df_15m is not None else {"trend": "NEUTRAL", "signal": None, "is_shift": False}
        struct_5m = detect_bos_choch(df_5m, 10)

        fvg_5m = detect_fvg(df_5m, 0.12)
        fvg_15m = detect_fvg(df_15m, 0.12) if df_15m is not None else None
        ob_5m = detect_ob(df_5m)
        ob_15m = detect_ob(df_15m) if df_15m is not None else None
        rsi_5m = get_rsi(df_5m)

        htf_bull = struct_4h['trend'] == "BULL" or struct_1h['trend'] == "BULL"
        htf_bear = struct_4h['trend'] == "BEAR" or struct_1h['trend'] == "BEAR"

        confluence = []
        score = 0
        direction = None
        entry = sl = tp = 0

        confluence.append(f"HTF: Daily {zone_daily} {pct_daily*100:.0f}% | 4H {zone_4h} {pct_4h*100:.0f}%")

        # SHIFT DETECTION
        if struct_5m['is_shift'] and struct_5m['signal']:
            if "BULL_CHOCH" in struct_5m['signal']:
                if zone_daily == "DISCOUNT" or zone_4h == "DISCOUNT":
                    direction = "BUY"
                    confluence.append(f"🔥 5M SHIFT: {struct_5m['signal']} in DISCOUNT - EARLY BULL REVERSAL")
                    score += 4
                else:
                    direction = "BUY"
                    confluence.append(f"⚡ 5M {struct_5m['signal']} - Potential Shift")
                    score += 2
            elif "BEAR_CHOCH" in struct_5m['signal']:
                if zone_daily == "PREMIUM" or zone_4h == "PREMIUM":
                    direction = "SELL"
                    confluence.append(f"🔥 5M SHIFT: {struct_5m['signal']} in PREMIUM - EARLY BEAR REVERSAL")
                    score += 4
                else:
                    direction = "SELL"
                    confluence.append(f"⚡ 5M {struct_5m['signal']} - Potential Shift")
                    score += 2

        if not direction:
            if struct_5m['signal'] and "BULL_BOS" in struct_5m['signal']:
                if htf_bull or zone_daily == "DISCOUNT":
                    direction = "BUY"
                    confluence.append(f"✅ 5M {struct_5m['signal']} + HTF {struct_4h['trend']}/{struct_1h['trend']}")
                    score += 2
            elif struct_5m['signal'] and "BEAR_BOS" in struct_5m['signal']:
                if htf_bear or zone_daily == "PREMIUM":
                    direction = "SELL"
                    confluence.append(f"✅ 5M {struct_5m['signal']} + HTF {struct_4h['trend']}/{struct_1h['trend']}")
                    score += 2

        if not direction and fvg_5m:
            direction = "BUY" if "BULL" in fvg_5m['type'] else "SELL"
            confluence.append(f"FVG direction {fvg_5m['type']}")

        if not direction:
            return {"signal": False, "symbol": symbol, "reason": f"No direction - HTF {zone_daily} {struct_4h['trend']} | 5M {struct_5m['signal']}", "score": score}

        fvg_entry = None
        if fvg_5m and ((direction == "BUY" and "BULL" in fvg_5m['type']) or (direction == "SELL" and "BEAR" in fvg_5m['type'])):
            fvg_entry = fvg_5m
            confluence.append(f"✅ 5M {fvg_5m['type']} {fvg_5m['size']:.2f}% ATR")
            score += 3
        elif fvg_15m and ((direction == "BUY" and "BULL" in fvg_15m['type']) or (direction == "SELL" and "BEAR" in fvg_15m['type'])):
            fvg_entry = fvg_15m
            confluence.append(f"✅ 15M {fvg_15m['type']} {fvg_15m['size']:.2f}% ATR")
            score += 2

        if not fvg_entry:
            return {"signal": False, "symbol": symbol, "reason": f"No {direction} FVG in 5m/15m", "score": score}

        entry = fvg_entry['entry']
        sl = fvg_entry['sl']
        risk = abs(entry - sl)
        if risk == 0:
            return {"signal": False, "symbol": symbol, "reason": "Zero risk", "score": score}
        tp = entry + risk * rr_target if direction == "BUY" else entry - risk * rr_target

        if ob_5m:
            if direction == "BUY" and "BULL" in ob_5m['type']:
                tag = "MB Breaker 🔥" if ob_5m['mitigated'] else "Order Block"
                confluence.append(f"✅ 5M {tag} Low {ob_5m['low']:.5f}")
                score += 3 if ob_5m['mitigated'] else 2
            elif direction == "SELL" and "BEAR" in ob_5m['type']:
                tag = "MB Breaker 🔥" if ob_5m['mitigated'] else "Order Block"
                confluence.append(f"✅ 5M {tag} High {ob_5m['high']:.5f}")
                score += 3 if ob_5m['mitigated'] else 2

        if ob_15m and direction in ob_15m['type']:
            confluence.append(f"✅ 15M {ob_15m['type']} confirms")
            score += 1

        if struct_15m['signal'] and direction in struct_15m['signal']:
            confluence.append(f"✅ 15M {struct_15m['signal']} confirms")
            score += 1
        if struct_1h['trend'] == ("BULL" if direction == "BUY" else "BEAR"):
            confluence.append(f"✅ 1H Trend {struct_1h['trend']}")
            score += 1
        if struct_4h['trend'] == ("BULL" if direction == "BUY" else "BEAR"):
            confluence.append(f"✅ 4H Trend {struct_4h['trend']}")
            score += 1

        if direction == "BUY" and zone_daily == "DISCOUNT":
            confluence.append(f"✅ Daily DISCOUNT {pct_daily*100:.0f}%")
            score += 2
        elif direction == "SELL" and zone_daily == "PREMIUM":
            confluence.append(f"✅ Daily PREMIUM {pct_daily*100:.0f}%")
            score += 2
        elif direction == "BUY" and zone_daily == "PREMIUM":
            confluence.append(f"❌ BUY in PREMIUM {pct_daily*100:.0f}% - penalized")
            score -= 2
        elif direction == "SELL" and zone_daily == "DISCOUNT":
            confluence.append(f"❌ SELL in DISCOUNT {pct_daily*100:.0f}% - penalized")
            score -= 2

        if 30 < rsi_5m < 70:
            confluence.append(f"✅ RSI 5M {rsi_5m:.1f}")
            score += 1

        if score >= 9: quality = "SNIPER 🔥🔥🔥 SHIFT"
        elif score >= 7: quality = "PREMIUM 🔥 SHIFT"
        elif score >= 5: quality = "STANDARD"
        else: quality = "WEAK"

        if score >= 5:
            bias_text = f"Daily {zone_daily} {pct_daily*100:.0f}% | 4H {zone_4h} {struct_4h['trend']} | 5M {struct_5m['signal']} {'SHIFT' if struct_5m['is_shift'] else ''}"
            return {
                "signal": True, "symbol": symbol, "direction": direction,
                "entry": round(float(entry), 5), "sl": round(float(sl), 5), "tp": round(float(tp), 5),
                "score": int(score), "quality": quality, "bias": bias_text,
                "confluence": confluence,
                "reason": f"HTF {zone_daily} + 5M {struct_5m['signal']} + {fvg_entry['type']} + {ob_5m['type'] if ob_5m else 'No OB'} | Score {score}/12",
                "news_warning": ""
            }
        else:
            return {"signal": False, "symbol": symbol, "reason": f"Weak {score}/12", "score": score}

    except Exception as e:
        import traceback; traceback.print_exc()
        return {"signal": False, "symbol": symbol, "reason": f"Error: {e}", "score": 0}

def analyze_symbol(symbol, use_news_filter=True):
    return full_multi_tf_analysis(symbol, use_news_filter)
