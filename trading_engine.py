import yfinance as yf
import pandas as pd
import numpy as np
import time

MAP = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X",
    "USDZAR": "USDZAR=X",
    "EURZAR": "EURZAR=X",
    "GBPZAR": "GBPZAR=X",
    "ZARJPY": "ZARJPY=X",
    "USDCHF": "USDCHF=X",
    "XAUUSD": "GC=F",
    "GOLD": "GC=F",
    "XAGUSD": "SI=F",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "SOLUSD": "SOL-USD",
    "NAS100": "^NDX",
    "US30": "^DJI",
    "SPX500": "^GSPC",
    "GER40": "^GDAXI",
    "UK100": "^FTSE",
    "JP225": "^N225",
    "USOIL": "CL=F",
    "UKOIL": "BZ=F",
    "AAPL": "AAPL",
    "TSLA": "TSLA",
    "NVDA": "NVDA",
    "MSFT": "MSFT"
}

# Cache to stop YFRateLimitError
PRICE_CACHE = {}
CACHE_TTL = 300 # 5 minutes cache

def round_by_symbol(symbol, price):
    try:
        s = symbol.upper()
        if "JPY" in s: return round(float(price), 3)
        if "ZAR" in s: return round(float(price), 3)
        if "CHF" in s: return round(float(price), 5)
        if "XAU" in s or "GOLD" in s: return round(float(price), 2)
        if "XAG" in s: return round(float(price), 3)
        if "BTC" in s: return round(float(price), 2)
        if "ETH" in s or "SOL" in s: return round(float(price), 2)
        if any(x in s for x in ["NAS100","US30","SPX500","GER40","UK100","JP225"]):
            return round(float(price), 1)
        if "OIL" in s: return round(float(price), 2)
        return round(float(price), 5)
    except:
        return round(float(price), 5)

def get_data(symbol, period="60d", interval="15m"):
    cache_key = f"{symbol}_{interval}"
    now = time.time()

    # Use cache if exists and fresh
    if cache_key in PRICE_CACHE and now - PRICE_CACHE[cache_key]['time'] < CACHE_TTL:
        return PRICE_CACHE[cache_key]['data'].copy()

    try:
        yfs = MAP.get(symbol.upper(), symbol.upper()+"=X")
        # CRITICAL FIX: Delay stops Yahoo rate limit
        time.sleep(1.2)

        df = yf.download(yfs, period=period, interval=interval, progress=False, auto_adjust=True, threads=False)

        if df.empty:
            print(f"Empty {symbol} {interval}")
            # Return stale cache if rate limited
            if cache_key in PRICE_CACHE:
                print(f"Using stale cache for {symbol}")
                return PRICE_CACHE[cache_key]['data'].copy()
            return None

        try:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        except: pass

        df = df.dropna()
        if len(df) < 50:
            print(f"Too short {symbol} {len(df)}")
            if cache_key in PRICE_CACHE:
                return PRICE_CACHE[cache_key]['data'].copy()
            return None

        # Save to cache
        PRICE_CACHE[cache_key] = {'time': now, 'data': df.copy()}
        print(f"Downloaded {symbol} {interval} - {len(df)} candles")
        return df

    except Exception as e:
        print(f"get_data err {symbol} {interval} {e}")
        # If rate limited, use stale cache
        if "Rate" in str(e) or "Too Many" in str(e):
            if cache_key in PRICE_CACHE:
                print(f"RATE LIMITED - using stale cache for {symbol}")
                return PRICE_CACHE[cache_key]['data'].copy()
        return None

def add_indicators(df):
    try:
        df['EMA20'] = df['Close'].ewm(span=20).mean()
        df['EMA50'] = df['Close'].ewm(span=50).mean()
        df['EMA200'] = df['Close'].ewm(span=200).mean()
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(14).mean()
        return df
    except:
        return df

def detect_order_block(df, direction="BUY"):
    try:
        last_10 = df.tail(10)
        if direction == "BUY":
            for i in range(len(last_10)-3, 0, -1):
                if last_10['Close'].iloc[i] < last_10['Open'].iloc[i]:
                    if last_10['Close'].iloc[i+1] > last_10['Open'].iloc[i+1]:
                        return True, f"Bu-OB at {last_10['Low'].iloc[i]:.5f}"
        else:
            for i in range(len(last_10)-3, 0, -1):
                if last_10['Close'].iloc[i] > last_10['Open'].iloc[i]:
                    if last_10['Close'].iloc[i+1] < last_10['Open'].iloc[i+1]:
                        return True, f"Be-OB at {last_10['High'].iloc[i]:.5f}"
        return False, ""
    except:
        return False, ""

def detect_market_structure(df):
    try:
        highs = df['High'].tail(20)
        lows = df['Low'].tail(20)
        hh = highs.iloc[-1] > highs.iloc[-5] and lows.iloc[-1] > lows.iloc[-5]
        ll = highs.iloc[-1] < highs.iloc[-5] and lows.iloc[-1] < lows.iloc[-5]
        if hh: return "Bullish BOS", "Bullish"
        elif ll: return "Bearish BOS", "Bearish"
        else: return "Ranging", "Neutral"
    except:
        return "Unknown", "Neutral"

