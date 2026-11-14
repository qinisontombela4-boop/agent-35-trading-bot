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
    "USDZAR": {"CONT": (38, -0.54)},
    "SPX500": {"CONT": (39, 0.25)},
}
PRIOR_ALIASES = {"XTIUSD": "USOIL"}

# ---------------- FEATURE LEARNING (per pair: WHEN and HOW does a setup work on this market?) ----------------
# Every shadow trade is stored with its features: direction, session, score band, planned reward, which checklist items were true, and the
# news state. For each pair the bot keeps the R of every (feature = value) bucket. If, on that pair, a bucket has lost money clearly and
# consistently - at least FEAT_MIN_N trades, average <= FEAT_MAX_MEAN R and statistically significant (z <= -FEAT_Z) - signals that carry
# it are held back (e.g. "SELLs on USDCHF", "Asia-session setups on EURUSD"), and they are released again if the bucket recovers.
# Walk-forward test on 370 backtested trades (every decision used only EARLIER trades): vetoed trades averaged -0.45R (21% win);
# total profit rose from +28.6R to +41.7R. Pooling buckets across pairs did NOT help, so it is strictly per pair.
FEAT_MIN_N = 12
FEAT_MAX_MEAN = -0.30
FEAT_Z = 1.5
FEAT_PRIOR_CAP = 15
FEAT_LIVE_WINDOW = 40
# {symbol: {"feature=value": (n, mean R, stdev R)}} from the backtests (only buckets with >= 8 trades)
PRIOR_FEATS = {
    "BTCUSD": {"dir=BUY": (47, 0.124, 1.594), "session=asia": (25, 0.102, 1.578), "score=7+": (73, 0.047, 1.547), "rr=2.2-2.7": (29, 0.019, 1.626), "sweep=True": (67, 0.064, 1.571), "h4=True": (27, 0.149, 1.627), "h1=False": (49, 0.085, 1.585), "range=True": (75, 0.069, 1.564), "m15=True": (75, 0.069, 1.564), "m5=True": (69, 0.062, 1.546), "session=london": (17, 0.114, 1.65), "rr=lt2.2": (40, 0.083, 1.494), "h4=False": (48, 0.025, 1.543), "h1=True": (26, 0.04, 1.555), "session=late": (22, 0.014, 1.602), "dir=SELL": (28, -0.023, 1.536), "session=ny": (11, 0.035, 1.539), "sweep=False": (8, 0.111, 1.61)},
    "ETHUSD": {"dir=BUY": (8, 0.164, 1.589), "score=7+": (13, -0.088, 1.505), "sweep=True": (12, 0.0, 1.537), "h4=False": (13, -0.235, 1.506), "range=True": (14, -0.162, 1.473), "m15=True": (14, -0.162, 1.473), "m5=True": (14, -0.162, 1.473), "rr=lt2.2": (10, -0.805, 0.706), "h1=False": (11, -0.25, 1.337)},
    "EURUSD": {"dir=SELL": (23, 0.103, 1.467), "session=asia": (10, -0.195, 1.444), "score=7+": (37, 0.185, 1.518), "rr=lt2.2": (29, 0.366, 1.494), "sweep=True": (38, 0.23, 1.523), "h1=False": (29, -0.056, 1.418), "range=True": (40, 0.203, 1.5), "m15=True": (40, 0.203, 1.5), "m5=True": (35, -0.049, 1.434), "session=late": (18, 0.263, 1.512), "h4=False": (36, 0.256, 1.504), "h1=True": (11, 0.885, 1.559), "dir=BUY": (17, 0.338, 1.577), "rr=2.2-2.7": (9, -0.369, 1.44)},
    "NAS100": {"dir=BUY": (9, -0.442, 1.328), "score=7+": (31, 0.198, 1.609), "rr=2.2-2.7": (12, 0.573, 1.764), "sweep=True": (30, 0.343, 1.625), "h4=False": (25, 0.176, 1.621), "h1=False": (20, 0.069, 1.543), "range=True": (34, 0.259, 1.605), "m15=True": (34, 0.259, 1.605), "m5=True": (31, 0.066, 1.546), "dir=SELL": (25, 0.512, 1.644), "session=asia": (12, 0.649, 1.63), "rr=lt2.2": (19, 0.076, 1.473), "h4=True": (9, 0.492, 1.631), "session=late": (13, 0.325, 1.625), "h1=True": (14, 0.531, 1.71)},
    "SPX500": {"dir=SELL": (30, 0.31, 1.627), "session=late": (14, 0.767, 1.676), "rr=2.2-2.7": (9, 0.431, 1.814), "h4=False": (26, 0.171, 1.617), "h1=False": (24, 0.293, 1.668), "range=True": (39, 0.246, 1.622), "m15=True": (39, 0.246, 1.622), "m5=True": (37, 0.316, 1.637), "score=7+": (36, 0.257, 1.619), "sweep=True": (35, 0.201, 1.605), "rr=lt2.2": (23, 0.242, 1.538), "session=ny": (8, -0.161, 1.658), "h4=True": (13, 0.396, 1.689), "h1=True": (15, 0.171, 1.6), "session=asia": (9, 0.276, 1.628), "session=london": (8, -0.291, 1.494), "dir=BUY": (9, 0.034, 1.685)},
    "US30": {"dir=SELL": (29, 0.091, 1.565), "session=late": (17, 1.0, 1.573), "score=7+": (38, 0.205, 1.553), "rr=lt2.2": (29, 0.133, 1.502), "sweep=True": (36, 0.089, 1.51), "h4=False": (28, -0.156, 1.408), "h1=False": (26, 0.282, 1.57), "range=True": (42, 0.088, 1.519), "m15=True": (42, 0.088, 1.519), "m5=True": (38, 0.204, 1.553), "h4=True": (14, 0.576, 1.666), "h1=True": (16, -0.226, 1.424), "session=ny": (8, -0.637, 1.09), "session=asia": (11, -0.462, 1.237), "dir=BUY": (13, 0.082, 1.474)},
    "USDCHF": {"dir=BUY": (19, 0.254, 1.618), "session=late": (16, -0.112, 1.519), "score=7+": (31, -0.179, 1.468), "rr=lt2.2": (17, -0.016, 1.5), "sweep=True": (30, -0.15, 1.484), "h4=False": (21, -0.356, 1.379), "h1=True": (8, -0.344, 1.407), "range=True": (32, -0.208, 1.454), "m15=True": (32, -0.208, 1.454), "m5=True": (29, -0.218, 1.455), "h4=True": (11, 0.074, 1.616), "h1=False": (24, -0.163, 1.496), "dir=SELL": (13, -0.884, 0.837), "rr=2.2-2.7": (11, -0.453, 1.458)},
    "USDZAR": {"dir=BUY": (18, -0.435, 1.264), "session=london": (9, -0.434, 1.327), "score=7+": (33, -0.551, 1.171), "rr=lt2.2": (25, -0.364, 1.314), "sweep=True": (34, -0.658, 1.07), "h4=False": (31, -0.701, 1.024), "h1=True": (11, -0.022, 1.498), "range=True": (38, -0.543, 1.173), "m15=True": (38, -0.543, 1.173), "m5=True": (34, -0.478, 1.226), "session=asia": (9, -0.417, 1.342), "h1=False": (27, -0.755, 0.967), "session=ny": (8, -0.745, 0.98), "rr=2.2-2.7": (12, -0.865, 0.802), "session=late": (12, -0.584, 1.173), "dir=SELL": (20, -0.64, 1.11)},
    "USOIL": {"dir=BUY": (18, 0.184, 1.599), "session=late": (11, 0.041, 1.542), "score=7+": (24, 0.035, 1.571), "rr=lt2.2": (13, 0.04, 1.438), "sweep=True": (23, -0.073, 1.514), "h1=False": (17, -0.125, 1.492), "range=True": (26, 0.068, 1.571), "m15=True": (26, 0.068, 1.571), "m5=True": (23, 0.081, 1.59), "h4=False": (23, -0.034, 1.546), "dir=SELL": (8, -0.194, 1.576), "rr=2.2-2.7": (8, -0.134, 1.647), "h1=True": (9, 0.432, 1.741)},
    "XAUUSD": {"dir=BUY": (11, 0.022, 1.513), "session=late": (10, 0.07, 1.461), "score=7+": (25, 0.512, 1.661), "rr=lt2.2": (14, 0.631, 1.527), "sweep=True": (25, 0.632, 1.655), "h4=False": (26, 0.817, 1.641), "h1=False": (21, 0.624, 1.651), "range=True": (30, 0.698, 1.668), "m15=True": (30, 0.698, 1.668), "m5=True": (29, 0.653, 1.68), "session=asia": (14, 1.151, 1.691), "dir=SELL": (19, 1.089, 1.665), "rr=2.2-2.7": (13, 0.575, 1.783), "h1=True": (9, 0.871, 1.797)},
}
FEATURE_LABELS = {"dir=BUY": "BUY trades", "dir=SELL": "SELL trades", "session=asia": "Asia-session setups (00-08 UTC)", "session=london": "London-session setups (08-13 UTC)",
                  "session=ny": "New York-session setups (13-17 UTC)", "session=late": "late-session setups (17-24 UTC)", "score=5": "5/10-score setups", "score=6": "6/10-score setups",
                  "score=7+": "7+/10-score setups", "rr=lt2.2": "setups with a small (<2.2R) target", "rr=2.2-2.7": "setups with a ~2.5R target", "rr=2.7+": "setups with a far (2.7R+) target",
                  "sweep=True": "setups after a liquidity sweep", "sweep=False": "setups without a liquidity sweep", "h4=True": "setups with the 4H trend agreeing", "h4=False": "setups against the 4H trend",
                  "h1=True": "setups with 1H structure agreeing", "h1=False": "setups with 1H structure not agreeing", "range=True": "setups on the right side of the range", "range=False": "setups on the wrong side of the range",
                  "m15=True": "setups with a 15m structure shift", "m15=False": "setups without a 15m shift", "m5=True": "setups with a 5m trigger", "m5=False": "setups without a 5m trigger",
                  "news=before": "setups just before high-impact news", "news=after": "setups just after high-impact news", "news=quiet": "setups away from news"}

