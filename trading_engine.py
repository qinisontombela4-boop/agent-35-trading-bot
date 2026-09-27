import os, requests
from datetime import datetime
import news_calendar

def get_keys():
    keys=[]
    for k in ["TWELVE_DATA_API_KEY","TWELVE_DATA_API_KEY_2","TWELVE_DATA_API_KEY_3","TWELVE_DATA_API_KEY_4"]:
        v=os.getenv(k)
        if v: keys.append(v)
    return keys

KEYS=get_keys()
KEY_INDEX=0

SYMBOL_MAP={
    "EURUSD":"EUR/USD","GBPUSD":"GBP/USD","USDJPY":"USD/JPY","USDCHF":"USD/CHF",
    "AUDUSD":"AUD/USD","USDCAD":"USD/CAD","NZDUSD":"NZD/USD","EURJPY":"EUR/JPY",
    "GBPJPY":"GBP/JPY","EURGBP":"EUR/GBP","AUDJPY":"AUD/JPY","CADJPY":"CAD/JPY",
    "CHFJPY":"CHF/JPY","EURCHF":"EUR/CHF","GBPCHF":"GBP/CHF","EURAUD":"EUR/AUD",
    "GBPAUD":"GBP/AUD","EURCAD":"EUR/CAD","GBPCAD":"GBP/CAD","EURNZD":"EUR/NZD",
    "GBPNZD":"GBP/NZD","AUDNZD":"AUD/NZD","AUDCAD":"AUD/CAD","NZDCAD":"NZD/CAD",
    "AUDCHF":"AUD/CHF","NZDJPY":"NZD/JPY",
    "XAUUSD":"XAU/USD","XAGUSD":"XAG/USD","XTIUSD":"WTI/USD","XBRUSD":"BRENT/USD",
    "US30":"DJI","NAS100":"NDX","SPX500":"SPX","GER40":"DAX","UK100":"FTSE",
    "FRA40":"CAC","ESP35":"IBEX","ITA40":"FTSE MIB","JPN225":"NIKKEI","AUS200":"ASX 200",
    "BTCUSD":"BTC/USD","ETHUSD":"ETH/USD","SOLUSD":"SOL/USD","BNBUSD":"BNB/USD",
    "XRPUSD":"XRP/USD","ADAUSD":"ADA/USD","DOGEUSD":"DOGE/USD","DOTUSD":"DOT/USD",
    "AVAXUSD":"AVAX/USD","LINKUSD":"LINK/USD","MATICUSD":"MATIC/USD","LTCUSD":"LTC/USD"
}

def get_next_key():
    global KEY_INDEX
    if not KEYS: return None
    key=KEYS[KEY_INDEX % len(KEYS)]; KEY_INDEX+=1; return key

def td_request(symbol, interval, outputsize=50):
    if not KEYS: return {"code":500,"message":"No keys"}
    td_symbol=SYMBOL_MAP.get(symbol,symbol); last_error=None
    for _ in range(len(KEYS)):
        key=get_next_key()
        url=f"https://api.twelvedata.com/time_series?symbol={td_symbol}&interval={interval}&outputsize={outputsize}&apikey={key}"
        try:
            r=requests.get(url,timeout=12).json()
            if "code" in r and r["code"]==429: last_error=r; continue
            if "values" in r: return r
            last_error=r
        except Exception as e: last_error={"code":500,"message":str(e)}; continue
    return last_error if last_error else {"code":500,"message":"fail"}

def get_values(symbol, interval, outputsize=50):
    data=td_request(symbol, interval, outputsize)
    if "values" not in data: return None, data
    vals=data["values"]; vals.reverse(); candles=[]
    for v in vals:
        try: candles.append({"open":float(v["open"]),"high":float(v["high"]),"low":float(v["low"]),"close":float(v["close"]),"time":v.get("datetime","")})
        except: continue
    return candles, None

# ---- NEW: simple per-analysis cache so the same symbol+interval is never
# fetched twice in one call to full_multi_tf_analysis. Saves API quota and
# guarantees h1_ob and multi_ob score off the SAME 1h candles, not two
# separately-fetched (and possibly slightly different) sets. ----
def get_values_cached(cache, symbol, interval, outputsize=50, historical=None):
    # BACKTEST SUPPORT: if `historical` provides pre-fetched candles for this
    # interval, use those instead of calling the live API — this is what lets
    # the backtester reuse this EXACT function (and therefore the exact same
    # scoring logic) instead of a separate reimplementation that could drift
    # from what's actually trading live.
    if historical and interval in historical:
        candles = historical[interval]
        return (candles[-outputsize:] if outputsize else candles), None
    key=(symbol, interval, outputsize)
    if key in cache: return cache[key]
    result = get_values(symbol, interval, outputsize)
    cache[key] = result
    return result

def is_market_open(symbol, as_of=None):
    # BACKTEST SUPPORT: as_of lets a backtest ask "was the market open at
    # THIS simulated point in time" instead of always checking right now.
    now_utc = as_of or datetime.utcnow(); weekday = now_utc.weekday(); hour = now_utc.hour
    crypto = ["BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD","ADAUSD","DOGEUSD","DOTUSD","AVAXUSD","LINKUSD","MATICUSD","LTCUSD"]
    if symbol in crypto: return True, ""
    if weekday==5: return False, "Closed - Saturday"
    if weekday==6 and hour<22: return False, "Closed - Sunday opens 22:00 UTC"
    if weekday==4 and hour>=22: return False, "Closed - Friday 22:00"
    return True, ""

