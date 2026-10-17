"""
Economic calendar + "news lean" for Agent 35.   (one file: news_calendar.py)

CALENDAR SOURCES (tried in this order, first one that returns events wins):
  1. Forex Factory's public weekly JSON feed (nfs.faireconomy.media) — FREE, NO
     API KEY, explicit UTC offset on every timestamp (no timezone guessing).
  1b. The same feed on its CDN mirror host (cdn-nfs.faireconomy.media), in case
     the main host rate-limits or blocks your server.
  2. JBlanked's News API — only if JBLANKED_API_KEY is set (fallback, or the
     primary if NEWS_SOURCE=jblanked; the only source with "Actual" values).
  3. A SAVED COPY of the last good calendar (persisted via set_persistence), so
     a restart/redeploy during a feed outage doesn't leave you with nothing.
If everything fails the calendar degrades to "no events known" AND records
exactly why in STATUS — shown on /news and /news-status, never silent.

NEWS LEAN (Cobra-style, experimental): ~30 min before a High-impact release,
compare FORECAST with PREVIOUS (e.g. CPI 3.6% vs 3.4% -> inflation expected
hotter -> USD expected stronger -> SELL XAUUSD/EURUSD, BUY USDJPY). This is a
GUESS from public numbers — the real driver is ACTUAL vs forecast, which isn't
known yet. So every lean is logged and scored against the real price move
+5/+15/+60 min after the release, and the track record travels with the lean.

NOTE ON JBLANKED TIMEZONE: its "Date" ("YYYY.MM.DD HH:MM:SS") has no timezone
marker. If its event times are off by a fixed number of hours, set
JBLANKED_UTC_OFFSET_HOURS (e.g. -2). Not needed for the free feed.
"""

import os, sys, requests
from datetime import datetime, timedelta, timezone

BUILD_ID = "2026-10-15-lean"   # app.py checks this matches, so a half-uploaded deploy is caught

JBLANKED_API_KEY = os.getenv("JBLANKED_API_KEY", "")
JBLANKED_BASE_URL = "https://www.jblanked.com/news/api"
JBLANKED_UTC_OFFSET_HOURS = float(os.getenv("JBLANKED_UTC_OFFSET_HOURS", "0") or 0)
_FF_PRIMARY = os.getenv("FF_FEED_URL", "https://nfs.faireconomy.media/ff_calendar_thisweek.json")
FF_FEED_URLS = [_FF_PRIMARY]   # the old cdn-nfs mirror host does not resolve (DNS error), so it is no longer tried
NEWS_SOURCE = os.getenv("NEWS_SOURCE", "auto").strip().lower()  # "auto" (free feed first) or "jblanked"

CACHE_TTL_MINUTES = 60       # the free feed allows only ~2 requests per 5 min PER IP and Render shares IPs, so fetch rarely; scheduled times almost never change
FAILURE_BACKOFF_MINUTES = 5  # after a failed fetch, wait this long before trying again
RATE_LIMIT_BACKOFF_MINUTES = 30  # after an HTTP 429, leave the feed alone this long
NEXT_WEEK_TTL_HOURS = 6
SAVED_COPY_MAX_AGE_DAYS = 8  # a saved copy older than this is from a different week — ignore it
HTTP_TIMEOUT = 12
USER_AGENT = "Mozilla/5.0 (compatible; Agent35/1.0; +https://agent-35-trading-bot.onrender.com)"

_CACHE = {"events": [], "fetched_at": None, "next_try_at": None}
_NEXT = {"events": [], "at": None}
_PERSIST = {"load": None, "save": None, "restore_tried": False, "last_sig": None, "last_saved": None}

STATUS = {
    "source": None,          # which feed the current events came from
    "ok": False,             # did the LAST live fetch succeed?
    "stale": False,          # are the events shown from a saved/old copy?
    "last_attempt": None,    # UTC datetime
    "last_success": None,    # UTC datetime
    "last_error": "",        # human-readable reason if the last attempt failed
    "event_count": 0,
}

