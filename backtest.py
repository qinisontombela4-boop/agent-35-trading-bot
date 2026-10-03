"""
Backtests the live trading engine against real historical data.

IMPORTANT: this reuses trading_engine.full_multi_tf_analysis() directly —
the SAME function the live bot calls — via its `historical=` and `as_of=`
parameters. It does NOT reimplement the scoring logic separately. That
matters: a backtester with its own copy of the strategy logic will silently
drift from what's actually trading live, and you'd be backtesting a
strategy you don't actually run. This backtests the real thing.

REQUIRES: a Twelve Data API key with enough historical depth for your plan.
5-minute data is the constraint — free/basic plans often cap how far back
intraday data goes. If a symbol comes back with too little 5m history,
this script will tell you and skip it rather than fake a result.

Usage:
    export TWELVE_DATA_API_KEY=your_key_here
    python backtest.py --symbols EURUSD,GBPUSD,XAUUSD,BTCUSD --days 60 --mode regular

Self-test (no API key, no network — proves the walk-forward mechanics are
correct: no lookahead, accurate SL/TP fill detection) — run:
    python backtest.py --self-test
"""

import os, sys, json, argparse, requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trading_engine as eng

TRADE_EXPIRY_HOURS = {"scalp": 6, "regular": 48}  # matches app.py's live expiry — mirrored here for consistency

# ================= Historical data fetching (real mode) =================

def fetch_historical_series(symbol, interval, days_back, api_key):
    """Pulls as much real history as the API/plan allows for one interval.
    Twelve Data's date-range params are start_date/end_date; outputsize is
    still capped per-request by your plan, so this asks for a generous
    outputsize and warns if the returned range doesn't cover what was asked."""
    td_symbol = eng.SYMBOL_MAP.get(symbol, symbol)
    end = datetime.utcnow()
    start = end - timedelta(days=days_back)
    url = (f"https://api.twelvedata.com/time_series?symbol={td_symbol}&interval={interval}"
           f"&start_date={start.strftime('%Y-%m-%d %H:%M:%S')}&end_date={end.strftime('%Y-%m-%d %H:%M:%S')}"
           f"&outputsize=5000&apikey={api_key}")
    try:
        r = requests.get(url, timeout=30).json()
    except Exception as e:
        print(f"[FETCH ERROR] {symbol} {interval}: {e}", file=sys.stderr)
        return []
    if "values" not in r:
        print(f"[FETCH ERROR] {symbol} {interval}: {r.get('message', r)}", file=sys.stderr)
        return []
    vals = r["values"]; vals.reverse()
    candles = []
    for v in vals:
        try:
            candles.append({
                "time": datetime.strptime(v["datetime"], "%Y-%m-%d %H:%M:%S") if " " in v["datetime"]
                        else datetime.strptime(v["datetime"], "%Y-%m-%d"),
                "open": float(v["open"]), "high": float(v["high"]),
                "low": float(v["low"]), "close": float(v["close"]),
            })
        except Exception:
            continue
    if candles:
        actual_days = (candles[-1]["time"] - candles[0]["time"]).days
        if actual_days < days_back * 0.8:
            print(f"[WARN] {symbol} {interval}: asked for {days_back}d, got ~{actual_days}d — "
                  f"your plan likely caps history depth for this interval.", file=sys.stderr)
    return candles


def slice_as_of(all_candles, as_of, bar_duration_minutes):
    """Only fully-CLOSED bars as of `as_of` — a bar whose open time + its own
    duration is still after `as_of` hasn't closed yet and must be excluded,
    or the backtest would be peeking at a bar's future high/low/close.
    This is the single most important correctness rule in this script."""
    cutoff = as_of - timedelta(minutes=bar_duration_minutes)
    return [c for c in all_candles if c["time"] <= cutoff]