def ema(candles, period):
    if len(candles)<period: return None
    closes=[c["close"] for c in candles]; ema_val=sum(closes[:period])/period; k=2/(period+1)
    for price in closes[period:]: ema_val=price*k + ema_val*(1-k)
    return ema_val

# ---- FIXED: proper Wilder's RSI, smoothed across the WHOLE fetched series
# (not just the earliest period+1 candles). Reflects current momentum. ----
def rsi(candles, period=14):
    if len(candles) < period + 1: return 50
    closes = [c["close"] for c in candles]
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]

    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ---- NEW: ATR, used for stop-loss distance and volatility-aware scalp checks ----
def atr(candles, period=14):
    if len(candles) < period + 1: return None
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    recent = trs[-period:]
    return sum(recent) / len(recent)

def get_htf_bias(symbol, cache, historical=None):
    candles,_=get_values_cached(cache, symbol,"1day",100, historical)
    if not candles or len(candles)<30: return "NEUTRAL",50,None
    swings = find_swing_points(candles, lookback=2)
    events = detect_structure_events(candles, swings)
    if events:
        bias = events[-1]["direction"]
    else:
        ema5=ema(candles,5); ema20=ema(candles,20)
        bias = ("BULLISH" if ema5>ema20 else "BEARISH" if ema5<ema20 else "NEUTRAL") if (ema5 and ema20) else "NEUTRAL"
    d_range = compute_dealing_range(swings, lookback_swings=8, candles=candles)
    current = candles[-1]["close"]
    premium = fib_level(d_range, current)*100 if d_range else 50
    return bias,premium,candles

def check_4h_alignment(symbol, daily_bias, cache, historical=None):
    candles,_=get_values_cached(cache, symbol,"4h",100, historical)
    if not candles or len(candles)<30: return False,"NEUTRAL"
    swings = find_swing_points(candles, lookback=2)
    events = detect_structure_events(candles, swings)
    if events:
        bias4h = events[-1]["direction"]
    else:
        ema5=ema(candles,5); ema20=ema(candles,20)
        bias4h = ("BULLISH" if ema5>ema20 else "BEARISH" if ema5<ema20 else "NEUTRAL") if (ema5 and ema20) else "NEUTRAL"
    aligned=(bias4h==daily_bias and daily_bias!="NEUTRAL"); return aligned,bias4h

def detect_candle(candles):
    if len(candles)<3: return [],0
    last=candles[-1]; prev=candles[-2]; patterns=[]; score=0
    body=abs(last["close"]-last["open"]); range_c=last["high"]-last["low"]
    if range_c==0: return [],0
    if prev["close"]<prev["open"] and last["close"]>last["open"] and last["close"]>prev["open"] and last["open"]<prev["close"]: patterns.append("Bull Engulf"); score+=4
    if prev["close"]>prev["open"] and last["close"]<last["open"] and last["close"]<prev["open"] and last["open"]>prev["close"]: patterns.append("Bear Engulf"); score+=4
    lower_wick=min(last["open"],last["close"])-last["low"]; upper_wick=last["high"]-max(last["open"],last["close"])
    if lower_wick>body*2 and upper_wick<body*0.5 and range_c>0: patterns.append("Hammer"); score+=3
    if upper_wick>body*2 and lower_wick<body*0.5: patterns.append("Hang Man"); score+=3
    if body<range_c*0.1: patterns.append("Doji"); score+=2
    return patterns,score

def detect_sweep(candles, bias):
    if len(candles)<12: return False,0
    recent=candles[-11:-1]; last=candles[-1]
    if "BULLISH" in bias.upper():
        recent_low=min([c["low"] for c in recent])
        if last["low"]<recent_low and last["close"]>recent_low: return True,3
    if "BEARISH" in bias.upper():
        recent_high=max([c["high"] for c in recent])
        if last["high"]>recent_high and last["close"]<recent_high: return True,3
    return False,0

def detect_fvg(candles):
    if len(candles)<4: return False
    c1=candles[-3]; c3=candles[-1]
    if c3["low"]>c1["high"]: return True
    if c3["high"]<c1["low"]: return True
    return False

# ================= REAL MARKET STRUCTURE (swings, BOS/CHoCH, liquidity, =================
# ================= dealing range) — replaces crude rolling-window checks =================
#
# WHY THIS EXISTS: the old approach used a rolling 20-candle high/low for
# "BOS" and a 10-candle high/low for "sweep" — arbitrary windows with no
# concept of genuine swing structure. That let a raw breakout candle at the
# top of an extended move score as a valid bullish continuation (BOS +
# daily/4H trend + a pattern), even with nothing above it but liquidity to
# grab before a pullback — exactly the false signal this section fixes.

def find_swing_points(candles, lookback=2):
    """A swing high/low: the most extreme high/low among `lookback` candles
    on both sides — a genuine structural pivot, not a window maximum."""
    swings = []
    n = len(candles)
    for i in range(lookback, n - lookback):
        window = candles[i-lookback:i+lookback+1]
        c = candles[i]
        if c["high"] == max(k["high"] for k in window):
            swings.append({"index": i, "candle": c, "kind": "high"})
        if c["low"] == min(k["low"] for k in window):
            swings.append({"index": i, "candle": c, "kind": "low"})
    return swings

