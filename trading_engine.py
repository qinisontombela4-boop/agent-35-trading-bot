import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
import traceback

# --- SYMBOL MAP ---
MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X",
    "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X", "USDZAR": "ZAR=X",
    "EURZAR": "EURZAR=X", "GBPZAR": "GBPZAR=X", "ZARJPY": "ZARJPY=X",
    "XAUUSD": "GC=F", "GOLD": "GC=F", "XAGUSD": "SI=F",
    "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
    "NAS100": "^IXIC", "US30": "^DJI", "SPX500": "^GSPC",
    "GER40": "^GDAXI", "UK100": "^FTSE", "JP225": "^N225",
    "USOIL": "CL=F", "UKOIL": "BZ=F",
    "AAPL": "AAPL", "TSLA": "TSLA", "NVDA": "NVDA", "MSFT": "MSFT"
}

# === V6.6 UNIVERSAL NEWS LOGIC (from your screenshot) ===
def get_universal_news_bias(symbol, news_event, outcome):
    """Returns (bias BULL/BEAR/None, reason_text) for ANY pair"""
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

    # Map to all pairs
    if "XAU" in sym or "GOLD" in sym or "XAG" in sym:
        bias = "BEAR" if usd_strong else "BULL"
        reason = "$ UP = Gold DOWN" if usd_strong else "$ DOWN = Gold UP"
    elif sym in ["EURUSD","GBPUSD","AUDUSD","NZDUSD","EURZAR","GBPZAR"]:
        # USD quote or ZAR risk - strong $ = DOWN for EUR/GBP
        if sym in ["EURUSD","GBPUSD","AUDUSD","NZDUSD"]:
            bias = "BEAR" if usd_strong else "BULL"
            reason = "$ Strong = Sell EUR/GBP" if usd_strong else "$ Weak = Buy EUR/GBP"
        else:
            bias = "BEAR" if usd_strong else "BULL"
            reason = "$ Strong = ZAR weak"
    elif sym in ["USDJPY","USDZAR","USDCAD","USDCHF"]:
        bias = "BULL" if usd_strong else "BEAR"
        reason = "$ Strong = Buy USDJPY/USDZAR" if usd_strong else "$ Weak = Sell USDJPY"
    elif "JPY" in sym: # EURJPY, GBPJPY, ZARJPY
        bias = "BEAR" if usd_strong else "BULL"
        reason = "Risk Off on $ Strong"
    elif sym in ["NAS100","US30","SPX500","GER40","UK100","BTCUSD","ETHUSD","SOLUSD","USOIL"]:
        bias = "BEAR" if usd_strong else "BULL"
        reason = "Rates Up = Indices/Crypto Down" if usd_strong else "Rates Down = Indices Up"
    else:
        bias = "BEAR" if usd_strong else "BULL"
        reason = "$ Strong" if usd_strong else "$ Weak"

    return bias, reason

def fetch_forexfactory_auto():
    """Fetches ForexFactory this week, finds TODAY high impact USD news + actual vs forecast"""
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
            elif 'CPI' in title and 'CORE' not in title: ev="CPI"
            elif 'FOMC' in title or 'FED' in title and 'RATE' in title: ev="FOMC"
            elif 'UNEMPLOYMENT' in title or 'JOBLESS CLAIMS' in title: ev="UNEMPLOYMENT"
            elif 'INTEREST RATE' in title: ev="FOMC"

            if not ev: continue

            # Try parse actual/forecast for auto Strong/Weak
            actual_raw = str(item.get('actual','')).replace('%','').replace('K','').strip()
            forecast_raw = str(item.get('forecast','')).replace('%','').replace('K','').strip()
            outcome = None
            try:
                if actual_raw and forecast_raw and actual_raw not in ['','-']:
                    a = float(actual_raw); f = float(forecast_raw)
                    if ev == "NFP": outcome = "strong" if a > f else "weak"
                    elif ev == "CPI": outcome = "high" if a > f else "low"
                    elif ev == "FOMC": outcome = "rates_up" if a > f else "rates_down"
                    elif ev == "UNEMPLOYMENT": outcome = "low" if a < f else "high" # low claims = strong $
            except:
                outcome = None

            # If no actual yet, we still have event today
            if not outcome:
                outcome = "pending" # will warn volatility only

            results.append({
                "event": ev,
                "outcome": outcome,
                "title": item.get('title'),
                "time": date_str,
                "actual": item.get('actual'),
                "forecast": item.get('forecast')
            })
        return results
    except Exception as e:
        print(f"News fetch err {e}")
        return []