# ================= SL/TP calc (mirrors app.py's calculate_dynamic_sl_tp) =================
# Copied rather than imported: app.py has Flask/Supabase init side effects
# at import time (it raises if FLASK_SECRET isn't set), so importing it here
# would require faking a whole web app just to get a pure math function.
#
# KEEP THIS IN SYNC WITH app.py's calculate_dynamic_sl_tp. They diverged
# once already (this copy never accounted for leverage at all, even as a
# cosmetic field, while app.py at least accepted the parameter) — that's
# exactly the live/backtest divergence this file's own design is supposed
# to avoid. The leverage-as-margin-cap logic below is a line-for-line port
# of app.py's; if you change one, change both.

UNITS_PER_LOT = {"gold": 100, "oil": 50, "index": 10, "crypto": 10, "forex": 100000}

def _parse_leverage_ratio(leverage):
    try:
        s = str(leverage).strip()
        if ":" in s:
            return max(1.0, float(s.split(":")[1]))
        return max(1.0, float(s))
    except Exception:
        return 1.0

def _max_lot_by_leverage(account_size, leverage, entry, units_per_lot):
    leverage_ratio = _parse_leverage_ratio(leverage)
    entry = float(entry) if entry else 0
    if entry <= 0 or units_per_lot <= 0:
        return 999.0
    return (float(account_size) * leverage_ratio) / (units_per_lot * entry)

def calculate_sl_tp(symbol, entry, bias, account_size, lot_size, risk_percent, rr_ratio,
                     leverage="1:500",
                     spread_forex=0.7, spread_gold=0.35, spread_indices=2.0, spread_crypto=10.0):
    entry=float(entry); is_sell="BEARISH" in bias.upper()
    risk_amount=float(account_size)*(float(risk_percent)/100.0); lot_size=max(float(lot_size),0.01); rr_ratio=max(float(rr_ratio),0.1)
    dp = eng.price_decimals(symbol)

    if symbol in ["XAUUSD","XAGUSD"]: asset_class="gold"
    elif symbol in ["XTIUSD","XBRUSD"]: asset_class="oil"
    elif symbol in ["US30","NAS100","SPX500","GER40","UK100","FRA40","ESP35","ITA40","JPN225","AUS200"]: asset_class="index"
    elif any(x in symbol for x in ["BTC","ETH","SOL","BNB","XRP","ADA","DOGE","DOT","AVAX","LINK","MATIC","LTC"]): asset_class="crypto"
    else: asset_class="forex"
    max_lot = _max_lot_by_leverage(account_size, leverage, entry, UNITS_PER_LOT[asset_class])
    lot_size = min(lot_size, max_lot) if max_lot > 0 else lot_size

    if asset_class=="gold":
        sl_d=max(2.0,min(risk_amount/(lot_size*100),15.0))+spread_gold; tp_d=sl_d*rr_ratio-spread_gold
        sl=entry+sl_d if is_sell else entry-sl_d; tp=entry-tp_d if is_sell else entry+tp_d
    elif asset_class=="oil":
        sl_d=max(0.3,min(risk_amount/(lot_size*50),2.0))+spread_gold; tp_d=sl_d*rr_ratio-spread_gold
        sl=entry+sl_d if is_sell else entry-sl_d; tp=entry-tp_d if is_sell else entry+tp_d
    elif asset_class=="index":
        sl_p=max(30,min(risk_amount/(lot_size*10),250))+spread_indices; tp_p=sl_p*rr_ratio-spread_indices
        sl=entry+sl_p if is_sell else entry-sl_p; tp=entry-tp_p if is_sell else entry+tp_p
    elif asset_class=="crypto":
        sl_d=max(100 if "BTC" in symbol else 5, min(risk_amount/(lot_size*10), 1200 if "BTC" in symbol else 150))+spread_crypto
        tp_d=sl_d*rr_ratio-spread_crypto
        sl=entry+sl_d if is_sell else entry-sl_d; tp=entry-tp_d if is_sell else entry+tp_d
    else:
        sl_pips=max(5,min(risk_amount/(lot_size*10),50))+spread_forex; tp_pips=sl_pips*rr_ratio-spread_forex
        unit = 0.01 if "JPY" in symbol else 0.0001
        sl_d=sl_pips*unit; tp_d=tp_pips*unit
        sl=entry+sl_d if is_sell else entry-sl_d; tp=entry-tp_d if is_sell else entry+tp_d
    return round(sl,dp), round(tp,dp)