IMPACT_ORDER = {"None": 0, "Holiday": 0, "Low": 1, "Medium": 2, "High": 3}
CRYPTO_SYMBOLS = ["BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD","ADAUSD","DOGEUSD","DOTUSD","AVAXUSD","LINKUSD","MATICUSD","LTCUSD"]
MAJORS = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]


def _normalize_impact(value):
    v = str(value or "").strip().lower()
    return {"high": "High", "medium": "Medium", "low": "Low", "holiday": "Holiday"}.get(v, "None")


# ================================================================ persistence

def set_persistence(load_fn, save_fn):
    """Give the module somewhere durable to keep the last good calendar.
    load_fn() -> dict (or {}), save_fn(dict). app.py wires these to its
    Supabase-aware load_json/save_json so it survives restarts."""
    _PERSIST.update(load=load_fn, save=save_fn, restore_tried=False)


def _events_to_json(events):
    return [{**e, "time": e["time"].isoformat()} for e in events]


def _events_from_json(rows):
    out = []
    for r in rows or []:
        try:
            out.append({**r, "time": datetime.fromisoformat(r["time"])})
        except Exception:
            continue
    out.sort(key=lambda e: e["time"])
    return out


def _save_persisted(events, now):
    if not _PERSIST["save"]:
        return
    sig = hash(tuple((e["id"], str(e.get("forecast")), str(e.get("previous")), str(e.get("actual"))) for e in events))
    if sig == _PERSIST["last_sig"] and _PERSIST["last_saved"] and (now - _PERSIST["last_saved"]).total_seconds() < 6 * 3600:
        return  # nothing changed; don't write to storage every 15 minutes
    try:
        _PERSIST["save"]({"fetched_at": now.isoformat(), "source": STATUS["source"], "events": _events_to_json(events)})
        _PERSIST.update(last_sig=sig, last_saved=now)
    except Exception as ex:
        print(f"[NEWS CALENDAR] could not save calendar copy: {ex}", file=sys.stderr)


def _restore_persisted(now):
    """Returns (events, saved_at) from the saved copy, or (None, None)."""
    if not _PERSIST["load"]:
        return None, None
    try:
        blob = _PERSIST["load"]() or {}
        saved_at = datetime.fromisoformat(blob["fetched_at"])
        if (now - saved_at).days > SAVED_COPY_MAX_AGE_DAYS:
            return None, None
        events = _events_from_json(blob.get("events"))
        return (events, saved_at) if events else (None, None)
    except Exception:
        return None, None


# ================================================================ sources

def _ff_rows_to_events(raw):
    events = []
    for e in raw:
        dt = _parse_iso_to_utc(e.get("date", ""))
        if not dt:
            continue
        currency = e.get("country", "")
        title = e.get("title", "Unnamed event")
        events.append({
            "id": f"{currency}_{title}_{e.get('date','')}",
            "name": title,
            "currency": currency,
            "impact": _normalize_impact(e.get("impact")),
            "time": dt,
            "actual": None,  # this feed doesn't publish actuals
            "forecast": e.get("forecast") or None,
            "previous": e.get("previous") or None,
        })
    return events


def _get_ff_week(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}" + (" (rate limited)" if r.status_code == 429 else ""))
    raw = r.json()
    if not isinstance(raw, list):
        raise RuntimeError(f"unexpected response shape: {str(raw)[:100]}")
    return _ff_rows_to_events(raw)


def _fetch_forex_factory_feed():
    """Free, keyless. THIS week (required). NEXT week is best effort, only asked
    for Thursday-Sunday and cached for hours, because the feed rate-limits hard
    (HTTP 429) and next week's file doesn't exist until late in the week."""
    errors = []
    events = None
    for url in FF_FEED_URLS:
        try:
            events = _get_ff_week(url)
            if not events:
                raise RuntimeError("responded but contained zero usable events")
            this_url = url
            break
        except Exception as ex:
            events = None
            errors.append(f"{url.split('/')[2]}: {ex}")
    if events is None:
        raise RuntimeError("; ".join(errors))
    now = datetime.utcnow()
    if now.weekday() >= 3:
        stale = _NEXT["at"] is None or (now - _NEXT["at"]).total_seconds() > NEXT_WEEK_TTL_HOURS * 3600
        if stale:
            try:
                _NEXT.update(events=_get_ff_week(this_url.replace("thisweek", "nextweek")), at=now)
                STATUS["next_week_note"] = ""
            except Exception as ex:
                _NEXT["at"] = now - timedelta(hours=NEXT_WEEK_TTL_HOURS - 0.5)  # retry in ~30 min
                STATUS["next_week_note"] = f"next week not available yet ({ex})"
        events = events + _NEXT["events"]
    seen, unique = set(), []
    for e in events:
        if e["id"] not in seen:
            seen.add(e["id"]); unique.append(e)
    return unique