def detect_structure_events(candles, swings):
    """Walks forward tracking the last confirmed swing and the active
    trend. BOS = price closes beyond the last swing in the SAME direction
    as the trend (continuation). CHoCH = closes beyond it AGAINST the
    trend — the first sign of a possible reversal.

    Break checks run BEFORE this candle's own swing-point status is
    recorded, so a candle that both breaks a prior swing AND becomes the
    new extreme itself (common on a single strong impulse candle) still
    registers the break — it isn't silently absorbed into swing-point
    formation just because it happens to be both things at once."""
    events = []
    if not swings: return events
    trend = None
    last_high = None; last_low = None
    swings_by_index = {s["index"]: s for s in swings}
    for i, c in enumerate(candles):
        if last_high is not None and c["close"] > last_high["candle"]["high"]:
            kind = "CHoCH" if trend in (None, "BEARISH") else "BOS"
            events.append({"index": i, "kind": kind, "direction": "BULLISH", "level": last_high["candle"]["high"], "candle": c})
            trend = "BULLISH"; last_high = None
        elif last_low is not None and c["close"] < last_low["candle"]["low"]:
            kind = "CHoCH" if trend in (None, "BULLISH") else "BOS"
            events.append({"index": i, "kind": kind, "direction": "BEARISH", "level": last_low["candle"]["low"], "candle": c})
            trend = "BEARISH"; last_low = None
        if i in swings_by_index:
            s = swings_by_index[i]
            if s["kind"] == "high": last_high = s
            else: last_low = s
    return events

def find_liquidity_zones(swings, tolerance_pct=0.0008):
    """Clusters swing highs within tolerance into a buy-side liquidity pool
    (equal highs), swing lows into sell-side (equal lows) — genuine resting
    stop-order pools, not an arbitrary N-candle lookback high/low."""
    zones = []
    highs = sorted([s for s in swings if s["kind"]=="high"], key=lambda s: s["candle"]["high"])
    lows = sorted([s for s in swings if s["kind"]=="low"], key=lambda s: s["candle"]["low"])
    def cluster(points, attr, kind):
        used = set()
        for i, p in enumerate(points):
            if p["index"] in used: continue
            level = p["candle"][attr]
            group = [p]
            for q in points[i+1:]:
                if q["index"] in used: continue
                other = q["candle"][attr]
                if level != 0 and abs(other-level)/level <= tolerance_pct:
                    group.append(q); used.add(q["index"])
            if len(group) >= 2:
                avg = sum(g["candle"][attr] for g in group)/len(group)
                zones.append({"price": avg, "kind": kind, "indices": [g["index"] for g in group]})
            used.add(p["index"])
    cluster(highs, "high", "buy_side")
    cluster(lows, "low", "sell_side")
    return zones

def check_sweep(zones, candles, lookback_bars=20):
    """Was any liquidity zone swept (wick through, close back inside)
    within the last `lookback_bars` candles? Returns the most recent sweep
    event (with its resulting direction), or None."""
    start_index = max(0, len(candles) - lookback_bars)
    latest = None
    for z in zones:
        zone_start = max(z["indices"], default=start_index) + 1
        for i in range(max(zone_start, start_index), len(candles)):
            c = candles[i]
            if z["kind"]=="buy_side" and c["high"] > z["price"] and c["close"] < z["price"]:
                if latest is None or i > latest["index"]: latest = {"index": i, "direction": "BEARISH"}
            if z["kind"]=="sell_side" and c["low"] < z["price"] and c["close"] > z["price"]:
                if latest is None or i > latest["index"]: latest = {"index": i, "direction": "BULLISH"}
    return latest

def compute_dealing_range(swings, lookback_swings=8, candles=None, raw_lookback=40):
    """Current dealing range from the most recent swing points — highest
    high and lowest low among them. Discount = below equilibrium (favorable
    for buying), Premium = above (favorable for selling).

    Also widens the range to include the raw recent candle extremes (not
    just CONFIRMED swing points) when `candles` is provided. A swing needs
    a couple of pullback candles afterward before it's confirmed — so a
    still-extending breakout that hasn't paused yet has no confirmed swing
    at its own tip, and without this widening, current price could sit
    miles outside a now-stale range, producing a nonsensical reading like
    "251% premium" instead of the correct "100%, fully extended right now."
    """
    top = None; bottom = None
    if len(swings) >= 2:
        recent = swings[-lookback_swings:]
        highs = [s for s in recent if s["kind"]=="high"]
        lows = [s for s in recent if s["kind"]=="low"]
        if highs: top = max(h["candle"]["high"] for h in highs)
        if lows: bottom = min(l["candle"]["low"] for l in lows)
    if candles:
        window = candles[-raw_lookback:]
        raw_high = max(c["high"] for c in window)
        raw_low = min(c["low"] for c in window)
        top = raw_high if top is None else max(top, raw_high)
        bottom = raw_low if bottom is None else min(bottom, raw_low)
    if top is None or bottom is None or top <= bottom:
        return None
    return {"high": top, "low": bottom}

def zone_of(dealing_range, price):
    if not dealing_range: return "none"
    eq = (dealing_range["high"] + dealing_range["low"]) / 2
    if price > eq: return "premium"
    if price < eq: return "discount"
    return "equilibrium"

def ob_in_zone(bounds, direction, dealing_range):
    """Is this specific order block actually SITTING in a zone appropriate
    to its direction — a bullish OB in discount/equilibrium, a bearish OB
    in premium/equilibrium? Without this check, "an order block exists"
    could be satisfied by a block sitting right at a fresh high (premium),
    which is exactly the false-confidence-to-chase-a-breakout pattern this
    whole rewrite exists to prevent — an order block is not inherently a
    reason to buy if it's up at the top of the move, not down in the dip."""
    if not bounds or not dealing_range: return False
    mid = (bounds[0] + bounds[1]) / 2
    z = zone_of(dealing_range, mid)
    if direction == "BULLISH": return z in ("discount", "equilibrium")
    if direction == "BEARISH": return z in ("premium", "equilibrium")
    return False

