import yfinance as yf
import pandas as pd
import requests
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

# === UNIVERSAL NEWS LOGIC - FROM YOUR SCREENSHOT - ALL PAIRS ===
def get_universal_news_bias(symbol, news_event, outcome):
    sym = symbol.upper()
    usd_strong = None
    if (news_event == "NFP" and outcome == "strong") or \
       (news_event == "CPI" and outcome == "high") or \
       (news_event == "FOMC" and outcome == "rates_up") or \
       (news_event == "UNEMPLOYMENT" and outcome == "low"):
        usd_strong = True
    elif (news_event == "NFP" and outcome == "weak") or \
         (news_event == "CPI" and outcome == "low") or \
         (news_event == "FOMC" and outcome == "rates_down") or \
         (news_event == "UNEMPLOYMENT" and outcome == "high"):
        usd_strong = False
    else:
        return None, None

    if "XAU" in sym or "GOLD" in sym or "XAG" in sym:
        bias = "BEAR" if usd_strong else "BULL"
        reason = "$ UP = Gold DOWN" if usd_strong else "$ DOWN = Gold UP"
    elif sym in ["EURUSD","GBPUSD","AUDUSD","NZDUSD"]:
        bias = "BEAR" if usd_strong else "BULL"
        reason = "$ Strong = Sell EUR/GBP" if usd_strong else "$ Weak = Buy EUR/GBP"
    elif sym in ["USDJPY","USDZAR","USDCAD","USDCHF"]:
        bias = "BULL" if usd_strong else "BEAR"
        reason = "$ Strong = Buy USDJPY/USDZAR" if usd_strong else "$ Weak = Sell USDJPY"
    elif "ZAR" in sym or "JPY" in sym:
        bias = "BEAR" if usd_strong else "BULL"
        reason = "$ Strong = ZAR/JPY weak"
    else: # NAS100, US30, BTC, etc
        bias = "BEAR" if usd_strong else "BULL"
        reason = "Rates Up = Indices/Crypto Down" if usd_strong else "Rates Down = Indices Up"
    return bias, reason

def fetch_forexfactory_auto():
    """Auto fetches ForexFactory High Impact USD news for TODAY"""
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        r = requests.get(url, timeout=12, headers={'User-Agent':'Mozilla/5.0'})
        data = r.json()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        results = []
        for item in data:
            date_str = item.get('date','')
            if today not in date_str: continue
            if item.get('country')!= 'USD': continue
            if item.get('impact')!= 'High': continue
            title = item.get('title','').upper()
            ev = None
            if 'NON-FARM' in title or 'NFP' in title: ev="NFP"
            elif 'CPI' in title: ev="CPI"
            elif 'FOMC' in title or ('FED' in title and 'RATE' in title): ev="FOMC"
            elif 'UNEMPLOYMENT' in title or 'JOBLESS' in title: ev="UNEMPLOYMENT"
            elif 'INTEREST RATE' in title: ev="FOMC"
            if not ev: continue
            actual_raw = str(item.get('actual','')).replace('%','').replace('K','').strip()
            forecast_raw = str(item.get('forecast','')).replace('%','').replace('K','').strip()
            outcome = "pending"
            try:
                if actual_raw and forecast_raw and actual_raw not in ['','-','--']:
                    a = float(actual_raw); f = float(forecast_raw)
                    if ev == "NFP": outcome = "strong" if a > f else "weak"
                    elif ev == "CPI": outcome = "high" if a > f else "low"
                    elif ev == "FOMC": outcome = "rates_up" if a > f else "rates_down"
                    elif ev == "UNEMPLOYMENT": outcome = "low" if a < f else "high"
            except:
                outcome = "pending"
            results.append({
                "event": ev, "outcome": outcome,
                "title": item.get('title'), "time": date_str,
                "actual": item.get('actual'), "forecast": item.get('forecast')
            })
        return results
    except Exception as e:
        print(f"News fetch err {e}")
        return []

def _normalize_df(df):
    """FIX: Handles yfinance multi-index (Close, GC=F) -> Close"""
    if df is None or df.empty: return None
    try:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        # Normalize to Title case: close -> Close, CLOSE -> Close
        new_cols = {}
        for c in df.columns:
            cs = str(c).strip()
            if cs.lower() == 'close': new_cols[c] = 'Close'
            elif cs.lower() == 'open': new_cols[c] = 'Open'
            elif cs.lower() == 'high': new_cols[c] = 'High'
            elif cs.lower() == 'low': new_cols[c] = 'Low'
            elif cs.lower() == 'volume': new_cols[c] = 'Volume'
            else: new_cols[c] = cs.title()
        df = df.rename(columns=new_cols)
    except Exception as e:
        print(f"normalize err {e}")
    return df

def get_data(symbol, period="1d", interval="5m"):
    try:
        yf_sym = MAP.get(symbol.upper(), symbol.upper())
        df = yf.download(yf_sym, period=period, interval=interval, progress=False, auto_adjust=True, threads=False)
        df = _normalize_df(df)
        if df is None or df.empty: return None
        if 'Close' not in df.columns: return None
        return df
    except Exception as e:
        print(f"get_data {symbol} err {e}")
        return None

