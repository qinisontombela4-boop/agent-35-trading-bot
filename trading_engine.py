import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
import traceback

# --- FIX FOR RENDER 429 BAN ---
try:
    from curl_cffi import requests as c_requests
    session = c_requests.Session(impersonate="chrome110")
    HAS_CURL = True
except:
    session = None
    HAS_CURL = False

MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "USDZAR": "USDZAR=X", "XAUUSD": "GC=F", "BTCUSD": "BTC-USD",
    "EURZAR": "EURZAR=X", "GBPZAR": "GBPZAR=X", "USDCHF": "CHF=X"
}

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
            res.append({"event":ev,"outcome":"pending","title":i.get('title'),"time":i.get('date'),"actual":i.get('actual'),"forecast":i.get('forecast')})
        return res
    except: return []

def _norm(df):
    if df is None or df.empty: return None
    try:
        if isinstance(df.columns, pd.MultiIndex): df.columns=df.columns.get_level_values(0)
        df.columns=[str(c).title() for c in df.columns]
    except: pass
    return df

def get_data(symbol, period="5d", interval="1h"):
    yf_sym=MAP.get(symbol.upper(), symbol.upper())
    try:
        if HAS_CURL:
            df=yf.download(yf_sym, period=period, interval=interval, progress=False, auto_adjust=True, threads=False, session=session)
        else:
            df=yf.download(yf_sym, period=period, interval=interval, progress=False, auto_adjust=True, threads=False)
        df=_norm(df)
        if df is not None and not df.empty and 'Close' in df.columns and len(df)>20:
            return df
    except Exception as e:
        print(f"yf {symbol} {e}")
    return None

# ===== REAL SMC LOGIC =====
def detect_smc(df):
    """Returns CHoCH, BOS, Bu-OB, Be-OB, MB"""
    if df is None or len(df)<30: return None
    try:
        # Find swings
        highs = df['High'].rolling(5).max()
        lows = df['Low'].rolling(5).min()

        # BOS/CHoCH logic
        last_close = float(df['Close'].iloc[-1])
        prev_high = float(highs.iloc[-6:-1].max())
        prev_low = float(lows.iloc[-6:-1].min())

        bos_bull = last_close > prev_high
        bos_bear = last_close < prev_low

        # CHoCH = break opposite structure
        choch_bull = bos_bull and float(df['Close'].iloc[-10]) < float(df['Close'].iloc[-20]) # was bearish now bullish
        choch_bear = bos_bear and float(df['Close'].iloc[-10]) > float(df['Close'].iloc[-20])

        # Find OBs: last opposite candle before BOS
        bu_ob = None; be_ob = None; mb = None
        # Look back 20 candles
        for i in range(len(df)-3, len(df)-20, -1):
            c = df.iloc[i]
            # Bu-OB = bearish candle before bullish BOS
            if c['Close'] < c['Open'] and bos_bull:
                bu_ob = {"high": float(c['High']), "low": float(c['Low']), "idx": i}
                break
        for i in range(len(df)-3, len(df)-20, -1):
            c = df.iloc[i]
            if c['Close'] > c['Open'] and bos_bear:
                be_ob = {"high": float(c['High']), "low": float(c['Low']), "idx": i}
                break

        # MB (Mitigation Block) = failed swing high/low that becomes breaker
        # Simplified: previous BOS that failed
        if bos_bull:
            mb = bu_ob # MB = Bu-OB that held
        else:
            mb = be_ob

        discount = 0
        try:
            hi = float(df['High'].rolling(20).max().iloc[-1])
            lo = float(df['Low'].rolling(20).min().iloc[-1])
            discount = ((hi - last_close)/(hi-lo)*100) if hi!=lo else 50
        except: discount=50

        return {
            "bos_bull": bos_bull, "bos_bear": bos_bear,
            "choch_bull": choch_bull, "choch_bear": choch_bear,
            "bu_ob": bu_ob, "be_ob": be_ob, "mb": mb,
            "discount": discount, "close": last_close,
            "prev_high": prev_high, "prev_low": prev_low
        }
    except Exception as e:
        print(f"smc err {e}")
        return None