def _fetch_jblanked():
    if not JBLANKED_API_KEY:
        raise RuntimeError("JBLANKED_API_KEY not set")
    r = requests.get(
        f"{JBLANKED_BASE_URL}/forex-factory/calendar/week/",
        headers={"Content-Type": "application/json", "Authorization": f"Api-Key {JBLANKED_API_KEY}"},
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} from JBlanked: {r.text[:120]}")
    raw = r.json()
    if not isinstance(raw, list):
        raise RuntimeError(f"unexpected response shape from JBlanked: {str(raw)[:120]}")
    events = []
    for e in raw:
        dt = _parse_dt(e.get("Date", ""))
        if not dt:
            continue
        dt = dt - timedelta(hours=JBLANKED_UTC_OFFSET_HOURS)
        events.append({
            "id": f"{e.get('Currency','')}_{e.get('Name','')}_{e.get('Date','')}",
            "name": e.get("Name", "Unnamed event"),
            "currency": e.get("Currency", ""),
            "impact": _normalize_impact(e.get("Impact")),
            "time": dt,
            "actual": e.get("Actual"),
            "forecast": e.get("Forecast"),
            "previous": e.get("Previous"),
        })
    return events


def _parse_dt(date_str):
    try:
        return datetime.strptime(date_str, "%Y.%m.%d %H:%M:%S")
    except Exception:
        return None


def _parse_iso_to_utc(s):
    """'2026-10-12T05:30:00-04:00' -> naive UTC datetime 2026-10-12 09:30."""
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt  # no offset given: assume it is already UTC
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _source_order():
    free = ("Forex Factory (free feed)", _fetch_forex_factory_feed)
    jb = ("JBlanked", _fetch_jblanked)
    if NEWS_SOURCE == "jblanked":
        return [jb, free]
    order = [free]
    if JBLANKED_API_KEY:
        order.append(jb)
    return order


# ================================================================ public API

def fetch_calendar(force=False):
    """This week's calendar, normalized and cached. Never raises: on total
    failure it serves the last good cache (or the saved copy) and records the
    reason in STATUS."""
    now = datetime.utcnow()
    # Cold start (Render woke up / redeployed): reuse the saved copy if it is still fresh,
    # instead of spending a rate-limited request on the feed.
    if not _CACHE["events"] and not _PERSIST["restore_tried"]:
        _PERSIST["restore_tried"] = True
        events, saved_at = _restore_persisted(now)
        if events:
            _CACHE["events"] = events
            fresh = (now - saved_at).total_seconds() < CACHE_TTL_MINUTES * 60
            _CACHE["fetched_at"] = saved_at if fresh else None
            STATUS.update({"source": f"saved copy from {saved_at.strftime('%a %d %b %H:%M')} UTC", "stale": not fresh,
                           "ok": fresh, "event_count": len(events)})
            if fresh:
                return events
    if _CACHE["next_try_at"] and now < _CACHE["next_try_at"]:
        return _CACHE["events"]  # backing off after a recent failure (force can't override: a 429 gets worse if hammered)
    if not force and _CACHE["fetched_at"] and (now - _CACHE["fetched_at"]).total_seconds() < CACHE_TTL_MINUTES * 60:
        return _CACHE["events"]

    STATUS["last_attempt"] = now
    errors = []
    for name, fetch in _source_order():
        try:
            events = fetch()
            if not events:
                raise RuntimeError("feed responded but contained zero usable events")
            events.sort(key=lambda e: e["time"])
            _CACHE.update({"events": events, "fetched_at": now, "next_try_at": None})
            STATUS.update({"source": name, "ok": True, "stale": False, "last_success": now, "last_error": "", "event_count": len(events)})
            _save_persisted(events, now)
            return events
        except Exception as ex:
            errors.append(f"{name}: {ex}")
            print(f"[NEWS CALENDAR] {name} failed: {ex}", file=sys.stderr)

    # every live source failed
    limited = any("429" in e for e in errors)
    _CACHE["next_try_at"] = now + timedelta(minutes=RATE_LIMIT_BACKOFF_MINUTES if limited else FAILURE_BACKOFF_MINUTES)
    STATUS.update({"ok": False, "last_error": " | ".join(errors) + (" — the free feed is rate-limiting this server; retrying in 30 min. Admin: paste the calendar manually at /news-import." if limited else "")})
    if _CACHE["events"]:
        STATUS["stale"] = True
    STATUS["event_count"] = len(_CACHE["events"])
    return _CACHE["events"]  # stale beats nothing


