import pandas as pd
import requests, time, traceback
from datetime import datetime
try:
    from curl_cffi import requests as c_requests
    session = c_requests.Session(impersonate="chrome110")
except:
    session = requests.Session()

MAP = {"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"USDJPY=X","USDZAR":"USDZAR=X","XAUUSD":"GC=F","GBPZAR":"GBPZAR=X","EURZAR":"EURZAR=X","BTCUSD":"BTC-USD"}

def get_data_direct(symbol, interval="60m", range_="5d"):
    """Direct Yahoo Chart API with Chrome impersonation - bypasses 429"""
    yf_sym = MAP.get(symbol.upper(), symbol.upper())
    # interval map: 5m,15m,60m,4h,1d
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?range={range_}&interval={interval}&includePrePost=false"
    try:
        r = session.get(url, timeout=15)
        j = r.json()
        result = j['chart']['result'][0]
        timestamps = result['timestamp']
        ohlc = result['indicators']['quote'][0]
        df = pd.DataFrame({
            'Open': ohlc['open'],
            'High': ohlc['high'],
            'Low': ohlc['low'],
            'Close': ohlc['close'],
            'Volume': ohlc['volume']
        })
        df.index = pd.to_datetime(timestamps, unit='s')
        df = df.dropna()
        if len(df) > 20:
            print(f"OK {symbol} {interval} len {len(df)}")
            return df
    except Exception as e:
        print(f"Direct {symbol} err {e}")
    return None

def fetch_forexfactory_auto():
    try:
        r=requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json",timeout=8,headers={'User-Agent':'Mozilla/5.0'})
        return []
    except: return []

def detect_smc(df):
    if df is None or len(df)<25: return None
    try:
        last_close=float(df['Close'].iloc[-1])
        hi=float(df['High'].rolling(20).max().iloc[-1]); lo=float(df['Low'].rolling(20).min().iloc[-1])
        disc=((hi-last_close)/(hi-lo)*100) if hi!=lo else 50

        # BOS logic
        prev_high=float(df['High'].iloc[-20:-1].max())
        prev_low=float(df['Low'].iloc[-20:-1].min())
        bos_bull=last_close>prev_high
        bos_bear=last_close<prev_low

        # Find Bu-OB / Be-OB / MB
        bu_ob=None; be_ob=None
        for i in range(len(df)-3, len(df)-25, -1):
            if df['Close'].iloc[i] < df['Open'].iloc[i] and bos_bull:
                bu_ob={"low":float(df['Low'].iloc[i]), "high":float(df['High'].iloc[i])}
                break
        for i in range(len(df)-3, len(df)-25, -1):
            if df['Close'].iloc[i] > df['Open'].iloc[i] and bos_bear:
                be_ob={"low":float(df['Low'].iloc[i]), "high":float(df['High'].iloc[i])}
                break

        # CHoCH = trend flip
        choch_bull=bos_bull and float(df['Close'].iloc[-15])<float(df['Low'].iloc[-25])
        choch_bear=bos_bear and float(df['Close'].iloc[-15])>float(df['High'].iloc[-25])

        return {"bos_bull":bos_bull,"bos_bear":bos_bear,"choch_bull":choch_bull,"choch_bear":choch_bear,"bu_ob":bu_ob,"be_ob":be_ob,"mb":bu_ob or be_ob,"discount":disc,"close":last_close}
    except: return None

def full_multi_tf_analysis(symbol):
    try:
        df_4h=get_data_direct(symbol,"4h","1mo")
        df_1h=get_data_direct(symbol,"60m","5d")
        df_15m=get_data_direct(symbol,"15m","2d")

        if df_1h is None and df_15m is None:
            return {"signal":False,"symbol":symbol,"reason":"Yahoo still blocking - wait 60s then hit scan again, curl fix deploying"}

        smc_4h=detect_smc(df_4h); smc_1h=detect_smc(df_1h); smc_15m=detect_smc(df_15m)
        if not smc_1h or not smc_15m:
            return {"signal":False,"symbol":symbol,"reason":f"No SMC 1h:{smc_1h is not None} 15m:{smc_15m is not None}"}

        score=0; conf=[]; direction=None; ob_type=""
        disc=smc_15m['discount']; close=smc_15m['close']

        if smc_4h and smc_4h['bos_bull']: score+=1; conf.append("4H BULL")
        if smc_1h['choch_bull']: score+=2; conf.append("CHoCH BULL"); direction="BUY"
        if smc_1h['choch_bear']: score+=2; conf.append("CHoCH BEAR"); direction="SELL"
        if smc_1h['bos_bull'] and smc_15m['bos_bull']: score+=1; conf.append("BOS chain")

        # Bu-OB in Discount
        if disc>60 and smc_1h['bu_ob']:
            if smc_1h['bu_ob']['low']*0.999 <= close <= smc_1h['bu_ob']['high']*1.001:
                conf.append(f"🔥 Bu-OB RETEST"); score+=3; direction="BUY"; ob_type="Bu-OB"
            elif disc>70:
                conf.append(f"📊 Disc {disc:.0f}% + Bu-OB"); score+=2; direction="BUY"; ob_type="Bu-OB"
            if smc_1h['mb']: conf.append("✅ MB"); score+=1

        # Be-OB in Premium
        if disc<40 and smc_1h['be_ob']:
            if smc_1h['be_ob']['low']*0.999 <= close <= smc_1h['be_ob']['high']*1.001:
                conf.append(f"🔥 Be-OB RETEST"); score+=3; direction="SELL"; ob_type="Be-OB"
            elif disc<30:
                conf.append(f"📊 Prem {disc:.0f}% + Be-OB"); score+=2; direction="SELL"; ob_type="Be-OB"

        if not direction: direction="BUY" if disc>50 else "SELL"
        entry=close
        try: atr=float((df_15m['High']-df_15m['Low']).rolling(10).mean().iloc[-1])
        except: atr=entry*0.002
        sl=entry-atr*1.5 if direction=="BUY" else entry+atr*1.5
        if ob_type=="Bu-OB" and smc_1h['bu_ob']: sl=smc_1h['bu_ob']['low']-atr*0.5
        if ob_type=="Be-OB" and smc_1h['be_ob']: sl=smc_1h['be_ob']['high']+atr*0.5
        tp=entry+(entry-sl)*3 if direction=="BUY" else entry-(sl-entry)*3

        quality="LOW"
        if score>=7: quality=f"🔥🔥 SNIPER {ob_type}+CHoCH"
        elif score>=6: quality=f"🔥 PREMIUM {ob_type}+BOS"
        elif score>=5: quality=f"✅ HIGH {ob_type}"

        if score<4:
            return {"signal":False,"symbol":symbol,"reason":f"Score {score}/8 disc {disc:.0f}% {ob_type} {conf}","score":score}

        return {"signal":True,"symbol":symbol,"direction":direction,"entry":round(entry,5),"sl":round(sl,5),"tp":round(tp,5),"score":score,"quality":quality,"bias":f"disc {disc:.0f}% BuOB:{smc_1h['bu_ob'] is not None} BeOB:{smc_1h['be_ob'] is not None} MB:{smc_1h['mb'] is not None}","confluence":conf,"reason":f"{ob_type}+CHoCH","news_warning":False,"news_text":""}

    except Exception as e:
        traceback.print_exc()
        return {"signal":False,"symbol":symbol,"reason":f"Error {str(e)[:80]}"}
