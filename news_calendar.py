"""
Economic calendar for Agent 35.

SOURCES (tried in this order, first one that returns events wins):
  1. Forex Factory's public weekly JSON feed (nfs.faireconomy.media) — FREE,
     NO API KEY. Every event carries an explicit UTC offset in its timestamp,
     so there is no timezone guessing. This is the default.
  2. JBlanked's News API — only used if JBLANKED_API_KEY is set. It is the
     fallback when the free feed is down, OR the primary if you set
     NEWS_SOURCE=jblanked (it is the only source that publishes "Actual"
     values, which the /news page uses for its "printed above/below forecast"
     note).

If both fail, the calendar degrades to "no events known" (so nothing blocks
or alerts) AND records exactly why in STATUS, which the /news page and the
/news-status endpoint show — it never fails silently any more.

NOTE ON JBLANKED TIMEZONE: its "Date" field ("YYYY.MM.DD HH:MM:SS") has no
timezone marker and its docs don't state one. Compare one known event
(e.g. US NFP = 12:30 UTC in summer / 13:30 UTC in winter) against /news-status
and, if it is off by a fixed number of hours, set JBLANKED_UTC_OFFSET_HOURS to
the correction (e.g. -2 if the feed runs 2 hours ahead of UTC). Not needed for
the free Forex Factory feed.
"""

import os, sys, requests
from datetime import datetime, timedelta, timezone

JBLANKED_API_KEY = os.getenv("JBLANKED_API_KEY", "")
JBLANKED_BASE_URL = "https://www.jblanked.com/news/api"
JBLANKED_UTC_OFFSET_HOURS = float(os.getenv("JBLANKED_UTC_OFFSET_HOURS", "0") or 0)
FF_FEED_URL = os.getenv("FF_FEED_URL", "https://nfs.faireconomy.media/ff_calendar_thisweek.json")
NEWS_SOURCE = os.getenv("NEWS_SOURCE", "auto").strip().lower()  # "auto" (free feed first) or "jblanked"

CACHE_TTL_MINUTES = 15       # don't hammer the feeds; a 15-min-stale calendar is fine
FAILURE_BACKOFF_MINUTES = 5  # after a failed fetch, wait this long before trying again
HTTP_TIMEOUT = 12
USER_AGENT = "Mozilla/5.0 (compatible; Agent35/1.0; +https://agent-35-trading-bot.onrender.com)"

_CACHE = {"events": [], "fetched_at": None, "next_try_at": None}

# What happened on the most recent fetch attempt — surfaced on /news and /news-status.
STATUS = {
    "source": None,          # which feed the current events came from
    "ok": False,
    "last_attempt": None,    # UTC datetime
    "last_success": None,    # UTC datetime
    "last_error": "",        # human-readable reason if the last attempt failed
    "event_count": 0,
}

IMPACT_ORDER = {"None": 0, "Holiday": 0, "Low": 1, "Medium": 2, "High": 3}

CRYPTO_SYMBOLS = ["BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD","ADAUSD","DOGEUSD","DOTUSD","AVAXUSD","LINKUSD","MATICUSD","LTCUSD"]


def _normalize_impact(value):
    v = str(value or "").strip().lower()
    return {"high": "High", "medium": "Medium", "low": "Low", "holiday": "Holiday"}.get(v, "None")


# ---------------------------------------------------------------- sources

def _fetch_forex_factory_feed():
    """Free, keyless. Returns a list of normalized events (UTC, naive datetimes)."""
    r = requests.get(FF_FEED_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} from Forex Factory feed" + (" (rate limited — will retry later)" if r.status_code == 429 else ""))
    raw = r.json()
    if not isinstance(raw, list):
        raise RuntimeError(f"unexpected response shape from Forex Factory feed: {str(raw)[:120]}")
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


# ---------------------------------------------------------------- public API

def fetch_calendar(force=False):
    """This week's calendar, normalized and cached. Never raises: on total
    failure it serves the last good cache (possibly empty) and records the
    reason in STATUS."""
    now = datetime.utcnow()
    if not force:
        if _CACHE["fetched_at"] and (now - _CACHE["fetched_at"]).total_seconds() < CACHE_TTL_MINUTES * 60:
            return _CACHE["events"]
        if _CACHE["next_try_at"] and now < _CACHE["next_try_at"]:
            return _CACHE["events"]  # backing off after a recent failure

    STATUS["last_attempt"] = now
    errors = []
    for name, fetch in _source_order():
        try:
            events = fetch()
            if not events:
                raise RuntimeError("feed responded but contained zero usable events")
            events.sort(key=lambda e: e["time"])
            _CACHE.update({"events": events, "fetched_at": now, "next_try_at": None})
            STATUS.update({"source": name, "ok": True, "last_success": now, "last_error": "", "event_count": len(events)})
            return events
        except Exception as ex:
            errors.append(f"{name}: {ex}")
            print(f"[NEWS CALENDAR] {name} failed: {ex}", file=sys.stderr)

    _CACHE["next_try_at"] = now + timedelta(minutes=FAILURE_BACKOFF_MINUTES)
    STATUS.update({"ok": False, "last_error": " | ".join(errors), "event_count": len(_CACHE["events"])})
    return _CACHE["events"]  # stale beats nothing


def status_summary():
    """JSON-safe snapshot of the calendar's health."""
    def iso(d): return d.isoformat() + "Z" if d else None
    return {
        "source": STATUS["source"], "ok": STATUS["ok"], "event_count": STATUS["event_count"],
        "last_attempt_utc": iso(STATUS["last_attempt"]), "last_success_utc": iso(STATUS["last_success"]),
        "last_error": STATUS["last_error"],
        "jblanked_key_set": bool(JBLANKED_API_KEY), "news_source_setting": NEWS_SOURCE,
    }


def currencies_for_symbol(symbol):
    """Which currencies' news can move this symbol. Best-effort mapping,
    not exhaustive — commodities/indices/crypto react to USD macro data
    even though it isn't in their ticker."""
    currencies = set()
    for cur in ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]:
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


def upcoming_high_impact(hours_ahead=72, min_impact="High", lookback_minutes=0):
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
