
"""
PAIR LEARNING - the bot keeps score of how each pair actually behaves and adapts what it sends.

What it learns from: every signal the engine produces is also logged as a private 'shadow' trade (independent of any user) and
resolved against later candles. Each result (in R, after estimated spread) is added to that pair's record, per setup type:
    CONT   regular-mode trade with the daily bias
    PB     pullback (against the daily bias)
    SCALP  scalp-mode trade
The record starts from a PRIOR taken from the Mar-Nov 2026 MT5 backtests (discounted: at most PRIOR_MAX_N trades' worth) so a brand-new
pair is not judged on two lucky/unlucky trades, then live results gradually outweigh it.

What it changes (only ever makes the bot MORE selective, never looser than the tested rules):
    CONT/SCALP  strong  (avg >= +0.25R)  -> sent, tagged as a proven pair
                normal                   -> sent as usual
                weak    (avg <= -0.05R)  -> only the best setups (score 7+)
                paused  (avg <= -0.15R)  -> not sent; keeps being tracked privately, resumes by itself once the average recovers
    PB          sent only on pairs where pullbacks have PROVEN positive (avg >= +0.05R over 20+ trades) - and only to users who opted in
"""

PRIOR_MAX_N = 20
MIN_N_FOR_JUDGEMENT = 15
MIN_N_FOR_PAUSE = 20
STRONG_AVG = 0.25
WEAK_AVG = -0.05
PAUSE_AVG = -0.15
RESUME_AVG = -0.10          # a paused pair resumes only once its average is back above this (hysteresis: no flip-flopping)
PB_PROVEN_AVG = 0.05
LIVE_WINDOW = 60            # only the latest 60 live results count (markets change)

# {symbol: {kind: (backtest trades, average net R)}} - from the 8-pair MT5 backtests, Mar-Nov 2026
PRIORS = {
    "EURUSD": {"CONT": (40, 0.20), "PB": (83, -0.48)},
    "XAUUSD": {"CONT": (30, 0.70), "PB": (91, 0.08), "SCALP": (80, -0.06)},
    "NAS100": {"CONT": (34, 0.26), "PB": (97, -0.34)},
    "BTCUSD": {"CONT": (75, 0.07), "PB": (105, -0.20), "SCALP": (46, -0.02)},
    "USDCHF": {"CONT": (32, -0.21), "PB": (96, -0.13)},
    "ETHUSD": {"CONT": (14, -0.16), "PB": (83, -0.48)},
    "US30":   {"CONT": (42, 0.09), "PB": (84, -0.04)},
    "USOIL":  {"CONT": (26, 0.07), "PB": (94, -0.33)},
}
PRIOR_ALIASES = {"XTIUSD": "USOIL"}


def key(symbol, kind):
    return f"{symbol}|{kind}"


def _prior(symbol, kind):
    p = PRIORS.get(PRIOR_ALIASES.get(symbol, symbol), {}).get(kind)
    if not p:
        return 0, 0.0
    return min(p[0], PRIOR_MAX_N), p[1]


def posterior(stats, symbol, kind):
    """(effective_n, average_R, live_n)."""
    rec = (stats or {}).get(key(symbol, kind), {})
    live = list(rec.get("live", []))[-LIVE_WINDOW:]
    pn, pa = _prior(symbol, kind)
    n = pn + len(live)
    avg = ((pn * pa + sum(live)) / n) if n else 0.0
    return n, avg, len(live)


def record(stats, symbol, kind, r_value, now_iso=None):
    """Add one resolved shadow trade (in R) and update the paused flag. Mutates and returns `stats`."""
    rec = stats.setdefault(key(symbol, kind), {"live": [], "paused": False})
    rec["live"] = (list(rec.get("live", [])) + [round(float(r_value), 3)])[-LIVE_WINDOW:]
    rec["total_live"] = int(rec.get("total_live", 0)) + 1
    if now_iso: rec["updated"] = now_iso
    n, avg, _ = posterior(stats, symbol, kind)
    if kind != "PB":
        if rec.get("paused"):
            if avg > RESUME_AVG: rec["paused"] = False
        elif n >= MIN_N_FOR_PAUSE and avg <= PAUSE_AVG:
            rec["paused"] = True
    return stats


def evaluate(stats, symbol, kind):
    """{"status", "n", "avg", "live_n", "min_score", "allowed"}  status in learning|strong|normal|weak|paused|proven|blocked."""
    n, avg, live_n = posterior(stats, symbol, kind)
    rec = (stats or {}).get(key(symbol, kind), {})
    out = {"n": n, "avg": round(avg, 2), "live_n": live_n, "min_score": None}
    if kind == "PB":
        if n >= MIN_N_FOR_PAUSE and avg >= PB_PROVEN_AVG:
            out.update(status="proven", allowed=True)
        else:
            out.update(status="blocked" if n >= MIN_N_FOR_JUDGEMENT else "learning", allowed=False)
        return out
    # a pair we have never seen and have no prior for: allowed (the tested rules apply), tagged "learning"
    paused_now = bool(rec["paused"]) if "paused" in rec else (n >= MIN_N_FOR_PAUSE and avg <= PAUSE_AVG)
    if paused_now:
        out.update(status="paused", allowed=False)
    elif n < MIN_N_FOR_JUDGEMENT:
        out.update(status="learning", allowed=True)
    elif avg >= STRONG_AVG:
        out.update(status="strong", allowed=True)
    elif avg <= WEAK_AVG:
        out.update(status="weak", allowed=True, min_score=7)
    else:
        out.update(status="normal", allowed=True)
    return out


def gate(stats, symbol, kind, score):
    """(allowed, reason_or_label). reason is a user-facing sentence when blocked; a short tag when allowed (may be '')."""
    ev = evaluate(stats, symbol, kind)
    names = {"CONT": "regular", "PB": "pullback", "SCALP": "scalp"}
    if not ev["allowed"]:
        if kind == "PB":
            return False, (f"pullback trades on {symbol} are not proven yet (bot's record {ev['avg']:+.2f}R over {ev['n']} trades)")
        return False, (f"{symbol} {names[kind]} signals are paused: the bot's own tracking shows {ev['avg']:+.2f}R per trade over {ev['n']} trades. "
                       f"It keeps watching and resumes automatically once the pair recovers")
    if ev["min_score"] and (score or 0) < ev["min_score"]:
        return False, (f"{symbol} has been weak so far ({ev['avg']:+.2f}R per trade over {ev['n']} trades), so only {ev['min_score']}/10 setups or better are sent "
                       f"(this one was {score}/10)")
    tag = ""
    if ev["status"] in ("strong", "proven"):
        tag = f"⭐ Proven pair: {ev['avg']:+.2f}R average over {ev['n']} tracked trades"
    return True, tag