def features_of(direction, hour_utc, score, planned_rr, checklist, news="quiet"):
    """The feature buckets one setup falls into, as {"dir": "BUY", ...}."""
    f = {"dir": "BUY" if "BULL" in str(direction).upper() else "SELL"}
    h = int(hour_utc)
    f["session"] = "asia" if h < 8 else "london" if h < 13 else "ny" if h < 17 else "late"
    sc = int(score or 0); f["score"] = "5" if sc <= 5 else "6" if sc == 6 else "7+"
    # (the planned reward is NOT a feature: it depends on each user's own R:R setting, so it would not mean the same thing for every user)
    ck = checklist or {}
    for k, n in (("Liquidity swept", "sweep"), ("4H agrees", "h4"), ("1H structure agrees", "h1"), ("Right side of range", "range"), ("15m structure shift", "m15"), ("5m trigger", "m5")):
        if k in ck: f[n] = str(bool(ck[k]))
    f["news"] = news if news in ("before", "after", "quiet") else "quiet"
    return f

def _fkey(symbol, kind): return f"FEAT|{symbol}|{kind}"

def feature_stat(stats, symbol, kind, fv):
    """(n, mean, z) for one bucket: discounted backtest prior + live results."""
    live = list(((stats or {}).get(_fkey(symbol, kind), {}) or {}).get(fv, []))[-FEAT_LIVE_WINDOW:]
    pn, pm, ps = 0, 0.0, 0.0
    if kind == "CONT":
        p = PRIOR_FEATS.get(PRIOR_ALIASES.get(symbol, symbol), {}).get(fv)
        if p:
            full, pm, ps = p; pn = min(full, FEAT_PRIOR_CAP)
    n = pn + len(live)
    if n < 2: return n, 0.0, 0.0
    sx = pn * pm + sum(live)
    sxx = pn * (ps * ps + pm * pm) + sum(x * x for x in live)
    m = sx / n; var = max(1e-9, (sxx - n * m * m) / (n - 1)); z = m / ((var ** 0.5) / (n ** 0.5))
    return n, m, z

