import os, requests
from datetime import datetime, timedelta, timezone
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
        url=f"https://api.twelvedata.com/time_series?symbol={td_symbol}&interval={interval}&outputsize={outputsize}&timezone=UTC&apikey={key}"
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
        try: candles.append({"open":float(v["open"]),"high":float(v["high"]),"low":float(v["low"]),"close":float(v["close"]),"time":v.get("datetime",""),"volume":float(v.get("volume") or 0)})
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
    # reuse an earlier, larger fetch of the same symbol+interval (no extra API request)
    for (s, i, o), (cached_candles, _err) in list(cache.items()):
        if s == symbol and i == interval and cached_candles and o >= outputsize:
            return cached_candles[-outputsize:], None
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
        left = candles[i-lookback:i]
        # Strictly higher than everything to the LEFT, >= everything to the right:
        # if two adjacent candles share an identical extreme (a flat top/bottom),
        # only the FIRST is the pivot. Without this, one turning point was
        # reported as two swings - corrupting HH/HL checks and fabricating
        # "equal highs/lows" liquidity pools out of a single pivot.
        if c["high"] == max(k["high"] for k in window) and c["high"] > max(k["high"] for k in left):
            swings.append({"index": i, "candle": c, "kind": "high"})
        if c["low"] == min(k["low"] for k in window) and c["low"] < min(k["low"] for k in left):
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

# ================= 10-STRATEGY CONFLUENCE ENGINE =================
# Each of the ten strategies below is evaluated INDEPENDENTLY and returns
# either a direction ("BULLISH"/"BEARISH") or nothing. The confluence
# score is simply how many strategies agree on the same direction.
# Anything under `min_score` (currently 2 — see DEFAULT_WEIGHTS below for
# the history of that number) is not sent to the user.
#
# HONEST CAVEATS baked into the design:
#  - These aren't ten independent opinions. AMD, Wyckoff, SMC, ICT and the
#    Liquidity Sweep model can all be triggered by the SAME sweep event, so
#    a single stop-hunt can legitimately earn several votes at once. The
#    backtester (backtest.py / analyze_backtest.py) is how you find out
#    whether "5+ aligned" actually has an edge — don't assume it does.
#  - Volume Profile uses real volume when the data feed provides it
#    (crypto, some indices) and falls back to a time-at-price (TPO) profile
#    when it doesn't (spot forex has no real volume).
#  - ICT's SMT divergence needs a second correlated instrument's feed and
#    is NOT implemented; ICT votes on Asia-sweep + killzone MSS + OTE only.
#  - "Buy/Sell Power flip" (from the Power Channel indicator) is an
#    approximation: dominance of buying vs selling candle-body pressure
#    flipping across two consecutive M5 windows.

STRATEGY_NAMES = [
    "AMD", "SMC", "ICT", "Wyckoff", "Supply&Demand",
    "Volume Profile", "Breakout+Retest", "Trend Following",
    "Mean Reversion", "Liquidity Sweep",
]

DEFAULT_WEIGHTS = {name: 1.0 for name in STRATEGY_NAMES}
DEFAULT_WEIGHTS.update({
    # LOWERED from 5->2 and 1->2: in testing, several of the ten strategies
    # individually need quite narrow conditions (Trend Following needs
    # 200+ clean trending candles, ICT only evaluates inside a ~6hr/day
    # killzone window, Wyckoff/AMD need specific range geometry). Requiring
    # FIVE of them to agree simultaneously turned out to be unrealistic for
    # live data (zero signals across 11 real hours). This is a judgment
    # call, not a backtested number — validate it with backtest.py once you
    # have real results, and adjust from there.
    "min_score": 2,        # strategies that must line up before a signal is sent
    "max_opposing": 2,     # if more than this many strategies vote the OTHER way, skip
    "zone_veto": True,     # never buy in premium / sell in discount unless a zone-appropriate OB backs it
})

# ---------------- shared helpers ----------------

def _fmt_score(s):
    s = round(s, 1)
    return int(s) if s == int(s) else s

