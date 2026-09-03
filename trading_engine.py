import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime

MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X", "USDZAR": "USDZAR=X",
    "EURZAR": "EURZAR=X", "GBPZAR": "GBPZAR=X", "ZARJPY": "ZARJPY=X",
    "USDCHF": "USDCHF=X", "XAUUSD": "GC=F", "GOLD": "GC=F", "XAGUSD": "SI=F",
    "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
    "NAS100": "^NDX", "US30": "^DJI", "SPX500": "^GSPC", "GER40": "^GDAXI",
    "UK100": "^FTSE", "JP225": "^N225", "USOIL": "CL=F", "UKOIL": "BZ=F",
    "AAPL": "AAPL", "TSLA": "TSLA", "NVDA": "NVDA", "MSFT": "MSFT"
}

PRICE_CACHE = {}
CACHE_TTL = 300
NEWS_CACHE = {"time": 0, "events": []}
NEWS_CACHE_TTL = 3600

HIGH_IMPACT_KEYWORDS = ["NFP","NON FARM","CPI","FOMC","FED FUNDS","INTEREST RATE","GDP","RETAIL SALES","PPI","PMI","ISM","UNEMPLOYMENT","JOLTS","ADP"]

def fetch_forex_factory_news():
    now = time.time()
    if now - NEWS_CACHE["time"] < NEWS_CACHE_TTL and NEWS_CACHE["events"]:
        return NEWS_CACHE["events"]
    events = []
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for e in data:
                if e.get('impact') == 'High' or e.get('impactTitle') == 'High':
                    events.append({"currency": (e.get('country','') or e.get('currency','')).upper(),"title": e.get('title',''),"impact": "High","hour": None})
            print(f"NEWS: Fetched {len(events)} high impact")
    except Exception as ex:
        print(f"News fetch fail {ex}")
    if not events:
        events = [
            {"currency": "USD", "title": "CPI / NFP Window 12:30 UTC", "impact": "High", "hour": 12, "minute": 30},
            {"currency": "USD", "title": "ISM / PMI Window 14:00 UTC", "impact": "High", "hour": 14, "minute": 0},
            {"currency": "EUR", "title": "EUR High Impact", "impact": "High", "hour": 9, "minute": 0},
            {"currency": "GBP", "title": "GBP High Impact", "impact": "High", "hour": 9, "minute": 30},
            {"currency": "USD", "title": "FOMC / Fed", "impact": "High", "hour": 18, "minute": 0},
        ]
    NEWS_CACHE["time"] = now
    NEWS_CACHE["events"] = events
    return events

def is_news_time(symbol, buffer_minutes=35):
    try:
        sym = symbol.upper()
        currs = []
        if "USD" in sym: currs.append("USD")
        if "EUR" in sym: currs.append("EUR")
        if "GBP" in sym: currs.append("GBP")
        if "JPY" in sym: currs.append("JPY")
        if "ZAR" in sym: currs.append("ZAR")
        if "XAU" in sym or "GOLD" in sym or "XAG" in sym: currs.append("USD")
        if not currs: currs = ["USD"]
        now_utc = datetime.utcnow()
        events = fetch_forex_factory_news()
        for ev in events:
            ev_curr = ev.get('currency','').upper()
            if ev_curr not in currs and ev_curr!="ALL": continue
            title = ev.get('title','').upper()
            is_high = any(k in title for k in HIGH_IMPACT_KEYWORDS) or ev.get('impact') == 'High'
            if not is_high: continue
            if 'hour' in ev and ev['hour'] is not None:
                ev_time = now_utc.replace(hour=ev['hour'], minute=ev.get('minute',0), second=0, microsecond=0)
                diff = abs((now_utc - ev_time).total_seconds() / 60)
                if diff <= buffer_minutes:
                    return True, f"🚨 {ev_curr} HIGH IMPACT NOW: {ev.get('title')} - NO TRADE"
                future_diff = (ev_time - now_utc).total_seconds() / 60
                if 0 < future_diff <= buffer_minutes:
                    return True, f"🚨 {ev_curr} HIGH IMPACT in {int(future_diff)}min: {ev.get('title')} - PAUSE"
        return False, ""
    except Exception as e:
        print(f"is_news_time err {e}")
        return False, ""

