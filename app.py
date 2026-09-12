from flask import Flask, request, jsonify, session, redirect, Response
import os, json, hashlib, requests, random, string, csv, io, sys, secrets, smtplib
from email.mime.text import MIMEText
from urllib.parse import quote
from dotenv import load_dotenv
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()
app = Flask(__name__)

# --- FLASK_SECRET is required, no fallback. A predictable/hardcoded session
# secret lets anyone forge a login session cookie for any user, including admin.
if not os.getenv("FLASK_SECRET"):
    raise RuntimeError(
        "FLASK_SECRET environment variable is not set. "
        "Set it to a long random string before starting the app."
    )
app.secret_key = os.environ["FLASK_SECRET"]

# --- CREATOR_SECRET replaces the old hardcoded "ADMIN35" bypass string.
# If it's not set, the query-param admin bypass is simply disabled — the
# admin can still always get in via normal login as admin@agent35.com.
CREATOR_SECRET = os.getenv("CREATOR_SECRET", "")
if not CREATOR_SECRET:
    print("[WARN] CREATOR_SECRET is not set. The /creator?secret=... bypass "
          "is disabled until you set it (admin login still works normally).",
          file=sys.stderr)

import trading_engine as eng

# --- PERSISTENCE NOTE (read this if data keeps resetting on deploy):
# BASE_DIR only survives redeploys if "/data" is an actually-mounted
# persistent volume on your hosting platform (e.g. a Render Disk attached
# to this service). This is an infrastructure setting, not something fixable
# in code — if you haven't attached a persistent disk at /data, every deploy
# WILL wipe local files regardless of anything below. The backup/restore
# system here is a safety net for that case, not a replacement for it.
BASE_DIR = "/data" if os.path.exists("/data") else "."
print(f"[STARTUP] BASE_DIR={BASE_DIR} "
      f"({'persistent disk detected' if BASE_DIR == '/data' else 'WARNING: no persistent disk detected at /data — data will NOT survive redeploys unless BASE_DIR is backed by a mounted volume'})",
      file=sys.stderr)

BACKUP_URL = os.getenv("DATA_BACKUP_URL", "")
if not BACKUP_URL:
    print("[WARN] DATA_BACKUP_URL is not set — no off-box backup safety net is active.", file=sys.stderr)

MAX_TRACKED = 6