def full_multi_tf_analysis(symbol):
    try:
        df_4h = get_data(symbol, "1mo", "4h")
        df_1h = get_data(symbol, "5d", "1h")
        df_15m = get_data(symbol, "2d", "15m")

        if not df_1h: # fallback if 4h blocked
            df_1h = get_data(symbol, "5d", "1h")
        if not df_15m:
            df_15m = get_data(symbol, "1d", "15m")

        if df_4h is None and df_1h is None:
            return {"signal":False,"symbol":symbol,"reason":"Yahoo blocked by Render IP - installing curl_cffi fix, retry in 30s"}

        smc_4h = detect_smc(df_4h) if df_4h is not None else None
        smc_1h = detect_smc(df_1h) if df_1h is not None else None
        smc_15m = detect_smc(df_15m) if df_15m is not None else None

        if not smc_1h or not smc_15m:
            return {"signal":False,"symbol":symbol,"reason":f"No SMC yet (1h:{smc_1h is not None} 15m:{smc_15m is not None}) - retry"}

        score=0; conf=[]; direction=None; ob_type=""

        # 1. HTF Trend
        if smc_4h:
            if smc_4h['bos_bull']: conf.append(f"4H BULL BOS"); score+=1; direction="BUY"
            elif smc_4h['bos_bear']: conf.append(f"4H BEAR BOS"); score+=1; direction="SELL"

        # 2. CHoCH = strong signal
        if smc_1h['choch_bull']:
            conf.append("✅ 1H CHoCH BULL"); score+=2; direction="BUY"
        if smc_1h['choch_bear']:
            conf.append("✅ 1H CHoCH BEAR"); score+=2; direction="SELL"

        # 3. BOS chain
        if smc_1h['bos_bull'] and smc_15m['bos_bull']:
            conf.append("✅ BOS chain 1H+15M"); score+=1

        # 4. Discount + Bu-OB / Be-OB / MB retest - YOUR CHART LOGIC
        disc = smc_15m['discount']
        close = smc_15m['close']

        if disc > 65: # Discount zone
            if smc_1h['bu_ob']:
                # Check if price touched Bu-OB
                if smc_1h['bu_ob']['low'] <= close <= smc_1h['bu_ob']['high']+0.0005:
                    conf.append(f"🔥 Bu-OB RETEST {smc_1h['bu_ob']['low']:.5f}"); score+=3; direction="BUY"; ob_type="Bu-OB"
                elif disc>70:
                    conf.append(f"📊 Discount {disc:.0f}% near Bu-OB"); score+=2; direction="BUY"; ob_type="Bu-OB"
            if smc_1h['mb'] and disc>70:
                conf.append(f"✅ MB (Mitigation) in discount"); score+=2

        if disc < 35: # Premium zone
            if smc_1h['be_ob']:
                if smc_1h['be_ob']['low']-0.0005 <= close <= smc_1h['be_ob']['high']:
                    conf.append(f"🔥 Be-OB RETEST {smc_1h['be_ob']['high']:.5f}"); score+=3; direction="SELL"; ob_type="Be-OB"
                elif disc<30:
                    conf.append(f"📊 Premium {disc:.0f}% near Be-OB"); score+=2; direction="SELL"; ob_type="Be-OB"

        if not direction:
            direction = "BUY" if disc>50 else "SELL"

        # Entry/SL/TP based on OB
        entry=close
        if ob_type=="Bu-OB" and smc_1h['bu_ob']: sl=smc_1h['bu_ob']['low'] - (entry*0.0005)
        elif ob_type=="Be-OB" and smc_1h['be_ob']: sl=smc_1h['be_ob']['high'] + (entry*0.0005)
        else:
            try: atr=float((df_15m['High']-df_15m['Low']).rolling(10).mean().iloc[-1])
            except: atr=entry*0.002
            sl=entry-atr*1.5 if direction=="BUY" else entry+atr*1.5

        tp = entry + (entry-sl)*3 if direction=="BUY" else entry - (sl-entry)*3

        quality="LOW"
        if score>=7: quality="🔥🔥 SNIPER Bu-OB+CHoCH"
        elif score>=6: quality=f"🔥 PREMIUM {ob_type}+BOS"
        elif score>=5: quality=f"✅ HIGH {ob_type}"
        elif score>=4: quality=f"📊 {ob_type} pullback"

        news=fetch_forexfactory_auto()
        nt=""; nw=False
        if news: nw=True; nt=f"📰 {news[0]['event']}"

        if score<4:
            return {"signal":False,"symbol":symbol,"reason":f"Score {score}/8 {ob_type} disc:{disc:.0f}% {conf}","score":score,"news_warning":nw,"news_text":nt}

        return {
            "signal":True,"symbol":symbol,"direction":direction,
            "entry":round(entry,5),"sl":round(sl,5),"tp":round(tp,5),
            "score":score,"quality":quality,
            "bias":f"CHoCH:{smc_1h['choch_bull'] or smc_1h['choch_bear']} BOS:{smc_1h['bos_bull']} Bu-OB:{smc_1h['bu_ob'] is not None} Be-OB:{smc_1h['be_ob'] is not None} MB:{smc_1h['mb'] is not None} | disc:{disc:.0f}%",
            "confluence":conf,"reason":f"{ob_type} + CHoCH + BOS","news_warning":nw,"news_text":nt
        }
    except Exception as e:
        traceback.print_exc()
        return {"signal":False,"symbol":symbol,"reason":f"Error {str(e)[:100]}"}
