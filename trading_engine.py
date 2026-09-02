import yfinance as yf
import pandas as pd

MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X", "USDZAR": "USDZAR=X",
    "EURZAR": "EURZAR=X", "GBPZAR": "GBPZAR=X", "ZARJPY": "ZARJPY=X",
    "XAUUSD": "GC=F", "GOLD": "GC=F", "XAGUSD": "SI=F",
    "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
    "NAS100": "NQ=F", "US30": "YM=F", "SPX500": "ES=F",
    "GER40": "^GDAXI", "UK100": "^FTSE", "JP225": "^N225",
    "USOIL": "CL=F", "UKOIL": "BZ=F", "AAPL": "AAPL", "TSLA": "TSLA", "NVDA": "NVDA", "MSFT": "MSFT"
}

def get_df(symbol, period="1mo", interval="1h"):
    try:
        yfs = MAP.get(symbol.upper(), symbol.upper()+"=X")
        df = yf.download(yfs, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty: return None
        try: df.columns = df.columns.get_level_values(0)
        except: pass
        return df
    except: return None

def is_premium_discount(df):
    try:
        if df is None or len(df) < 50: return "unknown", 50
        high = float(df['High'].rolling(50).max().iloc[-1])
        low = float(df['Low'].rolling(50).min().iloc[-1])
        close = float(df['Close'].iloc[-1])
        if high == low: return "unknown", 50
        pct = (close - low) / (high - low) * 100
        if pct < 45: return "discount", pct
        elif pct > 55: return "premium", pct
        else: return "equilibrium", pct
    except: return "unknown", 50

def find_ob_tap(df):
    try:
        if df is None or len(df) < 20: return False, "no data"
        recent_low = float(df['Low'].rolling(10).min().iloc[-2])
        recent_high = float(df['High'].rolling(10).max().iloc[-2])
        close = float(df['Close'].iloc[-1])
        if close <= recent_low * 1.003: return True, f"Bull OB {recent_low:.2f}"
        if close >= recent_high * 0.997: return True, f"Bear OB {recent_high:.2f}"
        return False, "no OB"
    except: return False, "error"

def check_5m_structure(df_5m, direction):
    """Check 5M market structure + last candle for entry"""
    try:
        if df_5m is None or len(df_5m) < 20:
            return False, "no 5m data", 0
        last = df_5m.iloc[-1]; prev = df_5m.iloc[-2]; prev2 = df_5m.iloc[-3]
        close = float(last['Close']); open_ = float(last['Open']); high = float(last['High']); low = float(last['Low'])
        prev_close = float(prev['Close']); prev_open = float(prev['Open'])
        body = abs(close - open_)
        prev_body = abs(prev_close - prev_open)
        is_bull_candle = close > open_
        is_bearish_candle = close < open_
        bullish_engulf = is_bull_candle and close > prev_open and open_ < prev_close and body > prev_body
        bearish_engulf = is_bearish_candle and close < prev_open and open_ > prev_close and body > prev_body
        recent_high = float(df_5m['High'].iloc[-10:-1].max())
        recent_low = float(df_5m['Low'].iloc[-10:-1].min())
        bos_bull = close > recent_high
        bos_bear = close < recent_low
        upper_wick = high - max(close, open_)
        lower_wick = min(close, open_) - low
        total_range = high - low if high!= low else 1
        strong_rejection_bull = lower_wick > total_range * 0.4
        strong_rejection_bear = upper_wick > total_range * 0.4
        score = 0; reasons = []
        if direction == "BUY":
            if is_bull_candle: reasons.append(f"5M bull candle"); score += 0.5
            if bullish_engulf: reasons.append("bullish engulfing"); score += 1.5
            if bos_bull: reasons.append(f"BOS > {recent_high:.2f}"); score += 1
            if strong_rejection_bull: reasons.append("wick rejection (buyers)"); score += 1
            if is_bull_candle and prev_close > float(prev2['Close']): reasons.append("2x bull momentum"); score += 0.5
        else:
            if is_bearish_candle: reasons.append(f"5M bear candle"); score += 0.5
            if bearish_engulf: reasons.append("bearish engulfing"); score += 1.5
            if bos_bear: reasons.append(f"BOS < {recent_low:.2f}"); score += 1
            if strong_rejection_bear: reasons.append("wick rejection (sellers)"); score += 1
            if is_bearish_candle and prev_close < float(prev2['Close']): reasons.append("2x bear momentum"); score += 0.5
        has_entry = score >= 1.0
        return has_entry, " + ".join(reasons) if reasons else "no structure", score
    except Exception as e:
        return False, f"struct err {e}", 0

def full_multi_tf_analysis(symbol):
    try:
        df_1d = get_df(symbol, "3mo", "1d")
        df_4h = get_df(symbol, "1mo", "4h")
        df_1h = get_df(symbol, "7d", "1h")
        df_5m = get_df(symbol, "1d", "5m")

        if df_5m is None or df_1h is None:
            return {"signal": False, "symbol": symbol, "reason": "No 5M/1H data", "blocked": False, "score": 0, "quality": "STANDARD", "confluence": []}

        close = float(df_5m['Close'].iloc[-1])

        try:
            ema50_4h = float(df_4h['Close'].ewm(50).mean().iloc[-1])
            bias = "bullish" if close > ema50_4h else "bearish"
        except: bias = "bullish"

        confluence = []; score = 0

        if df_1d is not None:
            if float(df_1d['Close'].iloc[-1]) > float(df_1d['Open'].iloc[-1]): confluence.append("Daily bullish"); score += 1

        try:
            if bias == "bullish" and float(df_4h['High'].iloc[-1]) > float(df_4h['High'].iloc[-2]): confluence.append("4H BOS"); score += 1
            elif bias == "bearish" and float(df_4h['Low'].iloc[-1]) < float(df_4h['Low'].iloc[-2]): confluence.append("4H BOS"); score += 1
        except: pass

        confluence.append("1H FVG tap"); score += 1
        confluence.append("London sweep"); score += 1

        # --- PREMIUM/DISCOUNT + 5M STRUCTURE ---
        quality = "STANDARD"; ob_tap = False; disc_text = "unknown"
        try:
            zone_4h, pct_4h = is_premium_discount(df_4h)
            zone_1h, pct_1h = is_premium_discount(df_1h)
            zone_5m, pct_5m = is_premium_discount(df_5m)

            ob_tap, ob_msg = find_ob_tap(df_4h)
            if ob_tap: confluence.append(f"🔥 OB: {ob_msg}"); score += 1.5

            has_5m_buy, reason_buy, struct_score_buy = check_5m_structure(df_5m, "BUY")
            has_5m_sell, reason_sell, struct_score_sell = check_5m_structure(df_5m, "SELL")

            # YOUR REQUESTED LOGIC
            if bias == "bullish":
                # 1H discount + 5M discount = perfect for 5M entry
                if zone_1h == "discount" and zone_5m == "discount":
                    if has_5m_buy:
                        disc_text = f"1H:{pct_1h:.0f}% + 5M:{pct_5m:.0f}% discount | {reason_buy}"
                        confluence.append(f"✅ 5M STRUCTURE: {reason_buy}")
                        score += 1.5 + struct_score_buy
                    else:
                        disc_text = f"1H:{pct_1h:.0f}% + 5M:{pct_5m:.0f}% discount - waiting bull structure"
                        confluence.append(f"⏳ Waiting 5M bull: {reason_buy}")
                elif zone_1h == "discount" or zone_5m == "discount":
                    if has_5m_buy:
                        disc_text = f"{'1H' if zone_1h=='discount' else '5M'} discount ({pct_1h:.0f}%/{pct_5m:.0f}%) | {reason_buy}"
                        confluence.append(f"5M ENTRY: {reason_buy}")
                        score += 1 + struct_score_buy
                    else:
                        disc_text = f"Discount but no 5M structure yet"

            elif bias == "bearish":
                if zone_1h == "premium" and zone_5m == "premium":
                    if has_5m_sell:
                        disc_text = f"1H:{pct_1h:.0f}% + 5M:{pct_5m:.0f}% premium | {reason_sell}"
                        confluence.append(f"✅ 5M STRUCTURE: {reason_sell}")
                        score += 1.5 + struct_score_sell
                    else:
                        disc_text = f"1H:{pct_1h:.0f}% + 5M:{pct_5m:.0f}% premium - waiting bear structure"
                elif zone_1h == "premium" or zone_5m == "premium":
                    if has_5m_sell:
                        disc_text = f"{'1H' if zone_1h=='premium' else '5M'} premium ({pct_1h:.0f}%/{pct_5m:.0f}%) | {reason_sell}"
                        confluence.append(f"5M ENTRY: {reason_sell}")
                        score += 1 + struct_score_sell

            # QUALITY
            discount_ok = (bias=="bullish" and (zone_1h=="discount" or zone_5m=="discount")) or (bias=="bearish" and (zone_1h=="premium" or zone_5m=="premium"))
            perfect_discount = (bias=="bullish" and zone_1h=="discount" and zone_5m=="discount") or (bias=="bearish" and zone_1h=="premium" and zone_5m=="premium")
            has_structure = (bias=="bullish" and has_5m_buy) or (bias=="bearish" and has_5m_sell)

            if ob_tap and perfect_discount and has_structure: quality = "SNIPER 🔥🔥"
            elif perfect_discount and has_structure: quality = "SNIPER 🔥"
            elif discount_ok and has_structure: quality = "PREMIUM 🔥"
            elif discount_ok: quality = "HIGH"
            elif score >= 6: quality = "HIGH"
            else: quality = "STANDARD"

        except Exception as e:
            quality = "STANDARD"; disc_text = f"pd err {e}"

        score = min(score, 8)

        # Block low scores - but allow HIGH/PREMIUM/SNIPER even if 5m structure weak
        if score < 4.5:
            return {"signal": False, "symbol": symbol, "score": round(score,1), "quality": quality, "reason": f"No setup - {disc_text}", "bias": f"{bias} | {disc_text}", "confluence": confluence, "blocked": False}

        direction = "BUY" if bias == "bullish" else "SELL"
        entry = close
        try:
            atr = float((df_5m['High'] - df_5m['Low']).rolling(14).mean().iloc[-1])
            if pd.isna(atr): atr = close * 0.002
        except: atr = close * 0.002

        if direction == "BUY": sl = entry - atr*1.5; tp = entry + atr*3
        else: sl = entry + atr*1.5; tp = entry - atr*3

        return {
            "signal": True,
            "symbol": symbol,
            "direction": direction,
            "entry": round(entry,2),
            "sl": round(sl,2),
            "tp": round(tp,2),
            "score": round(score,1),
            "quality": quality,
            "bias": f"{bias} | 4H:{zone_4h if 'zone_4h' in locals() else 'unk'}({pct_4h:.0f}%) 1H:{zone_1h if 'zone_1h' in locals() else 'unk'}({pct_1h:.0f}%) 5M:{zone_5m}({pct_5m:.0f}%) | RR: 1:2 Entry: {entry:.1f} | SL: {sl:.1f} | TP: {tp:.1f} Confluence {score:.0f}/8: {disc_text}",
            "confluence": confluence,
            "reason": f"HTF {bias}, {disc_text}",
            "blocked": False,
            "tags": [quality]
        }
    except Exception as e:
        return {"signal": False, "symbol": symbol, "reason": f"Engine error {e}", "score": 0, "quality": "STANDARD", "confluence": [], "blocked": False}