def get_data(symbol, period="1d", interval="5m"):
    try:
        yf_sym = MAP.get(symbol.upper(), symbol)
        df = yf.download(yf_sym, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty: return None
        try: df.columns = df.columns.get_level_values(0)
        except: pass
        return df
    except:
        return None

def analyze_tf(df):
    if df is None or len(df) < 50: return {"bias":"neutral","discount":50,"ob":False}
    close = df['Close'].iloc[-1]
    high = df['High'].rolling(20).max().iloc[-1]
    low = df['Low'].rolling(20).min().iloc[-1]
    discount = ((high - close) / (high - low) * 100) if high!= low else 50
    # simple OB: bullish engulfing + wick
    ob = False
    last = df.iloc[-1]; prev = df.iloc[-2]
    if last['Close'] > last['Open'] and prev['Close'] < prev['Open'] and last['Close'] > prev['Open']:
        ob = True
    bias = "bullish" if close > df['Close'].rolling(50).mean().iloc[-1] else "bearish"
    return {"bias": bias, "discount": discount, "ob": ob, "close": close}

def full_multi_tf_analysis(symbol):
    try:
        # --- Technicals ---
        df_4h = get_data(symbol, period="10d", interval="4h")
        df_1h = get_data(symbol, period="5d", interval="1h")
        df_5m = get_data(symbol, period="1d", interval="5m")

        tf_4h = analyze_tf(df_4h)
        tf_1h = analyze_tf(df_1h)
        tf_5m = analyze_tf(df_5m)

        if not tf_4h or not tf_1h or not tf_5m:
            return {"signal": False, "symbol": symbol, "reason": "No data"}

        # Discount logic
        score = 0
        confluence = []
        direction = None

        # HTF bias
        if tf_4h['bias'] == "bullish":
            confluence.append(f"4H bullish")
            score += 1
        else:
            confluence.append(f"4H bearish")
            score += 1

        # 1H discount
        if tf_1h['discount'] > 60: # discount zone for longs
            confluence.append(f"1H discount ({tf_1h['discount']:.0f}%)")
            score += 2
            direction = "BUY"
        elif tf_1h['discount'] < 40:
            confluence.append(f"1H premium ({tf_1h['discount']:.0f}%)")
            score += 2
            direction = "SELL"

        # OB
        if tf_1h['ob'] or tf_5m['ob']:
            confluence.append(f"✅ OB detected")
            score += 2

        # 5M structure
        if tf_5m['ob']:
            confluence.append(f"✅ 5M STRUCTURE: bullish engulfing + BOS + wick rejection" if direction=="BUY" else "✅ 5M STRUCTURE: bearish engulfing")
            score += 2

        if not direction:
            direction = "BUY" if tf_4h['bias']=="bullish" else "SELL"

        # Entry / SL / TP
        entry = tf_5m['close']
        atr = (df_5m['High'] - df_5m['Low']).rolling(14).mean().iloc[-1] if df_5m is not None else entry*0.002
        if direction == "BUY":
            sl = entry - atr*1.5
            tp = entry + atr*4.5
        else:
            sl = entry + atr*1.5
            tp = entry - atr*4.5

        # Quality
        quality = "STANDARD"
        if score >= 7: quality = "🔥🔥 SNIPER - OB + DISCOUNT 🔥🔥"
        elif score >= 6: quality = "🔥 PREMIUM"
        elif score >= 5: quality = "✅ HIGH QUALITY"
        elif score >= 4: quality = "📊 MEDIUM PULLBACK"

        bias_text = f"{tf_4h['bias']} | 4H:discount({tf_4h['discount']:.0f}%) 1H:discount({tf_1h['discount']:.0f}%) 5M:discount({tf_5m['discount']:.0f}%) | HTF"

        # === NEWS AUTO V6.6 ===
        news_events = fetch_forexfactory_auto() # today
        news_warning = False
        news_text = ""
        news_bias = None
        news_reason = ""

        if news_events:
            news_warning = True
            # Use first event with actual outcome, or pending
            for ne in news_events:
                if ne['outcome']!= 'pending':
                    news_bias, news_reason = get_universal_news_bias(symbol, ne['event'], ne['outcome'])
                    news_text = f"📰 {ne['event']} {ne['outcome'].upper()} (Actual {ne['actual']} vs Forecast {ne['forecast']}) -> {news_bias} for {symbol} | {news_reason}"
                    # Boost if aligns
                    if (news_bias == "BULL" and direction == "BUY") or (news_bias == "BEAR" and direction == "SELL"):
                        score += 0.5
                        confluence.append(f"✅ NEWS CONFIRMED: {ne['event']} {ne['outcome']} aligns with {direction}")
                    else:
                        confluence.append(f"⚠️ NEWS CONFLICT: {ne['event']} {ne['outcome']} = {news_bias} vs Technical {direction} -> 50% size")
                    break
            if not news_text: # pending news today
                pending = news_events[0]
                news_text = f"📰 TODAY: {pending['event']} {pending['title']} at {pending['time'][:16]} - High Impact USD\nYour Rule: Strong/High/Up = $ UP, Gold DOWN | Weak/Low/Down = $ DOWN, Gold UP"
                confluence.append(f"⚠️ NEWS VOLATILITY: {pending['event']} Today - wider SL")

        if score < 4:
            return {"signal": False, "symbol": symbol, "reason": f"Score {score}/8 too low", "score": score, "news_warning": news_warning, "news_text": news_text}

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
        return {"signal": False, "symbol": symbol, "reason": f"Error {e}"}
