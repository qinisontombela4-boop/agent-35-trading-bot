import pandas as pd
import requests
import traceback
from datetime import datetime

try:
    from curl_cffi import requests as c_requests
    session = c_requests.Session(impersonate="chrome110")
    print("Using curl_cffi Chrome bypass")
except:
    session = requests.Session()
    print("Using normal requests - install curl_cffi")

MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "USDZAR": "USDZAR=X", "XAUUSD": "GC=F", "GOLD": "GC=F",
    "GBPZAR": "GBPZAR=X", "EURZAR": "EURZAR=X", "ZARJPY": "ZARJPY=X",
    "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
    "NAS100": "^IXIC", "US30": "^DJI", "SPX500": "^GSPC"
}

def round_by_symbol(symbol, price):
    s = symbol.upper()
    if "JPY" in s: return round(price, 3)
    if "ZAR" in s: return round(price, 3) # FIX FOR YOUR SCREENSHOT
    if "XAU" in s or "GOLD" in s: return round(price, 2)
    if "BTC" in s or "ETH" in s or "SOL" in s: return round(price, 2)
    if "NAS100" in s or "US30" in s or "SPX500" in s or "GER" in s or "UK100" in s: return round(price, 1)
    return round(price, 5)

def fetch_forexfactory_auto():
    try:
        r = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=8, headers={'User-Agent':'Mozilla/5.0'})
        today = datetime.utcnow().strftime("%Y-%m-%d")
        res = []
        for i in r.json():
            if today not in i.get('date',''): continue
            if i.get('country')!='USD' or i.get('impact')!='High': continue
            t = i.get('title','').upper()
            ev = "NFP" if "NFP" in t or "NON-FARM" in t else "CPI" if "CPI" in t else "FOMC" if "FOMC" in t or "RATE" in t else "UNEMPLOYMENT" if "JOBLESS" in t or "UNEMPLOY" in t else None
            if not ev: continue
            res.append({"event":ev,"outcome":"pending","title":i.get('title'),"time":i.get('date'),"actual":i.get('actual'),"forecast":i.get('forecast')})
        return res
    except:
        return []

def get_data_direct(symbol, interval="60m", range_="5d"):
    yf_sym = MAP.get(symbol.upper(), symbol.upper())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?range={range_}&interval={interval}&includePrePost=false"
    try:
        r = session.get(url, timeout=15)
        j = r.json()
        if 'chart' not in j or j['chart']['result'] is None:
            return None
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
            return df
    except Exception as e:
        print(f"Direct {symbol} {interval} err {e}")
    return None

def detect_smc(df):
    if df is None or len(df) < 25:
        return None
    try:
        last_close = float(df['Close'].iloc[-1])
        hi = float(df['High'].rolling(20).max().iloc[-1])
        lo = float(df['Low'].rolling(20).min().iloc[-1])
        disc = ((hi - last_close) / (hi - lo) * 100) if hi!= lo else 50
        prev_high = float(df['High'].iloc[-20:-1].max())
        prev_low = float(df['Low'].iloc[-20:-1].min())
        bos_bull = last_close > prev_high
        bos_bear = last_close < prev_low
        bu_ob = None
        be_ob = None
        for i in range(len(df)-2, len(df)-30, -1):
            if df['Close'].iloc[i] < df['Open'].iloc[i]:
                bu_ob = {"low": float(df['Low'].iloc[i]), "high": float(df['High'].iloc[i])}
                break
        for i in range(len(df)-2, len(df)-30, -1):
            if df['Close'].iloc[i] > df['Open'].iloc[i]:
                be_ob = {"low": float(df['Low'].iloc[i]), "high": float(df['High'].iloc[i])}
                break
        choch_bull = bos_bull and float(df['Close'].iloc[-10]) < float(df['Low'].iloc[-25])
        choch_bear = bos_bear and float(df['Close'].iloc[-10]) > float(df['High'].iloc[-25])
        mb = None
        if bu_ob:
            mb = {"low": (bu_ob['low']+bu_ob['high'])/2, "high": bu_ob['high']}
        elif be_ob:
            mb = {"low": be_ob['low'], "high": (be_ob['low']+be_ob['high'])/2}
        return {
            "bos_bull": bos_bull, "bos_bear": bos_bear,
            "choch_bull": choch_bull, "choch_bear": choch_bear,
            "bu_ob": bu_ob, "be_ob": be_ob, "mb": mb,
            "discount": disc, "close": last_close
        }
    except Exception as e:
        print(f"smc err {e}")
        return None