def analyze_tf(df):
    if df is None or len(df) < 50: return None
    try:
        close = float(df['Close'].iloc[-1])
        high = float(df['High'].rolling(20).max().iloc[-1])
        low = float(df['Low'].rolling(20).min().iloc[-1])
        discount = ((high - close) / (high - low) * 100) if high!= low else 50
        ob = False
        try:
            last = df.iloc[-1]; prev = df.iloc[-2]
            # Bullish engulfing or bearish engulfing
            if last['Close'] > last['Open'] and prev['Close'] < prev['Open'] and last['Close'] > prev['Open']:
                ob = True
            if last['Close'] < last['Open'] and prev['Close'] > prev['Open'] and last['Close'] < prev['Open']:
                ob = True
        except:
            ob = False
        ma50 = float(df['Close'].rolling(50).mean().iloc[-1])
        bias = "bullish" if close > ma50 else "bearish"
        return {"bias": bias, "discount": discount, "ob": ob, "close": close}
    except Exception as e:
        print(f"analyze_tf err {e}")
        return None

def full_multi_tf_analysis(symbol):
    try:
        df_4h = get_data(symbol, period="10d", interval="4h")
        df_1h = get_data(symbol, period="5d", interval="1h")
        df_5m = get_data(symbol, period="1d", interval="5m")

        tf_4h = analyze_tf(df_4h)
        tf_1h = analyze_tf(df_1h)
        tf_5m = analyze_tf(df_5m)

        if not tf_4h or not tf_1h or not tf_5m:
            return {"signal": False, "symbol": symbol, "reason": "No data yet (yfinance loading) - retry 30s"}

        score = 0
        confluence = []
        direction = None

        confluence.append(f"4H {tf_4h['bias']}")
        score += 1

        if tf_1h['discount'] > 60:
            confluence.append(f"1H discount ({tf_1h['discount']:.0f}%)")
            score += 2
            direction = "BUY"
        elif tf_1h['discount'] < 40:
            confluence.append(f"1H premium ({tf_1h['discount']:.0f}%)")
            score += 2
            direction = "SELL"

        if tf_1h['ob'] or tf_5m['ob']:
            confluence.append("✅ OB detected")
            score += 2

        if tf_5m['ob']:
            confluence.append("✅ 5M STRUCTURE: engulfing + BOS")
            score += 2

        if not direction:
            direction = "BUY" if tf_4h['bias'] == "bullish" else "SELL"

        entry = tf_5m['close']
        try:
            atr = float((df_5m['High'] - df_5m['Low']).rolling(14).mean().iloc[-1])
        except:
            atr = entry * 0.002
        if atr == 0 or atr!= atr: # NaN check
            atr = entry * 0.002

        if direction == "BUY":
            sl = entry - atr*1.5
            tp = entry + atr*4.5
        else:
            sl = entry + atr*1.5
            tp = entry - atr*4.5

        quality = "STANDARD"
        if score >= 7: quality = "🔥🔥 SNIPER - OB + DISCOUNT 🔥🔥"
        elif score >= 6: quality = "🔥 PREMIUM"
        elif score >= 5: quality = "✅ HIGH QUALITY"
        elif score >= 4: quality = "📊 MEDIUM PULLBACK"

        bias_text = f"{tf_4h['bias']} | 4H:discount({tf_4h['discount']:.0f}%) 1H:discount({tf_1h['discount']:.0f}%) 5M:discount({tf_5m['discount']:.0f}%) | HTF"

        # === AUTO NEWS FOR ALL PAIRS ===
        news_events = fetch_forexfactory_auto()
        news_warning = False
        news_text = ""
        news_bias = None

        if news_events:
            news_warning = True
            for ne in news_events:
                if ne['outcome']!= 'pending':
                    news_bias, news_reason = get_universal_news_bias(symbol, ne['event'], ne['outcome'])
                    news_text = f"📰 {ne['event']} {ne['outcome'].upper()} (Actual {ne['actual']} vs Forecast {ne['forecast']}) -> {news_bias} for {symbol} | {news_reason}"
                    if (news_bias == "BULL" and direction == "BUY") or (news_bias == "BEAR" and direction == "SELL"):
                        score += 0.5
                        confluence.append(f"✅ NEWS CONFIRMED: {ne['event']} {ne['outcome']} aligns")
                    else:
                        confluence.append(f"⚠️ NEWS CONFLICT: {ne['event']} {ne['outcome']} = {news_bias} vs {direction} -> 50% size")
                    break
            if not news_text:
                p = news_events[0]
                news_text = f"📰 TODAY: {p['event']} {p['title']} at {p['time'][:16]} - High Impact USD"

        if score < 4:
            return {"signal": False, "symbol": symbol, "reason": f"Score {score}/8 too low - waiting for discount + OB", "score": score, "news_warning": news_warning, "news_text": news_text}

        return {
            "signal": True,
            "symbol": symbol,
            "direction": direction,
            "entry": round(entry, 5),
            "sl": round(sl, 5),
            "tp": round(tp, 5),
            "score": score,
            "quality": quality,
            "bias": bias_text,
            "confluence": confluence,
            "reason": f"{tf_4h['bias']} + 1H discount + 5M structure",
            "news_warning": news_warning,
            "news_text": news_text,
            "news_bias": news_bias
        }

    except Exception as e:
        traceback.print_exc()
        return {"signal": False, "symbol": symbol, "reason": f"Error {str(e)[:120]}"}
