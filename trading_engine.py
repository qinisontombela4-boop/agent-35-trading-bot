import yfinance as yf
import pandas as pd

def get_data(symbol="EURUSD=X", tf="1h", period="5d"):
    tf_map = {"D":"1d","4H":"1h","2H":"1h","1H":"1h","30M":"30m","15M":"15m","5M":"5m"}
    try:
        data = yf.download(symbol, period=period, interval=tf_map.get(tf, "1h"), progress=False, auto_adjust=True)
        if data.empty: return pd.DataFrame()
        if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
        return data.dropna()
    except: return pd.DataFrame()

def detect_bos_choch(df):
    if len(df) < 25: return "RANGING"
    highs = df['High'].rolling(20).max(); lows = df['Low'].rolling(20).min()
    last_close = df['Close'].iloc[-1]
    if last_close > highs.iloc[-2]: return "BULLISH_BOS"
    if last_close < lows.iloc[-2]: return "BEARISH_BOS"
    return "RANGING"

def detect_order_blocks(df):
    obs=[]
    for i in range(len(df)-5, len(df)-1):
        if df['Close'].iloc[i] < df['Open'].iloc[i] and df['Close'].iloc[i+1] > df['Open'].iloc[i+1] and df['Close'].iloc[i+1] > df['High'].iloc[i]:
            obs.append({"type":"BULLISH_OB","high":float(df['High'].iloc[i]),"low":float(df['Low'].iloc[i])})
        if df['Close'].iloc[i] > df['Open'].iloc[i] and df['Close'].iloc[i+1] < df['Open'].iloc[i+1] and df['Close'].iloc[i+1] < df['Low'].iloc[i]:
            obs.append({"type":"BEARISH_OB","high":float(df['High'].iloc[i]),"low":float(df['Low'].iloc[i])})
    return obs[-2:]

def detect_fvg(df):
    fvgs=[]
    for i in range(1, len(df)-1):
        if df['Low'].iloc[i+1] > df['High'].iloc[i-1]: fvgs.append({"type":"BULL_FVG","top":float(df['Low'].iloc[i+1]),"bottom":float(df['High'].iloc[i-1])})
        if df['High'].iloc[i+1] < df['Low'].iloc[i-1]: fvgs.append({"type":"BEAR_FVG","top":float(df['Low'].iloc[i-1]),"bottom":float(df['High'].iloc[i+1])})
    return fvgs[-3:]

def detect_liquidity(df):
    if len(df) < 21: return {"eqh":0,"eql":0,"sweep":None}
    recent_high = df['High'].iloc[-20:-1].max(); recent_low = df['Low'].iloc[-20:-1].min(); sweep=None
    if df['High'].iloc[-1] > recent_high and df['Close'].iloc[-1] < recent_high: sweep="BSL_SWEEP_BEARISH"
    if df['Low'].iloc[-1] < recent_low and df['Close'].iloc[-1] > recent_low: sweep="SSL_SWEEP_BULLISH"
    return {"eqh":float(recent_high),"eql":float(recent_low),"sweep":sweep}

def premium_discount(df):
    if len(df) < 50: return "EQUILIBRIUM"
    high = df['High'].rolling(50).max().iloc[-1]; low = df['Low'].rolling(50).min().iloc[-1]; close = df['Close'].iloc[-1]
    rng = high-low; level = (close-low)/rng if rng!=0 else 0.5
    if level>0.7: return "PREMIUM"
    if level<0.3: return "DISCOUNT"
    return "EQUILIBRIUM"

def full_multi_tf_analysis(symbol="EURUSD"):
    map_sym = {"EURUSD":"EURUSD=X","XAUUSD":"GC=F","BTCUSD":"BTC-USD","GBPUSD":"GBPUSD=X","NAS100":"^NDX","USDJPY":"JPY=X"}
    yf_sym = map_sym.get(symbol, "EURUSD=X")
    d_df = get_data(yf_sym, "D", "3mo"); daily_bias = detect_bos_choch(d_df)
    tf_results={}
    for tf in ["4H","1H"]:
        df = get_data(yf_sym, tf, "10d"); tf_results[tf] = {"bias":detect_bos_choch(df),"zone":premium_discount(df),"liq":detect_liquidity(df)}
    h4_bias = tf_results["4H"]["bias"]; h1_bias = tf_results["1H"]["bias"]
    aligned = (h4_bias == h1_bias and "RANGING" not in h4_bias)
    m5_df = get_data(yf_sym, "5M", "2d")
    if m5_df.empty: return {"signal":False,"symbol":symbol,"reason":"No data"}
    obs = detect_order_blocks(m5_df); fvgs = detect_fvg(m5_df); liq = detect_liquidity(m5_df); zone_5m = premium_discount(m5_df)
    score=0; reasons=[]
    if aligned: score+=2; reasons.append(f"HTF Aligned {h4_bias}")
    if liq['sweep']: score+=2; reasons.append(liq['sweep'])
    if obs: score+=2; reasons.append(f"{obs[-1]['type']}")
    if fvgs: score+=1; reasons.append(f"{fvgs[-1]['type']}")
    if zone_5m in ["DISCOUNT","PREMIUM"]: score+=1; reasons.append(f"{zone_5m}")
    if score>=5:
        entry = float(m5_df['Close'].iloc[-1]); direction="BUY" if "BULLISH" in h4_bias else "SELL"
        sl = obs[-1]['low'] if direction=="BUY" and obs else (entry*0.998 if direction=="BUY" else entry*1.002)
        risk = abs(entry-sl); tp = entry+risk*3 if direction=="BUY" else entry-risk*3
        return {"signal":True,"symbol":symbol,"direction":direction,"entry":round(entry,5),"sl":round(float(sl),5),"tp":round(float(tp),5),"bias":daily_bias,"htf_aligned":aligned,"confluence":" | ".join(reasons),"score":score,"zone":zone_5m,"obs":obs,"fvgs":fvgs}
    return {"signal":False,"symbol":symbol,"score":score,"reasons":reasons,"daily":daily_bias,"htf":tf_results}