def import_manual(text, now=None):
    """Admin fallback: the raw JSON from the free feed URL, pasted by hand (a browser
    isn't rate-limited like the server is). Returns the number of events loaded."""
    import json
    now = now or datetime.utcnow()
    raw = json.loads(text)
    if not isinstance(raw, list):
        raise ValueError("expected a JSON list of events")
    events = _ff_rows_to_events(raw)
    if not events:
        raise ValueError("no usable events found in that JSON")
    events.sort(key=lambda e: e["time"])
    _CACHE.update({"events": events, "fetched_at": now, "next_try_at": None})
    STATUS.update({"source": "manual import", "ok": True, "stale": False, "last_success": now, "last_error": "", "event_count": len(events)})
    _PERSIST["last_sig"] = None
    _save_persisted(events, now)
    return len(events)


def status_summary():
    """JSON-safe snapshot of the calendar's health."""
    def iso(d): return d.isoformat() + "Z" if d else None
    return {
        "build": BUILD_ID,
        "source": STATUS["source"], "ok": STATUS["ok"], "stale": STATUS["stale"], "event_count": STATUS["event_count"],
        "last_attempt_utc": iso(STATUS["last_attempt"]), "last_success_utc": iso(STATUS["last_success"]),
        "last_error": STATUS["last_error"], "next_week_note": STATUS.get("next_week_note", ""),
        "jblanked_key_set": bool(JBLANKED_API_KEY), "news_source_setting": NEWS_SOURCE,
    }


def currencies_for_symbol(symbol):
    """Which currencies' news can move this symbol. Best-effort mapping,
    not exhaustive — commodities/indices/crypto react to USD macro data
    even though it isn't in their ticker."""
    currencies = set()
    for cur in MAJORS:
        if cur in symbol:
            currencies.add(cur)
    if symbol in ("XAUUSD", "XAGUSD", "XTIUSD", "XBRUSD", "US30", "NAS100", "SPX500"):
        currencies.add("USD")
    if symbol in ("GER40", "FRA40", "ESP35", "ITA40"):
        currencies.add("EUR")
    if symbol == "UK100":
        currencies.add("GBP")
    if symbol == "JPN225":
        currencies.add("JPY")
    if symbol == "AUS200":
        currencies.add("AUD")
    if symbol in CRYPTO_SYMBOLS:
        currencies.add("USD")
    return currencies


def upcoming_high_impact(hours_ahead=168, min_impact="High", lookback_minutes=0):
    """Events from `lookback_minutes` ago up to `hours_ahead` from now, at or
    above `min_impact`, soonest first. (Name kept for compatibility — pass
    min_impact="None" for everything.)"""
    events = fetch_calendar()
    now = datetime.utcnow()
    start = now - timedelta(minutes=lookback_minutes)
    cutoff = now + timedelta(hours=hours_ahead)
    threshold = IMPACT_ORDER.get(min_impact, 3)
    result = [e for e in events if start <= e["time"] <= cutoff and IMPACT_ORDER.get(e["impact"], 0) >= threshold]
    result.sort(key=lambda e: e["time"])
    return result