AUTH_FILE = os.path.join(BASE_DIR, "auth_users.json")
USERS_FILE = os.path.join(BASE_DIR, "users_data.json")
REFERRAL_FILE = os.path.join(BASE_DIR, "referrals.json")
REF_CODE_FILE = os.path.join(BASE_DIR, "ref_codes.json")
JOURNAL_FILE = os.path.join(BASE_DIR, "journal.json")
TRACK_FILE = os.path.join(BASE_DIR, "tracked_trades.json")
SYSTEM_FILE = os.path.join(BASE_DIR, "system_status.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "user_settings.json")
TG_FILE = os.path.join(BASE_DIR, "telegram_users.json")
TEMP_CHAT_FILE = os.path.join(BASE_DIR, "temp_chats.json")

DATA_FILES = ["auth_users.json","users_data.json","referrals.json","ref_codes.json","journal.json",
              "tracked_trades.json","system_status.json","user_settings.json","telegram_users.json","temp_chats.json"]

ALL_SYMBOLS = ["EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD","EURJPY","GBPJPY","EURGBP","AUDJPY","CADJPY","CHFJPY","EURCHF","GBPCHF","EURAUD","GBPAUD","EURCAD","GBPCAD","EURNZD","GBPNZD","AUDNZD","AUDCAD","NZDCAD","AUDCHF","NZDJPY","XAUUSD","XAGUSD","XTIUSD","XBRUSD","US30","NAS100","SPX500","GER40","UK100","FRA40","ESP35","ITA40","JPN225","AUS200","BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD","ADAUSD","DOGEUSD","DOTUSD","AVAXUSD","LINKUSD","MATICUSD","LTCUSD"]
CURRENCY_MAP = {"ZAR":{"symbol":"R","name":"Rand"},"USD":{"symbol":"$","name":"Dollar"},"EUR":{"symbol":"€","name":"Euro"},"GBP":{"symbol":"£","name":"Pound"}}

# ================= STORAGE (JSON files, kept as-is by request) =================

def load_json(p, dt=dict):
    if not os.path.exists(p): return {} if dt==dict else []
    try:
        with open(p,"r") as f: return json.load(f)
    except: return {} if dt==dict else []

def _backup_sync():
    """Synchronous (blocking) backup so it actually completes before the
    process can be killed for a redeploy. Failures are logged, not swallowed."""
    if not BACKUP_URL: return
    try:
        all_data = {}
        for fname in DATA_FILES:
            fp = os.path.join(BASE_DIR, fname)
            if os.path.exists(fp):
                try:
                    with open(fp,"r") as ff: all_data[fname] = json.load(ff)
                except Exception as e:
                    print(f"[BACKUP] Skipped {fname}, unreadable: {e}", file=sys.stderr)
        r = requests.post(BACKUP_URL, json=all_data, timeout=8)
        if r.status_code != 200:
            print(f"[BACKUP FAILED] status={r.status_code} body={r.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"[BACKUP FAILED] {e}", file=sys.stderr)

def save_json(p, data):
    os.makedirs(os.path.dirname(p) if os.path.dirname(p) else ".", exist_ok=True)
    with open(p,"w") as f: json.dump(data,f,indent=2)
    _backup_sync()

def remote_restore():
    if not BACKUP_URL: return False
    try:
        if os.path.exists(AUTH_FILE) and os.path.getsize(AUTH_FILE) > 50:
            d = load_json(AUTH_FILE, dict)
            if len(d) > 1: return False
        r = requests.get(BACKUP_URL, timeout=15)
        if r.status_code!=200: return False
        remote = r.json()
        if not remote or not isinstance(remote, dict): return False
        for fname, content in remote.items():
            if not fname.endswith(".json"): continue
            dst = os.path.join(BASE_DIR, fname)
            try:
                with open(dst,"w") as f: json.dump(content, f, indent=2)
            except: pass
        print("[STARTUP] Restored data from remote backup.", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[STARTUP] Remote restore failed: {e}", file=sys.stderr)
        return False

# ================= PASSWORD HASHING (salted, with legacy migration) =================

def hash_pwd_legacy(p): return hashlib.sha256(p.encode()).hexdigest()
def hash_pwd(p): return generate_password_hash(p)

def verify_and_maybe_upgrade_password(auth, email, plain_password):
    """Checks a password against the stored hash. Supports old unsalted
    SHA-256 hashes from before this fix and transparently upgrades them to
    a salted Werkzeug hash on successful login, so no one gets locked out."""
    user = auth.get(email)
    if not user: return False
    stored = user.get("password", "")
    if stored.startswith(("pbkdf2:", "scrypt:", "argon2:")):
        return check_password_hash(stored, plain_password)
    if stored and stored == hash_pwd_legacy(plain_password):
        user["password"] = hash_pwd(plain_password)
        save_json(AUTH_FILE, auth)
        return True
    return False

def ensure_files():
    remote_restore()
    if not os.path.exists(AUTH_FILE):
        save_json(AUTH_FILE, {"admin@agent35.com":{"email":"admin@agent35.com","name":"Master Creator","password":hash_pwd("Agent35!"),"account_size":142.0,"total_profit":-1.42,"plan_status":"ACTIVE lifetime - CREATOR","referred_by":"","expires":(datetime.now()+timedelta(days=36500)).isoformat(),"created":datetime.now().isoformat(),"reset_token":None,"reset_token_expires":None,"ref_code":"ADMIN35"}})
    for fp in [USERS_FILE, REFERRAL_FILE, REF_CODE_FILE, SETTINGS_FILE, TG_FILE, TEMP_CHAT_FILE]:
        if not os.path.exists(fp): save_json(fp, {})
    if not os.path.exists(JOURNAL_FILE): save_json(JOURNAL_FILE, [])
    if not os.path.exists(TRACK_FILE): save_json(TRACK_FILE, {})
    if not os.path.exists(SYSTEM_FILE): save_json(SYSTEM_FILE, {"last_scan":None,"total_scans":0,"total_signals":0,"system_up_since":datetime.now().isoformat()})
ensure_files()

def get_user_settings(email):
    settings = load_json(SETTINGS_FILE, dict)
    default = {"account_size":142.0,"lot_size":0.01,"leverage":"1:500","sessions":["London","New York"],"symbols":ALL_SYMBOLS[:10],"risk_percent":1.0,"rr_ratio":2.5,"trade_news":True,"spread_forex":0.7,"spread_gold":0.35,"spread_indices":2.0,"spread_crypto":10.0,"currency":"ZAR","trading_mode":"regular"}
    s = settings.get(email, default)
    for k,v in default.items():
        if k not in s: s[k]=v
    if "trading_method" in s: s.pop("trading_method",None)
    return s

def get_currency_symbol(code): return CURRENCY_MAP.get(code, CURRENCY_MAP["ZAR"])["symbol"]
def save_user_settings(email, new_settings):
    s = load_json(SETTINGS_FILE, dict); s[email] = new_settings; save_json(SETTINGS_FILE, s)

def generate_ref_code(email):
    code_file = load_json(REF_CODE_FILE, dict)
    if email in code_file: return code_file[email]
    base = "".join([c for c in email.upper().split('@')[0] if c.isalnum()])[:5]
    if len(base)<3: base="A35"+base
    code = f"{base}{random.randint(10,99)}"
    while code in code_file: code = f"{base}{random.randint(10,99)}"
    code_file[email]=code; code_file[code]=email; save_json(REF_CODE_FILE, code_file); return code

def get_ref_count_and_auto_upgrade(referrer_email):
    auth = load_json(AUTH_FILE); ref_codes = load_json(REF_CODE_FILE, dict)
    referrer_code = ref_codes.get(referrer_email,"")
    if not referrer_code: return 0
    count=0
    for e,info in auth.items():
        if info.get("referred_by","").upper()==referrer_code.upper() and "ACTIVE" in info.get("plan_status",""): count+=1
    if count>=10 and referrer_email in auth and "CREATOR" not in auth[referrer_email].get("plan_status",""):
        if "lifetime" not in auth[referrer_email].get("plan_status","").lower():
            auth[referrer_email]["plan_status"]="ACTIVE lifetime - FREE 10 Referrals"; auth[referrer_email]["expires"]=(datetime.now()+timedelta(days=36500)).isoformat(); save_json(AUTH_FILE, auth)
    ref_data=load_json(REFERRAL_FILE, dict)
    ref_data[referrer_email]={"code":referrer_code,"count":count,"paid_count":count,"free_eligible":count>=10,"updated":datetime.now().isoformat()}
    save_json(REFERRAL_FILE, ref_data); return count

def calculate_pnl_stats(journal):
    now=datetime.now(); today_str=now.strftime("%Y-%m-%d"); week_start=(now - timedelta(days=now.weekday())).strftime("%Y-%m-%d"); month_str=now.strftime("%Y-%m"); year_str=now.strftime("%Y")
    stats={"total_trades":0,"wins":0,"losses":0,"be":0,"win_rate":0,"daily":0,"weekly":0,"monthly":0,"yearly":0,"total_pnl":0}
    for j in journal:
        result=j.get("result",""); pnl=j.get("pnl",0); date=j.get("date",today_str)
        try:
            if "WIN" in result.upper(): stats["wins"]+=1; stats["total_trades"]+=1
            elif "LOSS" in result.upper(): stats["losses"]+=1; stats["total_trades"]+=1
            elif "BE" in result.upper(): stats["be"]+=1; stats["total_trades"]+=1
        except: pass
        try:
            stats["total_pnl"]+=float(pnl)
            if date==today_str: stats["daily"]+=float(pnl)
            if date>=week_start: stats["weekly"]+=float(pnl)
            if date.startswith(month_str): stats["monthly"]+=float(pnl)
            if date.startswith(year_str): stats["yearly"]+=float(pnl)
        except: pass
    if stats["total_trades"]>0: stats["win_rate"]=round((stats["wins"]/stats["total_trades"])*100,1)
    return stats

def calculate_dynamic_sl_tp(symbol, entry, bias, account_size, lot_size, leverage, risk_percent, rr_ratio, spread_forex=0.7, spread_gold=0.35, spread_indices=2.0, spread_crypto=10.0):
    entry=float(entry); is_sell="BEARISH" in bias.upper() or "SELL" in bias.upper()
    risk_amount=float(account_size)*(float(risk_percent)/100.0); lot_size=float(lot_size) if float(lot_size)>0 else 0.01; rr_ratio=float(rr_ratio) if float(rr_ratio)>0 else 2.5
    if symbol in ["XAUUSD","XAGUSD"]:
        spread=float(spread_gold); sl_dollar=risk_amount/(lot_size*100) if lot_size>0 else 5.0; sl_dollar=max(2.0,min(sl_dollar,15.0)); sl_dollar+=spread; tp_dollar=sl_dollar*rr_ratio - spread
        sl=entry+sl_dollar if is_sell else entry-sl_dollar; tp=entry-tp_dollar if is_sell else entry+tp_dollar
        return round(sl,2),round(tp,2),round(sl_dollar,2),round(tp_dollar,2),risk_amount
    elif symbol in ["XTIUSD","XBRUSD"]:
        spread=float(spread_gold); sl_dollar=risk_amount/(lot_size*50) if lot_size>0 else 0.5; sl_dollar=max(0.3,min(sl_dollar,2.0)); sl_dollar+=spread; tp_dollar=sl_dollar*rr_ratio - spread
        sl=entry+sl_dollar if is_sell else entry-sl_dollar; tp=entry-tp_dollar if is_sell else entry+tp_dollar
        return round(sl,2),round(tp,2),round(sl_dollar,2),round(tp_dollar,2),risk_amount
    elif symbol in ["US30","NAS100","SPX500","GER40","UK100","FRA40","ESP35","ITA40","JPN225","AUS200"]:
        spread=float(spread_indices); sl_points=(risk_amount/(lot_size*10)) if lot_size>0 else 80; sl_points=max(30,min(sl_points,250)); sl_points+=spread; tp_points=sl_points*rr_ratio - spread
        sl=entry+sl_points if is_sell else entry-sl_points; tp=entry-tp_points if is_sell else entry+tp_points
        return round(sl,2),round(tp,2),round(sl_points,1),round(tp_points,1),risk_amount
    else:
        if any(x in symbol for x in ["BTC","ETH","SOL","BNB","XRP","ADA","DOGE","DOT","AVAX","LINK","MATIC","LTC"]):
            spread=float(spread_crypto)
            if "BTC" in symbol: sl_d=max(100,min(risk_amount/(lot_size*10) if lot_size>0 else 400,1200))
            else: sl_d=max(5,min(risk_amount/(lot_size*10) if lot_size>0 else 40,150))
            sl_d+=spread; tp_d=sl_d*rr_ratio - spread; sl=entry+sl_d if is_sell else entry-sl_d; tp=entry-tp_d if is_sell else entry+tp_d
            return round(sl,2),round(tp,2),round(sl_d,1),round(tp_d,1),risk_amount
        else:
            spread=float(spread_forex); pip_value=lot_size*10; sl_pips=risk_amount/pip_value if pip_value!=0 else 10; sl_pips=max(5,min(sl_pips,50)); sl_pips+=spread; tp_pips=sl_pips*rr_ratio - spread
            if "JPY" in symbol: sl_dist=sl_pips*0.01; tp_dist=tp_pips*0.01
            else: sl_dist=sl_pips*0.0001; tp_dist=tp_pips*0.0001
            sl=entry+sl_dist if is_sell else entry-sl_dist; tp=entry-tp_dist if is_sell else entry+tp_dist
            if entry<20: return round(sl,5),round(tp,5),round(sl_pips,1),round(tp_pips,1),risk_amount
            else: return round(sl,2),round(tp,2),round(sl_pips,1),round(tp_pips,1),risk_amount

def send_telegram_pro(symbol, score, bias, entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot_size, leverage, account_size, confluence_text, currency_symbol="R", mode_name=""):
    entry_f=float(entry)
    if entry_f==0: return {"error":"No price"}
    signal_type="BUY" if "BULLISH" in bias.upper() else "SELL"
    if entry_f<20: entry_fmt=f"{entry_f:.5f}"; sl_fmt=f"{float(sl):.5f}"; tp_fmt=f"{float(tp):.5f}"
    else: entry_fmt=f"{entry_f:.2f}"; sl_fmt=f"{float(sl):.2f}"; tp_fmt=f"{float(tp):.2f}"
    bot=os.getenv("TELEGRAM_BOT_TOKEN"); main_chat=os.getenv("TELEGRAM_CHAT_ID")
    tg_users=load_json(TG_FILE, dict); all_chats=[]
    if main_chat: all_chats.append(str(main_chat))
    for data in tg_users.values():
        cid=str(data.get("chat_id",""))
        if cid and cid not in all_chats: all_chats.append(cid)
    if not bot or not all_chats: return {"error":"no bot/chats"}
    sast_now=(datetime.utcnow()+timedelta(hours=2)).strftime("%H:%M SAST")
    mode_emoji = "⚡" if mode_name=="scalp" else "🎯"
    strength = "🔥 A+" if score>=8 else "✅ Strong" if score>=7 else "👍 Good" if score>=6 else "⚡ Takeable"
    text=f"{mode_emoji} {symbol} {signal_type} | {score}/10 {strength} | {mode_name.upper()}\n\n📊 {currency_symbol}{account_size} Lot {lot_size} Lev {leverage}\n💰 Entry: {entry_fmt}\n🛑 SL: {sl_fmt} ({sl_dist})\n🎯 TP: {tp_fmt} ({tp_dist})\n📊 RR 1:{rr} | Risk {currency_symbol}{risk_amt:.2f} ({risk_percent}%)\n\n🔍 {confluence_text}\n\n⏰ {sast_now}"
    keyboard={"inline_keyboard": [[{"text":"✅ TOOK ENTRY","callback_data":f"TOOK_{symbol}_{entry_fmt}"},{"text":"❌ SKIP","callback_data":f"SKIP_{symbol}"}],[{"text":"📊 Journal","url":"https://agent-35-trading-bot.onrender.com/journal"}]]}
    results=[]
    for chat_id in all_chats:
        try: r=requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":text,"reply_markup":keyboard}, timeout=10); results.append(r.json())
        except Exception as e: results.append({"error":str(e)})
    return results

def get_active_sessions():
    utc_hour = datetime.utcnow().hour
    sessions = []
    if 0 <= utc_hour < 9: sessions.append("Asia")
    if 8 <= utc_hour < 17: sessions.append("London")
    if 13 <= utc_hour < 22: sessions.append("New York")
    if not sessions: sessions=["Closed"]
    return sessions

# ================= EMAIL (forgot password) =================

def send_reset_email(to_email, reset_link):
    """Sends via SMTP using env vars. If SMTP isn't configured, returns
    False so the caller can fall back to showing the link on-screen."""
    host = os.getenv("SMTP_HOST"); port = os.getenv("SMTP_PORT")
    user = os.getenv("SMTP_USER"); pwd = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM", user)
    if not (host and port and user and pwd):
        return False, "SMTP not configured"
    try:
        msg = MIMEText(
            f"Reset your AGENT 35 PRO password:\n\n{reset_link}\n\n"
            f"This link expires in 1 hour. If you didn't request this, you can ignore this email."
        )
        msg["Subject"] = "AGENT 35 PRO - Password Reset"
        msg["From"] = sender
        msg["To"] = to_email
        with smtplib.SMTP(host, int(port), timeout=10) as server:
            server.starttls()
            server.login(user, pwd)
            server.sendmail(sender, [to_email], msg.as_string())
        return True, ""
    except Exception as e:
        return False, str(e)

# ================= ANALYSIS CACHE (reduces API rate-limit errors during scans) =================

_ANALYSIS_CACHE = {}
_ANALYSIS_TTL_SECONDS = 240  # ~ one 5-minute candle

def cached_analysis(symbol, user_settings):
    mode = user_settings.get("trading_mode", "regular")
    key = (symbol, mode)
    now = datetime.now()
    hit = _ANALYSIS_CACHE.get(key)
    if hit and (now - hit[0]).total_seconds() < _ANALYSIS_TTL_SECONDS:
        return hit[1]
    result = eng.full_multi_tf_analysis(symbol, user_settings)
    _ANALYSIS_CACHE[key] = (now, result)
    return result

# ================= SHARED UI =================

FAVICON = "<link rel='icon' href=\"data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>📈</text></svg>\">"

SHARED_STYLE_VARS = """
:root{
  --bg:#050a14; --panel:#111a2e; --panel-2:#151e32; --border:#1e293b; --border-hover:#334155;
  --text:#e2e8f0; --muted:#64748b; --muted-2:#94a3b8;
  --accent:#10b981; --accent-2:#059669; --danger:#ef4444; --warn:#f59e0b; --info:#3b82f6;
}
"""

def alert(message, kind="info"):
    colors = {
        "error": ("rgba(239,68,68,0.12)", "rgba(239,68,68,0.3)", "#fca5a5"),
        "success": ("rgba(16,185,129,0.12)", "rgba(16,185,129,0.3)", "#6ee7b7"),
        "info": ("rgba(59,130,246,0.12)", "rgba(59,130,246,0.3)", "#93c5fd"),
    }
    bg, border, color = colors.get(kind, colors["info"])
    return f"<div style='background:{bg};border:1px solid {border};color:{color};padding:10px 14px;border-radius:10px;font-size:12px;margin-bottom:12px;line-height:1.5'>{message}</div>"

def auth_layout(title, body_html):
    return f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1'>
{FAVICON}
<title>{title} - AGENT 35 PRO</title>
<style>
{SHARED_STYLE_VARS}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,Inter,Arial,sans-serif;margin:0;padding:20px;box-sizing:border-box;display:flex;align-items:center;justify-content:center;min-height:100vh}}
.auth-card{{width:100%;max-width:380px;background:linear-gradient(135deg,var(--panel-2) 0%,var(--panel) 100%);padding:28px;border-radius:20px;border:1px solid var(--border);box-shadow:0 20px 40px rgba(0,0,0,0.4)}}
.auth-logo{{text-align:center;margin-bottom:20px}}
.auth-logo .name{{font-weight:900;font-size:22px;letter-spacing:-1px;color:#fff}}
.auth-logo .name span{{color:var(--accent)}}
.auth-logo .tag{{font-size:11px;color:var(--muted);margin-top:4px}}
input{{width:100%;padding:12px;margin:6px 0;border-radius:10px;border:1px solid var(--border);background:#0b1220;color:white;font-size:14px;box-sizing:border-box;font-family:inherit}}
input:focus{{outline:none;border-color:var(--accent)}}
.btn-primary{{background:linear-gradient(135deg,var(--accent) 0%,var(--accent-2) 100%);color:white;padding:13px;border-radius:12px;font-weight:800;border:none;width:100%;cursor:pointer;font-size:13px;margin-top:10px;box-shadow:0 4px 12px rgba(16,185,129,0.3)}}
.auth-link{{text-align:center;margin-top:14px;font-size:12px}}
.auth-link a{{color:var(--accent);text-decoration:none;font-weight:600}}
h2{{text-align:center}}
</style></head><body>
<div class='auth-card'>
<div class='auth-logo'><div class='name'>AGENT <span>35</span> PRO</div><div class='tag'>Unified Strategy • 2 Modes • Score 5+ Send</div></div>
{body_html}
</div>
</body></html>"""

def pro_layout(content, active="Dashboard", is_admin=False):
    user=session.get("user","Guest")
    active_sess = get_active_sessions()
    sess_html = ""
    for s in ["Asia","London","New York"]:
        if s in active_sess: sess_html+=f"<span style='background:#10b981;padding:3px 8px;border-radius:20px;font-size:9px;font-weight:800;color:white;margin-right:4px;animation:pulse 2s infinite'>● {s}</span>"
        else: sess_html+=f"<span style='background:#1e293b;border:1px solid #334155;padding:3px 8px;border-radius:20px;font-size:9px;color:#64748b;margin-right:4px'>{s}</span>"
    tabs=[("Dashboard","📊"),("Journal","📓"),("All Signals","📡"),("Settings","⚙️"),("Referral","👥"),("Plans","💳"),("Guide","📖")]
    if is_admin: tabs.append(("Master","👑"))
    nav_html=""
    for t,icon in tabs:
        url="/creator" if t=="Master" else f"/{t.lower().replace(' ','-')}"
        if active==t: nav_html+=f"<a href='{url}' class='nav-active'>{icon} {t}</a>"
        else: nav_html+=f"<a href='{url}' class='nav-item'>{icon} {t}</a>"
    html=f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0, maximum-scale=1.0'>
{FAVICON}
<title>{active} - AGENT 35 PRO</title>
<style>
{SHARED_STYLE_VARS}
@keyframes pulse{{0%{{opacity:1}}50%{{opacity:0.6}}100%{{opacity:1}}}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,Inter,Arial,sans-serif;margin:0;padding:0; -webkit-font-smoothing:antialiased}}
.topbar{{background:rgba(15,23,42,0.95);backdrop-filter:blur(12px);padding:12px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100;border-bottom:1px solid var(--border);flex-wrap:wrap;gap:8px}}
.logo{{font-weight:900;font-size:16px;color:#fff;letter-spacing:-0.5px}}.logo span{{color:var(--accent)}}
.live-clock{{background:#0f172a;border:1px solid var(--border);padding:6px 12px;border-radius:10px;font-family:monospace;font-weight:700;font-size:12px;color:var(--accent);letter-spacing:0.5px}}
.badge-live{{background:var(--accent);padding:4px 10px;border-radius:20px;font-weight:800;font-size:9px;color:white;letter-spacing:0.5px}}
.navbar{{background:#0b1220;border-bottom:1px solid var(--border);padding:10px 12px;display:flex;gap:6px;overflow-x:auto;position:sticky;top:60px;z-index:90; -webkit-overflow-scrolling:touch; scrollbar-width:none}}
.navbar::-webkit-scrollbar{{display:none}}
.nav-active{{padding:8px 14px;border-radius:10px;text-decoration:none;color:white;font-weight:700;font-size:11px;background:var(--accent);white-space:nowrap;box-shadow:0 2px 8px rgba(16,185,129,0.3)}}
.nav-item{{padding:8px 14px;border-radius:10px;text-decoration:none;color:var(--muted-2);font-weight:600;font-size:11px;background:var(--panel-2);border:1px solid var(--border);white-space:nowrap;transition:all 0.2s}}
.nav-item:hover{{color:white;border-color:var(--border-hover)}}
.main{{padding:14px;display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;max-width:1600px;margin:0 auto}}
.card{{background:linear-gradient(135deg,var(--panel-2) 0%,var(--panel) 100%);border-radius:16px;padding:16px;border:1px solid var(--border);box-shadow:0 4px 12px rgba(0,0,0,0.2);min-width:0;transition:transform 0.2s}}
.card:hover{{transform:translateY(-1px);border-color:var(--border-hover)}}
.card-title{{color:var(--muted);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px}}
.card-value{{font-size:24px;font-weight:900;color:#f8fafc;letter-spacing:-0.5px;word-break:break-word}}
.card-sub{{font-size:11px;color:var(--muted-2);margin-top:8px;line-height:1.4}}
.btn-primary{{background:linear-gradient(135deg,var(--accent) 0%,var(--accent-2) 100%);color:white;padding:13px;border-radius:12px;font-weight:800;border:none;width:100%;cursor:pointer;font-size:13px;box-shadow:0 4px 12px rgba(16,185,129,0.3);transition:opacity 0.15s}}
.btn-primary:disabled{{opacity:0.6;cursor:wait}}
.btn-secondary{{background:var(--panel-2);border:1px solid var(--border);color:var(--text);padding:10px;border-radius:10px;text-align:center;display:block;text-decoration:none;margin-top:8px;font-size:11px;font-weight:600}}
.table-card{{grid-column:1 / -1;background:var(--panel);border-radius:16px;padding:18px;border:1px solid var(--border);box-shadow:0 4px 12px rgba(0,0,0,0.2);overflow-x:auto}}
table{{width:100%;border-collapse:collapse;min-width:500px}} th{{color:var(--muted);text-align:left;padding:10px 8px;font-size:9px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid var(--border);white-space:nowrap}} td{{padding:10px 8px;border-bottom:1px solid #0f172a;font-size:11px;white-space:nowrap}}
.pill{{padding:4px 10px;border-radius:20px;font-size:10px;font-weight:700;display:inline-block}}
.pill-took{{background:rgba(16,185,129,0.15);color:var(--accent);border:1px solid rgba(16,185,129,0.2)}}
.pill-win{{background:rgba(16,185,129,0.15);color:var(--accent)}}.pill-loss{{background:rgba(239,68,68,0.15);color:var(--danger)}}
.pro-badge{{background:#0f172a;border:1px solid var(--border);color:var(--muted-2);padding:5px 10px;border-radius:20px;font-size:9px;display:inline-block;margin:2px}}
@media(max-width:768px){{.main{{grid-template-columns:1fr; padding:10px}}.card-value{{font-size:20px}}}}
</style>
<script>
function updateClock(){{
  const now = new Date();
  const sast = new Date(now.toLocaleString('en-US', {{timeZone: 'Africa/Johannesburg'}}));
  const timeStr = sast.toLocaleTimeString('en-GB', {{hour12:false}}) + ' SAST';
  const dateStr = sast.toLocaleDateString('en-GB', {{day:'2-digit',month:'short'}});
  const el = document.getElementById('live-clock');
  if(el) el.textContent = dateStr + ' ' + timeStr;
}}
setInterval(updateClock,1000);
window.onload=updateClock;
</script>
</head><body>
<div class='topbar'>
  <div style='display:flex;align-items:center;gap:12px;flex-wrap:wrap'>
    <div class='logo'>AGENT <span>35</span> PRO</div>
    <span class='badge-live'>LIVE</span>
    <div class='live-clock' id='live-clock'>--:--:-- SAST</div>
  </div>
  <div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap'>
    <div style='display:flex;align-items:center;gap:4px'>{sess_html}</div>
    <span style='background:var(--panel);border:1px solid var(--border);color:var(--muted-2);padding:5px 10px;border-radius:20px;font-size:10px;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{user[:18]}</span>
  </div>
</div>
<div class='navbar'>{nav_html}</div>
{content}
</body></html>"""
    return html

# ================= ERROR PAGES =================

@app.errorhandler(404)
def not_found(e):
    body = "<h2 style='font-size:20px;font-weight:800;margin:0 0 8px'>404 - Page Not Found</h2><p style='color:var(--muted);font-size:12px;text-align:center;margin:0 0 16px'>That page doesn't exist.</p><div class='auth-link'><a href='/dashboard'>Back to Dashboard</a></div>"
    return auth_layout("Not Found", body), 404

@app.errorhandler(500)
def server_error(e):
    body = "<h2 style='font-size:20px;font-weight:800;margin:0 0 8px'>500 - Something Went Wrong</h2><p style='color:var(--muted);font-size:12px;text-align:center;margin:0 0 16px'>An unexpected error occurred. Please try again.</p><div class='auth-link'><a href='/dashboard'>Back to Dashboard</a></div>"
    return auth_layout("Error", body), 500

# ================= ROUTES =================

@app.route("/")
def home(): return redirect("/dashboard") if session.get("user") else redirect("/login")

@app.route("/dashboard")
def dashboard():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); journal=load_json(JOURNAL_FILE, list); user_settings=get_user_settings(email)
    tg_users=load_json(TG_FILE, dict); tracked=load_json(TRACK_FILE, dict)
    is_admin=email=="admin@agent35.com"; ref_count=get_ref_count_and_auto_upgrade(email)
    stats=calculate_pnl_stats(journal); curr_sym=get_currency_symbol(user_settings.get("currency","ZAR"))
    mode=user_settings.get("trading_mode","regular")
    rows=""
    if not journal: rows="<tr><td colspan=5 style='text-align:center;color:#64748b;padding:24px'>No trades yet. Take first signal via Telegram.</td></tr>"
    else:
        for t in reversed(journal[-6:]):
            cls="pill-took" if t.get("status")=="TOOK" else "pill-win" if "WIN" in t.get("result","") else "pill-loss"
            pnl=t.get("pnl",0)
            rows+=f"<tr><td style='color:#94a3b8'>{t.get('time')}</td><td style='font-weight:700'>{t.get('symbol')}</td><td><span class='pill {cls}'>{t.get('status')}</span></td><td>{t.get('result')}</td><td style='font-weight:700'>{curr_sym}{pnl}</td></tr>"
    tg_status="✅ Connected" if email in tg_users else "⚠️ Not linked"
    pnl_color="#10b981" if stats['total_pnl']>=0 else "#ef4444"
    admin_link="<a href='/creator' class='btn-secondary' style='background:#f59e0b;color:white;font-weight:700;border-color:#f59e0b'>👑 Creator Panel</a>" if is_admin else ""
    mode_badge = "⚡ SCALP MODE - Fast M5 - 10-20/day" if mode=="scalp" else "🎯 REGULAR MODE - Swing - 2-5/day"
    content=f"""
<div class='main'>
<div class='card'><div class='card-title'>Total Profit & Loss</div><div class='card-value' style='color:{pnl_color}'>{curr_sym}{stats['total_pnl']:.2f}</div><div style='background:#0b1220;border-radius:10px;padding:10px;margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:8px'><div><div style='font-size:9px;color:#64748b'>TODAY</div><div style='font-weight:700;font-size:12px'>{curr_sym}{stats['daily']:.2f}</div></div><div><div style='font-size:9px;color:#64748b'>WEEK</div><div style='font-weight:700;font-size:12px'>{curr_sym}{stats['weekly']:.2f}</div></div><div><div style='font-size:9px;color:#64748b'>MONTH</div><div style='font-weight:700;font-size:12px'>{curr_sym}{stats['monthly']:.2f}</div></div><div><div style='font-size:9px;color:#64748b'>YEAR</div><div style='font-weight:700;font-size:12px'>{curr_sym}{stats['yearly']:.2f}</div></div></div><div class='card-sub'>{mode_badge}<br>Score: 5=takeable, 6=good, 7=strong, 8+=A+</div></div>
<div class='card'><div class='card-title'>Performance</div><div class='card-value'>{stats['total_trades']} Trades • {stats['win_rate']}% WR</div><div class='card-sub'>✅ Wins: {stats['wins']} ❌ Losses: {stats['losses']} ➖ BE: {stats['be']}<br><br>Telegram: {tg_status}<br>Referrals: {ref_count}/10 free lifetime<br>Tracked: {len(tracked)}/{MAX_TRACKED} active (limit 6)</div></div>
<div class='card'><div class='card-title'>Account Overview</div><div class='card-value'>{curr_sym}{user_settings.get('account_size',142)}</div><div class='card-sub'>Lot Size: {user_settings.get('lot_size',0.01)} • Lev {user_settings.get('leverage','1:500')}<br>Risk: {user_settings.get('risk_percent',1)}% • RR 1:{user_settings.get('rr_ratio',2.5)}<br>Currency: {user_settings.get('currency','ZAR')} {curr_sym}<br>Mode: {mode.upper()} - All strategies as ONE<br><a href='/settings' style='color:#10b981;text-decoration:none;font-weight:700'>Edit Settings →</a></div></div>
<div class='card'><div class='card-title'>Quick Actions</div><div style='display:flex;flex-direction:column;gap:2px;margin-top:8px'><a href='/dashboard-scan' onclick="this.querySelector('button').innerHTML='⏳ Scanning...'; this.querySelector('button').disabled=true;"><button class='btn-primary'>🔍 Scan Market Now</button></a><a href='/test-telegram' class='btn-secondary'>📤 Test Telegram</a><a href='/link-telegram' class='btn-secondary'>🔗 Link Telegram</a><a href='/export-journal' class='btn-secondary'>📥 Export Journal CSV</a><a href='/clear-tracked' class='btn-secondary' style='color:#ef4444'>Clear Tracked ({len(tracked)}/{MAX_TRACKED})</a>{admin_link}</div></div>
</div>
<div style='max-width:1600px;margin:0 auto;padding:0 14px 14px'><div class='table-card'><div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:12px'><h3 style='margin:0;font-size:14px;font-weight:800'>Recent Activity - {mode_badge}</h3><span style='font-size:11px;color:#64748b;background:#0b1220;padding:5px 10px;border-radius:20px'>{stats['wins']}W / {stats['losses']}L • {stats['win_rate']}% WR</span></div><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th><th>PnL</th></tr>{rows}</table></div></div>
"""
    return pro_layout(content,"Dashboard", is_admin=is_admin)

@app.route("/settings", methods=["GET","POST"])
def settings_page():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"
    if request.method=="POST":
        new_settings={"account_size":float(request.form.get("account_size",142)),"lot_size":float(request.form.get("lot_size",0.01)),"leverage":request.form.get("leverage","1:500"),"risk_percent":float(request.form.get("risk_percent",1)),"rr_ratio":float(request.form.get("rr_ratio",2.5)),"trade_news":True if request.form.get("trade_news")=="yes" else False,"spread_forex":0.7,"spread_gold":0.35,"spread_indices":2.0,"spread_crypto":10.0,"currency":request.form.get("currency","ZAR"),"trading_mode":request.form.get("trading_mode","regular"),"symbols":request.form.getlist("symbols") or ALL_SYMBOLS[:10]}
        save_user_settings(email,new_settings)
        return redirect("/dashboard")
    s=get_user_settings(email)
    symbols_html="".join([f"<label style='display:flex;align-items:center;gap:6px;background:#0b1220;border:1px solid #1e293b;padding:8px 10px;border-radius:10px;font-size:11px;cursor:pointer'><input type='checkbox' name='symbols' value='{sym}' {'checked' if sym in s.get('symbols',[]) else ''}> {sym}</label>" for sym in ALL_SYMBOLS])
    curr=s.get('currency','ZAR'); mode=s.get('trading_mode','regular')
    currency_options="".join([f"<option value='{code}' {'selected' if curr==code else ''}>{code} - {info['symbol']} {info['name']}</option>" for code,info in CURRENCY_MAP.items()])
    content=f"""<div style='max-width:1100px;margin:0 auto;padding:14px'>
<h1 style='font-size:20px;font-weight:900;margin-bottom:4px'>Settings - Unified Strategy</h1><p style='color:#64748b;font-size:12px;margin-top:0'>One strategy combining all 5 old strategies as one score 0-10. Choose mode only. Score 5+ sends.</p>
<form method='post'>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:16px'>
<div class='card' style='border:2px solid #10b981'><div class='card-title'>Trading Mode - 2 Modes Only</div><select name='trading_mode' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;background:#0b1220;color:white;border:1px solid #10b981'>
<option value='regular' {'selected' if mode=='regular' else ''}>🎯 REGULAR - Swing H1/4H/Daily - 2-5/day - Score 5+ send</option>
<option value='scalp' {'selected' if mode=='scalp' else ''}>⚡ SCALP - Fast M5 only - 10-20/day - Score 5+ send</option>
</select><div style='font-size:11px;color:#94a3b8;margin-top:8px;line-height:1.4'>
<b>REGULAR:</b> Daily bias + 4H alignment + Discount/Premium + Sweep + Engulfing + EMA/RSI + Breakout + OB/BOS/FVG as ONE. Best for Gold/Forex/Indices. Choose: 5=takeable, 6=good, 7=strong, 8+=A+<br><br>
<b>SCALP:</b> M5 EMA9/21 + RSI + Sweep + OB + Engulfing as ONE. Fast, more signals. Best for R142 + Crypto 24/7.
</div></div>
<div class='card'><div class='card-title'>Currency</div><select name='currency' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;background:#0b1220;color:white;border:1px solid #1e293b'>{currency_options}</select></div>
<div class='card'><div class='card-title'>Account Size</div><input name='account_size' type='number' step='0.01' value='{s.get('account_size',142)}' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white'></div>
<div class='card'><div class='card-title'>Lot Size</div><input name='lot_size' type='number' step='0.01' value='{s.get('lot_size',0.01)}' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white'></div>
<div class='card'><div class='card-title'>Risk %</div><input name='risk_percent' type='number' step='0.1' value='{s.get('risk_percent',1)}' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white'></div>
<div class='card'><div class='card-title'>Risk Reward</div><select name='rr_ratio' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;background:#0b1220;color:white;border:1px solid #1e293b'><option value='1.5' {'selected' if str(s.get('rr_ratio'))=='1.5' else ''}>1:1.5 Scalp</option><option value='2' {'selected' if str(s.get('rr_ratio'))=='2' else ''}>1:2</option><option value='2.5' {'selected' if str(s.get('rr_ratio'))=='2.5' else ''}>1:2.5 Regular</option><option value='3' {'selected' if str(s.get('rr_ratio'))=='3' else ''}>1:3 SMC</option></select></div>
</div>
<div class='card' style='margin-top:12px'><div class='card-title'>Watchlist - {len(ALL_SYMBOLS)} Symbols Available - Score 5+ will be sent - Max Tracked {MAX_TRACKED}</div><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:6px;max-height:380px;overflow-y:auto;margin-top:10px;padding-right:4px'>{symbols_html}</div></div>
<button type='submit' class='btn-primary' style='margin-top:16px'>Save Settings - {mode.upper()} Mode</button>
</form></div>"""
    return pro_layout(content,"Settings", is_admin=is_admin)

@app.route("/all-signals")
@app.route("/dashboard-scan")
def dashboard_scan():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"; user_settings=get_user_settings(email)
    symbols_to_scan=user_settings.get("symbols", ALL_SYMBOLS[:12]); mode=user_settings.get("trading_mode","regular")
    tracked=load_json(TRACK_FILE, dict)
    rows=""
    for s in symbols_to_scan[:30]:
        try:
            r=cached_analysis(s, user_settings); score=r.get('score',0); bias=r.get('bias','NEUTRAL'); entry=r.get('entry',0)
            entry_display=f"{float(entry):.5f}" if entry and float(entry)<20 else f"{float(entry):.2f}" if entry else "0"
            color="#10b981" if score>=7 else "#f59e0b" if score>=5 else "#ef4444"
            if r.get('signal'):
                if len(tracked)>=MAX_TRACKED and s not in tracked: signal_btn=f"<span class='pill' style='background:rgba(239,68,68,0.15);color:#ef4444'>Limit {MAX_TRACKED}</span>"
                else: signal_btn=f"<a href='/send-signal?symbol={s}' style='background:#10b981;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-weight:700;font-size:11px'>Send {score}/10</a>"
            else: signal_btn=f"<span style='color:#64748b;font-size:10px'>{r.get('reason','')[:44]}</span>"
            rows+=f"<tr><td style='font-weight:700'>{s}<div style='font-size:9px;color:#64748b'>{entry_display}</div></td><td><span class='pill' style='background:{color}22;color:{color};border:1px solid {color}44'>{score}/10</span></td><td>{bias}</td><td>{'✅ SEND' if r.get('signal') else '⏳ Wait'}</td><td>{signal_btn}</td></tr>"
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "rate" in err_msg.lower():
                rows+=f"<tr><td style='font-weight:700'>{s}</td><td colspan=4><span class='pill' style='background:rgba(245,158,11,0.15);color:#f59e0b'>Rate limited — try again shortly</span></td></tr>"
            else:
                rows+=f"<tr><td>{s}</td><td colspan=4 style='color:#ef4444;font-size:10px'>{err_msg[:50]}</td></tr>"
    mode_badge = "⚡ SCALP MODE" if mode=="scalp" else "🎯 REGULAR MODE"
    content=f"""<div style='max-width:1600px;margin:0 auto;padding:14px'>
<div class='table-card'><div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px'><div><h2 style='font-size:16px;font-weight:800;margin:0'>Market Scan - {mode_badge} - Unified Strategy</h2><p style='font-size:11px;color:#64748b;margin:4px 0 0'>One strategy combining all methods as one score. Threshold 5+ sends. Choose: 5=takeable, 6=good, 7=strong, 8+=A+. Tracked {len(tracked)}/{MAX_TRACKED}</p></div><a href='/clear-tracked' style='background:#1e293b;border:1px solid #334155;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:11px'>Clear Tracked</a></div>
<table><tr><th>Symbol</th><th>Score</th><th>Bias</th><th>Signal</th><th>Action</th></tr>{rows}</table></div></div>"""
    return pro_layout(content,"All Signals", is_admin=is_admin)

@app.route("/journal")
def journal_page():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"; journal=load_json(JOURNAL_FILE, list)
    user_set=get_user_settings(email); curr_sym=get_currency_symbol(user_set.get("currency","ZAR"))
    stats=calculate_pnl_stats(journal); period=request.args.get("period","all"); now=datetime.now()
    if period=="today": filtered=[j for j in journal if j.get("date")==now.strftime("%Y-%m-%d")]
    elif period=="week":
        week_start=(now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        filtered=[j for j in journal if j.get("date","")>=week_start]
    elif period=="month": filtered=[j for j in journal if j.get("date","").startswith(now.strftime("%Y-%m"))]
    elif period=="year": filtered=[j for j in journal if j.get("date","").startswith(now.strftime("%Y"))]
    else: filtered=journal
    rows="".join([f"<tr><td>{j.get('time')}</td><td style='font-weight:700'>{j.get('symbol')}</td><td><span class='pill {('pill-win' if 'WIN' in j.get('result','') else 'pill-loss' if 'LOSS' in j.get('result','') else 'pill-took')}'>{j.get('status')}</span></td><td>{j.get('result')}</td><td style='font-weight:700'>{curr_sym}{j.get('pnl',0)}</td><td style='color:#64748b'>{j.get('date','')}</td></tr>" for j in reversed(filtered[-200:])])
    def get_style(p): return "background:#10b981;color:white;border:1px solid #10b981" if period==p else "background:#151e32;border:1px solid #1e293b;color:#94a3b8"
    content=f"""<div style='max-width:1400px;margin:0 auto;padding:14px'>
<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px'><h1 style='font-size:20px;font-weight:900;margin:0'>Journal - Unified Scores 5+ Send</h1><a href='/export-journal' class='btn-secondary' style='margin:0;display:inline-block'>Export CSV</a></div>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:14px 0'>
<div class='card'><div class='card-title'>Today</div><div class='card-value' style='font-size:18px;color:{"#10b981" if stats['daily']>=0 else "#ef4444"}'>{curr_sym}{stats['daily']:.2f}</div></div>
<div class='card'><div class='card-title'>This Week</div><div class='card-value' style='font-size:18px'>{curr_sym}{stats['weekly']:.2f}</div></div>
<div class='card'><div class='card-title'>This Month</div><div class='card-value' style='font-size:18px'>{curr_sym}{stats['monthly']:.2f}</div></div>
<div class='card'><div class='card-title'>Total PnL</div><div class='card-value' style='font-size:18px;color:{"#10b981" if stats['total_pnl']>=0 else "#ef4444"}'>{curr_sym}{stats['total_pnl']:.2f}</div></div>
</div>
<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px'>
<a href='/journal?period=all' style='padding:7px 14px;border-radius:20px;text-decoration:none;font-size:11px;font-weight:600;{get_style("all")}'>All</a>
<a href='/journal?period=today' style='padding:7px 14px;border-radius:20px;text-decoration:none;font-size:11px;font-weight:600;{get_style("today")}'>Today</a>
<a href='/journal?period=week' style='padding:7px 14px;border-radius:20px;text-decoration:none;font-size:11px;font-weight:600;{get_style("week")}'>Week</a>
<a href='/journal?period=month' style='padding:7px 14px;border-radius:20px;text-decoration:none;font-size:11px;font-weight:600;{get_style("month")}'>Month</a>
<a href='/journal?period=year' style='padding:7px 14px;border-radius:20px;text-decoration:none;font-size:11px;font-weight:600;{get_style("year")}'>Year</a>
</div>
<div class='table-card'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th><th>PnL</th><th>Date</th></tr>{rows if rows else "<tr><td colspan=6 style='text-align:center;color:#64748b;padding:20px'>No trades yet</td></tr>"}</table></div>
</div>"""
    return pro_layout(content,"Journal", is_admin=is_admin)

@app.route("/referral")
def referral_page():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"; my_code=generate_ref_code(email)
    ref_count=get_ref_count_and_auto_upgrade(email); auth=load_json(AUTH_FILE, dict)
    my_refs=[{"email":e,"plan":info.get("plan_status","No Plan"),"date":info.get("created","")[:10]} for e,info in auth.items() if info.get("referred_by","").upper()==my_code.upper()]
    ref_rows="".join([f"<tr><td style='font-weight:600'>{r['email'][:24]}</td><td><span class='pill { 'pill-win' if 'ACTIVE' in r['plan'] else 'pill-loss'}'>{r['plan'][:20]}</span></td><td style='color:#64748b'>{r['date']}</td></tr>" for r in my_refs[-20:]]) or "<tr><td colspan=3 style='text-align:center;color:#64748b;padding:16px'>No referrals yet. Share your link below.</td></tr>"
    progress_pct = min(ref_count*10,100)
    content=f"""<div style='max-width:900px;margin:0 auto;padding:14px'>
<h1 style='font-size:22px;font-weight:900;margin:0'>Referral Program</h1><p style='color:#64748b;font-size:13px;margin:6px 0 16px'>Invite 10 friends who buy a plan → Get Lifetime FREE worth R5000</p>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px'>
<div class='card' style='border:1px solid #10b98133'><div class='card-title'>Your Referral Code</div><div class='card-value' style='color:#10b981;letter-spacing:1px'>{my_code}</div><div class='card-sub'>Share this code - friends enter it at registration</div>
<div style='background:#0b1220;border-radius:10px;padding:12px;margin-top:12px'><div style='font-size:11px;color:#94a3b8;margin-bottom:6px'>Your Referral Link (click copy):</div><div style='background:#050a14;padding:10px;border-radius:8px;font-size:11px;word-break:break-all;border:1px solid #1e293b'>https://agent-35-trading-bot.onrender.com/register?ref={my_code}</div>
<button onclick="navigator.clipboard.writeText('https://agent-35-trading-bot.onrender.com/register?ref={my_code}');alert('Copied!')" style='background:#10b981;color:white;border:none;padding:8px 14px;border-radius:8px;font-weight:700;margin-top:8px;width:100%;cursor:pointer'>Copy Link</button></div></div>
<div class='card'><div class='card-title'>Progress to Free Lifetime</div><div class='card-value'>{ref_count} / 10 Referrals</div>
<div style='background:#0b1220;border-radius:10px;height:10px;margin-top:12px;overflow:hidden'><div style='background:linear-gradient(90deg,#10b981,#059669);height:100%;width:{progress_pct}%;border-radius:10px;transition:width 0.5s'></div></div>
<div class='card-sub' style='margin-top:8px'>{'🎉 You unlocked FREE Lifetime! Contact admin for activation.' if ref_count>=10 else f'Need {10-ref_count} more paid referrals to unlock Lifetime worth R5000'}</div>
<div style='margin-top:12px;display:flex;gap:6px;flex-wrap:wrap'><span class='pro-badge'>R500 = 1 Year</span><span class='pro-badge'>R5000 = Lifetime</span><span class='pro-badge'>10 Refs = Free Lifetime</span></div></div>
</div>
<div class='table-card' style='margin-top:12px'><h3 style='margin:0 0 12px;font-size:14px;font-weight:800'>Your Referrals ({len(my_refs)})</h3><table><tr><th>Email</th><th>Plan Status</th><th>Joined</th></tr>{ref_rows}</table></div>
</div>"""
    return pro_layout(content,"Referral", is_admin=is_admin)

@app.route("/plans")
def plans_page():
    is_admin=session.get("user")=="admin@agent35.com"; email=session.get("user","")
    user_set=get_user_settings(email or "admin@agent35.com"); curr_sym=get_currency_symbol(user_set.get("currency","ZAR"))
    content=f"""<div style='max-width:1000px;margin:0 auto;padding:14px'>
<h1 style='font-size:22px;font-weight:900;margin:0'>Choose Your Plan</h1><p style='color:#64748b;font-size:13px;margin:6px 0 18px'>One unified strategy - 2 modes - Score 5+ sends - 55 symbols - 6 max tracked</p>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px'>
<div class='card' style='border:1px solid #1e293b'><div style='display:flex;justify-content:space-between;align-items:center'><h3 style='margin:0;font-size:16px'>Yearly</h3><span class='pill pill-took'>Most Popular</span></div><div class='card-value' style='margin:12px 0'>{curr_sym}500 <span style='font-size:13px;color:#64748b;font-weight:500'>/ year</span></div><div style='font-size:12px;color:#94a3b8;line-height:1.6'>
✅ All 55 symbols (Forex, Gold, Oil, Indices, Crypto)<br>
✅ 2 Modes: Regular + Scalp unified<br>
✅ Telegram signals 24/7<br>
✅ Score 5+ sends - you choose 5-10<br>
✅ Journal + Export<br>
✅ Up to 6 tracked trades<br>
✅ Cloud backup<br>
✅ 65%+ win rate<br>
</div><a href='/pay?plan=yearly' style='display:block;background:#10b981;color:white;text-align:center;padding:12px;border-radius:12px;text-decoration:none;font-weight:800;margin-top:16px'>Choose Yearly</a></div>
<div class='card' style='border:1px solid #f59e0b44; background:linear-gradient(135deg,#1a1508 0%,#151e32 100%)'><div style='display:flex;justify-content:space-between;align-items:center'><h3 style='margin:0;font-size:16px'>Lifetime</h3><span style='background:#f59e0b;color:white;padding:4px 10px;border-radius:20px;font-size:10px;font-weight:800'>BEST VALUE</span></div><div class='card-value' style='margin:12px 0;color:#fbbf24'>{curr_sym}5000 <span style='font-size:13px;color:#94a3b8;font-weight:500'>once</span></div><div style='font-size:12px;color:#94a3b8;line-height:1.6'>
🔥 Everything in Yearly PLUS<br>
✅ Lifetime updates<br>
✅ Priority support<br>
✅ All future features<br>
✅ Never pay again<br>
✅ Free if you refer 10 friends<br>
✅ Worth {curr_sym}5000 - save forever<br>
</div><a href='/pay?plan=lifetime' style='display:block;background:linear-gradient(135deg,#f59e0b,#d97706);color:white;text-align:center;padding:12px;border-radius:12px;text-decoration:none;font-weight:800;margin-top:16px'>Choose Lifetime</a></div>
</div>
<div class='card' style='margin-top:14px'><h3 style='margin:0 0 8px;font-size:14px'>How to Pay - Capitec Business</h3><div style='background:#0b1220;padding:14px;border-radius:10px;border:1px solid #1e293b'><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;font-size:12px'><div><div style='color:#64748b;font-size:10px'>BANK</div><div style='font-weight:700'>Capitec Business</div></div><div><div style='color:#64748b;font-size:10px'>ACCOUNT NUMBER</div><div style='font-weight:700;font-family:monospace'>2586572676</div></div><div><div style='color:#64748b;font-size:10px'>REFERENCE</div><div style='font-weight:700'>A35-{'XXXX' if not email else email[:4].upper()}</div></div><div><div style='color:#64748b;font-size:10px'>AMOUNT</div><div style='font-weight:700;color:#10b981'>{curr_sym}500 Yearly or {curr_sym}5000 Lifetime</div></div></div><div style='margin-top:12px;font-size:11px;color:#94a3b8'>After payment, upload proof via Telegram or email. Admin approves within 1 hour.</div></div></div>
</div>"""
    return pro_layout(content,"Plans", is_admin=is_admin)

@app.route("/guide")
def guide_page():
    is_admin=session.get("user")=="admin@agent35.com"
    content="""<div style='max-width:900px;margin:0 auto;padding:14px'>
<h1 style='font-size:22px;font-weight:900;margin:0'>User Guide - Unified Strategy</h1><p style='color:#64748b;font-size:13px;margin:6px 0 18px'>One strategy combining all methods as one score. 2 modes only. Score 5+ sends.</p>
<div style='display:grid;gap:12px'>
<div class='card'><h3 style='margin:0 0 8px;font-size:14px'>🚀 Quick Start (2 min)</h3><div style='font-size:12px;color:#cbd5e1;line-height:1.7'>
1. <b>Settings</b> → Account Size (R142), Lot (0.01), Risk 1%, RR 1:2.5<br>
2. Pick Currency: ZAR R, USD $, EUR €, GBP £<br>
3. Choose Mode: 🎯 REGULAR for beginners (swing), ⚡ SCALP for fast<br>
4. Select 8-12 symbols max (Gold + majors)<br>
5. <b>Link Telegram</b> → /start bot → Paste Chat ID<br>
6. <b>Scan Now</b> → Send if Score 5+ → Take trade
</div></div>
<div class='card'><h3 style='margin:0 0 8px;font-size:14px'>🎯 One Strategy Explained - All Combined</h3><div style='font-size:12px;color:#cbd5e1;line-height:1.7'>
<b>We combined 5 old strategies into ONE score 0-10:</b><br>
• Premium/Discount (Daily bias) + 4H alignment +2-3 pts<br>
• EMA 5/20 + RSI pullback +2 pts<br>
• Breakout + BOS +2 pts<br>
• Order Block (BTC OB fixed) +4 pts<br>
• FVG +2 pts, Sweep +3 pts, Engulfing/Hammer +3-4 pts<br><br>
<b>Total capped 10/10. Threshold 5+ sends.</b><br>
You choose which to take based on score:<br>
<span style='background:#ef444422;color:#ef4444;padding:2px 8px;border-radius:20px;font-size:10px'>5/10 ⚡ Takeable - minimum decent</span><br>
<span style='background:#f59e0b22;color:#f59e0b;padding:2px 8px;border-radius:20px;font-size:10px'>6/10 👍 Good - solid confluence</span><br>
<span style='background:#10b98122;color:#10b981;padding:2px 8px;border-radius:20px;font-size:10px'>7/10 ✅ Strong - high probability</span><br>
<span style='background:#10b981;color:white;padding:2px 8px;border-radius:20px;font-size:10px'>8-10/10 🔥 A+ - best of day</span>
</div></div>
<div class='card'><h3 style='margin:0 0 8px;font-size:14px'>⏰ Sessions - Live Indicator Top Bar</h3><div style='font-size:12px;color:#cbd5e1;line-height:1.7'>
<span style='background:#10b981;padding:2px 8px;border-radius:20px;font-size:10px;color:white'>● Asia</span> 02:00-11:00 SAST → JPY pairs<br>
<span style='background:#10b981;padding:2px 8px;border-radius:20px;font-size:10px;color:white'>● London</span> 10:00-19:00 SAST → EUR/GBP/XAU best<br>
<span style='background:#10b981;padding:2px 8px;border-radius:20px;font-size:10px;color:white'>● New York</span> 15:00-00:00 SAST → US30/NAS100/BTC best<br>
Overlap 15:00-19:00 SAST = best volatility<br>
Weekend: Forex/Gold/Indices closed Sat, Crypto 24/7 trades
</div></div>
<div class='card'><h3 style='margin:0 0 8px;font-size:14px'>🔒 6 Max Tracked</h3><div style='font-size:12px;color:#cbd5e1;line-height:1.7'>Max 6 active tracked at once to stop overtrading. Clear via Dashboard or auto-clear 24h. 55 symbols: 26 Forex, 2 Metals, 2 Oil, 10 Indices, 13 Crypto.</div></div>
</div>
</div>"""
    return pro_layout(content,"Guide", is_admin=is_admin)

@app.route("/creator")
def creator_dashboard():
    email = session.get("user","")
    secret_param = request.args.get("secret","")
    is_authorized = (email=="admin@agent35.com") or (secret_param and CREATOR_SECRET and secret_param==CREATOR_SECRET)
    if not is_authorized:
        return pro_layout("<div style='max-width:600px;margin:80px auto;text-align:center'><div class='card'><h2>🔒 Access Denied</h2><p style='color:#64748b;font-size:13px'>Creator panel requires admin login.</p></div></div>","Master", is_admin=False)
    users=load_json(USERS_FILE); auth=load_json(AUTH_FILE); journal=load_json(JOURNAL_FILE, list); tracked=load_json(TRACK_FILE, dict); system=load_json(SYSTEM_FILE, dict); stats=calculate_pnl_stats(journal)
    pending={k:v for k,v in users.items() if v.get("status")=="pending"}
    pending_rows="".join([f"<tr><td style='font-family:monospace;font-size:10px'>{ref}</td><td>{pay.get('user','')[:24]}</td><td>{pay.get('plan','yearly')}</td><td>R{pay.get('price','')}</td><td><a href='/creator/action?act=approve_payment&ref={ref}&secret={secret_param}' style='background:#10b981;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-weight:700;font-size:11px'>Approve</a> <a href='/creator/action?act=reject&ref={ref}&secret={secret_param}' style='background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:11px'>Reject</a></td></tr>" for ref,pay in pending.items()]) or "<tr><td colspan=5 style='text-align:center;color:#64748b;padding:16px'>No pending payments ✅</td></tr>"
    user_rows="".join([f"<tr><td style='font-size:10px'>{e[:24]}</td><td style='font-size:10px'>{info.get('plan_status','')[:18]}</td><td style='font-size:10px'>{info.get('ref_code','')}</td><td style='font-size:10px'>{str(info.get('expires',''))[:10]}</td></tr>" for e,info in list(auth.items())[-15:]])
    content=f"""<div style='max-width:1600px;margin:0 auto;padding:14px'>
<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px'><h1 style='font-size:20px;font-weight:900;margin:0'>👑 Creator Master Panel - V24 Unified 2 Modes</h1><div style='display:flex;gap:6px;flex-wrap:wrap'><span class='pro-badge'>Users: {len(auth)}</span><span class='pro-badge'>Pending: {len(pending)}</span><span class='pro-badge'>Trades: {len(journal)}</span><span class='pro-badge'>Tracked: {len(tracked)}/{MAX_TRACKED}</span></div></div>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:14px'>
<div class='card'><div class='card-title'>Pending Payments</div><div class='card-value' style='font-size:20px;color:#f59e0b'>{len(pending)}</div></div>
<div class='card'><div class='card-title'>Total Users</div><div class='card-value' style='font-size:20px'>{len(auth)}</div></div>
<div class='card'><div class='card-title'>Total PnL</div><div class='card-value' style='font-size:18px;color:{"#10b981" if stats['total_pnl']>=0 else "#ef4444"}'>R{stats['total_pnl']:.2f}</div></div>
<div class='card'><div class='card-title'>System Scans</div><div class='card-value' style='font-size:20px'>{system.get('total_scans',0)}</div><div style='font-size:10px;color:#64748b'>Last: {str(system.get('last_scan','Never'))[:16]}</div></div>
</div>
<div class='table-card'><div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px'><h3 style='margin:0;font-size:14px;font-weight:800'>Pending Payments - Approve / Reject</h3><div style='display:flex;gap:6px'><a href='/backup-now' style='background:#10b981;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:11px'>Force Backup</a><a href='/clear-tracked?secret={secret_param}' style='background:#ef4444;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:11px'>Clear Tracked</a><a href='/health' style='background:#1e293b;border:1px solid #334155;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:11px'>Health</a></div></div><table><tr><th>Ref ID</th><th>Email</th><th>Plan</th><th>Price</th><th>Action</th></tr>{pending_rows}</table></div>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:12px'>
<div class='table-card'><h3 style='margin:0 0 12px;font-size:14px'>Recent Users (15)</h3><table><tr><th>Email</th><th>Plan</th><th>Ref Code</th><th>Expires</th></tr>{user_rows}</table></div>
<div class='card'><h3 style='margin:0 0 10px;font-size:14px'>Tracked Trades {len(tracked)}/{MAX_TRACKED}</h3><div style='font-size:11px;color:#cbd5e1;line-height:1.6'>{'<br>'.join([f"{k}: {v.get('bias')} {v.get('entry')} Score {v.get('score')}/10" for k,v in tracked.items()]) if tracked else "No tracked trades - clean"}</div><div style='margin-top:12px'><a href='/dashboard-scan' style='background:#10b981;color:white;padding:8px 14px;border-radius:8px;text-decoration:none;font-size:12px;font-weight:700'>View Signals</a></div></div>
</div>
</div>"""
    return pro_layout(content,"Master", is_admin=True)

@app.route("/creator/action")
def creator_action():
    secret=request.args.get("secret",""); email=session.get("user","")
    is_authorized = (email=="admin@agent35.com") or (secret and CREATOR_SECRET and secret==CREATOR_SECRET)
    if not is_authorized: return "Unauthorized"
    act=request.args.get("act",""); auth=load_json(AUTH_FILE); users=load_json(USERS_FILE)
    if act=="approve_payment":
        ref=request.args.get("ref","")
        if ref in users:
            users[ref]["status"]="active"; users[ref]["expires"]=(datetime.now()+timedelta(days=365 if users[ref].get('plan')=='yearly' else 36500)).isoformat()
            user_email=users[ref].get("user")
            if user_email in auth:
                plan = users[ref].get('plan','yearly')
                auth[user_email]["plan_status"]=f"ACTIVE {plan}"; auth[user_email]["expires"]=users[ref]["expires"]
            save_json(USERS_FILE, users); save_json(AUTH_FILE, auth)
        return redirect(f"/creator?secret={secret}")
    if act=="reject":
        ref=request.args.get("ref","")
        if ref in users: del users[ref]; save_json(USERS_FILE, users)
        return redirect(f"/creator?secret={secret}")
    return redirect(f"/creator?secret={secret}")

@app.route("/clear-tracked")
def clear_tracked():
    if not session.get("user") and not request.args.get("secret"): return redirect("/login")
    save_json(TRACK_FILE, {}); secret=request.args.get("secret","")
    if secret: return redirect(f"/creator?secret={secret}")
    return redirect("/dashboard")

@app.route("/send-signal")
def send_signal():
    if not session.get("user"): return redirect("/login")
    sym=request.args.get("symbol","EURUSD"); email=session.get("user"); user_set=get_user_settings(email)
    tracked=load_json(TRACK_FILE, dict)
    if len(tracked)>=MAX_TRACKED and sym not in tracked:
        return pro_layout(f"<div style='max-width:600px;margin:60px auto;text-align:center'><div class='card'><h2>Track Limit {MAX_TRACKED} Reached</h2><p style='color:#94a3b8'>Tracked: {', '.join(tracked.keys())}<br>Clear to allow new</p><div style='display:flex;gap:8px;justify-content:center;margin-top:16px'><a href='/all-signals' style='background:#10b981;color:white;padding:10px 18px;border-radius:10px;text-decoration:none'>Back</a><a href='/clear-tracked' style='background:#ef4444;color:white;padding:10px 18px;border-radius:10px;text-decoration:none'>Clear All</a></div></div></div>","All Signals", is_admin=email=="admin@agent35.com")
    try:
        r=cached_analysis(sym, user_set); entry=r.get('entry',0)
        if not entry or float(entry)==0: return pro_layout(f"<div class='card' style='max-width:600px;margin:40px auto'><h3>No entry for {sym}</h3><pre style='font-size:10px'>{r}</pre></div>","All Signals", is_admin=email=="admin@agent35.com")
        rr=user_set.get('rr_ratio',2.5); risk_percent=user_set.get('risk_percent',1); lot=user_set.get('lot_size',0.01); lev=user_set.get('leverage','1:500'); acc=user_set.get('account_size',142)
        curr_sym=get_currency_symbol(user_set.get("currency","ZAR")); mode=user_set.get("trading_mode","regular")
        sl,tp,sl_dist,tp_dist,risk_amt=calculate_dynamic_sl_tp(sym, entry, r.get('bias',''), acc, lot, lev, risk_percent, rr)
        res=send_telegram_pro(sym, r.get('score',0), r.get('bias',''), entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot, lev, acc, r.get('confluence',''), curr_sym, mode)
        tracked[sym]={"time":datetime.now().isoformat(),"bias":r.get('bias'),"entry":entry,"sl":sl,"tp":tp,"risk_amt":risk_amt,"rr":rr,"score":r.get('score'),"currency":user_set.get("currency","ZAR"),"mode":mode}; save_json(TRACK_FILE, tracked)
        msg=f"Sent {sym} Score {r.get('score')}/10 {entry} SL {sl} TP {tp} Mode {mode.upper()}"
    except Exception as e: res={"error":str(e)}; msg=f"Error {sym}: {e}"
    return pro_layout(f"<div style='max-width:700px;margin:40px auto'><div class='card'><h2 style='font-size:16px'>{msg}</h2><p style='font-size:11px;background:#0b1220;padding:10px;border-radius:8px;word-break:break-all;border:1px solid #1e293b'>{str(res)[:2000]}</p><div style='display:flex;gap:8px;margin-top:12px'><a href='/all-signals' style='background:#10b981;color:white;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:700'>Back to Signals</a><a href='/dashboard' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px 16px;border-radius:10px;text-decoration:none'>Dashboard</a></div></div></div>","All Signals", is_admin=email=="admin@agent35.com")

@app.route("/export-journal")
def export_journal():
    if not session.get("user"): return redirect("/login")
    journal=load_json(JOURNAL_FILE, list); output=io.StringIO(); writer=csv.writer(output); writer.writerow(["Time","Symbol","Status","Result","PnL","Date"])
    for j in journal: writer.writerow([j.get("time",""),j.get("symbol",""),j.get("status",""),j.get("result",""),j.get("pnl",0),j.get("date","")])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=journal.csv"})

@app.route("/test-telegram")
def test_telegram():
    email=session.get("user") or "admin@agent35.com"; user_set=get_user_settings(email)
    r=cached_analysis("GBPUSD", user_set); entry=r.get('entry',0)
    if not entry or float(entry)==0: entry=1.35057; r={"score":8,"bias":"BEARISH","confluence":"Test unified strategy - all 5 methods combined as ONE score 8/10 A+","details":{}}
    rr=user_set.get('rr_ratio',2.5); risk_percent=user_set.get('risk_percent',1); lot=user_set.get('lot_size',0.01); lev=user_set.get('leverage','1:500'); acc=user_set.get('account_size',142)
    curr_sym=get_currency_symbol(user_set.get("currency","ZAR")); mode=user_set.get("trading_mode","regular")
    sl,tp,sl_dist,tp_dist,risk_amt=calculate_dynamic_sl_tp("GBPUSD", entry, r.get('bias','BEARISH'), acc, lot, lev, risk_percent, rr)
    res=send_telegram_pro("GBPUSD", r.get('score',8), r.get('bias','BEARISH'), entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot, lev, acc, r.get('confluence','Test'), curr_sym, mode)
    return pro_layout(f"<div style='max-width:700px;margin:40px auto'><div class='card'><h2 style='font-size:15px'>Test Sent - GBPUSD {entry} Score {r.get('score')}/10 {mode.upper()}</h2><p style='font-size:11px;background:#0b1220;padding:12px;border-radius:10px;border:1px solid #1e293b;word-break:break-all'>{str(res)[:2000]}</p><a href='/dashboard' style='background:#10b981;color:white;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:700;display:inline-block;margin-top:10px'>Back to Dashboard</a></div></div>","Dashboard", is_admin=email=="admin@agent35.com")

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data=request.get_json()
    if not data: return jsonify({"ok":True})
    bot=os.getenv("TELEGRAM_BOT_TOKEN")
    if "message" in data:
        chat_id=data["message"]["chat"]["id"]; from_user=data["message"]["from"]
        temp=load_json(TEMP_CHAT_FILE, dict)
        temp[str(chat_id)]={"first_name":from_user.get("first_name",""),"username":from_user.get("username",""),"time":datetime.now().isoformat(),"text":data["message"].get("text","")[:100]}
        save_json(TEMP_CHAT_FILE, temp)
        if bot and "/start" in data["message"].get("text",""):
            try: requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":f"AGENT 35 PRO - Your Chat ID: {chat_id}\nCopy and paste in Dashboard > Link Telegram\n\nUnified Strategy - 2 Modes - Score 5+ sends"}, timeout=5)
            except: pass
    if "callback_query" in data:
        cb=data["callback_query"]; cb_data=cb.get("data",""); cb_id=cb.get("id"); chat_id=cb["message"]["chat"]["id"]; user_name=cb["from"].get("first_name","User")
        journal=load_json(JOURNAL_FILE, list); tracked=load_json(TRACK_FILE, dict); text="OK"
        if cb_data.startswith("TOOK_"):
            parts=cb_data.split("_"); sym=parts[1]; entry=parts[2] if len(parts)>2 else ""
            risk_amt=0; rr=2.5; sl=0; tp=0; curr="ZAR"; mode=""
            if sym in tracked: risk_amt=tracked[sym].get("risk_amt",0); rr=tracked[sym].get("rr",2.5); sl=tracked[sym].get("sl",0); tp=tracked[sym].get("tp",0); curr=tracked[sym].get("currency","ZAR"); mode=tracked[sym].get("mode","")
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"TOOK","result":f"Taken by {user_name} {mode} Score {tracked.get(sym,{}).get('score','')}/10","pnl":0,"entry":entry,"sl":sl,"tp":tp,"risk_amt":risk_amt,"rr":rr,"date":datetime.now().strftime("%Y-%m-%d"),"currency":curr})
            save_json(JOURNAL_FILE, journal[-500:]); text=f"TOOK {sym} {entry}"
        elif cb_data.startswith("SKIP_"):
            sym=cb_data.split("_")[1]
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"MISS","result":f"Skipped by {user_name}","pnl":0,"date":datetime.now().strftime("%Y-%m-%d")})
            save_json(JOURNAL_FILE, journal[-500:]); text=f"SKIP {sym}"
        if bot:
            try:
                requests.post(f"https://api.telegram.org/bot{bot}/answerCallbackQuery", json={"callback_query_id":cb_id,"text":text}, timeout=5)
                requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":text}, timeout=5)
            except: pass
        return jsonify({"ok":True})
    return jsonify({"ok":True})

@app.route("/login")
def login_page():
    err = request.args.get("error","")
    body = (alert(err, "error") if err else "") + """
<form action='/login/check' method='post'>
<input name='email' type='email' placeholder='Email address' required>
<input name='password' type='password' placeholder='Password' required>
<button class='btn-primary'>Login</button>
</form>
<div class='auth-link'><a href='/forgot-password'>Forgot password?</a></div>
<div class='auth-link'><a href='/register'>Create account →</a></div>
"""
    return auth_layout("Login", body)

@app.route("/register")
def register_page():
    ref=request.args.get("ref","")
    err = request.args.get("error","")
    ref_banner = alert(f"🎁 Referred by: <b>{ref}</b>", "info") if ref else ""
    err_html = alert(err, "error") if err else ""
    body = f"""<h2 style='font-size:18px;font-weight:800;margin:0 0 4px'>Create Account</h2>
<p style='color:#64748b;font-size:12px;margin:0 0 16px;text-align:center'>Unified strategy - 2 modes - Score 5+ send</p>
{err_html}{ref_banner}
<form action='/register/create' method='post'>
<input name='email' type='email' placeholder='Email' required>
<input name='name' placeholder='Full Name' required>
<input name='password' type='password' placeholder='Password' required>
<input name='ref' value='{ref}' placeholder='Referral Code (optional)'>
<button class='btn-primary'>Create Account</button>
</form>
<div class='auth-link'><a href='/login'>Already have account? Login</a></div>"""
    return auth_layout("Register", body)

@app.route("/register/create", methods=["POST"])
def register_create():
    email=request.form.get("email","").lower().strip(); auth=load_json(AUTH_FILE)
    if email in auth:
        return redirect(f"/register?error={quote('An account with that email already exists.')}&ref={request.form.get('ref','')}")
    ref_code=request.form.get("ref","").upper().strip(); my_code=generate_ref_code(email)
    auth[email]={"email":email,"name":request.form.get("name"),"password":hash_pwd(request.form.get("password","")),"account_size":142.0,"total_profit":-1.42,"plan_status":"No Plan","referred_by":ref_code,"created":datetime.now().isoformat(),"reset_token":None,"reset_token_expires":None,"ref_code":my_code}
    save_json(AUTH_FILE, auth); session["user"]=email; return redirect("/dashboard")

@app.route("/login/check", methods=["POST"])
def login_check():
    email=request.form.get("email","").lower().strip(); pwd=request.form.get("password",""); auth=load_json(AUTH_FILE)
    if email in auth and verify_and_maybe_upgrade_password(auth, email, pwd):
        session["user"]=email; return redirect("/dashboard")
    return redirect(f"/login?error={quote('Incorrect email or password.')}")

@app.route("/logout")
def logout(): session.pop("user",None); return redirect("/login")

@app.route("/forgot-password", methods=["GET","POST"])
def forgot_password():
    if request.method=="POST":
        email = request.form.get("email","").lower().strip()
        auth = load_json(AUTH_FILE)
        fallback_link = None
        if email in auth:
            token = secrets.token_urlsafe(32)
            auth[email]["reset_token"] = token
            auth[email]["reset_token_expires"] = (datetime.now()+timedelta(hours=1)).isoformat()
            save_json(AUTH_FILE, auth)
            base_url = os.getenv("APP_BASE_URL", request.host_url.rstrip("/"))
            reset_link = f"{base_url}/reset-password?token={token}&email={quote(email)}"
            sent, _ = send_reset_email(email, reset_link)
            if not sent:
                fallback_link = reset_link
        # Same message regardless of whether the email exists, so this
        # endpoint can't be used to discover which emails are registered.
        body = alert("If that email exists in our system, a password reset link has been sent.", "success")
        if fallback_link:
            body += alert(f"Email isn't configured yet — here's your reset link:<br><a href='{fallback_link}' style='color:#93c5fd;word-break:break-all'>{fallback_link}</a>", "info")
        body += "<div class='auth-link'><a href='/login'>Back to login</a></div>"
        return auth_layout("Check Your Email", body)
    body = """<h2 style='font-size:18px;font-weight:800;margin:0 0 4px'>Forgot Password</h2>
<p style='color:#64748b;font-size:12px;margin:0 0 16px;text-align:center'>Enter your email and we'll send you a reset link.</p>
<form method='post'>
<input name='email' type='email' placeholder='Email address' required>
<button class='btn-primary'>Send Reset Link</button>
</form>
<div class='auth-link'><a href='/login'>Back to login</a></div>"""
    return auth_layout("Forgot Password", body)

@app.route("/reset-password", methods=["GET","POST"])
def reset_password():
    token = request.args.get("token","") or request.form.get("token","")
    email = request.args.get("email","") or request.form.get("email","")
    auth = load_json(AUTH_FILE)
    user = auth.get(email)

    def token_valid(u):
        if not u or not token: return False
        if u.get("reset_token") != token: return False
        expires = u.get("reset_token_expires")
        if not expires: return False
        try: return datetime.fromisoformat(expires) > datetime.now()
        except: return False

    invalid_body = alert("This reset link is invalid or has expired. Please request a new one.", "error") + "<div class='auth-link'><a href='/forgot-password'>Request New Link</a></div>"

    if request.method=="POST":
        if not token_valid(user):
            return auth_layout("Reset Password", invalid_body)
        new_pwd = request.form.get("password","")
        if len(new_pwd) < 6:
            body = alert("Password must be at least 6 characters.", "error") + f"""
<form method='post'>
<input type='hidden' name='token' value='{token}'><input type='hidden' name='email' value='{email}'>
<input name='password' type='password' placeholder='New password' required minlength='6'>
<button class='btn-primary'>Reset Password</button>
</form>"""
            return auth_layout("Reset Password", body)
        auth[email]["password"] = hash_pwd(new_pwd)
        auth[email]["reset_token"] = None
        auth[email]["reset_token_expires"] = None
        save_json(AUTH_FILE, auth)
        body = alert("Your password has been reset. You can log in now.", "success") + "<div class='auth-link'><a href='/login'>Go to Login</a></div>"
        return auth_layout("Password Reset", body)

    if not token_valid(user):
        return auth_layout("Reset Password", invalid_body)
    body = f"""<h2 style='font-size:18px;font-weight:800;margin:0 0 4px'>Reset Password</h2>
<form method='post'>
<input type='hidden' name='token' value='{token}'><input type='hidden' name='email' value='{email}'>
<input name='password' type='password' placeholder='New password' required minlength='6'>
<button class='btn-primary'>Reset Password</button>
</form>"""
    return auth_layout("Reset Password", body)

@app.route("/link-telegram", methods=["GET","POST"])
def link_telegram():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"; tg_users=load_json(TG_FILE, dict)
    if request.method=="POST":
        chat_id=request.form.get("chat_id","").strip()
        if chat_id:
            tg_users[email]={"chat_id":chat_id,"linked_at":datetime.now().isoformat(),"manual":True}
            save_json(TG_FILE, tg_users); return redirect("/dashboard")
    current=tg_users.get(email,{}).get("chat_id","Not linked - follow steps below")
    content=f"""<div style='max-width:600px;margin:0 auto;padding:14px'>
<div class='card'><h2 style='font-size:16px;margin:0 0 6px'>Link Telegram</h2><p style='color:#64748b;font-size:12px;margin:0 0 14px'>Get signals directly to your Telegram. 2 steps.</p>
<div style='background:#0b1220;border:1px solid #1e293b;padding:12px;border-radius:10px;font-size:11px;margin-bottom:14px'><div style='color:#64748b;font-size:9px'>CURRENT</div><div style='font-weight:700;margin-top:4px'>{current}</div></div>
<div style='background:#111a2e;border:1px solid #1e293b;border-radius:12px;padding:14px;margin-bottom:14px'>
<h4 style='margin:0 0 10px;font-size:13px'>Step 1: Start Bot</h4>
<div style='font-size:12px;color:#94a3b8;line-height:1.6'>1. Open Telegram → Search your bot<br>2. Send /start<br>3. Copy Chat ID from reply</div>
</div>
<div style='background:#111a2e;border:1px solid #1e293b;border-radius:12px;padding:14px'>
<h4 style='margin:0 0 10px;font-size:13px'>Step 2: Paste Chat ID</h4>
<form method='post'><input name='chat_id' placeholder='Paste Chat ID (e.g. 1234567890)' style='width:100%;padding:12px;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white' required><button type='submit' style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:10px;font-weight:800;margin-top:10px;cursor:pointer'>Connect Telegram</button></form>
</div>
</div>
</div>"""
    return pro_layout(content,"Settings", is_admin=is_admin)

@app.route("/pay")
def pay_page():
    plan=request.args.get("plan","yearly"); is_admin=session.get("user")=="admin@agent35.com"; email=session.get("user","")
    curr_sym=get_currency_symbol(get_user_settings(email or "admin@agent35.com").get("currency","ZAR"))
    price = "500" if plan=="yearly" else "5000"
    content=f"""<div style='max-width:600px;margin:0 auto;padding:14px'>
<div class='card'><h2 style='font-size:18px;margin:0'>Pay for {plan.title()} - {curr_sym}{price}</h2>
<div style='background:#0b1220;padding:14px;border-radius:12px;margin:14px 0;border:1px solid #1e293b'>
<div style='display:grid;gap:10px;font-size:13px'>
<div><span style='color:#64748b;font-size:10px'>BANK</span><div style='font-weight:700'>Capitec Business</div></div>
<div><span style='color:#64748b;font-size:10px'>ACCOUNT</span><div style='font-weight:700;font-family:monospace;font-size:14px'>2586572676</div></div>
<div><span style='color:#64748b;font-size:10px'>REFERENCE</span><div style='font-weight:700'>A35-{email[:4].upper() if email else 'XXXX'}</div></div>
<div><span style='color:#64748b;font-size:10px'>AMOUNT</span><div style='font-weight:800;color:#10b981;font-size:16px'>{curr_sym}{price}</div></div>
</div>
</div>
<form action='/pay/submit' method='post' style='margin-top:14px'><input type='hidden' name='plan' value='{plan}'><input type='hidden' name='price' value='{price}'><input name='ref' placeholder='Payment Reference (e.g. A35-JOHN)' required style='width:100%;padding:12px;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white;margin-bottom:8px'><button type='submit' style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:10px;font-weight:800'>I Have Paid - Submit Proof</button></form>
<div style='font-size:11px;color:#64748b;margin-top:12px;text-align:center'>Admin approves within 1 hour after verification</div>
</div>
</div>"""
    return pro_layout(content,"Plans", is_admin=is_admin)

@app.route("/pay/submit", methods=["POST"])
def pay_submit():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); users=load_json(USERS_FILE, dict)
    ref_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    users[ref_id]={"user":email,"plan":request.form.get("plan","yearly"),"price":request.form.get("price","500"),"ref":request.form.get("ref",""),"status":"pending","created":datetime.now().isoformat()}
    save_json(USERS_FILE, users)
    return pro_layout(f"<div style='max-width:600px;margin:60px auto;text-align:center'><div class='card'><h2 style='color:#10b981'>Payment Submitted ✅</h2><p style='color:#94a3b8;font-size:13px'>Ref: {ref_id}<br>Admin will approve within 1 hour.</p><a href='/dashboard' style='background:#10b981;color:white;padding:10px 18px;border-radius:10px;text-decoration:none;font-weight:700;display:inline-block;margin-top:12px'>Back to Dashboard</a></div></div>","Plans", is_admin=email=="admin@agent35.com")

