"""
Agent 35 - V12.6 DUAL FREE - Finnhub (60/min) + TwelveData (8/min)
- Uses Finnhub for Forex first (fastest, no block)
- Uses TwelveData for Gold/Crypto/Indices
- R0 forever, 10 pairs every 5 min
"""

import os
import time
import random
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

TD_API_KEY = os.environ.get('TWELVEDATA_API_KEY', 'demo')
FH_API_KEY = os.environ.get('FINNHUB_API_KEY', '')
TD_BASE = "https://api.twelvedata.com"

# Symbol maps
TD_MAP = {
    "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY", "EURJPY": "EUR/JPY",
    "GBPJPY": "GBP/JPY", "USDZAR": "USD/ZAR", "EURZAR": "EUR/ZAR", "GBPZAR": "GBP/ZAR",
    "ZARJPY": "ZAR/JPY", "USDCHF": "USD/CHF",
    "XAUUSD": "XAU/USD", "GOLD": "XAU/USD", "XAGUSD": "XAG/USD",
    "BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD",
    "NAS100": "NDX", "US30": "DJI", "GER40": "DAX"
}

FH_MAP = {
    "EURUSD": "OANDA:EUR_USD", "GBPUSD": "OANDA:GBP_USD", "USDJPY": "OANDA:USD_JPY",
    "EURJPY": "OANDA:EUR_JPY", "GBPJPY": "OANDA:GBP_JPY", "USDZAR": "OANDA:USD_ZAR",
    "EURZAR": "OANDA:EUR_ZAR", "GBPZAR": "OANDA:GBP_ZAR", "USDCHF": "OANDA:USD_CHF",
    "XAUUSD": "OANDA:XAU_USD", "XAGUSD": "OANDA:XAG_USD",
    "BTCUSD": "BINANCE:BTCUSDT", "ETHUSD": "BINANCE:ETHUSDT"
}

INTERVAL_MAP_TD = {"5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1day"}
INTERVAL_MAP_FH = {"5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D"}

def get_data_finnhub(symbol, period="5d", interval="5m"):
    """Finnhub - 60 req/min FREE"""
    if not FH_API_KEY:
        return None
    fh_symbol = FH_MAP.get(symbol.upper())
    if not fh_symbol:
        return None # Not forex/gold/crypto, let TwelveData handle

    td_interval = INTERVAL_MAP_FH.get(interval, "5")
    # period -> from timestamp
    days_map = {"5d": 5, "10d": 10, "1mo": 30, "3mo": 90, "6mo": 180}
    days = days_map.get(period, 5)

    try:
        now = int(datetime.utcnow().timestamp())
        from_ts = int((datetime.utcnow() - timedelta(days=days+2)).timestamp())

        url = "https://finnhub.io/api/v1/forex/candle"
        # For crypto use different endpoint
        if "BINANCE" in fh_symbol:
            url = "https://finnhub.io/api/v1/crypto/candle"

        params = {
            "symbol": fh_symbol,
            "resolution": td_interval,
            "from": from_ts,
            "to": now,
            "token": FH_API_KEY
        }
        time.sleep(0.4) # respect 60/min = 1 per sec safe
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        if data.get("s")!= "ok" or "c" not in data:
            # print(f"FH fail {symbol} {fh_symbol}: {data}")
            return None

        df = pd.DataFrame({
            "Open": data["o"],
            "High": data["h"],
            "Low": data["l"],
            "Close": data["c"],
            "Volume": data.get("v", [0]*len(data["c"]))
        })
        df["datetime"] = pd.to_datetime(data["t"], unit='s')
        df.set_index("datetime", inplace=True)
        df = df.astype(float)
        if len(df) < 20:
            return None
        return df
    except Exception as e:
        print(f"Finnhub error {symbol}: {e}")
        return None