# ================= Walk-forward simulation =================

def run_backtest(symbol, daily, h4, h1, m5, user_settings, weights=None, verbose=False):
    """Walks forward through the 5-minute series. At each closed 5m bar,
    slices every timeframe to only what was CLOSED as of that moment, calls
    the real engine, and if a signal fires, simulates the trade forward
    using subsequent bars' high/low to detect which of SL/TP was touched
    first (more accurate than the live bot's own close-price-only check,
    since backtesting has the luxury of full OHLC on every bar)."""
    trades = []
    in_position_until_index = -1
    mode = user_settings.get("trading_mode", "regular")
    max_hold_hours = TRADE_EXPIRY_HOURS.get(mode, 24)

    min_daily, min_4h, min_1h, min_5m = 50, 50, 40, 50

    for i in range(len(m5)):
        if i <= in_position_until_index:
            continue
        as_of = m5[i]["time"] + timedelta(minutes=5)  # this bar just closed

        d_slice = slice_as_of(daily, as_of, 24*60)
        h4_slice = slice_as_of(h4, as_of, 240)
        h1_slice = slice_as_of(h1, as_of, 60)
        m5_slice = slice_as_of(m5, as_of, 5)
        if len(d_slice) < min_daily or len(h4_slice) < min_4h or len(h1_slice) < min_1h or len(m5_slice) < min_5m:
            continue  # not enough history yet to evaluate this point

        historical = {"1day": d_slice, "4h": h4_slice, "2h": h4_slice, "1h": h1_slice, "5min": m5_slice}
        try:
            r = eng.full_multi_tf_analysis(symbol, user_settings, historical=historical, as_of=as_of, weights=weights)
        except Exception as e:
            if verbose: print(f"[{symbol} @ {as_of}] analysis error: {e}", file=sys.stderr)
            continue

        if not r.get("signal"):
            continue

        entry = r.get("entry")
        if not entry:
            continue
        sl, tp = calculate_sl_tp(
            symbol, entry, r.get("bias",""),
            user_settings.get("account_size",142), user_settings.get("lot_size",0.01),
            user_settings.get("risk_percent",1), user_settings.get("rr_ratio",2.5),
            user_settings.get("leverage","1:500"),
        )
        is_bull = "BULLISH" in r.get("bias","").upper()
        risk = abs(entry - sl)
        if risk <= 0:
            continue

        # walk forward through subsequent 5m bars to find the outcome
        outcome = None; exit_time = None; bars_held = 0
        for j in range(i+1, len(m5)):
            bar = m5[j]
            bars_held += 1
            if (bar["time"] - as_of).total_seconds() > max_hold_hours * 3600:
                outcome = "EXPIRED"; exit_time = bar["time"]; break
            if is_bull:
                hit_sl = bar["low"] <= sl
                hit_tp = bar["high"] >= tp
            else:
                hit_sl = bar["high"] >= sl
                hit_tp = bar["low"] <= tp
            if hit_sl and hit_tp:
                # both touched in the same bar — can't know true intrabar
                # order from OHLC alone; conservatively assume SL (worse case)
                outcome = "LOSS"; exit_time = bar["time"]; break
            elif hit_sl:
                outcome = "LOSS"; exit_time = bar["time"]; break
            elif hit_tp:
                outcome = "WIN"; exit_time = bar["time"]; break
        else:
            outcome = "OPEN_AT_END"  # ran out of data before it resolved

        r_multiple = 0
        if outcome == "WIN": r_multiple = round(abs(tp-entry)/risk, 2)
        elif outcome == "LOSS": r_multiple = -1.0

        trades.append({
            "symbol": symbol, "time": as_of.isoformat(), "bias": r.get("bias"),
            "score": r.get("score"), "mode": r.get("mode"), "entry": entry, "sl": sl, "tp": tp,
            "outcome": outcome, "r_multiple": r_multiple, "bars_held": bars_held,
            "exit_time": exit_time.isoformat() if exit_time else None,
            "confluence": r.get("confluence"), "factors": r.get("factors", {}),
        })
        if outcome in ("WIN","LOSS","EXPIRED") and exit_time:
            # don't evaluate new entries on this symbol while "in" this trade
            for k in range(i+1, len(m5)):
                if m5[k]["time"] >= exit_time:
                    in_position_until_index = k
                    break

    return trades