def events_on_sast_day(day, min_impact="High", not_before=None):
    """Events whose SAST (UTC+2) calendar date is `day` (a date)."""
    threshold = IMPACT_ORDER.get(min_impact, 3)
    out = [e for e in fetch_calendar()
           if (e["time"] + timedelta(hours=2)).date() == day and IMPACT_ORDER.get(e["impact"], 0) >= threshold
           and (not_before is None or e["time"] >= not_before)]
    out.sort(key=lambda e: e["time"])
    return out


def is_in_blackout(symbol, minutes_before=15, minutes_after=15, min_impact="High"):
    """Is `symbol` inside a real news blackout window RIGHT NOW, for any
    event whose currency affects it? Returns (bool, event_or_None)."""
    syms_currencies = currencies_for_symbol(symbol)
    if not syms_currencies:
        return False, None
    now = datetime.utcnow()
    threshold = IMPACT_ORDER.get(min_impact, 3)
    for e in fetch_calendar():
        if e["currency"] not in syms_currencies:
            continue
        if IMPACT_ORDER.get(e["impact"], 0) < threshold:
            continue
        if (e["time"] - timedelta(minutes=minutes_before)) <= now <= (e["time"] + timedelta(minutes=minutes_after)):
            return True, e
    return False, None


def minutes_until(event):
    return (event["time"] - datetime.utcnow()).total_seconds() / 60.0


def countdown_str(event):
    mins = minutes_until(event)
    if mins < 0:
        return "in progress" if mins > -60 else "past"
    days, rem = divmod(int(mins), 60 * 24)
    hours, minutes = divmod(rem, 60)
    if days > 0:
        return f"in {days}d {hours}h"
    if hours > 0:
        return f"in {hours}h {minutes}m"
    return f"in {minutes}m"


def cluster_events(events):
    """Group events released at the same moment for the same currency (e.g.
    CPI m/m, CPI y/y, Core CPI m/m, Core CPI y/y all at 12:30 UTC) — they move
    the market ONCE, so they get one alert, one lean and one scorecard entry."""
    groups = {}
    for e in events:
        groups.setdefault((e["currency"], e["time"]), []).append(e)
    clusters = [{"currency": c, "time": t, "events": evs} for (c, t), evs in groups.items()]
    clusters.sort(key=lambda c: (c["time"], c["currency"]))
    return clusters


# ================================================================ NEWS LEAN

FX_AND_METALS = ["EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD","EURJPY","GBPJPY","EURGBP","AUDJPY","CADJPY",
                 "CHFJPY","EURCHF","GBPCHF","EURAUD","GBPAUD","EURCAD","GBPCAD","EURNZD","GBPNZD","AUDNZD","AUDCAD","NZDCAD",
                 "AUDCHF","NZDJPY","XAUUSD","XAGUSD"]
SCORE_PRIORITY = ["XAUUSD","EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD","XAGUSD"]
FLAT_PCT = 0.02       # a move smaller than this (%) counts as "flat", not a hit or a miss
WHIPSAW_PCT = 0.10    # moved this far BOTH with and against the lean inside 15 min -> whipsaw
MIN_TRUSTED_SAMPLE = 20

# Releases where a higher number is bad for the currency.
_BEARISH_WHEN_HIGHER = ["unemployment rate", "unemployment claims", "jobless claims", "initial claims", "continuing claims",
                        "claimant count"]
# Releases where a higher number is good for the currency (inflation -> rate hikes; growth/jobs -> strength).
_BULLISH_WHEN_HIGHER = ["cpi", "ppi", "pce", "price index", "inflation", "import prices", "retail sales", "non-farm", "nonfarm",
                        "employment change", "adp", "hourly earnings", "wage", "gdp", "pmi", "ism", "industrial production",
                        "manufacturing production", "durable goods", "consumer confidence", "consumer sentiment", "jolts",
                        "job openings", "housing starts", "building permits", "building approvals", "trade balance",
                        "current account", "ifo", "zew", "tankan", "business confidence", "business climate", "philly fed",
                        "empire state", "capacity utilization"]