def _dt(c):
    t = c.get("time") if isinstance(c, dict) else None
    if isinstance(t, datetime): return t
    if isinstance(t, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try: return datetime.strptime(t, fmt)
            except ValueError: pass
    return None

def _ny(dt_utc):
    try:
        from zoneinfo import ZoneInfo
        return dt_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return dt_utc - timedelta(hours=4)  # EDT approximation if tz data is unavailable

def killzone_name(dt_utc):
    """ICT killzones in New York time: London 03:00-06:00, NY open 08:00-11:00."""
    if dt_utc is None: return None
    h = _ny(dt_utc).hour
    if 3 <= h < 6: return "London killzone"
    if 8 <= h < 11: return "NY killzone"
    return None

def adx(candles, period=14):
    """Wilder's ADX. Below ~20 = no trend (range), above ~25 = trending."""
    n = len(candles)
    if n < period * 2 + 1: return None
    plus_dm, minus_dm, tr = [], [], []
    for i in range(1, n):
        up = candles[i]["high"] - candles[i-1]["high"]
        dn = candles[i-1]["low"] - candles[i]["low"]
        plus_dm.append(up if (up > dn and up > 0) else 0.0)
        minus_dm.append(dn if (dn > up and dn > 0) else 0.0)
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i-1]["close"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    def dx(a, p, m):
        if a == 0: return 0.0
        pdi, mdi = 100 * p / a, 100 * m / a
        s = pdi + mdi
        return 0.0 if s == 0 else 100 * abs(pdi - mdi) / s
    a_s, p_s, m_s = sum(tr[:period]), sum(plus_dm[:period]), sum(minus_dm[:period])
    dxs = [dx(a_s, p_s, m_s)]
    for i in range(period, len(tr)):
        a_s = a_s - a_s / period + tr[i]
        p_s = p_s - p_s / period + plus_dm[i]
        m_s = m_s - m_s / period + minus_dm[i]
        dxs.append(dx(a_s, p_s, m_s))
    if len(dxs) < period: return None
    val = sum(dxs[:period]) / period
    for d in dxs[period:]:
        val = (val * (period - 1) + d) / period
    return val

def volume_profile(candles, bins=24):
    """Volume Profile / Market Profile. Uses real volume if >=80% of bars
    carry it, otherwise counts time-at-price (TPO). Returns POC, value
    area (VAH/VAL) and high/low-volume nodes."""
    if not candles: return None
    lo = min(c["low"] for c in candles); hi = max(c["high"] for c in candles)
    if hi <= lo: return None
    vols = [(c.get("volume", 0) or 0) for c in candles]
    use_vol = sum(1 for v in vols if v > 0) >= 0.8 * len(candles)
    mean_vol = (sum(vols) / len(vols)) if use_vol else 1.0
    bw = (hi - lo) / bins
    prof = [0.0] * bins
    for c, v in zip(candles, vols):
        wgt = (v if v > 0 else mean_vol) if use_vol else 1.0
        b0 = min(bins - 1, int((c["low"] - lo) / bw)); b1 = min(bins - 1, int((c["high"] - lo) / bw))
        share = wgt / (b1 - b0 + 1)
        for b in range(b0, b1 + 1): prof[b] += share
    total = sum(prof); mean = total / bins
    poc_i = max(range(bins), key=lambda i: prof[i])
    lo_i = hi_i = poc_i; acc = prof[poc_i]
    while acc < 0.7 * total and (lo_i > 0 or hi_i < bins - 1):
        below = prof[lo_i - 1] if lo_i > 0 else -1
        above = prof[hi_i + 1] if hi_i < bins - 1 else -1
        if above >= below: hi_i += 1; acc += prof[hi_i]
        else: lo_i -= 1; acc += prof[lo_i]
    center = lambda i: lo + (i + 0.5) * bw
    hvns = [center(i) for i in range(1, bins - 1)
            if prof[i] > 1.25 * mean and prof[i] >= prof[i-1] and prof[i] >= prof[i+1]]
    lvns = [center(i) for i in range(1, bins - 1)
            if prof[i] < 0.6 * mean and prof[i] <= prof[i-1] and prof[i] <= prof[i+1]]
    return {"poc": center(poc_i), "vah": lo + (hi_i + 1) * bw, "val": lo + lo_i * bw,
            "hvns": hvns, "lvns": lvns, "uses_volume": use_vol}

def recent_fvg(candles, direction, max_age=30, after_index=0):
    """Most recent unfilled fair value gap in `direction` (3-candle imbalance)."""
    n = len(candles)
    for i in range(n - 1, max(2, n - max_age) - 1, -1):
        if i < after_index: break
        a, c = candles[i - 2], candles[i]
        later = candles[i + 1:]
        if direction == "BULLISH" and a["high"] < c["low"]:
            if not later or min(k["low"] for k in later) > a["high"]:
                return {"index": i, "top": c["low"], "bottom": a["high"]}
        if direction == "BEARISH" and a["low"] > c["high"]:
            if not later or max(k["high"] for k in later) < a["low"]:
                return {"index": i, "top": a["low"], "bottom": c["high"]}
    return None

def _bull_pat(pats): return any(p in pats for p in ("Bull Engulf", "Hammer"))
def _bear_pat(pats): return any(p in pats for p in ("Bear Engulf", "Hang Man"))

def power_flip(m5):
    """Approximation of a buy/sell 'power' flip: candle-body pressure
    dominance switching between two consecutive 8-bar windows."""
    if len(m5) < 20: return None
    def powers(seg):
        return (sum(max(c["close"] - c["open"], 0) for c in seg),
                sum(max(c["open"] - c["close"], 0) for c in seg))
    pb, ps = powers(m5[-16:-8]); nb, ns = powers(m5[-8:])
    if ps > pb and nb > ns: return "BULLISH"
    if pb > ps and ns > nb: return "BEARISH"
    return None

def find_fresh_zone(candles, direction, atr, max_back=60):
    """Untouched demand (bullish) / supply (bearish) zone: the last opposite
    candle before an imbalanced move of >=1.2 ATR that price has not
    revisited since."""
    n = len(candles)
    if not atr: return None
    for i in range(n - 4, max(n - max_back, 2), -1):
        c = candles[i]
        if direction == "BULLISH" and c["close"] < c["open"]:
            imp = max(k["close"] for k in candles[i+1:i+4]) - c["high"]
            if imp >= 1.2 * atr and all(k["low"] > c["high"] for k in candles[i+4:n-2]):
                return (c["low"], c["high"])
        if direction == "BEARISH" and c["close"] > c["open"]:
            imp = c["low"] - min(k["close"] for k in candles[i+1:i+4])
            if imp >= 1.2 * atr and all(k["high"] < c["low"] for k in candles[i+4:n-2]):
                return (c["low"], c["high"])
    return None

# ---------------- the ten strategies ----------------
# Each takes the shared context dict `x` and returns (direction|None, note).

def strat_amd(x):
    """Accumulation box -> sweep of one side (manipulation) -> reclaim ->
    retest of the box's Point of Control -> distribution move."""
    h1, atr, price = x["h1"], x["atr_h1"], x["price"]
    if not atr or len(h1) < 40: return None, ""
    for post in range(1, 9):
        for box_len in (12, 18, 24):
            box = h1[-(post + box_len):-post]
            if len(box) < box_len: continue
            bh = max(c["high"] for c in box); bl = min(c["low"] for c in box)
            height = bh - bl
            if height <= 0 or height > 4.0 * atr: continue             # must be a tight, sideways box
            if abs(box[-1]["close"] - box[0]["open"]) > 0.5 * height: continue   # no drift
            prof = volume_profile(box, bins=12)
            if not prof: continue
            poc = prof["poc"]
            for c in h1[-post:]:
                if c["low"] < bl and c["close"] > bl and price > bl and abs(price - poc) <= 0.3 * height:
                    return "BULLISH", f"box {bl:.5g}-{bh:.5g} lows swept, reclaimed, PoC {poc:.5g} retested"
                if c["high"] > bh and c["close"] < bh and price < bh and abs(price - poc) <= 0.3 * height:
                    return "BEARISH", f"box {bl:.5g}-{bh:.5g} highs swept, reclaimed, PoC {poc:.5g} retested"
    return None, ""

def strat_smc(x):
    """HTF order block (that swept liquidity first) -> LTF BOS/CHoCH -> LTF FVG."""
    m5 = x["m5"]
    for d in ("BULLISH", "BEARISH"):
        tfs = []
        for tf, cand, rng in (("H1", x["h1"], x["h1_range"]), ("H4", x["h4"], x["h4_range"])):
            if len(cand) < 20: continue
            found, _z, _s, bounds = detect_order_block(cand, d)
            if found and ob_in_zone(bounds, d, rng): tfs.append(tf)
        if not tfs: continue
        swept = any(ev and ev["direction"] == d for ev in (x["h1_sweep"], x["m5_sweep"]))
        if not swept: continue
        evs = [e for e in x["m5_events"] if e["direction"] == d and e["index"] >= len(m5) - 30]
        if not evs: continue
        ev = evs[-1]
        fvg = recent_fvg(m5, d, max_age=30, after_index=max(ev["index"] - 1, 2))
        if not fvg: continue
        return d, f"{'/'.join(tfs)} order block after liquidity sweep, M5 {ev['kind']} + FVG"
    return None, ""

def strat_ict(x):
    """ICT 2022 model: killzone active -> Asia range swept -> M5 market
    structure shift inside a killzone -> price in the 62-79% OTE zone."""
    now = x["now"]
    kz = killzone_name(now)
    if not kz: return None, ""
    day = now.date() if now.hour >= 5 else (now - timedelta(days=1)).date()
    asia_start = datetime(day.year, day.month, day.day, 0, 0)
    asia_end = asia_start + timedelta(hours=5)
    stream = []
    for src in (x["h1"], x["m5"]):
        for c in src:
            t = _dt(c)
            if t: stream.append((t, c))
    stream.sort(key=lambda p: p[0])
    asia = [c for t, c in stream if asia_start <= t < asia_end]
    if len(asia) < 3: return None, ""
    ah = max(c["high"] for c in asia); al = min(c["low"] for c in asia)
    sweep_t = None; d = None
    for t, c in stream:
        if t < asia_end: continue
        if c["low"] < al and c["close"] > al: sweep_t, d = t, "BULLISH"
        elif c["high"] > ah and c["close"] < ah: sweep_t, d = t, "BEARISH"
    if not d: return None, ""
    ev = None
    for e in x["m5_events"]:
        et = _dt(e["candle"])
        if e["direction"] == d and et and et >= sweep_t and killzone_name(et) and e["index"] >= len(x["m5"]) - 60:
            ev = e
    if not ev: return None, ""
    after = [c for t, c in stream if t >= sweep_t]
    price = x["price"]
    if d == "BULLISH":
        s = min(c["low"] for c in after); hgh = max(c["high"] for c in after)
        if hgh <= s: return None, ""
        r = (hgh - price) / (hgh - s)
    else:
        s = max(c["high"] for c in after); low = min(c["low"] for c in after)
        if s <= low: return None, ""
        r = (price - low) / (s - low)
    if 0.62 <= r <= 0.79:
        return d, f"{kz}: Asia {'low' if d=='BULLISH' else 'high'} swept, MSS, OTE {r*100:.0f}% retrace"
    return None, ""

def strat_wyckoff(x):
    """Spring/Upthrust + Test -> Last Point of Support/Supply, after a
    prior markdown/markup into a trading range."""
    h1, atr = x["h1"], x["atr_h1"]
    if not atr or len(h1) < 90: return None, ""
    base = h1[-60:-6]
    rh = max(c["high"] for c in base); rl = min(c["low"] for c in base)
    height = rh - rl
    if height <= 0 or height > 10 * atr: return None, ""     # must actually be a range
    prior = h1[-90:-60]
    prior_avg = sum(c["close"] for c in prior) / len(prior)
    mid = (rh + rl) / 2
    tail = h1[-6:]
    def quieter(a, spring):
        va, vs = a.get("volume", 0) or 0, spring.get("volume", 0) or 0
        if va > 0 and vs > 0: return va < vs
        return (a["high"] - a["low"]) < (spring["high"] - spring["low"])
    for idx, c in enumerate(tail[:-1]):
        after = tail[idx + 1:]
        if prior_avg > mid and c["low"] < rl and c["close"] > rl:
            test = any(a["low"] > c["low"] and a["low"] <= rl + 0.35 * height and quieter(a, c) for a in after)
            if test and tail[-1]["close"] > rl + 0.15 * height and x["price"] > c["close"]:
                return "BULLISH", f"spring below {rl:.5g}, quiet higher-low test, last point of support"
        if prior_avg < mid and c["high"] > rh and c["close"] < rh:
            test = any(a["high"] < c["high"] and a["high"] >= rh - 0.35 * height and quieter(a, c) for a in after)
            if test and tail[-1]["close"] < rh - 0.15 * height and x["price"] < c["close"]:
                return "BEARISH", f"upthrust above {rh:.5g}, quiet lower-high test, last point of supply"
    return None, ""

def strat_supply_demand(x):
    """Fresh zone + buy/sell power flip + engulfing candle."""
    h1, atr, price = x["h1"], x["atr_h1"], x["price"]
    if not atr: return None, ""
    flip = power_flip(x["m5"])
    if not flip: return None, ""
    pats = set(x["m5_patterns"]) | set(x["h1_patterns"])
    for d in ("BULLISH", "BEARISH"):
        if flip != d: continue
        if d == "BULLISH" and "Bull Engulf" not in pats: continue
        if d == "BEARISH" and "Bear Engulf" not in pats: continue
        zone = find_fresh_zone(h1, d, atr)
        if not zone or not ob_in_zone(zone, d, x["h1_range"]): continue
        zl, zh = zone
        if zl - 0.2 * atr <= price <= zh + 0.2 * atr:
            kind = "demand" if d == "BULLISH" else "supply"
            return d, f"fresh {kind} zone {zl:.5g}-{zh:.5g}, power flip, engulfing"
    return None, ""

def strat_volume_profile(x):
    """Return to a High Volume Node / POC with a rejection candle."""
    prof, atr, price = x["profile"], x["atr_h1"], x["price"]
    if not prof or not atr: return None, ""
    tol = 0.35 * atr
    nodes = [("POC", prof["poc"])] + [("HVN", h) for h in prof["hvns"]]
    hit = [(n, l) for n, l in nodes if abs(price - l) <= tol]
    if not hit: return None, ""
    name, level = hit[0]
    pats = set(x["m5_patterns"]) | set(x["h1_patterns"])
    src = "volume" if prof["uses_volume"] else "time-at-price"
    if _bull_pat(pats) and price <= prof["poc"] + tol:
        return "BULLISH", f"rejection at {name} {level:.5g} ({src} profile), buying at/below fair value"
    if _bear_pat(pats) and price >= prof["poc"] - tol:
        return "BEARISH", f"rejection at {name} {level:.5g} ({src} profile), selling at/above fair value"
    return None, ""

def strat_breakout_retest(x):
    """Clean breakout (>70% body, volume-confirmed if available) of a range,
    then a RETEST of the broken level - not the first break."""
    h1, atr, price = x["h1"], x["atr_h1"], x["price"]
    n = len(h1)
    if not atr or n < 50: return None, ""
    for b in range(n - 9, n - 1):
        base = h1[b - 30:b]
        if len(base) < 30: continue
        rh = max(k["high"] for k in base); rl = min(k["low"] for k in base)
        if rh - rl > 8 * atr: continue                      # not a range
        c = h1[b]; rng = c["high"] - c["low"]
        if rng <= 0 or abs(c["close"] - c["open"]) / rng <= 0.7: continue
        vols = [(k.get("volume", 0) or 0) for k in base]
        if sum(1 for v in vols if v > 0) >= 0.8 * len(base) and (c.get("volume", 0) or 0) > 0:
            if c["volume"] <= 1.2 * (sum(vols) / len(vols)): continue
        after = h1[b + 1:]
        if c["close"] > rh and c["close"] > c["open"]:
            if any(a["low"] <= rh + 0.25 * atr and a["close"] > rh - 0.1 * atr for a in after) \
               and price > rh and price - rh <= 1.2 * atr:
                return "BULLISH", f"strong breakout above {rh:.5g}, retest held"
        if c["close"] < rl and c["close"] < c["open"]:
            if any(a["high"] >= rl - 0.25 * atr and a["close"] < rl + 0.1 * atr for a in after) \
               and price < rl and rl - price <= 1.2 * atr:
                return "BEARISH", f"strong breakdown below {rl:.5g}, retest rejected"
    return None, ""

def strat_trend_following(x):
    """50/200 EMA + HH/HL (or LH/LL), pullback to the 21 EMA, BOS in trend direction."""
    h1, atr, price = x["h1"], x["atr_h1"], x["price"]
    n = len(h1)
    if not atr or n < 205: return None, ""
    e21, e50, e200 = ema(h1, 21), ema(h1, 50), ema(h1, 200)
    if None in (e21, e50, e200): return None, ""
    highs = [s for s in x["h1_swings"] if s["kind"] == "high"][-2:]
    lows = [s for s in x["h1_swings"] if s["kind"] == "low"][-2:]
    if len(highs) < 2 or len(lows) < 2: return None, ""
    hh = highs[1]["candle"]["high"] > highs[0]["candle"]["high"]
    hl = lows[1]["candle"]["low"] > lows[0]["candle"]["low"]
    lh = highs[1]["candle"]["high"] < highs[0]["candle"]["high"]
    ll = lows[1]["candle"]["low"] < lows[0]["candle"]["low"]
    recent = h1[-10:]   # the EMA touch comes BEFORE the BOS, so look back a little further
    bos = [e for e in x["h1_events"] if e["index"] >= n - 12]
    daily = x["daily_bias"]
    if e50 > e200 and price > e200 and hh and hl and daily != "BEARISH":
        touched = min(c["low"] for c in recent) <= e21 + 0.4 * atr and h1[-1]["close"] > e21 - 0.4 * atr
        if touched and any(e["direction"] == "BULLISH" for e in bos):
            return "BULLISH", "uptrend (50>200 EMA, HH/HL), pullback to 21 EMA, bullish BOS"
    if e50 < e200 and price < e200 and lh and ll and daily != "BULLISH":
        touched = max(c["high"] for c in recent) >= e21 - 0.4 * atr and h1[-1]["close"] < e21 + 0.4 * atr
        if touched and any(e["direction"] == "BEARISH" for e in bos):
            return "BEARISH", "downtrend (50<200 EMA, LH/LL), pullback to 21 EMA, bearish BOS"
    return None, ""

def strat_mean_reversion(x):
    """RSI extreme at HTF support/resistance, only when ADX < 20 (no trend)."""
    h1, atr, price = x["h1"], x["atr_h1"], x["price"]
    a = x["adx_h1"]
    if not atr or a is None or a >= 20: return None, ""
    r = x["rsi_h1"]
    h4, d1 = x["h4"], x["d1"]
    if len(h4) < 20: return None, ""
    res = [max(c["high"] for c in h4[-40:])] + [z["price"] for z in x["h4_liq"] if z["kind"] == "buy_side"]
    sup = [min(c["low"] for c in h4[-40:])] + [z["price"] for z in x["h4_liq"] if z["kind"] == "sell_side"]
    if d1:
        res.append(max(c["high"] for c in d1[-20:])); sup.append(min(c["low"] for c in d1[-20:]))
    if r > 70 and any(lv - 0.8 * atr <= price <= lv + 0.5 * atr for lv in res):
        return "BEARISH", f"RSI {r:.0f} overbought at HTF resistance, ADX {a:.0f} (ranging)"
    if r < 30 and any(lv - 0.5 * atr <= price <= lv + 0.8 * atr for lv in sup):
        return "BULLISH", f"RSI {r:.0f} oversold at HTF support, ADX {a:.0f} (ranging)"
    return None, ""

def strat_liquidity_sweep(x):
    """Equal highs/lows taken by a wick, then an immediate reversal candle."""
    for label, ev, cand, recent in (("M5", x["m5_sweep"], x["m5"], 8), ("H1", x["h1_sweep"], x["h1"], 3)):
        if not ev or ev["index"] < len(cand) - recent: continue
        d = ev["direction"]
        for k in range(ev["index"], len(cand)):
            pats, _ = detect_candle(cand[:k + 1])
            if d == "BULLISH" and any(p in pats for p in ("Hammer", "Bull Engulf", "Doji")):
                return d, f"{label} equal lows swept, reversal candle ({', '.join(pats)})"
            if d == "BEARISH" and any(p in pats for p in ("Hang Man", "Bear Engulf", "Doji")):
                return d, f"{label} equal highs swept, reversal candle ({', '.join(pats)})"
    return None, ""

STRATEGY_FUNCS = [
    ("AMD", strat_amd), ("SMC", strat_smc), ("ICT", strat_ict), ("Wyckoff", strat_wyckoff),
    ("Supply&Demand", strat_supply_demand), ("Volume Profile", strat_volume_profile),
    ("Breakout+Retest", strat_breakout_retest), ("Trend Following", strat_trend_following),
    ("Mean Reversion", strat_mean_reversion), ("Liquidity Sweep", strat_liquidity_sweep),
]

def build_confluence_rationale(direction, score, aligned):
    """Plain-language summary: which strategies lined up and why."""
    if not aligned: return "No strategies aligned."
    parts = "; ".join(f"{name}: {note}" for name, note in aligned)
    return f"{_fmt_score(score)}/10 strategies agree on a {direction.lower()} setup. {parts}."

# ================= ORCHESTRATION =================
def full_multi_tf_analysis(symbol, user_settings=None, historical=None, as_of=None, weights=None):
    """historical: optional dict {"1day":[...], "4h":[...], "1h":[...], "5min":[...]}
    of pre-fetched candles, used by the backtester instead of live API calls -
    this is the SAME function the live bot calls, so backtest and live never
    diverge. as_of: the datetime a backtest is simulating as "now".
    weights: optional overrides of DEFAULT_WEIGHTS (per-strategy vote
    multipliers, min_score, max_opposing, zone_veto)."""
    if user_settings is None: user_settings = {"trade_news": True, "trading_mode": "regular", "currency": "ZAR"}
    mode = user_settings.get("trading_mode", "regular")
    min_rr = user_settings.get("min_risk_reward", 1.5)
    cache = {}
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    now = as_of or datetime.utcnow()

    def _out(reason, score=0, bias="NEUTRAL", entry=0, pct=50, details=None, extra=None):
        base = {"symbol": symbol, "signal": False, "score": score, "bias": bias, "bias_4h": "NEUTRAL",
                "entry": entry, "premium_pct": pct, "reason": reason, "rationale": reason,
                "confluence": reason, "details": details or {}, "mode": mode}
        if extra: base.update(extra)
        return base

    is_open, closed_reason = is_market_open(symbol, as_of)
    if not is_open:
        return _out(closed_reason, details={"market_closed": True})
    blocked, news_reason = is_news_time(symbol, user_settings)
    if blocked:
        return _out(news_reason, details={"news_blocked": True})

    d1, _e = get_values_cached(cache, symbol, "1day", 100, historical)
    h4, _e = get_values_cached(cache, symbol, "4h", 100, historical)
    h1, _e = get_values_cached(cache, symbol, "1h", 250, historical)
    m5, _e = get_values_cached(cache, symbol, "5min", 100, historical)
    d1, h4 = d1 or [], h4 or []
    if not h1 or len(h1) < 30:
        return _out("No H1 data")
    # existing helpers, reused as-is (same cache keys as the fetches above -> no extra API calls)
    daily_bias, _daily_pct, _dc = get_htf_bias(symbol, cache, historical)
    aligned_4h, bias_4h = check_4h_alignment(symbol, daily_bias, cache, historical)
    m5 = m5 or []
    price = m5[-1]["close"] if m5 else h1[-1]["close"]

    # ---- shared structure / context, computed once and handed to every strategy ----
    h1_swings = find_swing_points(h1, lookback=2)
    h1_events = detect_structure_events(h1, h1_swings)
    h1_range = compute_dealing_range(h1_swings, lookback_swings=8, candles=h1)
    h4_swings = find_swing_points(h4, lookback=2) if h4 else []
    h4_range = compute_dealing_range(h4_swings, lookback_swings=8, candles=h4) if h4 else None
    h1_liq = find_liquidity_zones(h1_swings, tolerance_pct=0.0008)
    h4_liq = find_liquidity_zones(h4_swings, tolerance_pct=0.0012) if h4 else []
    m5_swings = find_swing_points(m5, lookback=2) if m5 else []
    m5_events = detect_structure_events(m5, m5_swings) if m5 else []
    m5_liq = find_liquidity_zones(m5_swings, tolerance_pct=0.001) if m5 else []
    h1_patterns, _p1 = detect_candle(h1)
    m5_patterns, _p2 = detect_candle(m5) if m5 else ([], 0)
    atr_h1 = atr(h1, 14); atr_m5 = atr(m5, 14) if m5 else None
    h1_zone = zone_of(h1_range, price)
    h1_pct = fib_level(h1_range, price) * 100 if h1_range else 50

    x = {
        "symbol": symbol, "now": now, "price": price,
        "d1": d1, "h4": h4, "h1": h1, "m5": m5,
        "daily_bias": daily_bias, "bias_4h": bias_4h, "aligned_4h": aligned_4h,
        "atr_h1": atr_h1, "atr_m5": atr_m5,
        "rsi_h1": rsi(h1, 14), "adx_h1": adx(h1, 14),
        "h1_swings": h1_swings, "h1_events": h1_events, "h1_range": h1_range, "h1_liq": h1_liq,
        "h4_range": h4_range, "h4_liq": h4_liq,
        "m5_swings": m5_swings, "m5_events": m5_events, "m5_liq": m5_liq,
        "h1_sweep": check_sweep(h1_liq, h1, lookback_bars=20),
        "m5_sweep": check_sweep(m5_liq, m5, lookback_bars=30) if m5 else None,
        "h1_patterns": h1_patterns, "m5_patterns": m5_patterns,
        "profile": volume_profile(h1[-100:]),
    }

    # ---- every strategy votes independently ----
    votes, errors = {}, {}
    for name, fn in STRATEGY_FUNCS:
        try: votes[name] = fn(x)
        except Exception as e:
            votes[name] = (None, ""); errors[name] = f"{type(e).__name__}: {e}"

    bull = [n for n in STRATEGY_NAMES if votes[n][0] == "BULLISH"]
    bear = [n for n in STRATEGY_NAMES if votes[n][0] == "BEARISH"]
    bs = sum(w.get(n, 1.0) for n in bull); rs = sum(w.get(n, 1.0) for n in bear)
    if bs > rs:   direction, agree, score, opposing = "BULLISH", bull, bs, len(bear)
    elif rs > bs: direction, agree, score, opposing = "BEARISH", bear, rs, len(bull)
    else:         direction, agree, score, opposing = None, [], max(bs, rs), len(bull)
    score_disp = _fmt_score(score)

    # ---- the safety veto: don't buy the premium / sell the discount ----
    # (unless a zone-appropriate order block/fresh zone backs the trade -
    # SMC and Supply&Demand only vote when they have one)
    veto = False
    if w["zone_veto"] and direction and h1_range:
        backed = any(n in agree for n in ("SMC", "Supply&Demand"))
        if direction == "BULLISH" and h1_zone == "premium" and not backed: veto = True
        if direction == "BEARISH" and h1_zone == "discount" and not backed: veto = True

    m5_trigger = (bool(m5_patterns) and
                  ((direction == "BULLISH" and any(p in m5_patterns for p in ("Bull Engulf", "Hammer", "Doji"))) or
                   (direction == "BEARISH" and any(p in m5_patterns for p in ("Bear Engulf", "Hang Man", "Doji")))))

    is_signal = False
    if direction is None:
        reason = "No strategy alignment" if score == 0 else f"Conflict: {len(bull)} bullish vs {len(bear)} bearish strategies"
    elif score < w["min_score"]:
        reason = f"{score_disp}/10 strategies aligned {direction} - need {w['min_score']}+"
    elif opposing > w["max_opposing"]:
        reason = f"{score_disp}/10 aligned {direction} but {opposing} strategies vote the other way"
    elif veto:
        reason = f"{score_disp}/10 {direction} but price in {h1_zone} ({h1_pct:.0f}%) with no zone-backed order block - refusing to chase"
    elif mode == "scalp" and not m5_trigger:
        reason = f"{score_disp}/10 aligned {direction}; scalp mode waiting for an M5 trigger candle"
    else:
        is_signal = True
        reason = f"{score_disp}/10 strategies aligned {direction}: {', '.join(agree)}"

    entry = price
    stop_loss = take_profit = risk_reward = None
    if is_signal and entry:
        ref_atr = atr_m5 if (mode == "scalp" and atr_m5) else atr_h1
        if ref_atr:
            buffer = ref_atr * 1.2
            rec_high = h1_range["high"] if h1_range else max(c["high"] for c in h1[-21:-1])
            rec_low = h1_range["low"] if h1_range else min(c["low"] for c in h1[-21:-1])
            if direction == "BULLISH":
                stop_loss = min(entry - buffer, min(rec_low, h1[-1]["low"]) - buffer * 0.25)
                risk = entry - stop_loss; take_profit = entry + risk * min_rr
            else:
                stop_loss = max(entry + buffer, max(rec_high, h1[-1]["high"]) + buffer * 0.25)
                risk = stop_loss - entry; take_profit = entry - risk * min_rr
            risk_reward = min_rr
            if risk <= 0:
                stop_loss = take_profit = risk_reward = None
                is_signal = False; reason = "Rejected: invalid SL distance"

    aligned_notes = [(n, votes[n][1]) for n in agree]
    rationale = build_confluence_rationale(direction, score, aligned_notes) if direction else reason
    bias = direction or "NEUTRAL"

    return {
        "symbol": symbol, "signal": is_signal, "score": score_disp, "bias": bias,
        "bias_4h": bias_4h, "entry": entry, "stop_loss": stop_loss, "take_profit": take_profit,
        "risk_reward": risk_reward, "premium_pct": h1_pct, "reason": reason, "rationale": rationale,
        "confluence": " | ".join(agree) if agree else "No confluence",
        "details": {
            "votes": {n: votes[n][0] for n in STRATEGY_NAMES},
            "notes": {n: votes[n][1] for n in STRATEGY_NAMES if votes[n][0]},
            "opposing": opposing, "zone": h1_zone, "zone_veto_blocked": veto,
            "rsi_h1": round(x["rsi_h1"], 1), "adx_h1": round(x["adx_h1"], 1) if x["adx_h1"] is not None else None,
            "candles": h1_patterns + m5_patterns, "strategy_errors": errors,
        },
        "mode": mode,
        # per-strategy flags (True = this strategy voted WITH the signal direction),
        # for the backtest analyzer to read reliably.
        "factors": {**{n: (votes[n][0] == direction and direction is not None) for n in STRATEGY_NAMES},
                    "zone": h1_zone, "zone_veto_blocked": veto},
    }