def fib_level(dealing_range, price):
    """0.0 at the range low, 1.0 at the range high — matches the old
    premium_pct field's semantics exactly, for compatibility."""
    if not dealing_range: return 0.5
    span = dealing_range["high"] - dealing_range["low"]
    if span == 0: return 0.5
    return (price - dealing_range["low"]) / span

# ---- FIXED: now takes `bias` and only returns an order block that AGREES
# with it (a bearish OB can no longer add score to a bullish setup).
# Also scans from the MOST RECENT candidate backward, so the nearest
# (most relevant, least likely already-invalidated) OB wins over an older
# one further back in the lookback window. ----
def detect_order_block(candles, bias=None):
    if len(candles) < 20: return False, "", 0, None
    last_close = candles[-1]["close"]; last_low = candles[-1]["low"]; last_high = candles[-1]["high"]
    want_bull = bias is None or "BULLISH" in bias.upper()
    want_bear = bias is None or "BEARISH" in bias.upper()

    for i in range(len(candles)-4, len(candles)-15, -1):
        c = candles[i]; body = abs(c["close"] - c["open"])
        if body == 0: continue
        next_candles = candles[i+1:i+5]
        if len(next_candles) < 2: continue

        if want_bull and c["close"] < c["open"]:
            impulse_high = max([cc["close"] for cc in next_candles])
            impulse_strength = (impulse_high - c["high"]) / c["high"] if c["high"]!=0 else 0
            if impulse_strength > 0.002:
                ob_low = c["low"]; ob_high = c["high"]; ob_mid = (ob_low + ob_high)/2
                tolerance = ob_high * 0.005 if ob_high > 1000 else ob_high * 0.0015
                # Invalidation: a normal retest dips INTO or slightly THROUGH
                # the zone before reversing — that's not a break, it's the
                # entry. Only treat it as genuinely broken if price closed a
                # full zone-height beyond it (a decisive structural break),
                # not just a marginal tick past a tight tolerance band.
                zone_height = ob_high - ob_low
                break_margin = max(zone_height, tolerance)
                broken = any(cc["close"] < ob_low - break_margin for cc in candles[i+1:-1])
                if broken: continue
                if abs(last_close - ob_mid) <= tolerance or (last_low <= ob_high and last_close >= ob_low):
                    return True, f"Bull OB {ob_low:.2f}-{ob_high:.2f}", 4, (ob_low, ob_high)

        if want_bear and c["close"] > c["open"]:
            impulse_low = min([cc["close"] for cc in next_candles])
            impulse_strength = (c["low"] - impulse_low) / c["low"] if c["low"]!=0 else 0
            if impulse_strength > 0.002:
                ob_low = c["low"]; ob_high = c["high"]; ob_mid = (ob_low + ob_high)/2
                tolerance = ob_high * 0.005 if ob_high > 1000 else ob_high * 0.0015
                # Same reasoning as the bullish case: only a full zone-height
                # breach counts as genuinely broken, not a marginal retest.
                zone_height = ob_high - ob_low
                break_margin = max(zone_height, tolerance)
                broken = any(cc["close"] > ob_high + break_margin for cc in candles[i+1:-1])
                if broken: continue
                if abs(last_close - ob_mid) <= tolerance or (last_high >= ob_low and last_close <= ob_high):
                    return True, f"Bear OB {ob_low:.2f}-{ob_high:.2f}", 4, (ob_low, ob_high)
    return False, "", 0, None

# ---- NEW: decimal precision per instrument CATEGORY, not per live price
# level. The old approach ("if price < 20, use 5 decimals, else 2") breaks
# down constantly: JPY pairs and indices sit above 20 but need their own
# conventions, and crypto alts drift across that threshold over time,
# silently changing how many decimals a symbol displays from one signal to
# the next. This is fixed per-symbol instead, matching how real trading
# platforms quote each instrument. ----
def price_decimals(symbol):
    if symbol == "XAUUSD": return 2
    if symbol == "XAGUSD": return 3
    if symbol in ("XTIUSD", "XBRUSD"): return 2
    if symbol in ("US30","NAS100","SPX500","GER40","UK100","FRA40","ESP35","ITA40","JPN225","AUS200"): return 1
    if symbol in ("BTCUSD","ETHUSD"): return 2
    if symbol in ("SOLUSD","BNBUSD","LINKUSD","LTCUSD","AVAXUSD"): return 3
    if symbol in ("XRPUSD","ADAUSD","DOGEUSD","DOTUSD","MATICUSD"): return 5
    if "JPY" in symbol: return 3
    return 5  # standard forex majors/crosses (pipette precision)