def get_data_twelvedata(symbol, period="5d", interval="5m"):
    """TwelveData - 8 req/min FREE fallback"""
    td_symbol = TD_MAP.get(symbol.upper(), symbol.upper())
    td_interval = INTERVAL_MAP_TD.get(interval, "5min")
    size_map = {"5d": "500", "10d": "500", "1mo": "500", "3mo": "400", "6mo": "500"}
    outputsize = size_map.get(period, "500")
    if td_interval == "4h":
        outputsize = "300"

    try:
        time.sleep(random.uniform(0.8, 1.2))
        url = f"{TD_BASE}/time_series"
        params = {"symbol": td_symbol, "interval": td_interval, "outputsize": outputsize, "apikey": TD_API_KEY, "format": "JSON"}
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if "values" not in data:
            if "limit" in str(data).lower():
                print("TD rate limited")
                time.sleep(30)
            return None
        values = data["values"]
        df = pd.DataFrame(values)
        df = df.iloc[::-1]
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)
        df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
        for col in ["Open", "High", "Low", "Close"]:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)
        if len(df) < 20:
            return None
        return df
    except Exception as e:
        print(f"TD error {symbol}: {e}")
        return None

def get_data(symbol, period="5d", interval="5m"):
    """DUAL: Try Finnhub first (faster), then TwelveData"""
    # Forex/Gold/BTC -> Finnhub first
    if symbol.upper() in FH_MAP:
        df = get_data_finnhub(symbol, period, interval)
        if df is not None and len(df) > 20:
            return df
        # Fallback to TD
        print(f"FH failed for {symbol}, trying TD...")

    df = get_data_twelvedata(symbol, period, interval)
    return df

def calc_atr(df, p=14):
    try:
        high = df['High']; low = df['Low']; close = df['Close']
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        return tr.rolling(p).mean().iloc[-1]
    except:
        return 0

def get_swing_structure(df, length=10):
    if df is None or len(df) < length*3: return None
    try:
        highs = df['High'].rolling(window=length*2+1, center=True).max()
        lows = df['Low'].rolling(window=length*2+1, center=True).min()
        is_sh = df['High'] == highs; is_sl = df['Low'] == lows
        sh = df[is_sh].tail(3); sl = df[is_sl].tail(3)
        if len(sh)<2 or len(sl)<2: return None
        return {"last_high": sh['High'].iloc[-1], "prev_high": sh['High'].iloc[-2], "last_low": sl['Low'].iloc[-1], "prev_low": sl['Low'].iloc[-2],
                "hh": sh['High'].iloc[-1] > sh['High'].iloc[-2], "hl": sl['Low'].iloc[-1] > sl['Low'].iloc[-2],
                "ll": sl['Low'].iloc[-1] < sl['Low'].iloc[-2], "lh": sh['High'].iloc[-1] < sh['High'].iloc[-2]}
    except: return None

def detect_bos_choch(df, length=10):
    st = get_swing_structure(df, length)
    if not st: return {"trend": "NEUTRAL", "signal": None, "is_shift": False, "last_high": 0, "last_low": 0}
    close = df['Close'].iloc[-1]
    try:
        if close > st['last_high']:
            if st['last_high'] > st['prev_high']: return {"trend": "BULL", "signal": "BULL_BOS", "is_shift": False, "last_high": st['last_high'], "last_low": st['last_low']}
            else: return {"trend": "BULL", "signal": "BULL_CHOCH", "is_shift": True, "last_high": st['last_high'], "last_low": st['last_low']}
        if close < st['last_low']:
            if st['last_low'] < st['prev_low']: return {"trend": "BEAR", "signal": "BEAR_BOS", "is_shift": False, "last_high": st['last_high'], "last_low": st['last_low']}
            else: return {"trend": "BEAR", "signal": "BEAR_CHOCH", "is_shift": True, "last_high": st['last_high'], "last_low": st['last_low']}
        if st['hh'] and st['hl']: return {"trend": "BULL", "signal": None, "is_shift": False, "last_high": st['last_high'], "last_low": st['last_low']}
        if st['ll'] and st['lh']: return {"trend": "BEAR", "signal": None, "is_shift": False, "last_high": st['last_high'], "last_low": st['last_low']}
        return {"trend": "NEUTRAL", "signal": None, "is_shift": False, "last_high": st['last_high'], "last_low": st['last_low']}
    except: return {"trend": "NEUTRAL", "signal": None, "is_shift": False, "last_high": 0, "last_low": 0}