@app.route("/cron/scan")
def cron_scan():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    system=load_json(SYSTEM_FILE, dict); system["last_scan"]=datetime.now().isoformat(); system["total_scans"]=system.get("total_scans",0)+1; save_json(SYSTEM_FILE, system)
    settings_all=load_json(SETTINGS_FILE, dict); all_syms=set()
    for s in settings_all.values(): all_syms.update(s.get("symbols",[]))
    if not all_syms: all_syms=set(ALL_SYMBOLS[:12])
    tracked=load_json(TRACK_FILE, dict); now=datetime.now()
    cleaned={};
    for k,v in tracked.items():
        try:
            t=datetime.fromisoformat(v.get("time","2000-01-01T00:00:00"))
            if (now - t).total_seconds() < 86400: cleaned[k]=v
        except: pass
    tracked=cleaned
    if len(tracked)>=MAX_TRACKED: return jsonify({"error":f"Limit {MAX_TRACKED}","tracked":list(tracked.keys())})
    sent=[]; skipped=[]
    for sym in list(all_syms)[:20]:
        if len(tracked)>=MAX_TRACKED and sym not in tracked: skipped.append(f"{sym} LIMIT"); continue
        try:
            sample_settings = next(iter(settings_all.values())) if settings_all else {"trade_news":True,"risk_percent":1,"rr_ratio":2.5,"lot_size":0.01,"leverage":"1:500","account_size":142,"currency":"ZAR","trading_mode":"regular"}
            r=cached_analysis(sym, sample_settings)
            if not r.get('signal'): continue
            entry=r.get('entry'); rr=sample_settings.get('rr_ratio',2.5)
            sl,tp,sl_dist,tp_dist,risk_amt=calculate_dynamic_sl_tp(sym, entry, r.get('bias',''), 142, 0.01, "1:500", 1, rr, 0.7, 0.35, 2.0, 10.0)
            curr_sym=get_currency_symbol(sample_settings.get("currency","ZAR"))
            send_telegram_pro(sym, r.get('score',7), r.get('bias',''), entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, 1, 0.01, "1:500", 142, r.get('confluence',''), curr_sym, r.get('mode','regular'))
            tracked[sym]={"time":now.isoformat(),"bias":r.get('bias'),"entry":entry,"sl":sl,"tp":tp,"risk_amt":risk_amt,"rr":rr,"score":r.get('score')}
            save_json(TRACK_FILE, tracked); sent.append(sym)
            if len(tracked)>=MAX_TRACKED: break
        except: pass
    return jsonify({"sent":sent,"skipped":skipped,"tracked":len(tracked),"limit":MAX_TRACKED,"score_threshold":5})

@app.route("/health")
def health():
    test=cached_analysis("BTCUSD", {"trade_news":True,"currency":"ZAR","trading_mode":"regular"})
    tracked=load_json(TRACK_FILE, dict)
    return jsonify({"ok":True,"version":"V24 - forgot password, security fixes, unified UI, scan caching","symbols":len(ALL_SYMBOLS),"tracked":f"{len(tracked)}/{MAX_TRACKED}","btc_test":test,"threshold":5,"modes":["regular","scalp"]})

@app.route("/backup-now")
def backup_now():
    if not session.get("user"): return redirect("/login")
    save_json(SYSTEM_FILE, load_json(SYSTEM_FILE, dict))
    return redirect("/dashboard")

@app.route("/master")
def master_redirect():
    return redirect("/creator") if session.get("user")=="admin@agent35.com" else redirect("/login")

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000)