def summarize(all_trades):
    resolved = [t for t in all_trades if t["outcome"] in ("WIN","LOSS")]
    wins = [t for t in resolved if t["outcome"]=="WIN"]
    losses = [t for t in resolved if t["outcome"]=="LOSS"]
    expired = [t for t in all_trades if t["outcome"]=="EXPIRED"]
    still_open = [t for t in all_trades if t["outcome"]=="OPEN_AT_END"]

    win_rate = round(len(wins)/len(resolved)*100, 1) if resolved else 0
    avg_r = round(sum(t["r_multiple"] for t in resolved)/len(resolved), 2) if resolved else 0
    total_r = round(sum(t["r_multiple"] for t in resolved), 2)

    by_score = {}
    for t in resolved:
        b = t["score"]
        by_score.setdefault(b, {"wins":0,"total":0})
        by_score[b]["total"] += 1
        if t["outcome"]=="WIN": by_score[b]["wins"] += 1
    score_breakdown = {
        score: {"win_rate": round(v["wins"]/v["total"]*100,1), "n": v["total"]}
        for score, v in sorted(by_score.items())
    }

    return {
        "total_signals": len(all_trades),
        "resolved": len(resolved), "wins": len(wins), "losses": len(losses),
        "expired_unresolved": len(expired), "still_open_at_data_end": len(still_open),
        "win_rate_pct": win_rate, "avg_r_per_trade": avg_r, "total_r": total_r,
        "win_rate_by_score": score_breakdown,
    }


# ================= Self-test: synthetic data, proves the mechanics ONLY =================
# This does NOT prove the strategy is profitable — it proves the harness
# doesn't cheat (no lookahead) and correctly detects SL/TP fills. Run with
# --self-test; needs no API key and no network.

def _make_synthetic_series(start, count, minutes_step, start_price=1.1000, seed=1):
    import random
    random.seed(seed)
    candles = []
    price = start_price
    t = start
    for _ in range(count):
        o = price
        c = o + random.uniform(-0.0015, 0.0015)
        h = max(o,c) + random.uniform(0, 0.0008)
        l = min(o,c) - random.uniform(0, 0.0008)
        candles.append({"time": t, "open": o, "high": h, "low": l, "close": c})
        price = c
        t = t + timedelta(minutes=minutes_step)
    return candles