def round_by_symbol(symbol, price):
    try:
        s = symbol.upper()
        if "JPY" in s: return round(float(price), 3)
        if "ZAR" in s: return round(float(price), 3)
        if "CHF" in s: return round(float(price), 5)
        if "XAU" in s or "GOLD" in s: return round(float(price), 2)
        if "XAG" in s: return round(float(price), 3)
        if "BTC" in s: return round(float(price), 2)
        if "ETH" in s or "SOL" in s: return round(float(price), 2)
        if any(x in s for x in ["NAS100","US30","SPX500","GER40","UK100","JP225"]): return round(float(price), 1)
        if "OIL" in s: return round(float(price), 2)
        return round(float(price), 5)
    except: return round(float(price), 5)

def get_data(symbol, period="60d", interval="15m"):
    cache_key = f"{symbol}_{interval}"
    now = time.time()
    if cache_key in PRICE_CACHE and now - PRICE_CACHE[cache_key]['time'] < CACHE_TTL:
        return PRICE_CACHE[cache_key]['data'].copy()
    try:
        yfs = MAP.get(symbol.upper(), symbol.upper()+"=X")
        time.sleep(1.2)
        df = yf.download(yfs, period=period, interval=interval, progress=False, auto_adjust=True, threads=False)
        if df.empty:
            if cache_key in PRICE_CACHE: return PRICE_CACHE[cache_key]['data'].copy()
            return None
        try:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        except: pass
        df = df.dropna()
        if len(df) < 50:
            if cache_key in PRICE_CACHE: return PRICE_CACHE[cache_key]['data'].copy()
            return None
        PRICE_CACHE[cache_key] = {'time': now, 'data': df.copy()}
        return df
    except:
        if cache_key in PRICE_CACHE: return PRICE_CACHE[cache_key]['data'].copy()
        return None