def detect_ob(df):
    if df is None or len(df)<25: return None
    try:
        for i in range(len(df)-6, len(df)-20, -1):
            c = df.iloc[i]
            if c['Close'] < c['Open']:
                future = df.iloc[i+1:i+4]
                if len(future)<3: continue
                if future['Close'].max() > c['High']*1.0008:
                    after = df.iloc[i+4:]
                    mitigated = (after['Low'].min() <= c['High']) if len(after)>0 else False
                    return {"type": "BULL_MB_BREAKER" if mitigated else "BULL_OB", "high": float(c['High']), "low": float(c['Low']), "mitigated": mitigated}
            if c['Close'] > c['Open']:
                future = df.iloc[i+1:i+4]
                if len(future)<3: continue
                if future['Close'].min() < c['Low']*0.9992:
                    after = df.iloc[i+4:]
                    mitigated = (after['High'].max() >= c['Low']) if len(after)>0 else False
                    return {"type": "BEAR_MB_BREAKER" if mitigated else "BEAR_OB", "high": float(c['High']), "low": float(c['Low']), "mitigated": mitigated}
        return None
    except: return None

def detect_fvg(df, min_atr_pct=0.12):
    if df is None or len(df)<5: return None
    try:
        atr = calc_atr(df,14)
        if atr==0 or pd.isna(atr): return None
        low=df['Low'].iloc[-1]; high=df['High'].iloc[-1]; high_2=df['High'].iloc[-3]; low_2=df['Low'].iloc[-3]; close=df['Close'].iloc[-1]
        bull_fvg = low > high_2; bear_fvg = high < low_2
        bull_size = (low-high_2)/atr*100; bear_size = (low_2-high)/atr*100
        if bull_fvg and bull_size>min_atr_pct:
            sl=low_2-0.0005; return {"type":"BULL_FVG","entry":float(close),"sl":float(sl),"risk":float(close-sl),"top":float(low),"bottom":float(high_2),"size":float(bull_size)}
        if bear_fvg and bear_size>min_atr_pct:
            sl=high_2+0.0005; return {"type":"BEAR_FVG","entry":float(close),"sl":float(sl),"risk":float(sl-close),"top":float(low_2),"bottom":float(high),"size":float(bear_size)}
        return None
    except: return None

def get_premium_discount(df_htf):
    if df_htf is None or len(df_htf)<50: return "EQUILIBRIUM",0.5,0,0
    try:
        hi=df_htf['High'].tail(50).max(); lo=df_htf['Low'].tail(50).min(); close=df_htf['Close'].iloc[-1]
        if hi==lo: return "EQUILIBRIUM",0.5,hi,lo
        pct=(close-lo)/(hi-lo); eq=(hi+lo)/2
        if pct>=0.7: return "PREMIUM",pct,eq,hi
        elif pct<=0.3: return "DISCOUNT",pct,eq,lo
        else: return "EQUILIBRIUM",pct,eq,(hi+lo)/2
    except: return "EQUILIBRIUM",0.5,0,0

def get_rsi(df, period=14):
    try:
        delta=df['Close'].diff(); gain=delta.where(delta>0,0).rolling(period).mean(); loss=-delta.where(delta<0,0).rolling(period).mean()
        rs=gain/loss; rsi=100-(100/(1+rs)); return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
    except: return 50.0