# ---- NEW: builds a short, plain-language explanation FROM the same factors
# that produced the score — not a separate guess, just that reasoning
# translated into a sentence a human can read in the Telegram message. ----
def build_rationale(symbol, final_bias, score, daily_bias, aligned_4h, bias_4h, premium_pct,
                     rsi_h1, bos_bull, bos_bear, breakout_bull, breakout_bear,
                     h1_fvg, m5_fvg, h1_ob, h1_ob_zone, m5_ob, multi_ob, multi_ob_details,
                     h1_sweep, m5_sweep, h1_patterns, m5_patterns):
    direction_word = "buyers" if final_bias == "BULLISH" else "sellers"
    parts = []

    if aligned_4h:
        parts.append(f"daily and 4H trend both point {final_bias.lower()}, so {direction_word} have the higher-timeframe trend behind them")
    elif daily_bias != "NEUTRAL":
        parts.append(f"daily trend is {daily_bias.lower()}")

    if final_bias == "BULLISH" and premium_pct <= 35:
        parts.append(f"price is in the discount zone of its recent range ({premium_pct:.0f}%), a level buyers have tended to defend")
    elif final_bias == "BEARISH" and premium_pct >= 65:
        parts.append(f"price is in the premium zone of its recent range ({premium_pct:.0f}%), a level sellers have tended to defend")

    if h1_sweep or m5_sweep:
        parts.append("a recent liquidity sweep took out resting stops just before reversing")

    ob_note = None
    if h1_ob: ob_note = f"an H1 {h1_ob_zone.split(' ')[0].lower()} order block"
    elif multi_ob: ob_note = f"an order block on {multi_ob_details.split('|')[0].strip()}"
    elif m5_ob: ob_note = "a fresh 5-minute order block"
    if ob_note:
        parts.append(f"price is reacting from {ob_note}")

    if h1_fvg or m5_fvg:
        parts.append("an unfilled imbalance (fair value gap) sits nearby, often acting as a magnet")

    if bos_bull or bos_bear or breakout_bull or breakout_bear:
        parts.append(f"structure just broke {'higher' if final_bias=='BULLISH' else 'lower'}, confirming momentum")

    pats = h1_patterns + m5_patterns
    if pats:
        parts.append(f"a {', '.join(sorted(set(pats)))} candle confirms rejection at this level")

    if final_bias=="BULLISH" and 40<=rsi_h1<=55:
        parts.append(f"RSI at {rsi_h1:.0f} shows a healthy pullback, not an overbought chase")
    elif final_bias=="BEARISH" and 45<=rsi_h1<=60:
        parts.append(f"RSI at {rsi_h1:.0f} shows a healthy pullback, not an oversold chase")

    if not parts:
        return f"{score}/10 confluence with no single dominant factor — lower-conviction setup, size accordingly."

    return f"{'; '.join(parts)}.".capitalize()

# ---- FIXED: reuses the already-fetched 1h candles instead of re-fetching,
# and passes bias through so it doesn't count an opposite-direction OB. ----
def detect_multi_tf_ob(symbol, bias, cache, h1_candles=None, historical=None):
    timeframes = ["4h","2h","1h"]; ob_found = False; ob_details = []; total_score = 0
    for tf in timeframes:
        if tf == "1h" and h1_candles is not None:
            candles = h1_candles
        else:
            candles,_ = get_values_cached(cache, symbol, tf, 50, historical)
        if not candles or len(candles) < 20: continue
        found, zone, score, _bounds = detect_order_block(candles, bias)
        if found: ob_found = True; ob_details.append(f"{tf.upper()} {zone}"); total_score += score
    return ob_found, " | ".join(ob_details), total_score

# ---- FIXED: now backed by a real economic calendar (news_calendar.py via
# JBlanked's API) instead of guessed date ranges, and scoped to the specific
# SYMBOL being analyzed — only blocks symbols actually correlated with the
# currency behind the imminent event, not a blanket block on everything. ----
def is_news_time(symbol, user_settings):
    trade_news = user_settings.get("trade_news", True)
    if trade_news:
        return False, ""  # user is OK trading through news — nothing to check
    blocked, event = news_calendar.is_in_blackout(
        symbol,
        minutes_before=user_settings.get("news_blackout_before_min", 15),
        minutes_after=user_settings.get("news_blackout_after_min", 15),
    )
    if blocked and event:
        when = event["time"].strftime("%H:%M UTC")
        return True, f"NEWS BLOCKED - {event['currency']} {event['name']} ({when})"
    return False, ""

DEFAULT_WEIGHTS = {
    # Multipliers applied to each scoring category. 1.0 = current/default
    # behavior. Override via full_multi_tf_analysis(..., weights={...}) —
    # backtest.py and optimize_weights.py use this to test variations
    # against real historical data without editing this file by hand.
    "daily_bias": 1.0, "h4_align": 1.0, "zone": 1.0, "rsi_pullback": 1.0,
    "structure": 1.0, "h1_fvg": 1.0, "m5_fvg": 1.0,
    "h1_ob": 1.0, "m5_ob": 1.0, "multi_ob": 1.0,
    "h1_sweep": 1.0, "m5_sweep": 1.0, "h1_pattern": 1.0, "m5_pattern": 1.0,
    "min_score": 5,  # the qualification threshold itself is tunable too
}