def full_multi_tf_analysis(symbol):
    try:
        df_4h = get_data_direct(symbol, "240m", "1mo")
        df_1h = get_data_direct(symbol, "60m", "5d")
        df_15m = get_data_direct(symbol, "15m", "2d")
        if df_1h is None and df_15m is None:
            return {"signal":False,"symbol":symbol,"reason":"Yahoo warming up - retry in 20s"}
        smc_4h = detect_smc(df_4h) if df_4h is not None else None
        smc_1h = detect_smc(df_1h) if df_1h is not None else None
        smc_15m = detect_smc(df_15m) if df_15m is not None else None
        if not smc_1h or not smc_15m:
            return {"signal":False,"symbol":symbol,"reason":f"Loading SMC 1h:{smc_1h is not None} 15m:{smc_15m is not None}"}
        score = 0
        conf = []
        direction = None
        ob_type = ""
        disc = smc_15m['discount']
        close = smc_15m['close']
        if disc > 60:
            score += 2
            conf.append(f"Disc {disc:.0f}%")
            direction = "BUY"
            if disc > 70:
                score += 1
                conf.append("Deep Disc")
        elif disc < 40:
            score += 2
            conf.append(f"Prem {disc:.0f}%")
            direction = "SELL"
            if disc < 30:
                score += 1
                conf.append("Deep Prem")
        else:
            score += 1
            conf.append(f"EQ {disc:.0f}%")
        if smc_4h:
            if smc_4h['bos_bull']:
                score += 1
                conf.append("4H BULL")
            if smc_4h['bos_bear']:
                score += 1
                conf.append("4H BEAR")
        if smc_1h['choch_bull']:
            score += 2
            conf.append("CHoCH BULL")
            direction = "BUY"
        if smc_1h['choch_bear']:
            score += 2
            conf.append("CHoCH BEAR")
            direction = "SELL"
        if smc_1h['bos_bull'] or smc_15m['bos_bull']:
            score += 1
            conf.append("BOS BULL")
        if smc_1h['bos_bear'] or smc_15m['bos_bear']:
            score += 1
            conf.append("BOS BEAR")
        if disc > 60:
            if smc_1h['bu_ob']:
                score += 2
                conf.append("Bu-OB")
                ob_type = "Bu-OB"
                if smc_1h['bu_ob']['low']*0.999 <= close <= smc_1h['bu_ob']['high']*1.001:
                    score += 2
                    conf.append("🔥 Bu-OB RETEST")
            if smc_1h['mb']:
                score += 1
                conf.append("MB")
        if disc < 40:
            if smc_1h['be_ob']:
                score += 2
                conf.append("Be-OB")
                ob_type = "Be-OB"
                if smc_1h['be_ob']['low']*0.999 <= close <= smc_1h['be_ob']['high']*1.001:
                    score += 2
                    conf.append("🔥 Be-OB RETEST")
            if smc_1h['mb']:
                score += 1
                conf.append("MB")
        if not direction:
            direction = "BUY" if disc > 50 else "SELL"
        entry = close
        try:
            atr = float((df_15m['High']-df_15m['Low']).rolling(10).mean().iloc[-1])
        except:
            atr = entry * 0.002
        if atr == 0 or str(atr) == 'nan':
            atr = entry * 0.002
        sl = entry - atr*1.5 if direction == "BUY" else entry + atr*1.5
        if ob_type == "Bu-OB" and smc_1h['bu_ob']:
            sl = smc_1h['bu_ob']['low'] - atr*0.5
        if ob_type == "Be-OB" and smc_1h['be_ob']:
            sl = smc_1h['be_ob']['high'] + atr*0.5
        tp = entry + (entry - sl)*3 if direction == "BUY" else entry - (sl - entry)*3

        # V8.3 DECIMALS FIX
        entry = round_by_symbol(symbol, entry)
        sl = round_by_symbol(symbol, sl)
        tp = round_by_symbol(symbol, tp)
        if direction == "BUY" and sl >= entry:
            sl = round_by_symbol(symbol, entry - atr*1.5)
        if direction == "SELL" and sl <= entry:
            sl = round_by_symbol(symbol, entry + atr*1.5)
        tp = round_by_symbol(symbol, entry + (entry - sl)*3 if direction == "BUY" else entry - (sl - entry)*3)

        quality = "LOW"
        if score >= 8:
            quality = f"🔥🔥 SNIPER {ob_type}+CHoCH+BOS"
        elif score >= 6:
            quality = f"🔥 PREMIUM {ob_type}+BOS"
        elif score >= 5:
            quality = f"✅ HIGH {ob_type}"
        elif score >= 4:
            quality = f"📊 {ob_type} pullback"

        news = fetch_forexfactory_auto()
        nt = ""
        nw = False
        if news:
            nw = True
            nt = f"📰 {news[0]['event']}"

        if score < 4:
            return {
                "signal": False,
                "symbol": symbol,
                "reason": f"Score {score}/8 disc {disc:.0f}% {ob_type} {conf}",
                "score": score,
                "news_warning": nw,
                "news_text": nt
            }

        return {
            "signal": True,
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "score": score,
            "quality": quality,
            "bias": f"disc {disc:.0f}% | Bu-OB:{smc_1h['bu_ob'] is not None} Be-OB:{smc_1h['be_ob'] is not None} MB:{smc_1h['mb'] is not None} CHoCH:{smc_1h['choch_bull'] or smc_1h['choch_bear']}",
            "confluence": conf,
            "reason": f"{ob_type} + CHoCH + BOS + MB",
            "news_warning": nw,
            "news_text": nt,
            "news_bias": None
        }

    except Exception as e:
        traceback.print_exc()
        return {"signal":False,"symbol":symbol,"reason":f"Error {str(e)[:100]}"}

def get_universal_news_bias(symbol, news_event, outcome):
    sym = symbol.upper()
    usd_strong = None
    if (news_event == "NFP" and outcome == "strong") or (news_event == "CPI" and outcome == "high") or (news_event == "FOMC" and outcome == "rates_up"):
        usd_strong = True
    elif (news_event == "NFP" and outcome == "weak") or (news_event == "CPI" and outcome == "low") or (news_event == "FOMC" and outcome == "rates_down"):
        usd_strong = False
    else:
        return None, None
    if "XAU" in sym or "GOLD" in sym:
        return ("BEAR" if usd_strong else "BULL", "$ UP = Gold DOWN")
    elif sym in ["EURUSD","GBPUSD"]:
        return ("BEAR" if usd_strong else "BULL", "$ Strong = Sell")
    else:
        return ("BULL" if usd_strong else "BEAR", "$ Strong = Buy USD")
