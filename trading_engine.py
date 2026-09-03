import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime
import traceback

MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X", "USDZAR": "USDZAR=X",
    "EURZAR": "EURZAR=X", "GBPZAR": "GBPZAR=X", "ZARJPY": "ZARJPY=X",
    "XAUUSD": "GC=F", "GOLD": "GC=F", "XAGUSD": "SI=F",
    "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
    "NAS100": "^IXIC", "US30": "^DJI", "SPX500": "^GSPC",
    "GER40": "^GDAXI", "UK100": "^FTSE", "JP225": "^N225",
    "USOIL": "CL=F", "UKOIL": "BZ=F",
    "AAPL": "AAPL", "TSLA": "TSLA", "NVDA": "NVDA", "MSFT": "MSFT"
}

def get_universal_news_bias(symbol, news_event, outcome):
    sym = symbol.upper()
    usd_strong = None
    if (news_event == "NFP" and outcome == "strong") or (news_event == "CPI" and outcome == "high") or (news_event == "FOMC" and outcome == "rates_up") or (news_event == "UNEMPLOYMENT" and outcome == "low"):
        usd_strong = True
    elif (news_event == "NFP" and outcome == "weak") or (news_event == "CPI" and outcome == "low") or (news_event == "FOMC" and outcome == "rates_down") or (news_event == "UNEMPLOYMENT" and outcome == "high"):
        usd_strong = False
    else: return None, None
    if "XAU" in sym or "GOLD" in sym or "XAG" in sym:
        return ("BEAR" if usd_strong else "BULL", "$ UP = Gold DOWN" if usd_strong else "$ DOWN = Gold UP")
    elif sym in ["EURUSD","GBPUSD","AUDUSD","NZDUSD"]:
        return ("BEAR" if usd_strong else "BULL", "$ Strong = Sell" if usd_strong else "$ Weak = Buy")
    elif "USD" in sym or "ZAR" in sym:
        return ("BULL" if usd_strong else "BEAR", "$ Strong = Buy USD pairs")
    else:
        return ("BEAR" if usd_strong else "BULL", "Risk On/Off")

def fetch_forexfactory_auto():
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        r = requests.get(url, timeout=10, headers={'User-Agent':'Mozilla/5.0'})
        data = r.json()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        res=[]
        for item in data:
            if today not in item.get('date',''): continue
            if item.get('country')!='USD': continue
            if item.get('impact')!='High': continue
            title=item.get('title','').upper()
            ev=None
            if 'NON-FARM' in title or 'NFP' in title: ev="NFP"
            elif 'CPI' in title: ev="CPI"
            elif 'FOMC' in title or 'RATE' in title: ev="FOMC"
            elif 'JOBLESS' in title or 'UNEMPLOY' in title: ev="UNEMPLOYMENT"
            if not ev: continue
            actual=str(item.get('actual','')).replace('%','').replace('K','').strip()
            forecast=str(item.get('forecast','')).replace('%','').replace('K','').strip()
            outcome="pending"
            try:
                if actual and forecast and actual not in ['','-']:
                    a=float(actual); f=float(forecast)
                    if ev=="NFP": outcome="strong" if a>f else "weak"
                    elif ev=="CPI": outcome="high" if a>f else "low"
                    elif ev=="FOMC": outcome="rates_up" if a>f else "rates_down"
                    else: outcome="low" if a<f else "high"
            except: pass
            res.append({"event":ev,"outcome":outcome,"title":item.get('title'),"time":item.get('date'),"actual":item.get('actual'),"forecast":item.get('forecast')})
        return res
    except: return []

def _normalize_df(df):
    if df is None or df.empty: return None
    try:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        rename={}
        for c in df.columns:
            lc=str(c).lower()
            if lc=='close': rename[c]='Close'
            elif lc=='open': rename[c]='Open'
            elif lc=='high': rename[c]='High'
            elif lc=='low': rename[c]='Low'
            elif lc=='volume': rename[c]='Volume'
        df=df.rename(columns=rename)
    except: pass
    return df

def get_data(symbol, period="1d", interval="5m"):
    yf_sym = MAP.get(symbol.upper(), symbol.upper())
    # RETRY 3 times - this fixes your screenshot issue
    for attempt in range(3):
        try:
            df = yf.download(yf_sym, period=period, interval=interval, progress=False, auto_adjust=True, threads=False, timeout=10)
            df = _normalize_df(df)
            if df is not None and not df.empty and 'Close' in df.columns and len(df)>=20:
                return df
        except Exception as e:
            print(f"get_data {symbol} attempt {attempt} err {e}")
        time.sleep(1.5) # wait for Yahoo unblock
    return None

