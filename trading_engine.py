import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# --- SMC DETECTION HELPERS ---
def get_data(symbol="EURUSD=X", tf="1h", period="5d"):
    # Mapping for yfinance
    tf_map = {"D":"1d","4H":"1h","2H":"1h","1H":"1h","30M":"30m","15M":"15m","5M":"5m"}
    data = yf.download(symbol, period=period, interval=tf_map.get(tf, "1h"), progress=False)
    if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
    return data.dropna()

def detect_bos_choch(df):
    highs = df['High'].rolling(20).max()
    lows = df['Low'].rolling(20).min()
    last_close = df['Close'].iloc[-1]
    if last_close > highs.iloc[-2]: return "BULLISH_BOS"
    if last_close < lows.iloc[-2]: return "BEARISH_BOS"
    return "RANGING"

def detect_order_blocks(df):
    # Last bearish before bullish impulse = Bullish OB
    obs = []
    for i in range(len(df)-5, len(df)-1):
        if df['Close'].iloc[i] < df['Open'].iloc[i] and df['Close'].iloc[i+1] > df['Open'].iloc[i+1] and df['Close'].iloc[i+1] > df['High'].iloc[i]:
            obs.append({"type":"BULLISH_OB","high":df['High'].iloc[i],"low":df['Low'].iloc[i],"idx":i})
        if df['Close'].iloc[i] > df['Open'].iloc[i] and df['Close'].iloc[i+1] < df['Open'].iloc[i+1] and df['Close'].iloc[i+1] < df['Low'].iloc[i]:
            obs.append({"type":"BEARISH_OB","high":df['High'].iloc[i],"low":df['Low'].iloc[i],"idx":i})
    return obs[-2:] if obs else []

def detect_fvg(df):
    fvgs = []
    for i in range(1, len(df)-1):
        # Bullish FVG: low[i+1] > high[i-1]
        if df['Low'].iloc[i+1] > df['High'].iloc[i-1]:
            fvgs.append({"type":"BULL_FVG","top":df['Low'].iloc[i+1],"bottom":df['High'].iloc[i-1],"mitigated": False})
        # Bearish FVG
        if df['High'].iloc[i+1] < df['Low'].iloc[i-1]:
            fvgs.append({"type":"BEAR_FVG","top":df['Low'].iloc[i-1],"bottom":df['High'].iloc[i+1],"mitigated": False})
    return fvgs[-3:] if fvgs else []

def detect_liquidity(df):
    # Equal Highs/Lows + Sweep detection
    recent_high = df['High'].iloc[-20:-1].max()
    recent_low = df['Low'].iloc[-20:-1].min()
    sweep = None
    if df['High'].iloc[-1] > recent_high and df['Close'].iloc[-1] < recent_high: sweep = "BSL_SWEEP_BEARISH"
    if df['Low'].iloc[-1] < recent_low and df['Close'].iloc[-1] > recent_low: sweep = "SSL_SWEEP_BULLISH"
    return {"eqh": recent_high, "eql": recent_low, "sweep": sweep}

def premium_discount(df):
    high = df['High'].rolling(50).max().iloc[-1]
    low = df['Low'].rolling(50).min().iloc[-1]
    close = df['Close'].iloc[-1]
    range_size = high - low
    if range_size == 0: return "EQUILIBRIUM"
    level = (close - low) / range_size
    if level > 0.7: return "PREMIUM"
    if level < 0.3: return "DISCOUNT"
    return "EQUILIBRIUM"

def check_news_risk():
    # V1: Placeholder - connect to ForexFactory API later
    # Return False if high impact news in next 60m
    return False

# --- MASTER ANALYSIS ---
def full_multi_tf_analysis(symbol="EURUSD"):
    symbols_map = {"EURUSD":"EURUSD=X","XAUUSD":"GC=F","BTCUSD":"BTC-USD","GBPUSD":"GBPUSD=X","NAS100":"^NDX"}
    yf_symbol = symbols_map.get(symbol, "EURUSD=X")

    # 1. DAILY BIAS
    d_df = get_data(yf_symbol, "D", "3mo")
    daily_bias = detect_bos_choch(d_df)
    daily_zone = premium_discount(d_df)

    # 2. 4H, 2H, 1H ALIGNMENT (Must align)
    tf_results = {}
    for tf in ["4H","1H"]:
        df = get_data(yf_symbol, tf, "10d")
        tf_results[tf] = {"bias": detect_bos_choch(df), "zone": premium_discount(df), "liq": detect_liquidity(df)}

    # Check alignment: 4H, 1H must be same direction
    h4_bias = tf_results["4H"]["bias"]
    h1_bias = tf_results["1H"]["bias"]
    aligned = (h4_bias == h1_bias) and "BULLISH" in h4_bias or "BEARISH" in h4_bias
    # Allow daily to be different but preferred aligned
    daily_match = daily_bias in h4_bias or daily_bias == "RANGING"

    # 3. 15M -> 5M ENTRY
    m15_df = get_data(yf_symbol, "15M", "5d")
    m5_df = get_data(yf_symbol, "5M", "2d")

    obs = detect_order_blocks(m5_df)
    fvgs = detect_fvg(m5_df)
    liq = detect_liquidity(m5_df)
    zone_5m = premium_discount(m5_df)

    # ENTRY RULES
    confluence_score = 0
    reasons = []

    if aligned:
        confluence_score += 2
        reasons.append(f"HTF Aligned {h4_bias}")
    if daily_match:
        confluence_score += 1
        reasons.append(f"Daily {daily_bias} aligns")
    if liq['sweep']:
        confluence_score += 2
        reasons.append(liq['sweep'])
    if obs:
        confluence_score += 2
        reasons.append(f"{obs[-1]['type']} at {zone_5m}")
    if fvgs:
        confluence_score += 1
        reasons.append(f"{fvgs[-1]['type']} unmitigated")
    if zone_5m in ["DISCOUNT","PREMIUM"]:
        confluence_score += 1
        reasons.append(f"Entry in {zone_5m}")
    if check_news_risk():
        return {"signal": False, "reason": "High Impact News"}

    # FINAL DECISION: Need 5+ confluence
    if confluence_score >= 5:
        direction = "BUY" if "BULLISH" in h4_bias else "SELL"
        # Entry at OB/FVG
        entry = m5_df['Close'].iloc[-1]
        sl = obs[-1]['low'] if direction=="BUY" and obs else entry * 0.998
        tp = entry + (entry-sl)*3 # 1:3 RR

        return {
            "signal": True,
            "symbol": symbol,
            "direction": direction,
            "entry": round(float(entry),5),
            "sl": round(float(sl),5),
            "tp": round(float(tp),5),
            "bias": daily_bias,
            "htf_aligned": aligned,
            "confluence": " | ".join(reasons),
            "score": confluence_score,
            "zone": zone_5m,
            "obs": obs,
            "fvgs": fvgs
        }

    return {"signal": False, "score": confluence_score, "reasons": reasons, "daily": daily_bias, "htf": tf_results}