# No reliable forecast-vs-previous read: speeches, rate decisions (priced in), minutes, auctions, inventories...
_NO_LEAN = ["speaks", "speech", "testifies", "minutes", "press conference", "statement", "summit", "meeting", "holiday",
            "auction", "policy rate", "interest rate", "cash rate", "bank rate", "funds rate", "refinancing", "overnight rate",
            "rate decision", "inventories", "storage", "budget", "tic ", "securities", "bond"]

_GROUPS = [("CPI", ["cpi", "inflation", "price index", "import prices"]), ("PPI", ["ppi"]), ("PCE", ["pce"]),
           ("Retail Sales", ["retail sales"]),
           ("Jobs", ["non-farm", "nonfarm", "employment", "adp", "earnings", "wage", "unemployment", "jobless", "claims",
                     "claimant", "jolts", "job openings"]),
           ("GDP", ["gdp"]), ("PMI/ISM", ["pmi", "ism", "philly", "empire"]),
           ("Industry", ["industrial", "manufacturing production", "durable", "capacity"]),
           ("Housing", ["housing", "building"]), ("Trade", ["trade balance", "current account"]),
           ("Confidence", ["confidence", "sentiment", "ifo", "zew", "tankan", "business climate"])]


def classify_event(name):
    """+1: a HIGHER number than before is bullish for the currency; -1: bearish;
    0: no meaningful forecast-vs-previous read."""
    n = (name or "").lower()
    if any(k in n for k in _NO_LEAN):
        return 0
    if any(k in n for k in _BEARISH_WHEN_HIGHER):
        return -1
    if any(k in n for k in _BULLISH_WHEN_HIGHER):
        return 1
    return 0


def event_group(name):
    n = (name or "").lower()
    for label, keys in _GROUPS:
        if any(k in n for k in keys):
            return label
    return "Other"


def parse_number(s):
    """'3.6%' -> 3.6, '199K' -> 199000, '-21.9B' -> -2.19e10, '' -> None."""
    if s is None:
        return None
    t = str(s).strip().replace(",", "").replace("$", "").replace("€", "").replace("£", "").replace("%", "")
    t = t.split("|")[0].strip()
    if not t or t in ("-", "—"):
        return None
    mult = 1.0
    if t[-1] in "KMBTkmbt":
        mult = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}[t[-1].lower()]
        t = t[:-1]
    try:
        return float(t) * mult
    except ValueError:
        return None


def _symbols_for(currency, ccy_dir):
    """+1 = currency expected stronger -> BUY pairs where it's the base, SELL where it's the quote."""
    out = {}
    for s in FX_AND_METALS:
        base, quote = s[:3], s[3:]
        if base == currency:
            out[s] = "BUY" if ccy_dir > 0 else "SELL"
        elif quote == currency:
            out[s] = "SELL" if ccy_dir > 0 else "BUY"
    return out


def compute_cluster_lean(cluster):
    """Lean for one (currency, release-time) cluster, from High-impact members'
    forecast-vs-previous. Returns None if nothing qualifies; a dict with
    mixed=True and no symbols if the members disagree (tie)."""
    cur = cluster["currency"]
    if cur not in MAJORS:
        return None
    members = []
    for e in cluster["events"]:
        if e["impact"] != "High":
            continue
        d = classify_event(e["name"])
        if d == 0:
            continue
        f, p = parse_number(e.get("forecast")), parse_number(e.get("previous"))
        if f is None or p is None or f == p:
            continue
        members.append({"name": e["name"], "forecast": e.get("forecast"), "previous": e.get("previous"),
                        "ccy_dir": d * (1 if f > p else -1), "group": event_group(e["name"])})
    if not members:
        return None
    base = {"cluster_id": f"{cur}_{cluster['time'].strftime('%Y%m%d%H%M')}", "currency": cur,
            "event_time_utc": cluster["time"].isoformat(), "members": members, "total": len(members)}
    net = sum(m["ccy_dir"] for m in members)
    if net == 0:
        return {**base, "mixed": True, "symbols": {}, "agree": 0, "ccy_dir": 0, "view": "mixed", "group": members[0]["group"]}
    ccy_dir = 1 if net > 0 else -1
    winners = [m for m in members if m["ccy_dir"] == ccy_dir]
    groups = [m["group"] for m in winners]
    return {**base, "mixed": False, "ccy_dir": ccy_dir, "agree": len(winners),
            "view": f"{cur} stronger" if ccy_dir > 0 else f"{cur} weaker",
            "group": max(set(groups), key=groups.count), "symbols": _symbols_for(cur, ccy_dir)}