def analyze_tf(df):
    if df is None or len(df)<30: return None
    try:
        close=float(df['Close'].iloc[-1])
        high=float(df['High'].rolling(20).max().iloc[-1])
        low=float(df['Low'].rolling(20).min().iloc[-1])
        discount=((high-close)/(high-low)*100) if high!=low else 50
        ob=False
        try:
            last=df.iloc[-1]; prev=df.iloc[-2]
            if last['Close']>last['Open'] and prev['Close']<prev['Open'] and last['Close']>prev['Open']: ob=True
            if last['Close']<last['Open'] and prev['Close']>prev['Open'] and last['Close']<prev['Open']: ob=True
        except: pass
        ma50=float(df['Close'].rolling(50).mean().iloc[-1])
        bias="bullish" if close>ma50 else "bearish"
        return {"bias":bias,"discount":discount,"ob":ob,"close":close}
    except: return None

def full_multi_tf_analysis(symbol):
    try:
        # Use more compatible periods for yfinance
        df_4h = get_data(symbol, period="1mo", interval="4h")
        df_1h = get_data(symbol, period="7d", interval="1h")
        df_5m = get_data(symbol, period="2d", interval="5m")

        tf_4h = analyze_tf(df_4h)
        tf_1h = analyze_tf(df_1h)
        tf_5m = analyze_tf(df_5m)

        if not tf_4h or not tf_1h or not tf_5m:
            # Fallback to 1h/15m if 4h fails
            if not tf_4h:
                df_4h = get_data(symbol, period="1mo", interval="1d")
                tf_4h = analyze_tf(df_4h)
            if not tf_4h or not tf_1h or not tf_5m:
                return {"signal":False,"symbol":symbol,"reason":f"No data yet - Yahoo busy (4h:{tf_4h is not None} 1h:{tf_1h is not None} 5m:{tf_5m is not None}) - hit refresh in 20s"}

        score=0; confluence=[]; direction=None
        confluence.append(f"4H {tf_4h['bias']}"); score+=1

        if tf_1h['discount']>60:
            confluence.append(f"1H discount ({tf_1h['discount']:.0f}%)"); score+=2; direction="BUY"
        elif tf_1h['discount']<40:
            confluence.append(f"1H premium ({tf_1h['discount']:.0f}%)"); score+=2; direction="SELL"

        if tf_1h['ob'] or tf_5m['ob']:
            confluence.append("✅ OB detected"); score+=2
        if tf_5m['ob']:
            confluence.append("✅ 5M STRUCTURE: engulfing + BOS"); score+=2

        if not direction:
            direction="BUY" if tf_4h['bias']=="bullish" else "SELL"

        entry=tf_5m['close']
        try: atr=float((df_5m['High']-df_5m['Low']).rolling(14).mean().iloc[-1])
        except: atr=entry*0.002
        if atr==0 or str(atr)=='nan': atr=entry*0.002

        sl = entry - atr*1.5 if direction=="BUY" else entry + atr*1.5
        tp = entry + atr*4.5 if direction=="BUY" else entry - atr*4.5

        quality="STANDARD"
        if score>=7: quality="🔥🔥 SNIPER"
        elif score>=6: quality="🔥 PREMIUM"
        elif score>=5: quality="✅ HIGH QUALITY"
        elif score>=4: quality="📊 MEDIUM"

        bias_text=f"{tf_4h['bias']} | 4H:discount({tf_4h['discount']:.0f}%) 1H:discount({tf_1h['discount']:.0f}%) 5M:discount({tf_5m['discount']:.0f}%) | HTF"

        news_events=fetch_forexfactory_auto()
        news_warning=False; news_text=""; news_bias=None
        if news_events:
            news_warning=True
            for ne in news_events:
                if ne['outcome']!='pending':
                    news_bias, reason = get_universal_news_bias(symbol, ne['event'], ne['outcome'])
                    news_text=f"📰 {ne['event']} {ne['outcome'].upper()} ({ne['actual']} vs {ne['forecast']}) -> {news_bias} | {reason}"
                    if (news_bias=="BULL" and direction=="BUY") or (news_bias=="BEAR" and direction=="SELL"):
                        score+=0.5; confluence.append(f"✅ NEWS CONFIRMED")
                    else: confluence.append(f"⚠️ NEWS CONFLICT -> 50% size")
                    break
            if not news_text and news_events:
                p=news_events[0]; news_text=f"📰 TODAY: {p['event']} at {p['time'][:16]}"

        if score<4:
            return {"signal":False,"symbol":symbol,"reason":f"Score {score}/8 too low - {bias_text}","score":score,"news_warning":news_warning,"news_text":news_text}

        return {"signal":True,"symbol":symbol,"direction":direction,"entry":round(entry,5),"sl":round(sl,5),"tp":round(tp,5),"score":score,"quality":quality,"bias":bias_text,"confluence":confluence,"reason":f"{tf_4h['bias']} + discount + structure","news_warning":news_warning,"news_text":news_text,"news_bias":news_bias}

    except Exception as e:
        traceback.print_exc()
        return {"signal":False,"symbol":symbol,"reason":f"Error {str(e)[:120]}"}