def add_indicators(df):
    try:
        df['EMA20'] = df['Close'].ewm(span=20).mean()
        df['EMA50'] = df['Close'].ewm(span=50).mean()
        df['EMA200'] = df['Close'].ewm(span=200).mean()
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        tr = pd.concat([df['High'] - df['Low'], np.abs(df['High'] - df['Close'].shift()), np.abs(df['Low'] - df['Close'].shift())], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(14).mean()
        df['DailyHigh'] = df['High'].rolling(20).max()
        df['DailyLow'] = df['Low'].rolling(20).min()
        return df
    except: return df

def get_premium_discount(df):
    try:
        last = df.iloc[-1]
        daily_high = df['DailyHigh'].iloc[-1]
        daily_low = df['DailyLow'].iloc[-1]
        daily_range = daily_high - daily_low
        if daily_range == 0: return "NEUTRAL", 0.5, False, False
        position = (last['Close'] - daily_low) / daily_range
        recent_highs = df['High'].tail(10).values
        eqh = False; weak_high = False
        if len(recent_highs) >= 3:
            top_highs = sorted(recent_highs)[-3:]
            if (top_highs[-1] - top_highs[0]) / top_highs[-1] < 0.0008: eqh = True
        last_high = df['High'].iloc[-1]
        prev_high = df['DailyHigh'].iloc[-2] if len(df) > 2 else daily_high
        if last_high > prev_high and (last_high - prev_high) / prev_high < 0.0015: weak_high = True
        if position > 0.70: return "PREMIUM", position, eqh, weak_high
        elif position < 0.30: return "DISCOUNT", position, eqh, weak_high
        else: return "EQUILIBRIUM", position, eqh, weak_high
    except: return "NEUTRAL", 0.5, False, False

def detect_order_block(df, direction="BUY"):
    try:
        last_10 = df.tail(10)
        if direction == "BUY":
            for i in range(len(last_10)-3, 0, -1):
                if last_10['Close'].iloc[i] < last_10['Open'].iloc[i]:
                    if last_10['Close'].iloc[i+1] > last_10['Open'].iloc[i+1]:
                        return True, f"Bu-OB at {last_10['Low'].iloc[i]:.5f}"
        else:
            for i in range(len(last_10)-3, 0, -1):
                if last_10['Close'].iloc[i] > last_10['Open'].iloc[i]:
                    if last_10['Close'].iloc[i+1] < last_10['Open'].iloc[i+1]:
                        return True, f"Be-OB at {last_10['High'].iloc[i]:.5f}"
        return False, ""
    except: return False, ""

def detect_market_structure(df):
    try:
        highs = df['High'].tail(20); lows = df['Low'].tail(20)
        prev_high = highs.iloc[-6:-1].max(); prev_low = lows.iloc[-6:-1].min()
        if lows.iloc[-1] < prev_low and highs.iloc[-1] > prev_high: return "Bullish CHoCH", "Bullish"
        if highs.iloc[-1] > prev_high and df['Close'].iloc[-1] < df['Open'].iloc[-1]: return "Bearish CHoCH", "Bearish"
        if highs.iloc[-1] > highs.iloc[-5] and lows.iloc[-1] > lows.iloc[-5]: return "Bullish BOS", "Bullish"
        elif highs.iloc[-1] < highs.iloc[-5] and lows.iloc[-1] < lows.iloc[-5]: return "Bearish BOS", "Bearish"
        else: return "Ranging", "Neutral"
    except: return "Unknown", "Neutral"

def check_confluence(df, direction, zone_info):
    score = 0; confluence = []
    try:
        last = df.iloc[-1]; prev = df.iloc[-2]
        zone, pos, eqh, weak_high = zone_info
        if direction == "BUY" and last['Close'] > last['EMA20'] and last['EMA20'] > last['EMA50']:
            score+=1; confluence.append("EMA Bullish Stack")
        elif direction == "SELL" and last['Close'] < last['EMA20'] and last['EMA20'] < last['EMA50']:
            score+=1; confluence.append("EMA Bearish Stack")
        if direction == "BUY" and last['Close'] > last['EMA200']:
            score+=1; confluence.append("Above EMA200")
        elif direction == "SELL" and last['Close'] < last['EMA200']:
            score+=1; confluence.append("Below EMA200")
        if direction == "BUY" and 40 < last['RSI'] < 70:
            score+=1; confluence.append(f"RSI {last['RSI']:.1f} Bullish")
        elif direction == "SELL" and 30 < last['RSI'] < 60:
            score+=1; confluence.append(f"RSI {last['RSI']:.1f} Bearish")
        ob_hit, ob_text = detect_order_block(df, direction)
        if ob_hit: score+=2; confluence.append(ob_text); confluence.append("OB RETEST")
        ms_text, ms_bias = detect_market_structure(df)
        if (direction == "BUY" and "Bullish" in ms_bias) or (direction == "SELL" and "Bearish" in ms_bias):
            score+=1; confluence.append(ms_text)
        if abs(last['Close'] - prev['Close']) > last['ATR'] * 0.5:
            score+=1; confluence.append("MB Momentum")
        if last['ATR'] > df['ATR'].tail(20).mean():
            score+=1; confluence.append("ATR Expansion")
        confluence.append(f"{zone} {pos*100:.0f}%")
        if eqh: confluence.append("EQH Detected")
        if weak_high: confluence.append("Weak High")
    except Exception as e: print(f"confluence err {e}")
    return score, confluence

def full_multi_tf_analysis(symbol, use_news_filter=True):
    try:
        symbol = symbol.upper().strip()
        # NEWS FILTER - can be toggled per user
        if use_news_filter:
            is_news, news_text = is_news_time(symbol, buffer_minutes=35)
            if is_news:
                return {"signal": False, "symbol": symbol, "reason": news_text, "score": 0, "news_block": True, "news_text": news_text}
        df_15m = get_data(symbol, period="60d", interval="15m")
        if df_15m is None:
            return {"signal": False, "symbol": symbol, "reason": "No data", "score": 0}
        df_15m = add_indicators(df_15m)
        last = df_15m.iloc[-1]
        try:
            df_1h = df_15m.resample('1h').agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna()
            if len(df_1h) > 50:
                df_1h['EMA50'] = df_1h['Close'].ewm(span=50).mean()
                bias = "Bullish HTF" if df_1h.iloc[-1]['Close'] > df_1h.iloc[-1]['EMA50'] else "Bearish HTF"
            else: bias = "Neutral HTF"
        except: bias = "Neutral HTF"
        zone, pos, eqh, weak_high = get_premium_discount(df_15m)
        buy_score, buy_conf = check_confluence(df_15m, "BUY", (zone, pos, eqh, weak_high))
        sell_score, sell_conf = check_confluence(df_15m, "SELL", (zone, pos, eqh, weak_high))
        direction = "BUY" if buy_score >= sell_score else "SELL"
        score = max(buy_score, sell_score)
        confluence = buy_conf if direction == "BUY" else sell_conf
        if zone == "PREMIUM" and pos > 0.75 and direction == "BUY" and (eqh or weak_high):
            direction = "SELL"
            score = sell_score + 2
            confluence = sell_conf + [f"PREMIUM REVERSAL {pos*100:.0f}%", "EQH Weak High Sweep"]
            if score < 4:
                return {"signal": False, "symbol": symbol, "reason": f"BUY blocked in PREMIUM {pos*100:.0f}%", "score": score, "bias": bias, "confluence": confluence}
        if zone == "DISCOUNT" and pos < 0.25 and direction == "SELL":
            direction = "BUY"
            score = buy_score + 2
            confluence = buy_conf + [f"DISCOUNT REVERSAL {pos*100:.0f}%", "EQL Sweep"]
            if score < 4:
                return {"signal": False, "symbol": symbol, "reason": f"SELL blocked in DISCOUNT {pos*100:.0f}%", "score": score, "bias": bias, "confluence": confluence}
        if score < 4:
            return {"signal": False, "symbol": symbol, "reason": f"Low score {score}/8 in {zone}", "score": score, "bias": f"{bias} | {zone} {pos*100:.0f}%", "confluence": confluence}
        atr = last['ATR']
        if pd.isna(atr) or atr == 0:
            atr = (last['High'] - last['Low']) * 0.5
            if atr == 0: atr = last['Close'] * 0.001
        entry = float(last['Close'])
        if direction == "BUY": sl = entry - (atr * 1.5); tp = entry + (atr * 3.0)
        else: sl = entry + (atr * 1.5); tp = entry - (atr * 3.0)
        has_ob = any("OB" in c for c in confluence)
        has_mb = any("MB" in c for c in confluence)
        if score >= 7 and has_ob and has_mb: quality = "SNIPER Bu-OB/Be-OB+MB"
        elif score >= 6 and has_ob: quality = "PREMIUM Be-OB"
        elif score >= 6: quality = "PREMIUM"
        else: quality = "STANDARD"
        entry = round_by_symbol(symbol, entry); sl = round_by_symbol(symbol, sl); tp = round_by_symbol(symbol, tp)
        if entry == sl:
            if direction == "BUY": sl = round_by_symbol(symbol, sl - atr)
            else: sl = round_by_symbol(symbol, sl + atr)
        is_news2, news_text2 = is_news_time(symbol, buffer_minutes=20) if use_news_filter else (False, "")
        return {"signal": True, "symbol": symbol, "direction": direction, "entry": entry, "sl": sl, "tp": tp, "score": score, "quality": quality, "bias": f"{bias} | {zone} {pos*100:.0f}% {'EQH' if eqh else ''} | OB:{has_ob} MB:{has_mb}", "confluence": confluence, "reason": f"{quality} {score}/8 - {zone} {pos*100:.0f}% {bias}", "news_warning": news_text2, "news_block": False}
    except Exception as e:
        import traceback
        print(f"full_multi_tf err {symbol} {e} {traceback.format_exc()}")
        return {"signal": False, "symbol": symbol, "reason": f"Error {e}", "score": 0}