def feature_vetoes(stats, symbol, kind, fvalues):
    """[(feature=value, n, mean)] - buckets of this setup that have lost clearly on this pair."""
    out = []
    for f, v in fvalues.items():
        fv = f"{f}={v}"; n, m, z = feature_stat(stats, symbol, kind, fv)
        if n >= FEAT_MIN_N and m <= FEAT_MAX_MEAN and z <= -FEAT_Z: out.append((fv, n, m))
    return out

def record_features(stats, symbol, kind, fvalues, r_value):
    rec = stats.setdefault(_fkey(symbol, kind), {})
    for f, v in fvalues.items():
        fv = f"{f}={v}"; rec[fv] = (list(rec.get(fv, [])) + [round(float(r_value), 3)])[-FEAT_LIVE_WINDOW:]
    return stats

def gate_features(stats, symbol, kind, fvalues):
    """(allowed, reason). Only continuation/scalp setups are filtered this way (pullbacks are already gated as a whole)."""
    if kind == "PB" or not fvalues: return True, ""
    v = feature_vetoes(stats, symbol, kind, fvalues)
    if not v: return True, ""
    fv, n, m = sorted(v, key=lambda x: x[2])[0]
    return False, (f"on {symbol}, {FEATURE_LABELS.get(fv, fv)} have lost {m:+.2f}R per trade over {n} tracked trades, so this one was skipped "
                   f"(the bot re-checks as results come in and releases the filter once it recovers)")

def learned_rules(stats, symbol, kind="CONT"):
    """Every bucket currently vetoed for this pair - shown on /pair-learning."""
    keys = set(PRIOR_FEATS.get(PRIOR_ALIASES.get(symbol, symbol), {})) | set(((stats or {}).get(_fkey(symbol, kind), {}) or {}))
    out = []
    for fv in sorted(keys):
        n, m, z = feature_stat(stats, symbol, kind, fv)
        if n >= FEAT_MIN_N and m <= FEAT_MAX_MEAN and z <= -FEAT_Z: out.append((fv, n, round(m, 2)))
    return out


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
