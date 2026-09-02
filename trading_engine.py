import yfinance as yf
import pandas as pd

MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X",
    "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X", "USDZAR": "USDZAR=X",
    "EURZAR": "EURZAR=X", "GBPZAR": "GBPZAR=X", "ZARJPY": "ZARJPY=X",
    "XAUUSD": "GC=F", "GOLD": "GC=F", "XAGUSD": "SI=F",
    "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
    "NAS100": "NQ=F", "US30": "YM=F", "SPX500": "ES=F",
    "GER40": "^GDAXI", "UK100": "^FTSE", "JP225": "N225=F",
    "USOIL": "CL=F", "UKOIL": "BZ=F",
    "AAPL": "AAPL", "TSLA": "TSLA", "NVDA": "NVDA", "MSFT": "MSFT"
}

def get_data(symbol, period="1mo", interval="1h"):
    yfs = MAP.get(symbol.upper(), symbol.upper())
    try:
        df = yf.download(yfs, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty: return None
        try: df.columns = df.columns.get_level_values(0)
        except: pass
        df = df[['Open','High','Low','Close']].dropna()
        return df
    except: return None

def get_swing_high_low(df, lookback=20):
    high = df['High'].tail(lookback).max()
    low = df['Low'].tail(lookback).min()
    # Find where
    high_idx = df['High'].tail(lookback).idxmax()
    low_idx = df['Low'].tail(lookback).idxmin()
    return high, low, high_idx, low_idx

def get_discount_premium_zone(high, low, price):
    mid = (high + low) / 2
    range_size = high - low
    if range_size == 0: return "mid", 50, mid
    pct = ((price - low) / range_size) * 100 # 0% = low, 100% = high
    if pct < 50:
        discount_pct = (50 - pct) # how deep in discount
        return "discount", discount_pct, mid
    else:
        premium_pct = (pct - 50)
        return "premium", premium_pct, mid

def detect_trend(df):
    # Simple HH/HL
    closes = df['Close'].tail(10).values
    if closes[-1] > closes[-3] and closes[-2] > closes[-5]:
        return "bullish"
    elif closes[-1] < closes[-3] and closes[-2] < closes[-5]:
        return "bearish"
    else:
        return "ranging"

def find_order_block(df, direction):
    # Bull OB = last bearish candle before impulse
    try:
        df5 = df.tail(20)
        for i in range(len(df5)-3, 2, -1):
            curr = df5.iloc[i]
            next_candles = df5.iloc[i+1:i+4]
            if direction == "BUY":
                # Last red before green impulse
                if curr['Close'] < curr['Open']:
                    # Next 2-3 candles bullish and break high
                    if next_candles['Close'].iloc[-1] > curr['High'] and (next_candles['Close'] > next_candles['Open']).sum() >= 2:
                        return float(curr['Low']), float(curr['High']), True
            else:
                if curr['Close'] > curr['Open']:
                    if next_candles['Close'].iloc[-1] < curr['Low'] and (next_candles['Close'] < next_candles['Open']).sum() >= 2:
                        return float(curr['Low']), float(curr['High']), True
        return None, None, False
    except:
        return None, None, False

def check_bos(df, direction):
    try:
        last_high = df['High'].tail(10).max()
        last_low = df['Low'].tail(10).min()
        curr_close = df['Close'].iloc[-1]
        prev_high = df['High'].iloc[-2]
        prev_low = df['Low'].iloc[-2]
        if direction == "BUY":
            if curr_close > prev_high or curr_close > last_high:
                return True, f"BOS > {prev_high:.2f}"
        else:
            if curr_close < prev_low or curr_close < last_low:
                return True, f"BOS < {prev_low:.2f}"
        return False, ""
    except:
        return False, ""

def check_engulfing_wick(df, direction):
    try:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        # Engulfing
        engulf = False
        if direction == "BUY":
            if last['Close'] > last['Open'] and prev['Close'] < prev['Open']:
                if last['Close'] > prev['Open'] and last['Open'] < prev['Close']:
                    engulf = True
        else:
            if last['Close'] < last['Open'] and prev['Close'] > prev['Open']:
                if last['Close'] < prev['Open'] and last['Open'] > prev['Close']:
                    engulf = True
        # Wick rejection
        body = abs(last['Close'] - last['Open'])
        upper_wick = last['High'] - max(last['Close'], last['Open'])
        lower_wick = min(last['Close'], last['Open']) - last['Low']
        wick_reject = False
        wick_type = ""
        if direction == "BUY" and lower_wick > body * 0.6:
            wick_reject = True
            wick_type = "wick rejection (buyers)"
        elif direction == "SELL" and upper_wick > body * 0.6:
            wick_reject = True
            wick_type = "wick rejection (sellers)"

        if engulf and wick_reject:
            return True, f"{'bullish' if direction=='BUY' else 'bearish'} engulfing + {wick_type}"
        elif engulf:
            return True, f"{'bullish' if direction=='BUY' else 'bearish'} engulfing"
        elif wick_reject:
            return True, wick_type
        return False, ""
    except:
        return False, ""

def full_multi_tf_analysis(symbol):
    symbol = symbol.upper().strip()
    try:
        # Get TFs
        df_4h = get_data(symbol, period="1mo", interval="4h")
        df_1h = get_data(symbol, period="5d", interval="1h")
        df_5m = get_data(symbol, period="1d", interval="5m")

        if df_4h is None or df_1h is None or df_5m is None:
            return {"signal": False, "symbol": symbol, "reason": "No data", "score": 0}

        # 1. HTF BIAS 4H
        bias_4h = detect_trend(df_4h)
        if bias_4h == "ranging":
            # Use 1H for bias if 4H ranging
            bias_4h = detect_trend(df_1h)

        # 2. 1H DISCOUNT/PREMIUM
        high_1h, low_1h, _, _ = get_swing_high_low(df_1h, 30)
        price_1h = df_1h['Close'].iloc[-1]
        zone_1h, zone_pct_1h, mid_1h = get_discount_premium_zone(high_1h, low_1h, price_1h)

        # 3. 5M DISCOUNT/PREMIUM + STRUCTURE
        high_5m, low_5m, _, _ = get_swing_high_low(df_5m, 40)
        price_5m = df_5m['Close'].iloc[-1]
        zone_5m, zone_pct_5m, mid_5m = get_discount_premium_zone(high_5m, low_5m, price_5m)

        # Determine direction
        direction = None
        if bias_4h == "bullish" and zone_1h == "discount":
            direction = "BUY"
        elif bias_4h == "bearish" and zone_1h == "premium":
            direction = "SELL"
        else:
            # Counter but still if deep discount/premium
            if zone_1h == "discount" and zone_pct_1h > 25:
                direction = "BUY"
            elif zone_1h == "premium" and zone_pct_1h > 25:
                direction = "SELL"

        if not direction:
            return {"signal": False, "symbol": symbol, "reason": f"HTF {bias_4h}, 1H {zone_1h} ({zone_pct_1h:.0f}%) - no edge", "score": 1}

        # 4. SCORE
        score = 0
        confluence = []

        # HTF aligned
        if (bias_4h == "bullish" and direction == "BUY") or (bias_4h == "bearish" and direction == "SELL"):
            score += 2
            confluence.append(f"Daily {bias_4h}")
            confluence.append(f"4H BOS - {bias_4h} structure")
        else:
            score += 0.5
            confluence.append(f"4H {bias_4h} (counter but deep value)")

        # 1H discount/premium depth
        if zone_pct_1h > 15:
            score += 1.5
            confluence.append(f"1H {zone_1h} ({zone_pct_1h:.0f}% deep)")
        elif zone_pct_1h > 5:
            score += 1
            confluence.append(f"1H {zone_1h} ({zone_pct_1h:.0f}%)")
        else:
            score += 0.5

        # 5M discount/premium
        if (zone_5m == zone_1h) and zone_pct_5m > 10:
            score += 1
            confluence.append(f"5M {zone_5m} ({zone_pct_5m:.0f}%)")

        # Order Block
        ob_low, ob_high, has_ob = find_order_block(df_5m, direction)
        if has_ob:
            score += 1.5
            confluence.append(f"🔥 OB: {'Bull' if direction=='BUY' else 'Bear'} OB {ob_low:.2f}-{ob_high:.2f}")

        # BOS
        has_bos, bos_text = check_bos(df_5m, direction)
        if has_bos:
            score += 1
            confluence.append(f"BOS: {bos_text}")

        # Engulfing + Wick
        has_struct, struct_text = check_engulfing_wick(df_5m, direction)
        if has_struct:
            score += 1
            confluence.append(f"✅ 5M STRUCTURE: {struct_text} + {bos_text if has_bos else 'rejection'}")

        # Asia sweep bonus
        if zone_pct_1h > 30:
            score += 0.5
            confluence.append("Swept Asia high/low")

        score = min(round(score,1), 8.0)

        # QUALITY - NEW WITH MEDIUM 4
        if score >= 7 and has_ob:
            quality = "SNIPER 🔥🔥"
        elif score >= 6:
            quality = "PREMIUM 🔥"
        elif score >= 5:
            quality = "HIGH ✅"
        elif score >= 4:
            quality = "MEDIUM 📊"
        else:
            return {"signal": False, "symbol": symbol, "reason": f"Score {score}/8 too low - need 4+", "score": score, "quality": "LOW"}

        # Entry, SL, TP
        entry = float(price_5m)
        if direction == "BUY":
            sl = float(df_5m['Low'].tail(5).min())
            # Ensure SL not too close
            if entry - sl < (high_1h - low_1h)*0.02:
                sl = entry - (high_1h - low_1h)*0.03
            risk = entry - sl
            tp = entry + risk * 3 # 1:3 RR default
        else:
            sl = float(df_5m['High'].tail(5).max())
            if sl - entry < (high_1h - low_1h)*0.02:
                sl = entry + (high_1h - low_1h)*0.03
            risk = sl - entry
            tp = entry - risk * 3

        bias_str = f"{bias_4h} | 4H:{zone_1h}({zone_pct_1h:.0f}%) 1H:{zone_1h}({zone_pct_1h:.0f}%) 5M:{zone_5m}({zone_pct_5m:.0f}%) | HTF"
        reason = f"HTF {bias_4h}, 1H+5M {zone_1h} + {struct_text if has_struct else 'pullback'} {'+ OB' if has_ob else ''}"

        return {
            "signal": True,
            "symbol": symbol,
            "direction": direction,
            "entry": round(entry, 2 if symbol not in ["XAUUSD","GOLD","BTCUSD"] else 2),
            "sl": round(sl, 2),
            "tp": round(tp, 2),
            "score": score,
            "quality": quality,
            "bias": bias_str,
            "confluence": confluence[:6],
            "reason": reason,
            "ob_low": ob_low,
            "ob_high": ob_high
        }

    except Exception as e:
        return {"signal": False, "symbol": symbol, "reason": f"Engine error {e}", "score": 0}