def check_confluence(df, direction):
    score = 0
    confluence = []
    try:
        last = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. EMA Stack
        if direction == "BUY" and last['Close'] > last['EMA20'] and last['EMA20'] > last['EMA50']:
            score += 1; confluence.append("EMA Bullish Stack")
        elif direction == "SELL" and last['Close'] < last['EMA20'] and last['EMA20'] < last['EMA50']:
            score += 1; confluence.append("EMA Bearish Stack")

        # 2. EMA200 Trend
        if direction == "BUY" and last['Close'] > last['EMA200']:
            score += 1; confluence.append("Above EMA200")
        elif direction == "SELL" and last['Close'] < last['EMA200']:
            score += 1; confluence.append("Below EMA200")

        # 3. RSI
        if direction == "BUY" and 40 < last['RSI'] < 70:
            score += 1; confluence.append(f"RSI {last['RSI']:.1f} Bullish")
        elif direction == "SELL" and 30 < last['RSI'] < 60:
            score += 1; confluence.append(f"RSI {last['RSI']:.1f} Bearish")

        # 4 & 5. Order Block + Retest
        ob_hit, ob_text = detect_order_block(df, direction)
        if ob_hit:
            score += 2; confluence.append(ob_text); confluence.append("OB RETEST")

        # 6. Market Structure
        ms_text, ms_bias = detect_market_structure(df)
        if (direction == "BUY" and "Bullish" in ms_bias) or (direction == "SELL" and "Bearish" in ms_bias):
            score += 1; confluence.append(ms_text)

        # 7. Momentum
        if abs(last['Close'] - prev['Close']) > last['ATR'] * 0.5:
            score += 1; confluence.append("MB Momentum")

        # 8. ATR Expansion
        if last['ATR'] > df['ATR'].tail(20).mean():
            score += 1; confluence.append("ATR Expansion")

    except Exception as e:
        print(f"confluence err {e}")
    return score, confluence

def full_multi_tf_analysis(symbol):
    try:
        symbol = symbol.upper().strip()

        # ONLY 1 download per symbol now - no second 1h download
        df_15m = get_data(symbol, period="60d", interval="15m")
        if df_15m is None:
            return {"signal": False, "symbol": symbol, "reason": "No data - rate limited, will use cache next run", "score": 0}

        df_15m = add_indicators(df_15m)
        last = df_15m.iloc[-1]

        # FIX: HTF bias from resampled 15m data - NO extra Yahoo call
        bias = "Neutral HTF"
        try:
            df_1h = df_15m.resample('1h').agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
            if len(df_1h) > 50:
                df_1h['EMA50'] = df_1h['Close'].ewm(span=50).mean()
                if df_1h.iloc[-1]['Close'] > df_1h.iloc[-1]['EMA50']:
                    bias = "Bullish HTF"
                else:
                    bias = "Bearish HTF"
        except:
            pass

        buy_score, buy_conf = check_confluence(df_15m, "BUY")
        sell_score, sell_conf = check_confluence(df_15m, "SELL")

        direction = "BUY" if buy_score >= sell_score else "SELL"
        score = max(buy_score, sell_score)
        confluence = buy_conf if direction == "BUY" else sell_conf

        if score < 4:
            return {"signal": False, "symbol": symbol, "reason": f"Low score {score}/8", "score": score, "bias": bias, "confluence": confluence}

        atr = last['ATR']
        if pd.isna(atr) or atr == 0:
            atr = (last['High'] - last['Low']) * 0.5
            if atr == 0: atr = last['Close'] * 0.001

        entry = float(last['Close'])
        if direction == "BUY":
            sl = entry - (atr * 1.5)
            tp = entry + (atr * 3.0)
        else:
            sl = entry + (atr * 1.5)
            tp = entry - (atr * 3.0)

        has_ob = any("OB" in c for c in confluence)
        has_mb = any("MB" in c for c in confluence)

        if score >= 7 and has_ob and has_mb:
            quality = "SNIPER Bu-OB/Be-OB+MB"
        elif score >= 6 and has_ob:
            quality = "PREMIUM Be-OB"
        elif score >= 6:
            quality = "PREMIUM"
        else:
            quality = "STANDARD"

        entry = round_by_symbol(symbol, entry)
        sl = round_by_symbol(symbol, sl)
        tp = round_by_symbol(symbol, tp)

        if entry == sl:
            if direction == "BUY": sl = round_by_symbol(symbol, sl - atr)
            else: sl = round_by_symbol(symbol, sl + atr)

        return {
            "signal": True,
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "score": score,
            "quality": quality,
            "bias": f"{bias} | OB:{has_ob} MB:{has_mb}",
            "confluence": confluence,
            "reason": f"{quality} {score}/8 - {bias}",
            "news_warning": False
        }
    except Exception as e:
        import traceback
        print(f"full_multi_tf err {symbol} {e} {traceback.format_exc()}")
        return {"signal": False, "symbol": symbol, "reason": f"Error {e}", "score": 0}
