"""
Agent 35 - Trading Engine V12.6.2 - FIXED RATE LIMIT + CACHING
FIXED: JPY=3 decimals, Gold=2, Forex=5
DUAL FREE with caching to avoid 429 limit
"""

MAP = {
    "XAUUSD": "XAUUSD", "GOLD": "XAUUSD",
    "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY",
    "EURJPY": "EUR/JPY", "GBPJPY": "GBP/JPY", "EURGBP": "EUR/GBP",
    "USDZAR": "USD/ZAR", "EURZAR": "EUR/ZAR", "GBPZAR": "GBP/ZAR",
    "ZARJPY": "ZAR/JPY", "USDCHF": "USD/CHF",
    "XAGUSD": "XAG/USD", "BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD",
    "SOLUSD": "SOL/USD", "NAS100": "QQQ", "US30": "DIA",
    "SPX500": "SPX", "GER40": "DAX", "UK100": "UKX", "JP225": "JPX",
    "USOIL": "WTI", "UKOIL": "BRENT", "AAPL": "AAPL", "TSLA": "TSLA",
    "NVDA": "NVDA", "MSFT": "MSFT"
}

import os, requests, pandas as pd, time
from datetime import datetime

FINNHUB_KEY = os.environ.get('FINNHUB_API_KEY', '').strip()
TWELVE_KEY = os.environ.get('TWELVEDATA_API_KEY', '').strip()

_cache = {}
_cache_time = {}

def get_pip_settings(symbol):
    s = symbol.upper()
    if "JPY" in s: return {"pip": 0.01, "sl_pips": 15, "sl_dist": 0.150, "decimals": 3}
    if "XAU" in s or "GOLD" in s: return {"pip": 0.10, "sl_pips": 25, "sl_dist": 2.5, "decimals": 2}
    if "XAG" in s: return {"pip": 0.01, "sl_pips": 20, "sl_dist": 0.15, "decimals": 3}
    if "BTC" in s: return {"pip": 10.0, "sl_pips": 15, "sl_dist": 150.0, "decimals": 2}
    if "ETH" in s: return {"pip": 0.10, "sl_pips": 20, "sl_dist": 20.0, "decimals": 2}
    if "NAS" in s or "US30" in s or "SPX" in s or "GER" in s or "UK100" in s or "JP225" in s:
        return {"pip": 1.0, "sl_pips": 30, "sl_dist": 30.0, "decimals": 2}
    if "USOIL" in s or "UKOIL" in s: return {"pip": 0.01, "sl_pips": 20, "sl_dist": 0.40, "decimals": 2}
    return {"pip": 0.0001, "sl_pips": 10, "sl_dist": 0.0010, "decimals": 5}

