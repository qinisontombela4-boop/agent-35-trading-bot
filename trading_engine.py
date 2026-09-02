import yfinance as yf
import pandas as pd
import math

MAP = {"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"JPY=X","USDZAR":"ZAR=X","EURZAR":"EURZAR=X","XAUUSD":"GC=F","GOLD":"GC=F","BTCUSD":"BTC-USD","ETHUSD":"ETH-USD","NAS100":"^NDX","US30":"^DJI","SPX500":"^GSPC","GER40":"^GDAXI","USOIL":"CL=F","XAGUSD":"SI=F","GBPJPY":"GBPJPY=X","EURJPY":"EURJPY=X"}
MIN_SCORE = 4

def get_df(symbol, period="5d", interval="1h"):
    try:
        yfs = MAP.get(symbol.upper(), symbol.upper()+"=X")
        fetch_interval = interval
        if interval == "2h":
            fetch_interval = "1h"
        df = yf.download(yfs, period=period, interval=fetch_interval, progress=False, auto_adjust=True)
        if df.empty:
            return None
        try:
            df.columns = df.columns.get_level_values(0)
        except:
            pass
        df = df.dropna()
        if interval == "2h" and df is not None and len(df) > 0:
            df.index = pd.to_datetime(df.index)
            df_2h = df.resample('2h').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            return df_2h
        return df
    except:
        return None

def pd_zone(price, high, low):
    if high == low:
        return "equilibrium", 50
    pos = (price - low) / (high - low) * 100
    if pos >= 70:
        return "premium", pos
    elif pos <= 30:
        return "discount", pos
    else:
        return "equilibrium", pos

def premium_discount_zones(df):
    if df is None or len(df) < 20:
        return {"zone":"neutral", "tap":False, "eq_tap":False, "pct":50, "high":0, "low":0}
    recent = df.tail(50)
    swing_high = float(recent['High'].max())
    swing_low = float(recent['Low'].min())
    rng = swing_high - swing_low
    if rng == 0:
        return {"zone":"neutral","tap":False,"eq_tap":False,"pct":50,"high":swing_high,"low":swing_low,"high_70":swing_high,"low_30":swing_low}
    
    close = float(df['Close'].iloc[-1])
    low = float(df['Low'].iloc[-1])
    high = float(df['High'].iloc[-1])
    
    zone, pct = pd_zone(close, swing_high, swing_low)
    
    high_70 = swing_low + rng*0.7
    low_30 = swing_low + rng*0.3
    mid_low = swing_low + rng*0.45
    mid_high = swing_low + rng*0.55
    
    tap = (high >= high_70 and close < high_70) or (low <= low_30 and close > low_30)
    eq_tap = mid_low <= close <= mid_high

    return {"zone":zone, "tap": tap or eq_tap, "eq_tap": eq_tap, "pct": round(pct,1), "high":swing_high, "low":swing_low, "high_70":high_70, "low_30":low_30}

def check_sweep(df):
    if df is None or len(df) < 30:
        return False, "No sweep"
    prev = df.iloc[-24:-6]
    if prev.empty:
        return False, "No range"
    ph = float(prev['High'].max())
    pl = float(prev['Low'].min())
    last3 = df.iloc[-3:]
    swept_h = any(float(r['High']) > ph and float(r['Close']) < ph for _, r in last3.iterrows())
    swept_l = any(float(r['Low']) < pl and float(r['Close']) > pl for _, r in last3.iterrows())
    if swept_h:
        return True, f"Swept High {ph:.2f}"
    if swept_l:
        return True, f"Swept Low {pl:.2f}"
    return False, "No sweep"

def full_multi_tf_analysis(symbol):
    try:
        df_d = get_df(symbol, "3mo", "1d")
        df_4h = get_df(symbol, "1mo", "4h")
        df_2h = get_df(symbol, "5d", "2h")
        df_1h = get_df(symbol, "5d", "1h")
        df_15m = get_df(symbol, "3d", "15m")
        df_5m = get_df(symbol, "2d", "5m")

        if df_1h is None or df_15m is None:
            return {"signal":False, "symbol":symbol, "reason":"No data"}

        score = 0
        conf = []

        d = premium_discount_zones(df_d)
        h4 = premium_discount_zones(df_4h)
        h2 = premium_discount_zones(df_2h)
        h1 = premium_discount_zones(df_1h)
        m15 = premium_discount_zones(df_15m)
        m5 = premium_discount_zones(df_5m)

        htf_zones = [h4['zone'], h2['zone'], h1['zone']]
        discount_count = htf_zones.count("discount")
        premium_count = htf_zones.count("premium")
        conf.append(f"4H:{h4['zone']}({h4['pct']}%) 2H:{h2['zone']}({h2['pct']}%) 1H:{h1['zone']}({h1['pct']}%)")

        bias = "NEUTRAL"
        if discount_count >= 2:
            bias = "BULLISH"
            score += 2
            conf.append(f"HTF DISCOUNT {discount_count}/3 -> BUY bias")
        elif premium_count >= 2:
            bias = "BEARISH"
            score += 2
            conf.append(f"HTF PREMIUM {premium_count}/3 -> SELL bias")
        elif d['zone'] == "discount":
            bias = "BULLISH"
            score += 1
            conf.append(f"Daily {d['zone']}")
        elif d['zone'] == "premium":
            bias = "BEARISH"
            score += 1
            conf.append(f"Daily {d['zone']}")

        for name, df in [("4H", df_4h), ("1H", df_1h)]:
            if df is not None and len(df) >= 10:
                lh = float(df['High'].iloc[-10:-1].max())
                ll = float(df['Low'].iloc[-10:-1].min())
                c = float(df['Close'].iloc[-1])
                if c > lh and bias != "BEARISH":
                    score += 1
                    conf.append(f"{name} BOS bullish")
                if c < ll and bias != "BULLISH":
                    score += 1
                    conf.append(f"{name} BOS bearish")

        swept, sweep_msg = check_sweep(df_1h)
        if swept:
            score += 1
            conf.append(sweep_msg)

        # --- STRICT LTF FILTER (NO CHASING) ---
        entry_ok = False
        
        if bias == "BULLISH":
            # BLOCK if LTF is premium - waiting for pullback
            if m5['zone'] == "premium" and m15['zone'] == "premium":
                return {"signal":False, "symbol":symbol, "score":round(score,1), "reason":f"BLOCKED: HTF DISCOUNT {discount_count}/3 but 5M {m5['pct']}% & 15M {m15['pct']}% PREMIUM - waiting for discount pullback", "zones":conf}
            # ENTRY only when LTF enters discount
            if m5['zone'] == "discount" or m15['zone'] == "discount":
                entry_ok = True
                score += 1.5
                conf.append(f"ENTRY PULLBACK 5M:{m5['zone']}({m5['pct']}%) 15M:{m15['zone']}({m15['pct']}%) -> BUY")
            elif m5['eq_tap'] or m15['eq_tap']:
                entry_ok = True
                score += 1
                conf.append(f"ENTRY EQ 5M:{m5['pct']}% 15M:{m15['pct']}% -> BUY")

        elif bias == "BEARISH":
            if m5['zone'] == "discount" and m15['zone'] == "discount":
                return {"signal":False, "symbol":symbol, "score":round(score,1), "reason":f"BLOCKED: HTF PREMIUM {premium_count}/3 but 5M {m5['pct']}% & 15M {m15['pct']}% DISCOUNT - waiting for premium rally", "zones":conf}
            if m5['zone'] == "premium" or m15['zone'] == "premium":
                entry_ok = True
                score += 1.5
                conf.append(f"ENTRY PULLBACK 5M:{m5['zone']}({m5['pct']}%) 15M:{m15['zone']}({m15['pct']}%) -> SELL")
            elif m5['eq_tap'] or m15['eq_tap']:
                entry_ok = True
                score += 1
                conf.append(f"ENTRY EQ 5M:{m5['pct']}% 15M:{m15['pct']}% -> SELL")

        if bias == "NEUTRAL":
            return {"signal":False, "symbol":symbol, "score":round(score,1), "zones":conf, "reason":f"No HTF bias - 4H {h4['zone']} 2H {h2['zone']} 1H {h1['zone']}"}

        if not entry_ok:
            return {"signal":False, "symbol":symbol, "score":round(score,1), "zones":conf, "reason":f"Waiting for LTF pullback - 15M {m15['zone']}({m15['pct']}%) 5M {m5['zone']}({m5['pct']}%) | Need { 'discount' if bias=='BULLISH' else 'premium' } for {bias}"}

        if score < MIN_SCORE:
            return {"signal":False, "symbol":symbol, "score":round(score,1), "confluence":conf, "reason":f"Score {score}<{MIN_SCORE}"}

        close = float(df_1h['Close'].iloc[-1])
        atr = float((df_1h['High'] - df_1h['Low']).rolling(14).mean().iloc[-1])
        if math.isnan(atr):
            atr = close * 0.002

        direction = "BUY" if bias == "BULLISH" else "SELL"
        if direction == "BUY":
            entry = close
            sl = min(float(df_1h['Low'].tail(5).min()), close - atr*1.5)
            tp = entry + (entry - sl) * 3
        else:
            entry = close
            sl = max(float(df_1h['High'].tail(5).max()), close + atr*1.5)
            tp = entry - (sl - entry) * 3

        return {
            "signal":True,
            "symbol":symbol,
            "direction":direction,
            "entry":round(entry,2),
            "sl":round(sl,2),
            "tp":round(tp,2),
            "score":round(score,1),
            "bias":f"{bias} | 4H:{h4['zone']}({h4['pct']}%) 2H:{h2['zone']}({h2['pct']}%) 1H:{h1['zone']}({h1['pct']}%) | 5M:{m5['zone']}({m5['pct']}%) 15M:{m15['zone']}({m15['pct']}%)",
            "confluence":conf,
            "zones":conf,
            "reason":f"HTF {'DISCOUNT' if bias=='BULLISH' else 'PREMIUM'} {discount_count if bias=='BULLISH' else premium_count}/3 + LTF PULLBACK into {m5['zone']} + {sweep_msg}",
            "blocked":None
        }
    except Exception as e:
        return {"signal":False, "symbol":symbol, "reason":f"Error {str(e)[:120]}"}

def analyze_symbol(symbol):
    return full_multi_tf_analysis(symbol)