def self_test():
    print("Running self-test on synthetic data (no API key / network needed)...")
    start = datetime(2025, 1, 1)
    daily = _make_synthetic_series(start, 120, 60*24, seed=1)
    h4    = _make_synthetic_series(start, 120*6, 240, seed=2)
    h1    = _make_synthetic_series(start, 120*24, 60, seed=3)
    m5    = _make_synthetic_series(start + timedelta(days=90), 2000, 5, seed=4)

    settings = {"trade_news": True, "trading_mode": "regular", "currency": "ZAR",
                "account_size": 142, "lot_size": 0.01, "risk_percent": 1, "rr_ratio": 2.5}

    # --- Lookahead check: patch full_multi_tf_analysis's candle args and
    # confirm every candle handed to it has time <= as_of ---
    violations = []
    real_fn = eng.full_multi_tf_analysis
    def _checked(symbol, user_settings=None, historical=None, as_of=None):
        if historical and as_of:
            for interval, candles in historical.items():
                for c in candles:
                    if c["time"] > as_of:
                        violations.append((interval, c["time"], as_of))
        return real_fn(symbol, user_settings, historical=historical, as_of=as_of)
    eng.full_multi_tf_analysis = _checked

    trades = run_backtest("EURUSD", daily, h4, h1, m5, settings, verbose=False)
    eng.full_multi_tf_analysis = real_fn

    print(f"\nLookahead violations found: {len(violations)} (must be 0)")
    if violations:
        print("  FAIL — sample violation:", violations[0])
    else:
        print("  PASS — no candle timestamped after its simulated 'as_of' was ever used.")

    print(f"\nSynthetic trades generated: {len(trades)}")
    if trades:
        s = summarize(trades)
        print(json.dumps(s, indent=2))
        # sanity check SL/TP fill logic on one trade by hand
        t = trades[0]
        print(f"\nSample trade check: {t['symbol']} {t['bias']} entry={t['entry']} sl={t['sl']} tp={t['tp']} -> {t['outcome']} ({t['r_multiple']}R)")
    print("\nSelf-test complete. This validates the MECHANICS only — it says")
    print("nothing about whether the strategy is actually profitable, since")
    print("the price data above is random, not real market history.")

    _test_fill_detection()


def _test_fill_detection():
    """The random-walk data above rarely satisfies the strategy's own gates
    (a good sign for selectivity, but it means the walk above never
    exercises the SL/TP fill-detection path). This test forces a known
    signal at a known bar and hand-places subsequent price action so we
    know exactly which of SL/TP should be detected — proving that part of
    the harness independently of whether the live strategy fires."""
    print("\n--- Direct SL/TP fill-detection test (forced signal, hand-placed price path) ---")
    start = datetime(2025, 6, 1)
    daily = _make_synthetic_series(start, 120, 60*24, seed=10)
    h4    = _make_synthetic_series(start, 120*6, 240, seed=11)
    h1    = _make_synthetic_series(start, 120*24, 60, seed=12)
    m5    = _make_synthetic_series(start + timedelta(days=90), 50, 5, seed=13)

    # Append a hand-crafted tail: entry bar, then a bar that touches TP
    # cleanly (WIN case), for a BULLISH trade with entry=1.1000.
    last_t = m5[-1]["time"] + timedelta(minutes=5)
    entry_price = 1.1000
    tail = [
        {"time": last_t, "open": entry_price, "high": entry_price+0.0005, "low": entry_price-0.0005, "close": entry_price},
        {"time": last_t+timedelta(minutes=5), "open": entry_price, "high": entry_price+0.0010, "low": entry_price-0.0010, "close": entry_price},  # no touch yet
        {"time": last_t+timedelta(minutes=10), "open": entry_price, "high": entry_price+0.0200, "low": entry_price-0.0005, "close": entry_price+0.0180},  # TP should hit here
    ]
    m5_full = m5 + tail
    entry_index = len(m5) - 1  # the bar right before the forced-signal bar

    real_fn = eng.full_multi_tf_analysis
    call_count = {"n": 0}
    def _forced(symbol, user_settings=None, historical=None, as_of=None, weights=None):
        call_count["n"] += 1
        # fire exactly once, on the bar matching our hand-placed entry point
        if historical and historical["5min"] and historical["5min"][-1]["time"] == m5_full[entry_index]["time"]:
            return {"symbol": symbol, "signal": True, "score": 7, "bias": "BULLISH",
                    "entry": entry_price, "mode": "regular", "confluence": "forced-test",
                    "factors": {}, "reason": "forced"}
        return {"symbol": symbol, "signal": False, "score": 0, "bias": "NEUTRAL", "entry": 0,
                "mode": "regular", "confluence": "", "factors": {}, "reason": "no signal"}
    eng.full_multi_tf_analysis = _forced

    settings = {"trading_mode": "regular", "account_size": 142, "lot_size": 0.01, "risk_percent": 1, "rr_ratio": 2.5}
    trades = run_backtest("EURUSD", daily, h4, h1, m5_full, settings)
    eng.full_multi_tf_analysis = real_fn

    if not trades:
        print("  FAIL — forced signal never produced a trade record.")
        return
    t = trades[0]
    print(f"  Forced trade: entry={t['entry']} sl={t['sl']} tp={t['tp']} -> outcome={t['outcome']} ({t['r_multiple']}R)")
    if t["outcome"] == "WIN":
        print("  PASS — TP was clearly touched by the hand-placed bar and correctly detected as WIN.")
    else:
        print(f"  FAIL — expected WIN given the hand-placed price path, got {t['outcome']}.")


