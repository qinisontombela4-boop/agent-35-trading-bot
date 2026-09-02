import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import math

def get_pd_zone(price, high, low):
    """Returns zone and % position in range"""
    if high == low:
        return "equilibrium", 50
    pos = (price - low) / (high - low) * 100
    if pos >= 75:
        return "premium", pos
    elif pos <= 25:
        return "discount", pos
    else:
        return "equilibrium", pos

def get_htf_zones(symbol, tf="4h"):
    """Get high/low for TF to calc PD zone"""
    try:
        interval_map = {"4h": "240m", "2h": "120m", "1h": "60m", "15m": "15m", "5m": "5m", "1d": "1d"}
        period_map = {"4h": "5d", "2h": "5d", "1h": "5d", "15m": "5d", "5m": "2d", "1d": "3mo"}
        # Use yfinance
        import yfinance as yf
        yfs = symbol+"=X" if len(symbol)==6 else symbol
        if symbol=="XAUUSD": yfs="GC=F"
        if "USD" in symbol and len(symbol)<=7 and symbol!="XAUUSD": yfs = symbol+"=X"
        
        df = yf.download(yfs, period=period_map.get(tf,"5d"), interval=interval_map.get(tf,"60m"), progress=False, auto_adjust=True)
        if df.empty:
            return None
        try:
            df.columns = df.columns.get_level_values(0)
        except:
            pass
        # Last 50 candles range for zone
        recent = df.tail(50)
        h = float(recent['High'].max())
        l = float(recent['Low'].min())
        close = float(df['Close'].iloc[-1])
        zone, pct = get_pd_zone(close, h, l)
        return {"zone": zone, "pct": round(pct,1), "high": h, "low": l, "price": close}
    except:
        return None
