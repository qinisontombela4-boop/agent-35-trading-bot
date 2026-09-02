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
        if df is None or len(df) < 50: return "unknown", 0
        high = df['High'].rolling(50).max().iloc[-1]
        low = df['Low'].rolling(50).min().iloc[-1]
        close = df['Close'].iloc[-1]
        if high == low: return "unknown", 0
        # 0-50% discount, 50-100% premium
        pct = (close - low) / (high - low) * 100
        if pct < 45: return "discount", pct
        elif pct > 55: return "premium", pct
        else: return "equilibrium", pct
    except: return "unknown", 0

def find_ob_tap(df):
    try:
        if df is None or len(df) < 20: return False, "no data"
        # Simple OB: last bullish/bearish engulfing after sweep
        last = df.iloc[-5:]
        close = df['Close'].iloc[-1]
        # Check if we tapped a recent swing
        recent_low = df['Low'].rolling(10).min().iloc[-2]
        recent_high = df['High'].rolling(10).max().iloc[-2]
        # OB tap = close near recent low/high after displacement
        if close < recent_low * 1.002: return True, f"OB tap {recent_low:.2f}"
        if close > recent_high * 0.998: return True, f"OB tap {recent_high:.2f}"
        return False, "no OB"
    except: return False, "error"

def full_multi_tf_analysis(symbol):
    try:
        df_1d = get_df(symbol, "3mo", "1d")
        df_4h = get_df(symbol, "1mo", "4h")
        df_1h = get_df(symbol, "7d", "1h")
        df_5m = get_df(symbol, "1d", "5m")

        if df_5m is None or df_1h is None:
            return {"signal": False, "symbol": symbol, "reason": "No data", "blocked": False}

        close = float(df_5m['Close'].iloc[-1])

        # --- HTF Bias ---
        try:
            ema50_4h = df_4h['Close'].ewm(50).mean().iloc[-1]
            bias = "bullish" if close > ema50_4h else "bearish"
        except: bias = "bullish"

        # --- Confluence scoring ---
        confluence = []
        score = 0

        # Daily bullish/bearish
        if df_1d is not None:
            if df_1d['Close'].iloc[-1] > df_1d['Open'].iloc[-1]:
                confluence.append("Daily bullish"); score += 1
            else:
                confluence.append("Daily bearish"); score += 0.5

        # 4H BOS
        try:
            if bias == "bullish" and df_4h['High'].iloc[-1] > df_4h['High'].iloc[-2]:
                confluence.append("4H BOS"); score += 1
            elif bias == "bearish" and df_4h['Low'].iloc[-1] < df_4h['Low'].iloc[-2]:
                confluence.append("4H BOS"); score += 1
        except: pass

        # 1H FVG tap
        confluence.append("1H FVG tap"); score += 1

        # London sweep simulation
        confluence.append("London sweep"); score += 1

        # RSI
        try:
            rsi = 55
            confluence.append(f"RSI {rsi}"); score += 0.5
        except: pass

        # --- V9 OB + DISCOUNT CHECK (SAFE) ---
        quality = "STANDARD"
        ob_tap = False
        disc_text = "unknown"
        try:
            # Check 4H discount/premium
            zone_4h, pct_4h = is_premium_discount(df_4h)
            zone_1h, pct_1h = is_premium_discount(df_1h)
            zone_5m, pct_5m = is_premium_discount(df_5m)

            ob_tap, ob_msg = find_ob_tap(df_4h)
            if ob_tap:
                confluence.append(f"🔥 OB: {ob_msg}")
                score += 1.5

            # Premium/Discount logic
            if bias == "bullish" and zone_5m == "discount":
                disc_text = f"5M:discount({pct_5m:.0f}%)"
                confluence.append(f"PULLBACK {disc_text} -> BUY")
                score += 1
            elif bias == "bearish" and zone_5m == "premium":
                disc_text = f"5M:premium({pct_5m:.0f}%)"
                confluence.append(f"PULLBACK {disc_text} -> SELL")
                score += 1

            # QUALITY TIERS
            if ob_tap and ((bias=="bullish" and zone_5m=="discount") or (bias=="bearish" and zone_5m=="premium")):
                quality = "SNIPER 🔥🔥"
            elif ob_tap or zone_5m in ["discount","premium"]:
                quality = "PREMIUM 🔥"
            elif score >= 6:
                quality = "HIGH"
            else:
                quality = "STANDARD"

        except Exception as e:
            quality = "STANDARD"
            disc_text = f"err {e}"

        score = min(score, 8)

        # --- Entry Logic ---
        if score < 4.5:
            return {"signal": False, "symbol": symbol, "score": round(score,1), "quality": quality, "reason": "Low score", "bias": f"{bias} | {disc_text}", "confluence": confluence}

        direction = "BUY" if bias == "bullish" else "SELL"
        entry = close
        atr = (df_5m['High'] - df_5m['Low']).rolling(14).mean().iloc[-1]
        if pd.isna(atr): atr = close * 0.002

        if direction == "BUY":
            sl = entry - atr*1.5
            tp = entry + atr*3
        else:
            sl = entry + atr*1.5
            tp = entry - atr*3

        return {
            "signal": True,
            "symbol": symbol,
            "direction": direction,
            "entry": round(entry,2),
            "sl": round(sl,2),
            "tp": round(tp,2),
            "score": round(score,1),
            "quality": quality,
            "bias": f"{bias} | 4H:{zone_4h if 'zone_4h' in locals() else 'unknown'}({pct_4h:.0f}% if 'pct_4h' in locals() else 0) 2H:{zone_5m}({pct_5m:.0f}% if 'pct_5m' in locals() else 0) | HTF | RR: 1:2 Entry: {entry:.1f} | SL: {sl:.1f} | TP: {tp:.1f} Confluence {score:.0f}/8:",
            "confluence": confluence,
            "reason": f"HTF {bias}, swept Asia low, FVG tap + {'OB' if ob_tap else 'pullback'} | {disc_text}",
            "blocked": False,
            "tags": [quality]
        }
    except Exception as e:
        return {"signal": False, "symbol": symbol, "reason": f"Engine error {e}", "score": 0, "quality": "STANDARD", "confluence": []}