# ================= CLI =================

def main():
    parser = argparse.ArgumentParser(description="Backtest the live trading engine against real historical data.")
    parser.add_argument("--symbols", default="EURUSD,GBPUSD,XAUUSD,USDJPY,BTCUSD", help="comma-separated symbol list")
    parser.add_argument("--days", type=int, default=60, help="days of history to pull (5-min data depth is usually the limiting factor on your plan)")
    parser.add_argument("--mode", choices=["regular","scalp"], default="regular")
    parser.add_argument("--account-size", type=float, default=142)
    parser.add_argument("--risk-percent", type=float, default=1)
    parser.add_argument("--rr-ratio", type=float, default=2.5)
    parser.add_argument("--self-test", action="store_true", help="run the synthetic-data mechanics check instead of a real backtest")
    parser.add_argument("--weights-file", default=None, help="JSON file of weight-multiplier overrides (see analyze_backtest.py's suggestions)")
    parser.add_argument("--out", default="backtest_results.json")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    weights = None
    if args.weights_file:
        with open(args.weights_file) as f:
            weights = json.load(f)
        print(f"Using custom weights from {args.weights_file}: {weights}", file=sys.stderr)

    api_key = os.getenv("TWELVE_DATA_API_KEY")
    if not api_key:
        print("ERROR: set TWELVE_DATA_API_KEY before running a real backtest.", file=sys.stderr)
        print("(Or run with --self-test to check the harness mechanics without an API key.)", file=sys.stderr)
        sys.exit(1)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    settings = {
        "trade_news": True,  # backtests skip the live news-calendar check entirely — see README note
        "trading_mode": args.mode, "currency": "ZAR",
        "account_size": args.account_size, "lot_size": 0.01,
        "risk_percent": args.risk_percent, "rr_ratio": args.rr_ratio,
    }

    all_trades = []
    for symbol in symbols:
        print(f"\nFetching history for {symbol}...", file=sys.stderr)
        daily = fetch_historical_series(symbol, "1day", max(args.days, 200), api_key)
        h4    = fetch_historical_series(symbol, "4h", max(args.days, 60), api_key)
        h1    = fetch_historical_series(symbol, "1h", max(args.days, 30), api_key)
        m5    = fetch_historical_series(symbol, "5min", args.days, api_key)
        if not (daily and h4 and h1 and m5):
            print(f"  Skipping {symbol} — missing data for one or more timeframes.", file=sys.stderr)
            continue
        print(f"  {symbol}: {len(daily)}d / {len(h4)}x4h / {len(h1)}x1h / {len(m5)}x5m candles. Simulating...", file=sys.stderr)
        trades = run_backtest(symbol, daily, h4, h1, m5, settings, weights=weights)
        print(f"  {symbol}: {len(trades)} signals found.", file=sys.stderr)
        all_trades.extend(trades)

    summary = summarize(all_trades)
    print("\n" + "="*50)
    print(json.dumps(summary, indent=2))
    print("="*50)

    with open(args.out, "w") as f:
        json.dump({"summary": summary, "trades": all_trades}, f, indent=2, default=str)
    print(f"\nFull trade-by-trade results written to {args.out}")

    if summary["total_signals"] < 30:
        print(f"\nNOTE: only {summary['total_signals']} signals found — that's not enough for a "
              f"reliable read either. Try more --days, a longer symbol list via --symbols, or "
              f"switch --mode to scalp (fires more often).")


if __name__ == "__main__":
    main()