def compute_event_leans(events):
    """{(currency, time): lean} for every High cluster in `events` that has one."""
    out = {}
    for c in cluster_events([e for e in events if e["impact"] == "High"]):
        lean = compute_cluster_lean(c)
        if lean:
            out[(c["currency"], c["time"])] = lean
    return out


def pick_scoring_symbols(symbols, n=4):
    ordered = [s for s in SCORE_PRIORITY if s in symbols] + sorted(s for s in symbols if s not in SCORE_PRIORITY)
    return ordered[:n]


def record_lean_call(calls, lean, now):
    """Log a lean (once per release) so it can be scored later. Returns True if newly logged."""
    if not lean or lean.get("mixed") or not lean.get("symbols") or lean["cluster_id"] in calls:
        return False
    calls[lean["cluster_id"]] = {
        "cluster_id": lean["cluster_id"], "currency": lean["currency"], "event_time_utc": lean["event_time_utc"],
        "group": lean["group"], "view": lean["view"], "ccy_dir": lean["ccy_dir"], "members": lean["members"],
        "symbols": lean["symbols"], "scored_symbols": pick_scoring_symbols(lean["symbols"]),
        "created_at": now.isoformat(), "status": "pending", "attempts": 0,
    }
    return True


# ---------------------------------------------------------------- scoring

def _parse_candle_time(s):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(s), fmt)
        except ValueError:
            continue
    return None


def _score_symbol(candles, T, direction):
    """1-minute candles (oldest first, UTC bar-open times) -> how the lean fared."""
    bars = sorted(((t, c) for c in candles if (t := _parse_candle_time(c.get("time"))) is not None), key=lambda x: x[0])
    if not bars:
        return None

    def close_at(minutes_after):
        # price at T+minutes_after = close of the 1-min bar that opened one minute earlier
        target = T + timedelta(minutes=minutes_after - 1)
        best = None
        for t, c in bars:
            if t <= target:
                best = (t, c)
            else:
                break
        if best and (target - best[0]).total_seconds() <= 3 * 60:
            return best[1]["close"]
        return None

    p0 = close_at(0)
    if not p0:
        return None
    sign = 1 if direction == "BUY" else -1
    res = {"dir": direction, "p0": p0}
    for h in (5, 15, 60):
        ph = close_at(h)
        if ph is None:
            res[f"move{h}"] = res[f"res{h}"] = None
            continue
        mv = (ph - p0) / p0 * 100
        res[f"move{h}"] = round(mv, 3)
        res[f"res{h}"] = "flat" if abs(mv) < FLAT_PCT else ("hit" if mv * sign > 0 else "miss")
    window = [c for t, c in bars if T <= t < T + timedelta(minutes=15)]
    if window:
        up = (max(c["high"] for c in window) - p0) / p0 * 100
        down = (p0 - min(c["low"] for c in window)) / p0 * 100
        res["mfe15"] = round(up if sign > 0 else down, 3)
        res["mae15"] = round(down if sign > 0 else up, 3)
        res["whipsaw"] = res["mfe15"] >= WHIPSAW_PCT and res["mae15"] >= WHIPSAW_PCT
    return res


def score_call(call, candles_by_symbol):
    """Outcome for a logged lean: per-symbol results + which symbol is the 'primary' one."""
    T = datetime.fromisoformat(call["event_time_utc"])
    out = {}
    for sym in call["scored_symbols"]:
        candles = candles_by_symbol.get(sym)
        if candles:
            r = _score_symbol(candles, T, call["symbols"][sym])
            if r:
                out[sym] = r
    if not out:
        return None
    primary = next(s for s in call["scored_symbols"] if s in out)
    return {"primary": primary, "symbols": out}


def _tally(results):
    h, m, f = results.count("hit"), results.count("miss"), results.count("flat")
    d = h + m
    return {"hits": h, "misses": m, "flats": f, "decided": d, "n": len(results), "hit_rate": round(100.0 * h / d, 1) if d else None}