# CONFIG
MAP = {"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"JPY=X","USDZAR":"ZAR=X","EURZAR":"EURZAR=X","XAUUSD":"GC=F","GOLD":"GC=F","BTCUSD":"BTC-USD","ETHUSD":"ETH-USD","NAS100":"^NDX","US30":"^DJI","SPX500":"^GSPC","GER40":"^GDAXI","USOIL":"CL=F"}
MIN_SCORE = 4  # <--- Dropped to 4 as requested

def get_df(symbol, period="5d", interval="1h"):
    try:
        yfs = MAP.get(symbol.upper(), symbol.upper()+"=X")
        df = yf.download(yfs, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty: return None
        try: df.columns = df.columns.get_level_values(0)
        except: pass
        return df.dropna()
    except:
        return None

def premium_discount_zones(df):
    """Returns if price is in premium/discount + 50% zones"""
    if df is None or len(df) < 20: return {"zone":"neutral", "premium_tap":False, "discount_tap":False, "eq_tap":False}
    recent = df.tail(50)
    swing_high = recent['High'].max()
    swing_low = recent['Low'].min()
    range_size = swing_high - swing_low
    if range_size == 0: return {"zone":"neutral","premium_tap":False,"discount_tap":False,"eq_tap":False}
    
    high_70 = swing_low + range_size * 0.7
    low_30 = swing_low + range_size * 0.3
    mid_45_55_low = swing_low + range_size * 0.45
    mid_45_55_high = swing_low + range_size * 0.55
    
    close = df['Close'].iloc[-1]
    low = df['Low'].iloc[-1]
    high = df['High'].iloc[-1]
    
    # Current zone
    if close > high_70: zone = "premium"
    elif close < low_30: zone = "discount"
    else: zone = "equilibrium"
    
    # Tap checks - did price tap premium/discount and return?
    premium_tap = high >= high_70 and close < high_70 # tapped premium then rejected
    discount_tap = low <= low_30 and close > low_30 # tapped discount then rejected
    eq_tap = mid_45_55_low <= close <= mid_45_55_high # equilibrium tap for entries
    
    return {"zone":zone, "premium_tap":premium_tap, "discount_tap":discount_tap, "eq_tap":eq_tap, "high_70":high_70, "low_30":low_30}

def check_generic_sweep(df_1h):
    """Option A: Generic liquidity sweep - any session, last 6H sweep of prev range"""
    if df_1h is None or len(df_1h) < 30: return False, "No sweep"
    # Previous 20H range (approx Asia or previous session)
    prev_range = df_1h.iloc[-24:-6] if len(df_1h) >=30 else df_1h.iloc[:-6]
    if prev_range.empty: return False, "No prev range"
    prev_high = prev_range['High'].max()
    prev_low = prev_range['Low'].min()
    last = df_1h.iloc[-3:] # last 3 hours
    swept_high = any((r['High'] > prev_high and r['Close'] < prev_high) for _, r in last.iterrows())
    swept_low = any((r['Low'] < prev_low and r['Close'] > prev_low) for _, r in last.iterrows())
    if swept_high: return True, f"Bearish sweep of {prev_high:.2f}"
    if swept_low: return True, f"Bullish sweep of {prev_low:.2f}"
    return False, "No sweep yet"

def full_multi_tf_analysis(symbol):
    try:
        # Data
        df_daily = get_df(symbol, period="3mo", interval="1d")
        df_4h = get_df(symbol, period="1mo", interval="4h")
        df_1h = get_df(symbol, period="5d", interval="1h")
        df_15m = get_df(symbol, period="3d", interval="15m")
        
        if df_1h is None or df_15m is None:
            return {"signal":False, "symbol":symbol, "reason":"No data"}
        
        score = 0
        confluence = []
        bias = "NEUTRAL"
        
        # 1. DAILY PREMIUM/DISCOUNT
        daily_pd = premium_discount_zones(df_daily)
        confluence.append(f"Daily {daily_pd['zone']} zone")
        if daily_pd['zone'] == "discount": bias = "BULLISH"
        if daily_pd['zone'] == "premium": bias = "BEARISH"
        if daily_pd['zone'] == "discount": score+=1
        if daily_pd['zone'] == "premium": score+=1
        
        # 2. 4H PREMIUM/DISCOUNT + BOS
        four_pd = premium_discount_zones(df_4h)
        if four_pd['zone'] == daily_pd['zone']: 
            score+=1
            confluence.append(f"4H aligns {four_pd['zone']}")
        
        # BOS 4H
        if df_4h is not None and len(df_4h) >=10:
            last_high = df_4h['High'].iloc[-10:-1].max()
            last_low = df_4h['Low'].iloc[-10:-1].min()
            if df_4h['Close'].iloc[-1] > last_high:
                score+=1
                confluence.append("4H BOS bullish")
                if bias=="NEUTRAL": bias="BULLISH"
            elif df_4h['Close'].iloc[-1] < last_low:
                score+=1
                confluence.append("4H BOS bearish")
                if bias=="NEUTRAL": bias="BEARISH"
        
        # 3. GENERIC SWEEP (Option A)
        swept, sweep_msg = check_generic_sweep(df_1h)
        if swept:
            score+=1
            confluence.append(f"Sweep: {sweep_msg}")
        
        # 4. 1H PREMIUM/DISCOUNT TAP - ENTRY CONDITION
        one_pd = premium_discount_zones(df_1h)
        entry_tap = False
        if one_pd['discount_tap'] and bias!="BEARISH":
            score+=1
            confluence.append(f"1H Discount tap {one_pd['low_30']:.2f} -> BUY entry")
            entry_tap = True
            if bias=="NEUTRAL": bias="BULLISH"
        if one_pd['premium_tap'] and bias!="BULLISH":
            score+=1
            confluence.append(f"1H Premium tap {one_pd['high_70']:.2f} -> SELL entry")
            entry_tap = True
            if bias=="NEUTRAL": bias="BEARISH"
        if one_pd['eq_tap']:
            score+=0.5
            confluence.append("1H Equilibrium retest")
        
        # 5. 15M ENTRY CONFIRM
        fifteen_pd = premium_discount_zones(df_15m)
        if fifteen_pd['discount_tap'] or fifteen_pd['eq_tap']:
            if bias=="BULLISH": 
                score+=1
                confluence.append("15m Discount tap confirm BUY")
                entry_tap=True
        if fifteen_pd['premium_tap'] or fifteen_pd['eq_tap']:
            if bias=="BEARISH":
                score+=1
                confluence.append("15m Premium tap confirm SELL")
                entry_tap=True
        
        # 6. RSI filter (not strict)
        try:
            rsi = 50
            delta = df_1h['Close'].diff()
            gain = delta.where(delta>0,0).rolling(14).mean()
            loss = -delta.where(delta<0,0).rolling(14).mean()
            rs = gain/loss
            rsi = 100 - (100/(1+rs))
            rsi_val = rsi.iloc[-1]
            if 40 <= rsi_val <= 65:
                score+=0.5
                confluence.append(f"RSI {rsi_val:.0f} healthy")
        except:
            pass
        
        # FINAL DECISION
        if bias=="NEUTRAL":
            return {"signal":False, "symbol":symbol, "score":score, "reason":"No clear premium/discount bias"}
        
        if not entry_tap:
            return {"signal":False, "symbol":symbol, "score":score, "reason":f"No premium/discount tap - Daily {daily_pd['zone']}, 1H {one_pd['zone']}"}
        
        if score < MIN_SCORE:
            return {"signal":False, "symbol":symbol, "score":score, "confluence":confluence, "reason":f"Score {score}<{MIN_SCORE}"}
        
        # Build entry
        close = float(df_1h['Close'].iloc[-1])
        atr = (df_1h['High'] - df_1h['Low']).rolling(14).mean().iloc[-1]
        if math.isnan(atr): atr = close*0.002
        
        direction = "BUY" if bias=="BULLISH" else "SELL"
        if direction=="BUY":
            entry = close
            sl = min(float(df_1h['Low'].tail(5).min()), close - atr*1.5)
            tp = entry + (entry-sl)*3  # RR 1:3 default
        else:
            entry = close
            sl = max(float(df_1h['High'].tail(5).max()), close + atr*1.5)
            tp = entry - (sl-entry)*3
        
        return {
            "signal":True,
            "symbol":symbol,
            "direction":direction,
            "entry":round(entry,2),
            "sl":round(sl,2),
            "tp":round(tp,2),
            "score":round(score,1),
            "bias":f"{bias} | D:{daily_pd['zone']} 4H:{four_pd['zone']} 1H:{one_pd['zone']}",
            "confluence":confluence,
            "reason":f"Price tapped {'discount' if direction=='BUY' else 'premium'} zone on 1H/15m + {sweep_msg}. Daily {daily_pd['zone']} bias.",
            "blocked":None
        }
    except Exception as e:
        return {"signal":False, "symbol":symbol, "reason":f"Error {str(e)[:100]}"}

# Keep old name for compat
def analyze_symbol(symbol):
    return full_multi_tf_analysis(symbol)