def fetch_candles(symbol, interval="5min", outputsize=100):
    global _cache, _cache_time
    clean_sym = MAP.get(symbol.upper(), symbol.upper())
    cache_key = f"{clean_sym}_{interval}"

    if interval in ["4h","1day","1h"] and cache_key in _cache:
        if time.time() - _cache_time.get(cache_key,0) < 3600:
            return _cache[cache_key]

    if not TWELVE_KEY:
        print(f"CRITICAL: TWELVEDATA_API_KEY missing!")
        return pd.DataFrame()

    try:
        url = f"https://api.twelvedata.com/time_series?symbol={clean_sym}&interval={interval}&outputsize={outputsize}&apikey={TWELVE_KEY}"
        r = requests.get(url, timeout=12).json()
        if 'code' in r and r['code']==429:
            print(f"TwelveData 429 LIMIT HIT {symbol} {interval}: {r.get('message')}")
            return _cache.get(cache_key, pd.DataFrame())
        if 'values' in r and r['values'] and len(r['values']) > 10:
            df = pd.DataFrame(r['values'])
            rename_map = {'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'datetime': 'Date'}
            df = df.rename(columns=rename_map)
            for col in ['Open', 'High', 'Low', 'Close']:
                df[col] = df[col].astype(float)
            df = df.iloc[::-1].reset_index(drop=True)
            _cache[cache_key]=df
            _cache_time[cache_key]=time.time()
            return df
        else:
            print(f"TwelveData no values {symbol} {interval}: {r}")
    except Exception as e:
        print(f"TwelveData error {symbol} {interval}: {e}")

    return _cache.get(cache_key, pd.DataFrame())

def fetch_quote(symbol):
    clean_sym = MAP.get(symbol.upper().replace("GOLD","XAUUSD"), symbol.upper())
    if TWELVE_KEY:
        try:
            url = f"https://api.twelvedata.com/quote?symbol={clean_sym}&apikey={TWELVE_KEY}"
            r = requests.get(url, timeout=8).json()
            if 'close' in r and float(r['close'])>0:
                return float(r['close']), float(r.get('high', r['close'])), float(r.get('low', r['close']))
        except: pass
    return None

def calculate_premium_discount(df):
    try:
        if df.empty or len(df)<2: return 50,"EQ"
        high=df['High'].max(); low=df['Low'].min(); close=float(df['Close'].iloc[-1])
        rng=high-low
        if rng==0: return 50,"EQ"
        pct=((close-low)/rng*100)
        if pct<30: return pct,"DISCOUNT"
        if pct>70: return pct,"PREMIUM"
        return pct,"EQ"
    except: return 50,"EQ"

def detect_fvg(df):
    try:
        if len(df)<5: return None,None
        c1=df.iloc[-3]; c2=df.iloc[-2]; c3=df.iloc[-1]
        if c1['High']<c3['Low'] and c2['Close']>c2['Open']: return "BULLFVG",float(c3['Low'])
        if c1['Low']>c3['High'] and c2['Close']<c2['Open']: return "BEARFVG",float(c3['High'])
        return None,None
    except: return None,None

def detect_order_block(df):
    try:
        if len(df)<10: return None
        for i in range(len(df)-3,len(df)-8,-1):
            c=df.iloc[i]; next_c=df.iloc[i+1]
            if c['Close']<c['Open'] and next_c['Close']>next_c['Open'] and (next_c['Close']-next_c['Open'])>(c['Open']-c['Close']):
                return "BULL_OB",float(c['Low'])
            if c['Close']>c['Open'] and next_c['Close']<next_c['Open'] and (next_c['Open']-next_c['Close'])>(c['Close']-c['Open']):
                return "BEAR_OB",float(c['High'])
        return None
    except: return None

def detect_bos_choch(df):
    try:
        if len(df)<20: return None,None
        recent_high=df['High'].iloc[-20:-5].max(); recent_low=df['Low'].iloc[-20:-5].min()
        close=float(df['Close'].iloc[-1])
        if close>recent_high: return "BULLBOS",recent_high
        if close<recent_low: return "BEARBOS",recent_low
        last_high=df['High'].iloc[-10:-1].max(); last_low=df['Low'].iloc[-10:-1].min()
        if close>last_high and df['Low'].iloc[-15]<df['Low'].iloc[-10]: return "BULLCHOCH",last_high
        if close<last_low and df['High'].iloc[-15]>df['High'].iloc[-10]: return "BEARCHOCH",last_low
        return None,None
    except: return None,None

def check_news_block(symbol, use_filter=True):
    if not use_filter: return False,""
    return False,""

def full_multi_tf_analysis(symbol, rr_target=2.5, use_news_filter=True):
    try:
        df5=fetch_candles(symbol,"5min",100)
        df15=fetch_candles(symbol,"15min",80)
        df1h=fetch_candles(symbol,"1h",80)
        df4h=fetch_candles(symbol,"4h",80)
        dfD=fetch_candles(symbol,"1day",30)

        if df5.empty or len(df5)<20:
            return {"signal":False,"symbol":symbol,"reason":f"No 5M data - KEY set? {bool(TWELVE_KEY)} - limit hit","score":0,"news_block":False,"quality":"NO_DATA"}

        close_5m=float(df5['Close'].iloc[-1])
        pip_cfg=get_pip_settings(symbol)
        sl_dist=pip_cfg["sl_dist"]; tp_dist=sl_dist*rr_target; dec=pip_cfg["decimals"]

        daily_pct,daily_zone=calculate_premium_discount(dfD) if not dfD.empty else (50,"EQ")
        h4_pct,h4_zone=calculate_premium_discount(df4h) if not df4h.empty else (50,"EQ")

        bos_choch_5m,level_5m=detect_bos_choch(df5)
        fvg_15m,fvg_level_15m=detect_fvg(df15) if not df15.empty else (None,None)
        ob_15m=detect_order_block(df15) if not df15.empty else None

        news_block,news_msg=check_news_block(symbol,use_news_filter)
        if news_block:
            return {"signal":False,"symbol":symbol,"reason":f"News block: {news_msg}","score":0,"news_block":True,"news_warning":news_msg}

        score=0; confluence=[]; direction=None
        confluence.append(f"HTF: Daily {daily_zone} {daily_pct:.0f}% | 4H {h4_zone} {h4_pct:.0f}%")
        if daily_zone in ["DISCOUNT","PREMIUM"]: score+=2
        if h4_zone==daily_zone and h4_zone!="EQ":
            score+=1; confluence.append(f"✅ 4H {h4_zone} {h4_pct:.0f}% aligned")

        if bos_choch_5m:
            if "BULL" in bos_choch_5m and daily_zone=="DISCOUNT":
                direction="BUY"; confluence.append(f"🔥 5M SHIFT: {bos_choch_5m} in {daily_zone}"); score+=3
            elif "BEAR" in bos_choch_5m and daily_zone=="PREMIUM":
                direction="SELL"; confluence.append(f"🔥 5M SHIFT: {bos_choch_5m} in {daily_zone}"); score+=3
            else:
                confluence.append(f"⚠️ 5M {bos_choch_5m} vs HTF {daily_zone}"); score+=1
        else:
            if daily_zone=="DISCOUNT":
                direction="BUY"; confluence.append(f"🔥 5M: Price in DISCOUNT {daily_pct:.0f}%"); score+=1
            elif daily_zone=="PREMIUM":
                direction="SELL"; confluence.append(f"🔥 5M: Price in PREMIUM {daily_pct:.0f}%"); score+=1

        if fvg_15m:
            if fvg_15m=="BULLFVG" and direction=="BUY": confluence.append(f"✅ 15M {fvg_15m}"); score+=2
            elif fvg_15m=="BEARFVG" and direction=="SELL": confluence.append(f"✅ 15M {fvg_15m}"); score+=2

        if daily_zone!="EQ":
            confluence.append(f"✅ Daily {daily_zone} {daily_pct:.0f}%")
            score+=1
        if ob_15m:
            ob_type=ob_15m[0] if isinstance(ob_15m,tuple) else str(ob_15m)
            if "BULL" in ob_type and direction=="BUY": confluence.append(f"✅ {ob_type}"); score+=1
            elif "BEAR" in ob_type and direction=="SELL": confluence.append(f"✅ {ob_type}"); score+=1

        if not direction or score<4:
            return {"signal":False,"symbol":symbol,"reason":f"No edge - {daily_zone} {daily_pct:.0f}% Score {score}/8","score":score,"news_block":False,"quality":"NO_SETUP"}

        entry=round(close_5m,dec)
        if direction=="BUY": sl=round(entry-sl_dist,dec); tp=round(entry+tp_dist,dec)
        else: sl=round(entry+sl_dist,dec); tp=round(entry-tp_dist,dec)

        if score>=8: quality="🔥 SNIPER SHIFT 8/8"
        elif score>=6: quality="PREMIUM 🔥 SHIFT"
        elif score>=4: quality="STANDARD"
        else: quality="LOW"

        reason_str=f"HTF {daily_zone} + 5M {bos_choch_5m or 'PRICE'} + {fvg_15m or 'FVG'} | Score {score}/8 | V12.6.2 FIXED"
        return {"signal":True,"symbol":symbol,"direction":direction,"entry":entry,"sl":sl,"tp":tp,"score":score,"quality":quality,"bias":f"{daily_zone} {daily_pct:.0f}% | 4H {h4_zone} {h4_pct:.0f}% - {direction} bias - V12.6.2","confluence":confluence,"reason":reason_str,"news_block":False,"news_warning":"","daily_pct":daily_pct,"h4_pct":h4_pct}
    except Exception as e:
        import traceback; print(f"Engine error {symbol}: {traceback.format_exc()}")
        return {"signal":False,"symbol":symbol,"reason":f"Engine Error {e}","score":0,"news_block":False,"quality":"ERROR"}
