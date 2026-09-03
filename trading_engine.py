import yfinance as yf
import pandas as pd
import numpy as np

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

# V9.0 DECIMALS FIX - Stops 16.02281 bug
def round_by_symbol(symbol, price):
    try:
        s = symbol.upper()
        if "JPY" in s:
            return round(float(price), 3)
        if "ZAR" in s:
            return round(float(price), 3) # USDZAR 16.038 not 16.02281
        if "XAU" in s or "GOLD" in s:
            return round(float(price), 2)
        if "XAG" in s:
            return round(float(price), 3)
        if "BTC" in s:
            return round(float(price), 2)
        if "ETH" in s or "SOL" in s:
            return round(float(price), 2)
        if "NAS100" in s or "US30" in s or "SPX500" in s or "GER40" in s or "UK100" in s or "JP225" in s:
            return round(float(price), 1)
        if "OIL" in s:
            return round(float(price), 2)
        return round(float(price), 5)
    except:
        return round(float(price), 5)

def get_data(symbol, period="60d", interval="15m"):
    try:
        yfs = MAP.get(symbol.upper(), symbol.upper()+"=X")
        df = yf.download(yfs, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            return None
        # Handle multi-index columns from yfinance
        try:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        except:
            pass
        df = df.dropna()
        if len(df) < 50:
            return None
        return df
    except Exception as e:
        print(f"get_data err {symbol} {e}")
        return None

def add_indicators(df):
    try:
        df['EMA20'] = df['Close'].ewm(span=20).mean()
        df['EMA50'] = df['Close'].ewm(span=50).mean()
        df['EMA200'] = df['Close'].ewm(span=200).mean()
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        # ATR for SL/TP
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
        # Simple OB detection: last bearish before bullish impulse and vice versa
        last_5 = df.tail(10)
        if direction == "BUY":
            # Look for bullish engulfing or Bu-OB
            for i in range(len(last_5)-3, 0, -1):
                if last_5['Close'].iloc[i] < last_5['Open'].iloc[i]: # bearish
                    if last_5['Close'].iloc[i+1] > last_5['Open'].iloc[i+1] and last_5['Close'].iloc[i+1] > last_5['Open'].iloc[i]:
                        return True, f"Bu-OB at {last_5['Low'].iloc[i]:.5f}"
        else:
            for i in range(len(last_5)-3, 0, -1):
                if last_5['Close'].iloc[i] > last_5['Open'].iloc[i]: # bullish
                    if last_5['Close'].iloc[i+1] < last_5['Open'].iloc[i+1] and last_5['Close'].iloc[i+1] < last_5['Open'].iloc[i]:
                        return True, f"Be-OB at {last_5['High'].iloc[i]:.5f}"
        return False, ""
    except:
        return False, ""

def detect_market_structure(df):
    try:
        highs = df['High'].tail(20)
        lows = df['Low'].tail(20)
        # Higher highs and higher lows = bullish
        hh = highs.iloc[-1] > highs.iloc[-5] and lows.iloc[-1] > lows.iloc[-5]
        ll = highs.iloc[-1] < highs.iloc[-5] and lows.iloc[-1] < lows.iloc[-5]
        if hh:
            return "Bullish BOS", "Bullish"
        elif ll:
            return "Bearish BOS", "Bearish"
        else:
            return "Ranging", "Neutral"
    except:
        return "Unknown", "Neutral"

def check_confluence(df, direction):
    score = 0
    confluence = []

    try:
        last = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. EMA Trend
        if direction == "BUY" and last['Close'] > last['EMA20'] and last['EMA20'] > last['EMA50']:
            score += 1
            confluence.append("EMA Bullish Stack")
        elif direction == "SELL" and last['Close'] < last['EMA20'] and last['EMA20'] < last['EMA50']:
            score += 1
            confluence.append("EMA Bearish Stack")

        # 2. EMA 200 Trend
        if direction == "BUY" and last['Close'] > last['EMA200']:
            score += 1
            confluence.append("Above EMA200")
        elif direction == "SELL" and last['Close'] < last['EMA200']:
            score += 1
            confluence.append("Below EMA200")

        # 3. RSI
        if direction == "BUY" and 40 < last['RSI'] < 70:
            score += 1
            confluence.append(f"RSI {last['RSI']:.1f} Bullish")
        elif direction == "SELL" and 30 < last['RSI'] < 60:
            score += 1
            confluence.append(f"RSI {last['RSI']:.1f} Bearish")

        # 4. Order Block
        ob_hit, ob_text = detect_order_block(df, direction)
        if ob_hit:
            score += 2
            confluence.append(ob_text)
            if "Bu-OB" in ob_text or "Be-OB" in ob_text:
                confluence.append("OB RETEST")

        # 5. Market Structure
        ms_text, ms_bias = detect_market_structure(df)
        if (direction == "BUY" and "Bullish" in ms_bias) or (direction == "SELL" and "Bearish" in ms_bias):
            score += 1
            confluence.append(ms_text)

        # 6. Momentum Break (MB)
        if abs(last['Close'] - prev['Close']) > last['ATR'] * 0.5:
            score += 1
            confluence.append("MB Momentum")

        # 7. Volume / ATR
        if last['ATR'] > df['ATR'].tail(20).mean():
            score += 1
            confluence.append("ATR Expansion")

        # 8. Pullback to EMA20
        if direction == "BUY" and abs(last['Low'] - last['EMA20']) < last['ATR']*0.3:
            score += 1
            confluence.append("Pullback to EMA20")
        elif direction == "SELL" and abs(last['High'] - last['EMA20']) < last['ATR']*0.3:
            score += 1
            confluence.append("Pullback to EMA20")

    except Exception as e:
        print(f"confluence err {e}")

    return score, confluence

def full_multi_tf_analysis(symbol):
    try:
        symbol = symbol.upper().strip()
        df_15m = get_data(symbol, period="60d", interval="15m")
        if df_15m is None:
            return {"signal": False, "symbol": symbol, "reason": "No data 15m", "score": 0}

        df_15m = add_indicators(df_15m)
        last = df_15m.iloc[-1]

        # Higher TF bias
        df_1h = get_data(symbol, period="60d", interval="1h")
        bias = "Neutral"
        if df_1h is not None:
            df_1h = add_indicators(df_1h)
            if df_1h.iloc[-1]['Close'] > df_1h.iloc[-1]['EMA50']:
                bias = "Bullish HTF"
            else:
                bias = "Bearish HTF"

        # Determine direction
        buy_score, buy_conf = check_confluence(df_15m, "BUY")
        sell_score, sell_conf = check_confluence(df_15m, "SELL")

        direction = "BUY" if buy_score >= sell_score else "SELL"
        score = max(buy_score, sell_score)
        confluence = buy_conf if direction == "BUY" else sell_conf

        if score < 4:
            return {"signal": False, "symbol": symbol, "reason": f"Low score {score}/8", "score": score, "bias": bias, "confluence": confluence}

        # Entry / SL / TP Calculation
        atr = last['ATR']
        if pd.isna(atr) or atr == 0:
            atr = (last['High'] - last['Low']) * 0.5
            if atr == 0:
                atr = last['Close'] * 0.001

        entry = float(last['Close'])

        if direction == "BUY":
            sl = entry - (atr * 1.5)
            tp = entry + (atr * 3.0) # 1:2 RR
        else:
            sl = entry + (atr * 1.5)
            tp = entry - (atr * 3.0)

        # QUALITY LABEL
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

        # V9.0 FIX - Round by symbol
        entry = round_by_symbol(symbol, entry)
        sl = round_by_symbol(symbol, sl)
        tp = round_by_symbol(symbol, tp)

        # Final validation - SL cannot equal entry
        if entry == sl:
            if direction == "BUY":
                sl = round_by_symbol(symbol, sl - atr)
            else:
                sl = round_by_symbol(symbol, sl + atr)

        return {
            "signal": True,
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "score": score,
            "quality": quality,
            "bias": f"{bias} | Bu-OB:{has_ob} Be-OB:{has_ob} MB:{has_mb}",
            "confluence": confluence,
            "reason": f"{quality} {score}/8 - {bias} - {', '.join(confluence[:3])}",
            "news_warning": False
        }

    except Exception as e:
        import traceback
        print(f"full_multi_tf err {symbol} {e} {traceback.format_exc()}")
        return {"signal": False, "symbol": symbol, "reason": f"Error {e}", "score": 0}
