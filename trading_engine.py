import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
import traceback

MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "USDZAR": "USDZAR=X", "XAUUSD": "GC=F",
    "EURZAR": "EURZAR=X", "GBPZAR": "GBPZAR=X",
    "BTCUSD": "BTC-USD", "NAS100": "^IXIC", "US30": "^DJI"
}

def get_universal_news_bias(symbol, news_event, outcome):
    sym=symbol.upper(); usd=None
    if outcome in ["strong","high","rates_up","low"]: usd=True if outcome in ["strong","high","rates_up"] or (news_event=="UNEMPLOYMENT" and outcome=="low") else False
    # simplified
    if usd is None:
        if (news_event=="NFP" and outcome=="strong") or (news_event=="CPI" and outcome=="high") or (news_event=="FOMC" and outcome=="rates_up"): usd=True
        elif (news_event=="NFP" and outcome=="weak") or (news_event=="CPI" and outcome=="low") or (news_event=="FOMC" and outcome=="rates_down"): usd=False
    if usd is None: return None,None
    if "XAU" in sym or "GOLD" in sym: return ("BEAR" if usd else "BULL", "$ UP=Gold DOWN" if usd else "$ DOWN=Gold UP")
    if "EUR" in sym or "GBP" in sym and "ZAR" not in sym: return ("BEAR" if usd else "BULL", "$ Strong")
    return ("BULL" if usd else "BEAR", "$ Strong=USD up")

def fetch_forexfactory_auto():
    try:
        r=requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json",timeout=8,headers={'User-Agent':'Mozilla/5.0'})
        data=r.json(); today=datetime.utcnow().strftime("%Y-%m-%d"); res=[]
        for i in data:
            if today not in i.get('date',''): continue
            if i.get('country')!='USD' or i.get('impact')!='High': continue
            t=i.get('title','').upper()
            ev="NFP" if "NFP" in t or "NON-FARM" in t else "CPI" if "CPI" in t else "FOMC" if "FOMC" in t or "RATE" in t else "UNEMPLOYMENT" if "JOBLESS" in t else None
            if not ev: continue
            actual=str(i.get('actual','')).replace('%','').strip(); forecast=str(i.get('forecast','')).replace('%','').strip()
            outcome="pending"
            try:
                if actual and forecast and actual!='-':
                    a=float(actual.split()[0]); f=float(forecast.split()[0])
                    if ev=="NFP": outcome="strong" if a>f else "weak"
                    elif ev=="CPI": outcome="high" if a>f else "low"
                    else: outcome="low" if a<f else "high"
            except: pass
            res.append({"event":ev,"outcome":outcome,"title":i.get('title'),"time":i.get('date'),"actual":i.get('actual'),"forecast":i.get('forecast')})
        return res
    except: return []

def _normalize(df):
    if df is None or df.empty: return None
    try:
        if isinstance(df.columns, pd.MultiIndex): df.columns=df.columns.get_level_values(0)
        df.columns=[str(c).title() for c in df.columns]
    except: pass
    return df

def get_data(symbol, period="7d", interval="1h"):
    try:
        yf_sym=MAP.get(symbol.upper(), symbol.upper())
        df=yf.download(yf_sym, period=period, interval=interval, progress=False, auto_adjust=True, threads=False, timeout=10)
        df=_normalize(df)
        if df is not None and not df.empty and 'Close' in df.columns and len(df)>=20: return df
    except Exception as e: print(f"yf {symbol} {e}")
    return None

def analyze_tf(df):
    if df is None or len(df)<20: return None
    try:
        close=float(df['Close'].iloc[-1])
        high=float(df['High'].rolling(20).max().iloc[-1]); low=float(df['Low'].rolling(20).min().iloc[-1])
        discount=((high-close)/(high-low)*100) if high!=low else 50
        ob=False
        try:
            last=df.iloc[-1]; prev=df.iloc[-2]
            if last['Close']>last['Open'] and prev['Close']<prev['Open']: ob=True
            if last['Close']<last['Open'] and prev['Close']>prev['Open']: ob=True
        except: pass
        ma=float(df['Close'].rolling(30).mean().iloc[-1])
        bias="bullish" if close>ma else "bearish"
        return {"bias":bias,"discount":discount,"ob":ob,"close":close}
    except: return None

def full_multi_tf_analysis(symbol):
    try:
        df_4h=get_data(symbol, period="1mo", interval="4h")
        df_1h=get_data(symbol, period="5d", interval="1h")
        df_5m=get_data(symbol, period="1d", interval="15m")
        tf_4h=analyze_tf(df_4h); tf_1h=analyze_tf(df_1h); tf_5m=analyze_tf(df_5m)
        if not tf_4h: tf_4h=tf_1h
        if not tf_4h or not tf_1h or not tf_5m:
            return {"signal":False,"symbol":symbol,"reason":f"Yahoo busy - retry 10s (4h:{tf_4h is not None} 1h:{tf_1h is not None} 5m:{tf_5m is not None})"}

        score=0; conf=[]; direction=None
        conf.append(f"4H {tf_4h['bias']}"); score+=1
        if tf_1h['discount']>60: conf.append(f"1H discount {tf_1h['discount']:.0f}%"); score+=2; direction="BUY"
        elif tf_1h['discount']<40: conf.append(f"1H premium {tf_1h['discount']:.0f}%"); score+=2; direction="SELL"
        if tf_1h['ob'] or tf_5m['ob']: conf.append("✅ OB"); score+=2
        if tf_5m['ob']: conf.append("✅ 5M BOS"); score+=2
        if not direction: direction="BUY" if tf_4h['bias']=="bullish" else "SELL"

        entry=tf_5m['close']
        try: atr=float((df_5m['High']-df_5m['Low']).rolling(10).mean().iloc[-1])
        except: atr=entry*0.002
        if atr==0 or str(atr)=='nan': atr=entry*0.002
        sl=entry-atr*1.5 if direction=="BUY" else entry+atr*1.5
        tp=entry+atr*4.5 if direction=="BUY" else entry-atr*4.5
        quality="🔥🔥 SNIPER" if score>=7 else "🔥 PREMIUM" if score>=6 else "✅ HIGH" if score>=5 else "📊 MEDIUM" if score>=4 else "LOW"
        bias_text=f"{tf_4h['bias']} | 4H:{tf_4h['discount']:.0f}% 1H:{tf_1h['discount']:.0f}% 5M:{tf_5m['discount']:.0f}%"

        news=fetch_forexfactory_auto(); nw=False; nt=""; nb=None
        if news:
            nw=True
            for ne in news:
                if ne['outcome']!='pending':
                    nb,rs=get_universal_news_bias(symbol, ne['event'], ne['outcome'])
                    nt=f"📰 {ne['event']} {ne['outcome']} -> {nb} for {symbol}"
                    break
            if not nt: nt=f"📰 TODAY: {news[0]['event']}"

        if score<4: return {"signal":False,"symbol":symbol,"reason":f"Score {score}/8 low - {bias_text}","score":score,"news_warning":nw,"news_text":nt}
        return {"signal":True,"symbol":symbol,"direction":direction,"entry":round(entry,5),"sl":round(sl,5),"tp":round(tp,5),"score":score,"quality":quality,"bias":bias_text,"confluence":conf,"reason":"HTF+discount","news_warning":nw,"news_text":nt,"news_bias":nb}
    except Exception as e:
        traceback.print_exc()
        return {"signal":False,"symbol":symbol,"reason":f"Error {str(e)[:80]}"}