# ================= V24 UNIFIED ENGINE - ONE STRATEGY, 2 MODES =================
def full_multi_tf_analysis(symbol, user_settings=None, historical=None, as_of=None, weights=None):
    """historical: optional dict {"1day":[...], "4h":[...], "1h":[...], "5min":[...]}
    of pre-fetched candles, used by the backtester instead of live API calls —
    this is the SAME function the live bot calls, so backtest and live never
    diverge in logic. as_of: optional datetime the backtest is simulating
    "now" as, so market-hours checks are evaluated historically correctly.
    weights: optional dict overriding DEFAULT_WEIGHTS' multipliers — lets a
    backtest/optimizer test scoring variations without editing this file."""
    if user_settings is None: user_settings={"trade_news":True,"trading_mode":"regular","currency":"ZAR"}
    mode = user_settings.get("trading_mode","regular") # regular or scalp
    min_rr = user_settings.get("min_risk_reward", 1.5)
    cache = {}  # per-call fetch cache: guarantees no duplicate API calls or double-counted candles
    w = {**DEFAULT_WEIGHTS, **(weights or {})}

    is_open, closed_reason = is_market_open(symbol, as_of)
    if not is_open:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"premium_pct":50,"reason":closed_reason,"confluence":closed_reason,"details":{"market_closed":True},"mode":mode}
    blocked,reason=is_news_time(symbol, user_settings)
    if blocked:
        return {"symbol":symbol,"signal":False,"score":0,"bias":"NEUTRAL","entry":0,"premium_pct":50,"reason":reason,"confluence":reason,"details":{"news_blocked":True},"mode":mode}

    daily_bias,premium_pct,daily_candles=get_htf_bias(symbol, cache, historical)
    aligned_4h,bias_4h=check_4h_alignment(symbol,daily_bias, cache, historical)
    h1_candles,_=get_values_cached(cache, symbol,"1h",100, historical)
    m5_candles,_=get_values_cached(cache, symbol,"5min",100, historical)
    if not h1_candles or len(h1_candles)<30:
        return {"symbol":symbol,"signal":False,"score":0,"bias":daily_bias,"entry":0,"premium_pct":premium_pct,"reason":"No H1 data","confluence":"No H1","details":{},"mode":mode}

    # ---- H1 STRUCTURE, DEALING RANGE, LIQUIDITY ----
    # This is the core of the fix: the H1 dealing range determines whether
    # CURRENT PRICE is in a discount (favorable to buy) or premium
    # (favorable to sell) zone. That gets used as a HARD requirement below,
    # not just a scoring bonus — a setup can no longer rack up enough
    # trend-following points to fire while price sits at the top of an
    # extended move with nothing above it but liquidity to grab.
    h1_swings = find_swing_points(h1_candles, lookback=2)
    h1_events = detect_structure_events(h1_candles, h1_swings)
    last_h1_event = h1_events[-1] if h1_events else None
    bos_bull = bool(last_h1_event and last_h1_event["direction"]=="BULLISH")
    bos_bear = bool(last_h1_event and last_h1_event["direction"]=="BEARISH")
    breakout_bull, breakout_bear = bos_bull, bos_bear  # kept for compatibility with build_rationale/details below

    h1_range = compute_dealing_range(h1_swings, lookback_swings=8, candles=h1_candles)
    current_price = h1_candles[-1]["close"]
    h1_zone = zone_of(h1_range, current_price)
    h1_premium_pct = fib_level(h1_range, current_price)*100 if h1_range else 50
    recent_high = h1_range["high"] if h1_range else max(c["high"] for c in h1_candles[-21:-1])
    recent_low = h1_range["low"] if h1_range else min(c["low"] for c in h1_candles[-21:-1])

    h1_liquidity = find_liquidity_zones(h1_swings, tolerance_pct=0.0008)
    h1_sweep_event = check_sweep(h1_liquidity, h1_candles, lookback_bars=20)
    h1_sweep = bool(h1_sweep_event)

    ema5_h1=ema(h1_candles,5); ema20_h1=ema(h1_candles,20); rsi_h1=rsi(h1_candles,14)
    atr_h1=atr(h1_candles,14)
    h1_patterns,h1_pat_score=detect_candle(h1_candles)
    h1_fvg=detect_fvg(h1_candles)

    # ---- M5 STRUCTURE, LIQUIDITY, SWEEP+CHoCH (the "sniper" entry trigger) ----
    m5_pat_score=0; m5_sweep=False; m5_fvg=False; m5_ob=False; m5_ob_score=0; m5_patterns=[]; ema9_m5=None; ema21_m5=None; rsi_m5=50; atr_m5=None
    m5_choch = False; m5_sweep_direction = None
    if m5_candles and len(m5_candles)>=30:
        ema9_m5=ema(m5_candles,9); ema21_m5=ema(m5_candles,21); rsi_m5=rsi(m5_candles,14)
        atr_m5=atr(m5_candles,14)
        m5_patterns,m5_pat_score=detect_candle(m5_candles)
        m5_fvg=detect_fvg(m5_candles)
        m5_swings = find_swing_points(m5_candles, lookback=2)
        m5_events = detect_structure_events(m5_candles, m5_swings)
        m5_liquidity = find_liquidity_zones(m5_swings, tolerance_pct=0.001)
        m5_sweep_event = check_sweep(m5_liquidity, m5_candles, lookback_bars=15)
        m5_sweep = bool(m5_sweep_event)
        m5_sweep_direction = m5_sweep_event["direction"] if m5_sweep_event else None
        last_m5_event = m5_events[-1] if m5_events else None
        if last_m5_event and last_m5_event["kind"] == "CHoCH":
            m5_choch = True
            m5_choch_direction = last_m5_event["direction"]
        else:
            m5_choch_direction = None
    else:
        m5_choch_direction = None

    # DETERMINE BIAS - unified (computed BEFORE order-block detection, since
    # OB detection needs to know which direction to look for)
    bias_votes = []
    if daily_bias!="NEUTRAL": bias_votes += [daily_bias]*2  # HTF trend weighted more heavily
    if bias_4h!="NEUTRAL": bias_votes += [bias_4h]*2
    if ema5_h1 and ema20_h1:
        bias_votes.append("BULLISH" if ema5_h1>ema20_h1 else "BEARISH")
    if ema9_m5 and ema21_m5:
        bias_votes.append("BULLISH" if ema9_m5>ema21_m5 else "BEARISH")
    if bos_bull: bias_votes.append("BULLISH")
    if bos_bear: bias_votes.append("BEARISH")
    final_bias = max(set(bias_votes), key=bias_votes.count) if bias_votes else "NEUTRAL"

    # Order blocks - direction-aware and de-duplicated against the shared
    # 1h candle set (no separate re-fetch, no double count)
    h1_ob, h1_ob_zone, h1_ob_score, h1_ob_bounds = detect_order_block(h1_candles, final_bias)
    m5_ob_bounds = None
    if m5_candles and len(m5_candles) >= 20:
        m5_ob, _, m5_ob_score, m5_ob_bounds = detect_order_block(m5_candles, final_bias)
    multi_ob, multi_ob_details, multi_ob_score = detect_multi_tf_ob(symbol, final_bias, cache, h1_candles=h1_candles, historical=historical)

    # ---- HARD GATES (this is the actual fix) ----
    # An order block only counts toward the gate if it's actually SITTING in
    # a zone appropriate to its direction (discount/equilibrium for a bullish
    # reaction, premium/equilibrium for bearish) — see ob_in_zone()'s own
    # docstring for why. Without this, an order block detected right up near
    # a fresh high could still wrongly validate a bullish entry into premium,
    # which is exactly the USDCHF scenario this rewrite exists to prevent.
    h1_ob_valid = bool(h1_ob and ob_in_zone(h1_ob_bounds, final_bias, h1_range))
    m5_ob_valid = bool(m5_ob and ob_in_zone(m5_ob_bounds, final_bias, h1_range))
    # multi_ob spans 4h/2h/1h timeframes at mixed scales — not meaningfully
    # checkable against the single H1 dealing range, so it stays a scoring
    # bonus only and is deliberately excluded from the hard gate below.

    # A bullish setup is only eligible if price is in the H1 discount zone,
    # OR it's reacting from a direction-matched, ZONE-VALIDATED order block
    # (which can sit near equilibrium and still be valid — a strict
    # discount-only rule would miss legitimate OB reactions). What it can
    # NEVER do anymore is qualify purely from trend-following points while
    # sitting in premium with nothing above it but liquidity to sweep —
    # exactly the USDCHF scenario this replaces.
    has_ob = h1_ob_valid or m5_ob_valid
    in_favorable_zone = (final_bias=="BULLISH" and h1_zone=="discount") or (final_bias=="BEARISH" and h1_zone=="premium")
    zone_gate_passed = in_favorable_zone or has_ob

    # The M5 "sniper" trigger: a liquidity sweep followed by a Change of
    # Character, BOTH confirming the SAME direction as the HTF bias — this
    # is what separates "the market is reversing right now" from "a candle
    # pattern happened to appear." Regular/sniper mode requires this
    # explicitly; scalp mode accepts a fresh M5 order block reaction as a
    # faster (but still zone-gated) alternative.
    sniper_trigger = bool(m5_sweep and m5_sweep_direction==final_bias and m5_choch and m5_choch_direction==final_bias)

    zone = h1_zone  # for the factors dict / backward-compatible naming below
    has_sweep = h1_sweep or m5_sweep
    has_pattern = h1_pat_score>=2 or m5_pat_score>=2
    rsi_pullback = False
    if final_bias=="BULLISH" and 40<=rsi_h1<=55: rsi_pullback = True
    elif final_bias=="BEARISH" and 45<=rsi_h1<=60: rsi_pullback = True

    # SCORING - now reflects the SAME structural factors that gate the
    # signal, so a high score actually means high-quality confluence
    # rather than an unrelated checklist total.
    score=0; parts=[]
    if daily_bias!="NEUTRAL": score+=2*w["daily_bias"]; parts.append(f"Daily {daily_bias}")
    if aligned_4h: score+=2*w["h4_align"]; parts.append(f"4H {bias_4h} aligned")
    if in_favorable_zone: score+=3*w["zone"]; parts.append(f"{h1_zone.title()} {h1_premium_pct:.0f}%")
    elif h1_zone == "equilibrium": score+=1*w["zone"]; parts.append(f"Equilibrium {h1_premium_pct:.0f}%")
    if rsi_pullback: score+=2*w["rsi_pullback"]; parts.append(f"RSI {rsi_h1:.0f} pullback")
    if (bos_bull and final_bias=="BULLISH") or (bos_bear and final_bias=="BEARISH"):
        score+=2*w["structure"]; parts.append("H1 BOS")
    if h1_fvg: score+=2*w["h1_fvg"]; parts.append("H1 FVG")
    if m5_fvg: score+=1*w["m5_fvg"]; parts.append("M5 FVG")
    if h1_ob_valid: score+=h1_ob_score*w["h1_ob"]; parts.append(f"H1 {h1_ob_zone}")
    if m5_ob_valid: score+=m5_ob_score*w["m5_ob"]; parts.append("M5 OB")
    if multi_ob: score+=multi_ob_score*w["multi_ob"]; parts.append(f"MTF {multi_ob_details}")
    if h1_sweep: score+=3*w["h1_sweep"]; parts.append("H1 Sweep")
    if m5_sweep and m5_sweep_direction==final_bias: score+=3*w["m5_sweep"]; parts.append("M5 Sweep")
    if sniper_trigger: score+=3*w.get("sniper_trigger",1.0); parts.append("M5 Sweep+CHoCH")
    if h1_patterns: score+=h1_pat_score*w["h1_pattern"]; parts.append(f"H1 {','.join(h1_patterns)}")
    if m5_patterns: score+=m5_pat_score*w["m5_pattern"]; parts.append(f"M5 {','.join(m5_patterns)}")
    score = min(score, 10)

    entry = m5_candles[-1]["close"] if m5_candles and len(m5_candles)>0 else h1_candles[-1]["close"] if h1_candles else 0

    if mode=="scalp":
        m5_bias_ok = bool(ema9_m5 and ema21_m5 and (
            (ema9_m5>ema21_m5 and final_bias=="BULLISH") or
            (ema9_m5<ema21_m5 and final_bias=="BEARISH")
        ))
        trigger_ok = sniper_trigger or (m5_ob_valid and zone_gate_passed)
        is_signal = zone_gate_passed and trigger_ok and score>=w["min_score"] and has_pattern and m5_bias_ok and 20<=rsi_m5<=80
        if not is_signal:
            if not zone_gate_passed: reason=f"Scalp: {final_bias} but price in {h1_zone} ({h1_premium_pct:.0f}%), no OB reaction"
            elif not trigger_ok: reason=f"Scalp: zone OK, waiting for M5 sweep+CHoCH or fresh OB"
            elif score<w["min_score"]: reason=f"Scalp Score {score}/10 - need {w['min_score']}+"
            elif not has_pattern: reason=f"Scalp Score {score}/10 no pattern"
            elif not m5_bias_ok: reason=f"Scalp Score {score}/10 M5 EMA not aligned with {final_bias}"
            else: reason=f"Scalp Score {score}/10 Wait RSI {rsi_m5:.0f}"
        else:
            reason=f"Scalp {score}/10 STRONG {final_bias} in {h1_zone}, {'sweep+CHoCH' if sniper_trigger else 'OB reaction'}"
    else:
        is_signal = zone_gate_passed and sniper_trigger and score>=w["min_score"] and has_pattern
        if not is_signal:
            if not zone_gate_passed: reason=f"Regular: {final_bias} but price in {h1_zone} ({h1_premium_pct:.0f}%), no OB reaction — refusing to chase"
            elif not sniper_trigger: reason=f"Regular: zone OK, waiting for M5 liquidity sweep + CHoCH confirming {final_bias}"
            elif score<w["min_score"]: reason=f"Regular Score {score}/10 - need {w['min_score']}+"
            elif not has_pattern: reason=f"Regular {score}/10 no engulf/hammer"
            else: reason=f"Regular {score}/10 Wait"
        else:
            if score>=8: strength="🔥 8-10 A+ Setup"
            elif score>=7: strength="✅ 7 Strong"
            elif score>=6: strength="👍 6 Good"
            else: strength="⚡ Takeable"
            reason=f"Regular {score}/10 {strength} {final_bias} sniper entry in {h1_zone}"

    # ---- stop-loss / take-profit / R:R, gated on min_rr ----
    stop_loss = None; take_profit = None; risk_reward = None
    if is_signal and entry:
        ref_atr = atr_m5 if mode == "scalp" and atr_m5 else atr_h1
        if ref_atr:
            buffer = ref_atr * 1.2
            if final_bias == "BULLISH":
                struct_low = min(recent_low, h1_candles[-1]["low"])
                stop_loss = min(entry - buffer, struct_low - buffer * 0.25)
                risk = entry - stop_loss
                take_profit = entry + risk * min_rr
            else:
                struct_high = max(recent_high, h1_candles[-1]["high"])
                stop_loss = max(entry + buffer, struct_high + buffer * 0.25)
                risk = stop_loss - entry
                take_profit = entry - risk * min_rr
            risk_reward = min_rr
            if risk <= 0:
                stop_loss = take_profit = risk_reward = None
                is_signal = False
                reason = "Rejected: invalid SL distance"

    rationale = build_rationale(symbol, final_bias, score, daily_bias, aligned_4h, bias_4h, h1_premium_pct,
                                 rsi_h1, bos_bull, bos_bear, breakout_bull, breakout_bear,
                                 h1_fvg, m5_fvg, h1_ob_valid, h1_ob_zone, m5_ob_valid, multi_ob, multi_ob_details,
                                 h1_sweep, m5_sweep, h1_patterns, m5_patterns)
    if sniper_trigger:
        rationale = f"Liquidity swept then a change of character confirmed {final_bias.lower()} on the 5-minute. " + rationale

    return {
        "symbol":symbol,
        "signal":is_signal,
        "score":score,
        "bias":final_bias,
        "bias_4h":bias_4h,
        "entry":entry,
        "stop_loss":stop_loss,
        "take_profit":take_profit,
        "risk_reward":risk_reward,
        "premium_pct":h1_premium_pct,
        "reason":reason,
        "rationale":rationale,
        "confluence":" | ".join(parts) if parts else "No confluence",
        "details":{"candles":h1_patterns+m5_patterns,"sweep":has_sweep,"fvg":h1_fvg or m5_fvg,"ob":has_ob,"ob_details":multi_ob_details,"rsi_h1":round(rsi_h1,1),"rsi_m5":round(rsi_m5,1),"bos":bos_bull or bos_bear,"breakout":breakout_bull or breakout_bear,"zone_gate_passed":zone_gate_passed,"sniper_trigger":sniper_trigger},
        "mode":mode,
        # Structured factor flags — for backtest analysis to read reliably,
        # instead of parsing them back out of the "confluence" text string.
        "factors": {
            "daily_bias": daily_bias != "NEUTRAL", "h4_aligned": aligned_4h, "zone": zone,
            "rsi_pullback": rsi_pullback, "bos_or_breakout": bool(bos_bull or bos_bear),
            "h1_fvg": h1_fvg, "m5_fvg": m5_fvg, "h1_ob": h1_ob, "m5_ob": m5_ob, "multi_ob": multi_ob,
            "h1_sweep": h1_sweep, "m5_sweep": m5_sweep, "sniper_trigger": sniper_trigger,
            "zone_gate_passed": zone_gate_passed,
            "h1_pattern": ",".join(h1_patterns) if h1_patterns else None,
            "m5_pattern": ",".join(m5_patterns) if m5_patterns else None,
        },
    }