def aggregate(calls):
    """Track record from logged calls. Headline numbers use ONE result per
    release (the primary symbol, e.g. XAUUSD) so correlated pairs aren't
    double-counted."""
    scored = [c for c in calls.values() if c.get("status") == "scored" and c.get("outcome")]
    prim = lambda c, key: c["outcome"]["symbols"][c["outcome"]["primary"]].get(key)
    out = {
        "scored": len(scored), "pending": sum(1 for c in calls.values() if c.get("status") == "pending"),
        "unscored": sum(1 for c in calls.values() if c.get("status") == "no_data"),
        "overall": _tally([prim(c, "res15") for c in scored if prim(c, "res15")]),
        "by_horizon": {f"{h}min": _tally([prim(c, f"res{h}") for c in scored if prim(c, f"res{h}")]) for h in (5, 15, 60)},
        "by_group": {}, "by_currency": {}, "by_symbol": {}, "recent": [],
    }
    for key, field in (("by_group", "group"), ("by_currency", "currency")):
        buckets = {}
        for c in scored:
            r = prim(c, "res15")
            if r:
                buckets.setdefault(c.get(field, "?"), []).append(r)
        out[key] = {k: _tally(v) for k, v in sorted(buckets.items())}
    sym_buckets = {}
    for c in scored:
        for sym, r in c["outcome"]["symbols"].items():
            if r.get("res15"):
                sym_buckets.setdefault(sym, []).append(r["res15"])
    out["by_symbol"] = {k: _tally(v) for k, v in sorted(sym_buckets.items())}
    for c in sorted(scored, key=lambda c: c["event_time_utc"], reverse=True)[:10]:
        p = c["outcome"]["primary"]; r = c["outcome"]["symbols"][p]
        out["recent"].append({"time": c["event_time_utc"], "currency": c["currency"], "group": c.get("group"), "view": c.get("view"),
                              "symbol": p, "dir": r["dir"], "move15": r.get("move15"), "res15": r.get("res15"), "whipsaw": r.get("whipsaw")})
    return out


def track_record_text(agg, group=None):
    o = agg["overall"]
    if not o["decided"]:
        return "no track record yet — this is still an experiment"
    parts = []
    g = agg["by_group"].get(group) if group else None
    if g and g["decided"]:
        parts.append(f"{group} {g['hits']}/{g['decided']} ({g['hit_rate']:.0f}%)")
    parts.append(f"all releases {o['hits']}/{o['decided']} ({o['hit_rate']:.0f}%)")
    text = "Track record (price +15min after release): " + " · ".join(parts)
    if o["decided"] < MIN_TRUSTED_SAMPLE:
        text += f" — only {o['decided']} releases scored, too few to trust"
    return text


def lean_message(lean, agg=None, watchlist=None):
    """Telegram text for a lean. Returns '' if nothing actionable (e.g. none of the
    lean's symbols are on the user's watchlist)."""
    if not lean or lean.get("mixed") or not lean.get("symbols"):
        return ""
    syms = lean["symbols"]
    if watchlist is not None:
        syms = {s: d for s, d in syms.items() if s in watchlist}
    if not syms:
        return ""
    order = {s: i for i, s in enumerate(SCORE_PRIORITY)}
    key = lambda s: (order.get(s, 99), s)
    sells = sorted((s for s, d in syms.items() if d == "SELL"), key=key)
    buys = sorted((s for s, d in syms.items() if d == "BUY"), key=key)
    ex = lean["members"][0]
    lines = [f"📊 NEWS LEAN — a guess from forecast vs previous, not a signal",
             f"{lean['agree']} of {lean['total']} {lean['currency']} releases point to {lean['view']} (e.g. {ex['name']}: forecast {ex['forecast']} vs previous {ex['previous']})."]
    if sells: lines.append("SELL: " + ", ".join(sells))
    if buys: lines.append("BUY: " + ", ".join(buys))
    if agg is not None: lines.append(track_record_text(agg, lean.get("group")))
    lines.append("If the actual number misses forecast this likely flips — the first minutes often whipsaw. Wait for the print.")
    return "\n".join(lines)