def full_multi_tf_analysis(symbol, use_news_filter=True, rr_target=2.5):
    try:
        df_5m=get_data(symbol, period="5d", interval="5m")
        if df_5m is None or len(df_5m)<50:
            return {"signal": False, "symbol": symbol, "reason": f"No 5m data - FH:{'yes' if FH_API_KEY else 'no'} TD:{'yes' if TD_API_KEY!='demo' else 'no'}", "score": 0}
        df_15m=get_data(symbol, period="10d", interval="15m")
        df_1h=get_data(symbol, period="1mo", interval="1h")
        df_4h=get_data(symbol, period="3mo", interval="4h")
        df_daily=get_data(symbol, period="6mo", interval="1d")

        zone_daily,pct_daily,eq_daily,_=get_premium_discount(df_daily if df_daily is not None else df_4h)
        zone_4h,pct_4h,eq_4h,_=get_premium_discount(df_4h if df_4h is not None else df_1h)
        struct_4h=detect_bos_choch(df_4h,10) if df_4h is not None else {"trend":"NEUTRAL","signal":None,"is_shift":False}
        struct_1h=detect_bos_choch(df_1h,10) if df_1h is not None else {"trend":"NEUTRAL","signal":None,"is_shift":False}
        struct_15m=detect_bos_choch(df_15m,10) if df_15m is not None else {"trend":"NEUTRAL","signal":None,"is_shift":False}
        struct_5m=detect_bos_choch(df_5m,10)
        fvg_5m=detect_fvg(df_5m,0.12); fvg_15m=detect_fvg(df_15m,0.12) if df_15m is not None else None
        ob_5m=detect_ob(df_5m); ob_15m=detect_ob(df_15m) if df_15m is not None else None
        rsi_5m=get_rsi(df_5m)
        htf_bull=struct_4h['trend']=="BULL" or struct_1h['trend']=="BULL"
        htf_bear=struct_4h['trend']=="BEAR" or struct_1h['trend']=="BEAR"
        confluence=[]; score=0; direction=None

        confluence.append(f"HTF: Daily {zone_daily} {pct_daily*100:.0f}% | 4H {zone_4h} {pct_4h*100:.0f}%")

        if struct_5m['is_shift'] and struct_5m['signal']:
            if "BULL_CHOCH" in struct_5m['signal']:
                if zone_daily=="DISCOUNT" or zone_4h=="DISCOUNT":
                    direction="BUY"; confluence.append(f"🔥 5M SHIFT: {struct_5m['signal']} in DISCOUNT - EARLY BULL"); score+=4
                else: direction="BUY"; confluence.append(f"⚡ 5M {struct_5m['signal']} - Potential Shift"); score+=2
            elif "BEAR_CHOCH" in struct_5m['signal']:
                if zone_daily=="PREMIUM" or zone_4h=="PREMIUM":
                    direction="SELL"; confluence.append(f"🔥 5M SHIFT: {struct_5m['signal']} in PREMIUM - EARLY BEAR"); score+=4
                else: direction="SELL"; confluence.append(f"⚡ 5M {struct_5m['signal']} - Potential Shift"); score+=2

        if not direction:
            if struct_5m['signal'] and "BULL_BOS" in struct_5m['signal'] and (htf_bull or zone_daily=="DISCOUNT"):
                direction="BUY"; confluence.append(f"✅ 5M {struct_5m['signal']} + HTF {struct_4h['trend']}"); score+=2
            elif struct_5m['signal'] and "BEAR_BOS" in struct_5m['signal'] and (htf_bear or zone_daily=="PREMIUM"):
                direction="SELL"; confluence.append(f"✅ 5M {struct_5m['signal']} + HTF {struct_4h['trend']}"); score+=2

        if not direction and fvg_5m:
            direction="BUY" if "BULL" in fvg_5m['type'] else "SELL"
            confluence.append(f"FVG direction {fvg_5m['type']}")

        if not direction:
            return {"signal": False, "symbol": symbol, "reason": f"No direction - HTF {zone_daily} {struct_4h['trend']} | 5M {struct_5m['signal']}", "score": score}

        fvg_entry=None
        if fvg_5m and ((direction=="BUY" and "BULL" in fvg_5m['type']) or (direction=="SELL" and "BEAR" in fvg_5m['type'])):
            fvg_entry=fvg_5m; confluence.append(f"✅ 5M {fvg_5m['type']} {fvg_5m['size']:.2f}% ATR"); score+=3
        elif fvg_15m and ((direction=="BUY" and "BULL" in fvg_15m['type']) or (direction=="SELL" and "BEAR" in fvg_15m['type'])):
            fvg_entry=fvg_15m; confluence.append(f"✅ 15M {fvg_15m['type']}"); score+=2

        if not fvg_entry:
            return {"signal": False, "symbol": symbol, "reason": f"No {direction} FVG", "score": score}

        entry=fvg_entry['entry']; sl=fvg_entry['sl']; risk=abs(entry-sl)
        if risk==0: return {"signal": False, "symbol": symbol, "reason": "Zero risk", "score": score}
        tp=entry+risk*rr_target if direction=="BUY" else entry-risk*rr_target

        if ob_5m and direction in ob_5m['type']:
            tag="MB Breaker 🔥" if ob_5m['mitigated'] else "Order Block"
            confluence.append(f"✅ 5M {tag}"); score+=3 if ob_5m['mitigated'] else 2
        if ob_15m and direction in ob_15m['type']:
            confluence.append(f"✅ 15M {ob_15m['type']}"); score+=1
        if struct_15m['signal'] and direction in struct_15m['signal']:
            confluence.append(f"✅ 15M {struct_15m['signal']}"); score+=1
        if struct_1h['trend']==("BULL" if direction=="BUY" else "BEAR"):
            confluence.append(f"✅ 1H {struct_1h['trend']}"); score+=1
        if struct_4h['trend']==("BULL" if direction=="BUY" else "BEAR"):
            confluence.append(f"✅ 4H {struct_4h['trend']}"); score+=1
        if direction=="BUY" and zone_daily=="DISCOUNT":
            confluence.append(f"✅ Daily DISCOUNT {pct_daily*100:.0f}%"); score+=2
        elif direction=="SELL" and zone_daily=="PREMIUM":
            confluence.append(f"✅ Daily PREMIUM {pct_daily*100:.0f}%"); score+=2
        elif direction=="BUY" and zone_daily=="PREMIUM": score-=2
        elif direction=="SELL" and zone_daily=="DISCOUNT": score-=2
        if 30<rsi_5m<70: confluence.append(f"✅ RSI {rsi_5m:.1f}"); score+=1

        if score>=9: quality="SNIPER 🔥🔥🔥 SHIFT"
        elif score>=7: quality="PREMIUM 🔥 SHIFT"
        elif score>=5: quality="STANDARD"
        else: quality="WEAK"

        if score>=5:
            bias_text=f"Daily {zone_daily} {pct_daily*100:.0f}% | 4H {zone_4h} {struct_4h['trend']} | 5M {struct_5m['signal']} {'SHIFT' if struct_5m['is_shift'] else ''}"
            return {"signal": True, "symbol": symbol, "direction": direction, "entry": round(float(entry),5), "sl": round(float(sl),5), "tp": round(float(tp),5),
                    "score": int(score), "quality": quality, "bias": bias_text, "confluence": confluence,
                    "reason": f"HTF {zone_daily} + 5M {struct_5m['signal']} + {fvg_entry['type']} | Score {score}/12", "news_warning": ""}
        else:
            return {"signal": False, "symbol": symbol, "reason": f"Weak {score}/12", "score": score}
    except Exception as e:
        import traceback; traceback.print_exc()
        return {"signal": False, "symbol": symbol, "reason": f"Error: {e}", "score": 0}

def analyze_symbol(symbol, use_news_filter=True):
    return full_multi_tf_analysis(symbol, use_news_filter)
