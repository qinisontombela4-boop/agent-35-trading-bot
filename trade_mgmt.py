
"""
SMOOTH MODE - profit-protection logic for a tracked trade (pure functions, no I/O, unit-testable).

A user who turns Smooth mode on is told when to tighten the stop, in stages that depend on how far the take-profit is:
    * +1R reached        -> move the stop to BREAKEVEN (entry)                    (only if the target is >= 1.8R away)
    * 80% of the way     -> LOCK profit: move the stop to 40% of the way to the target   (only if the target is >= 1.5R away)
        target 2R   : alert at +1.6R, lock +0.8R
        target 2.5R : alert at +2.0R, lock +1.0R
        target 3R   : alert at +2.4R, lock +1.2R
Backtest (293 trades, 8 pairs): losses 61% -> 45%, worst drawdown 17.6R -> 9.5R, total profit +39.6R -> +33.7R.

The same function re-plays the candles to decide the trade's result, assuming the user followed the alerts, so the journal shows
what really happened to a trade managed this way:  WIN (target hit) / LOCKED (stopped at a locked profit) / BE (stopped at entry) / LOSS.
A candle that touches the live stop AND the target is counted as a stop (worst case); a stage reached on a candle only protects the
NEXT candle (we cannot know the order inside one candle).
"""

BE_TRIGGER_R = 1.0
BE_MIN_TARGET_R = 1.8
LOCK_MIN_TARGET_R = 1.5
LOCK_TRIGGER_FRAC = 0.8     # alert when price is 80% of the way to the target...
LOCK_LEVEL_FRAC = 0.4       # ...and move the stop to 40% of the way (it leaves room for a normal pullback before the move continues)


def stage_rules(tp_r):
    """[(trigger_R, lock_R), ...] in the order they trigger. Empty when the target is too close to manage."""
    rules = []
    if tp_r >= BE_MIN_TARGET_R:
        rules.append((BE_TRIGGER_R, 0.0))
    trig = LOCK_TRIGGER_FRAC * tp_r
    if tp_r >= LOCK_MIN_TARGET_R and trig > (rules[-1][0] + 0.05 if rules else 1.05):
        rules.append((round(trig, 2), round(LOCK_LEVEL_FRAC * tp_r, 2)))
    return rules


def manage(entry, sl, tp, is_bull, candles, opened, to_dt, smooth=True):
    """Replay `candles` (oldest first) from `opened`.
    Returns {"outcome": None|"WIN"|"LOSS"|"BE"|"LOCKED", "price": exit price or None, "stage": stages reached,
             "live_sl": current protective stop, "lock_r": R locked at the exit (LOCKED only), "rules": [...]}."""
    entry, sl, tp = float(entry), float(sl), float(tp)
    risk = abs(entry - sl)
    res = {"outcome": None, "price": None, "stage": 0, "live_sl": sl, "lock_r": 0.0, "rules": []}
    if risk <= 0:
        return res
    d = 1.0 if is_bull else -1.0
    tp_r = abs(tp - entry) / risk
    rules = stage_rules(tp_r) if smooth else []
    res["rules"] = rules
    live_sl, stage = sl, 0
    for k in candles:
        kt = to_dt(k)
        if opened and kt and kt < opened:
            continue
        hi, lo = float(k["high"]), float(k["low"])
        hit_sl = (lo <= live_sl) if is_bull else (hi >= live_sl)
        hit_tp = (hi >= tp) if is_bull else (lo <= tp)
        if hit_sl:
            res.update(price=live_sl, stage=stage, live_sl=live_sl)
            if stage == 0:
                res["outcome"] = "LOSS"
            else:
                lock = rules[stage - 1][1]
                res["outcome"] = "LOCKED" if lock > 0 else "BE"
                res["lock_r"] = lock
            return res
        if hit_tp:
            res.update(outcome="WIN", price=tp, stage=stage, live_sl=live_sl)
            return res
        fav = hi if is_bull else lo
        prog = (fav - entry) * d / risk
        while stage < len(rules) and prog >= rules[stage][0]:
            lock = rules[stage][1]
            live_sl = entry + d * lock * risk
            stage += 1
    res["stage"] = stage
    res["live_sl"] = live_sl
    return res


def stage_message(symbol, is_bull, entry, live_sl, trigger_r, lock_r, tp, dp):
    """Telegram text for a newly reached stage."""
    side = "BUY" if is_bull else "SELL"
    if lock_r <= 0:
        return (f"🔒 {symbol} {side}: price has reached +{trigger_r:.1f}R.\n"
                f"Move your stop loss to BREAKEVEN ({live_sl:.{dp}f}) so this trade can no longer lose.\nTarget still {tp:.{dp}f}.")
    return (f"🔒 {symbol} {side}: price has reached +{trigger_r:.1f}R, close to your target ({tp:.{dp}f}).\n"
            f"Lock in profit: move your stop loss to {live_sl:.{dp}f} (that secures +{lock_r:g}R even if price turns around).")
