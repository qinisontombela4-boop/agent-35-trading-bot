"""
Real economic calendar, via JBlanked's News API (https://www.jblanked.com/news/api/docs/calendar/).
Free tier, API key required (sign up at https://www.jblanked.com/api/key/).

Set JBLANKED_API_KEY as an env var. Without it, this module degrades to
"no events known" rather than crashing — is_in_blackout() just always
returns False, so nothing blocks/alerts until the key is configured.

NOTE ON TIMEZONE: the upstream feed's "Date" field format is
"YYYY.MM.DD HH:MM:SS" with no explicit timezone marker. This module treats
it as UTC. Verify this against a known upcoming event (e.g. the next NFP
release, which is always 12:30 UTC / 8:30 AM ET) once you have a live API
key — if event times look off by a fixed number of hours, that's a
timezone offset to correct here, not a bug in the blackout logic itself.
"""

import os, sys, requests
from datetime import datetime, timedelta

JBLANKED_API_KEY = os.getenv("JBLANKED_API_KEY", "")
BASE_URL = "https://www.jblanked.com/news/api"

if not JBLANKED_API_KEY:
    print("[NEWS CALENDAR] JBLANKED_API_KEY not set — real calendar disabled, "
          "no news blackout or alerts will fire until it's configured.", file=sys.stderr)

_CACHE = {"events": [], "fetched_at": None}
CACHE_TTL_MINUTES = 15  # don't hammer the API; a 15-min-stale calendar is fine

IMPACT_ORDER = {"None": 0, "Low": 1, "Medium": 2, "High": 3}

CRYPTO_SYMBOLS = ["BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD","ADAUSD","DOGEUSD","DOTUSD","AVAXUSD","LINKUSD","MATICUSD","LTCUSD"]


def _headers():
    return {"Content-Type": "application/json", "Authorization": f"Api-Key {JBLANKED_API_KEY}"}


def _parse_dt(date_str):
    try:
        return datetime.strptime(date_str, "%Y.%m.%d %H:%M:%S")
    except Exception:
        return None


def fetch_calendar(force=False):
    """This week's Forex Factory calendar, normalized and cached."""
    if not JBLANKED_API_KEY:
        return []
    now = datetime.utcnow()
    if not force and _CACHE["fetched_at"] and (now - _CACHE["fetched_at"]).total_seconds() < CACHE_TTL_MINUTES * 60:
        return _CACHE["events"]
    try:
        r = requests.get(f"{BASE_URL}/forex-factory/calendar/week/", headers=_headers(), timeout=12)
        if r.status_code != 200:
            print(f"[NEWS CALENDAR] fetch failed: HTTP {r.status_code}", file=sys.stderr)
            return _CACHE["events"]  # serve stale cache rather than nothing
        raw = r.json()
        events = []
        for e in raw:
            dt = _parse_dt(e.get("Date", ""))
            if not dt:
                continue
            events.append({
                "id": f"{e.get('Currency','')}_{e.get('Name','')}_{e.get('Date','')}",
                "name": e.get("Name", "Unnamed event"),
                "currency": e.get("Currency", ""),
                "impact": e.get("Impact", "None"),
                "time": dt,
                "actual": e.get("Actual"),
                "forecast": e.get("Forecast"),
                "previous": e.get("Previous"),
            })
        _CACHE["events"] = events
        _CACHE["fetched_at"] = now
        return events
    except Exception as ex:
        print(f"[NEWS CALENDAR] fetch error: {ex}", file=sys.stderr)
        return _CACHE["events"]


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


def upcoming_high_impact(hours_ahead=72, min_impact="High"):
    events = fetch_calendar()
    now = datetime.utcnow()
    cutoff = now + timedelta(hours=hours_ahead)
    threshold = IMPACT_ORDER.get(min_impact, 3)
    result = [e for e in events if now <= e["time"] <= cutoff and IMPACT_ORDER.get(e["impact"], 0) >= threshold]
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
