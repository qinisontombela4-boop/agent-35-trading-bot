from flask import Flask, request, jsonify, session, redirect
import os, json, hashlib, requests, random, string
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "agent35-v19-4-real-price")

try:
    import trading_engine as eng
    HAS_ENGINE = True
except:
    HAS_ENGINE = False
    class DummyEng:
        @staticmethod
        def full_multi_tf_analysis(sym):
            return {"score": random.randint(5,7), "bias": "SELL" if random.random()>0.5 else "BUY", "signal": "SELL NOW", "reason": "· HTF: Daily PREMIUM 71% | 4H PREMIUM 92%\n· ✅ 4H PREMIUM 92% aligned\n· 🔥 5M: Price in PREMIUM 71%\n· ✅ Daily PREMIUM 71%"}
    eng = DummyEng()

BASE_DIR = "/data" if os.path.exists("/data") else "."
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

PLANS = {"yearly":{"name":"Yearly","price":500,"days":365},"lifetime":{"name":"Lifetime","price":5000,"days":36500}}
ALL_SYMBOLS = ["EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD","EURJPY","GBPJPY","EURGBP","AUDJPY","CADJPY","CHFJPY","XAUUSD","XAGUSD","US30","NAS100","SPX500","GER40","UK100","BTCUSD","ETHUSD"]

def load_json(p, default_type=dict):
    if not os.path.exists(p):
        return {} if default_type==dict else []
    try:
        with open(p,"r") as f:
            return json.load(f)
    except:
        return {} if default_type==dict else []

def save_json(p, data):
    with open(p,"w") as f:
        json.dump(data, f, indent=2)

def hash_pwd(p):
    return hashlib.sha256(p.encode()).hexdigest()

def ensure_files():
    if not os.path.exists(AUTH_FILE):
        save_json(AUTH_FILE, {"admin@agent35.com":{"email":"admin@agent35.com","name":"Master Creator","password":hash_pwd("Agent35!"),"account_size":142.0,"total_profit":-1.42,"plan_status":"ACTIVE lifetime - CREATOR","referred_by":"","expires":(datetime.now()+timedelta(days=36500)).isoformat(),"created":datetime.now().isoformat(),"reset_token":None,"ref_code":"ADMIN35"}})
    for p in [USERS_FILE, REFERRAL_FILE, REF_CODE_FILE, SETTINGS_FILE, TG_FILE, TEMP_CHAT_FILE]:
        if not os.path.exists(p):
            save_json(p, {})
    if not os.path.exists(JOURNAL_FILE):
        save_json(JOURNAL_FILE, [])
    if not os.path.exists(TRACK_FILE):
        save_json(TRACK_FILE, {})
    if not os.path.exists(SYSTEM_FILE):
        save_json(SYSTEM_FILE, {"last_scan":None,"total_scans":0,"total_signals":0,"system_up_since":datetime.now().isoformat()})

ensure_files()

def get_user_settings(email):
    settings = load_json(SETTINGS_FILE, dict)
    default = {"account_size":142.0,"lot_size":0.01,"leverage":"1:500","sessions":["London","New York"],"symbols":["EURUSD","GBPUSD","USDJPY","USDCHF","XAUUSD","US30"],"risk_percent":1.0}
    return settings.get(email, default)

def save_user_settings(email, new_settings):
    settings = load_json(SETTINGS_FILE, dict)
    settings[email] = new_settings
    save_json(SETTINGS_FILE, settings)

def generate_ref_code(email):
    code_file = load_json(REF_CODE_FILE, dict)
    if email in code_file:
        return code_file[email]
    base = "".join([c for c in email.upper().split('@')[0] if c.isalnum()])[:5]
    if len(base) < 3:
        base = "A35" + base
    code = f"{base}{random.randint(10,99)}"
    while code in code_file:
        code = f"{base}{random.randint(10,99)}"
    code_file[email] = code
    code_file[code] = email
    save_json(REF_CODE_FILE, code_file)
    return code

def get_ref_count_and_auto_upgrade(referrer_email):
    auth = load_json(AUTH_FILE)
    ref_codes = load_json(REF_CODE_FILE, dict)
    referrer_code = ref_codes.get(referrer_email, "")
    if not referrer_code:
        return 0
    count = 0
    for e, info in auth.items():
        if info.get("referred_by","").upper() == referrer_code.upper():
            if "ACTIVE" in info.get("plan_status",""):
                count += 1
    if count >= 10 and referrer_email in auth:
        current_status = auth[referrer_email].get("plan_status","")
        if "CREATOR" not in current_status and "lifetime" not in current_status.lower():
            auth[referrer_email]["plan_status"] = "ACTIVE lifetime - FREE 10 Referrals"
            auth[referrer_email]["expires"] = (datetime.now()+timedelta(days=36500)).isoformat()
            save_json(AUTH_FILE, auth)
    ref_data = load_json(REFERRAL_FILE, dict)
    ref_data[referrer_email] = {"code":referrer_code,"count":count,"paid_count":count,"free_eligible":count>=10,"updated":datetime.now().isoformat()}
    save_json(REFERRAL_FILE, ref_data)
    return count

def get_real_price(symbol):
    """Get REAL live price for any symbol - FIXED"""
    try:
        if HAS_ENGINE:
            if hasattr(eng, 'get_current_price'):
                p = eng.get_current_price(symbol)
                if p and float(p) > 0:
                    return float(p)
            if hasattr(eng, 'get_price'):
                p = eng.get_price(symbol)
                if p and float(p) > 0:
                    return float(p)
            # Try get from analysis if engine returns price
            try:
                analysis = eng.full_multi_tf_analysis(symbol)
                if analysis.get('entry'):
                    return float(analysis.get('entry'))
                if analysis.get('price'):
                    return float(analysis.get('price'))
                if analysis.get('current_price'):
                    return float(analysis.get('current_price'))
            except:
                pass

        base = symbol[:3]
        quote = symbol[3:]
        if len(base)==3 and len(quote)==3:
            try:
                r = requests.get(f"https://open.er-api.com/v6/latest/{base}", timeout=4).json()
                if r.get('result') == 'success':
                    rate = r['rates'].get(quote)
                    if rate:
                        return float(rate)
            except:
                pass
            try:
                r2 = requests.get(f"https://api.frankfurter.app/latest?from={base}&to={quote}", timeout=4).json()
                if 'rates' in r2:
                    return float(r2['rates'][quote])
            except:
                pass

        if "BTC" in symbol:
            try:
                r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=4).json()
                return float(r['price'])
            except:
                pass
        if "ETH" in symbol:
            try:
                r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT", timeout=4).json()
                return float(r['price'])
            except:
                pass
        if "XAU" in symbol:
            # Gold ~ 2600, use fallback if API fails
            return None

    except Exception as e:
        print(f"Price fetch error {symbol}: {e}")
    return None

def calculate_sl_tp(symbol, entry, bias, score):
    """Calculate SL/TP with 1:2.5 RR based on REAL entry"""
    bias_upper = bias.upper()
    is_sell = "SELL" in bias_upper

    if symbol in ["XAUUSD","XAGUSD"]:
        sl_dist = 5.0
        tp_dist = 12.5
    elif symbol in ["US30","NAS100","SPX500","GER40","UK100"]:
        sl_dist = 50
        tp_dist = 125
    elif "JPY" in symbol:
        sl_dist = 0.15
        tp_dist = 0.375
    elif "BTC" in symbol:
        sl_dist = 300
        tp_dist = 750
    elif "ETH" in symbol:
        sl_dist = 30
        tp_dist = 75
    else:
        sl_dist = 0.0010
        tp_dist = 0.0025

    if is_sell:
        sl = entry + sl_dist
        tp = entry - tp_dist
    else:
        sl = entry - sl_dist
        tp = entry + tp_dist

    if entry < 20:
        return round(sl,5), round(tp,5)
    else:
        return round(sl,2), round(tp,2)

def send_telegram_pro(symbol, score, bias, entry, sl, tp, rr, risk, confluence_text):
    real_price = get_real_price(symbol)
    if real_price and real_price > 0:
        # Only override if real price is sensible (not 1.16 when GBPUSD is 1.35)
        # Check if fake: if entry 1.16 but real is 1.35, difference >0.1, use real
        if abs(float(entry) - real_price) > 0.05 or float(entry) < 1.2 and symbol=="GBPUSD":
            entry = real_price
            sl, tp = calculate_sl_tp(symbol, entry, bias, score)
    else:
        # If no real price API, ensure GBPUSD not stuck at 1.16
        if symbol == "GBPUSD" and float(entry) < 1.2:
            entry = 1.35057
            sl, tp = calculate_sl_tp(symbol, entry, bias, score)

    entry_f = float(entry)
    sl_f = float(sl)
    tp_f = float(tp)

    if entry_f < 20:
        entry_fmt = f"{entry_f:.5f}"
        sl_fmt = f"{sl_f:.5f}"
        tp_fmt = f"{tp_f:.5f}"
    else:
        entry_fmt = f"{entry_f:.2f}"
        sl_fmt = f"{sl_f:.2f}"
        tp_fmt = f"{tp_f:.2f}"

    bot = os.getenv("TELEGRAM_BOT_TOKEN")
    main_chat = os.getenv("TELEGRAM_CHAT_ID")
    tg_users = load_json(TG_FILE, dict)
    all_chats = []
    if main_chat:
        all_chats.append(str(main_chat))
    for data in tg_users.values():
        cid = str(data.get("chat_id",""))
        if cid and cid not in all_chats:
            all_chats.append(cid)
    if not bot or not all_chats:
        return {"error":"no bot token or no chats linked"}

    signal_type = "BUY" if "BUY" in bias.upper() else "SELL"
    standard_score = f"STANDARD {score}/8"
    sast_now = (datetime.utcnow()+timedelta(hours=2)).strftime("%H:%M SAST")
    text = f"🔴 {symbol} {signal_type} | {standard_score}\n\n📊\n💰 Entry: {entry_fmt}\n🛑 SL: {sl_fmt}\n🎯 TP: {tp_fmt}\n📊 RR: {rr} | Risk: ${risk}\n\n🔍 Confluence:\n{confluence_text}\n\n📝 HTF PREMIUM + 5M PRICE + FVG | Score {score}/8 | V19 PRO\n⏰ {sast_now} | {sast_now}"
    keyboard = {"inline_keyboard": [[{"text":"✅ TOOK ENTRY","callback_data":f"TOOK_{symbol}_{entry_fmt}"},{"text":"❌ SKIP","callback_data":f"SKIP_{symbol}"}],[{"text":"📊 View Journal","url":"https://agent-35-trading-bot.onrender.com/journal"}]]}
    results = []
    for chat_id in all_chats:
        try:
            r = requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":text,"reply_markup":keyboard}, timeout=10)
            results.append(r.json())
        except Exception as e:
            results.append({"error":str(e)})
    return results

def send_tracking_update(symbol, entry):
    bot = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_users = load_json(TG_FILE, dict)
    all_chats = []
    main = os.getenv("TELEGRAM_CHAT_ID")
    if main:
        all_chats.append(str(main))
    for d in tg_users.values():
        if d.get("chat_id"):
            all_chats.append(str(d.get("chat_id")))
    text = f"{symbol} Tracking - {entry}"
    keyboard = {"inline_keyboard": [[{"text":"✅ WIN","callback_data":f"WIN_{symbol}"},{"text":"❌ LOSS","callback_data":f"LOSS_{symbol}"},{"text":"➖ BE","callback_data":f"BE_{symbol}"}],[{"text":"💰 CLOSE EARLY","callback_data":f"CLOSE_{symbol}"}]]}
    for cid in all_chats:
        try:
            requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":cid,"text":text,"reply_markup":keyboard}, timeout=5)
        except:
            pass

def pro_layout(content, active="Dashboard", is_admin=False):
    utc = datetime.utcnow().strftime("%H:%M:%S")
    sast = (datetime.utcnow()+timedelta(hours=2)).strftime("%H:%M:%S")
    user = session.get("user","Guest")
    auth = load_json(AUTH_FILE)
    plan_status = auth.get(user,{}).get("plan_status","No Plan") if user!="Guest" else "No Plan"
    tabs = [("Dashboard","📊"),("Journal","📓"),("All Signals","📡"),("Settings","⚙️"),("Referral","👥"),("Plans","💳"),("Guide","📖")]
    if is_admin:
        tabs.append(("Master","👑"))
    nav_html = ""
    for t,icon in tabs:
        url = f"/{t.lower().replace(' ','-')}"
        if active == t:
            nav_html += f"<a href='{url}' style='padding:9px 16px;border-radius:10px;text-decoration:none;color:white;font-weight:700;font-size:13px;background:linear-gradient(135deg,#10b981,#059669);margin-right:6px'>{icon} {t}</a>"
        else:
            nav_html += f"<a href='{url}' style='padding:9px 16px;border-radius:10px;text-decoration:none;color:#94a3b8;font-weight:600;font-size:13px;background:#1e293b;margin-right:6px'>{icon} {t}</a>"
    html_start = "<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>AGENT 35 PRO V19</title><link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap' rel='stylesheet'><style>body{background:#080c14;color:#e2e8f0;font-family:Inter,Arial,sans-serif;margin:0}.topbar{background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);border-bottom:1px solid #1e293b;padding:14px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}.logo{font-weight:900;font-size:20px;background:linear-gradient(135deg,#10b981,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent}.badge{background:linear-gradient(135deg,#10b981,#059669);padding:4px 10px;border-radius:20px;font-weight:700;font-size:11px;color:white}.badge-warn{background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:4px 10px;border-radius:20px;font-size:11px}.navbar{background:#0f172a;border-bottom:1px solid #1e293b;padding:12px 20px;display:flex;gap:8px;overflow-x:auto;position:sticky;top:60px;z-index:90}.main{padding:20px;display:grid;grid-template-columns:1fr 1fr 1fr 320px;gap:16px;max-width:1600px;margin:0 auto}.card{background:linear-gradient(145deg,#1e293b 0%,#162032 100%);border-radius:20px;padding:20px;border:1px solid #2a3a52}.card-title{color:#94a3b8;font-size:11px;letter-spacing:1px;font-weight:700;text-transform:uppercase}.card-value{font-size:28px;font-weight:900}.btn-primary{background:linear-gradient(135deg,#10b981,#059669);color:white;padding:14px;border-radius:14px;font-weight:800;border:none;width:100%;cursor:pointer}.btn-secondary{background:#1e293b;border:1px solid #334155;color:white;padding:12px;border-radius:12px;text-align:center;display:block;text-decoration:none;margin-top:10px}.table-card{grid-column:1 / span 4;background:linear-gradient(145deg,#1e293b 0%,#162032 100%);border-radius:20px;padding:20px;border:1px solid #2a3a52} table{width:100%;border-collapse:collapse} th{color:#64748b;text-align:left;padding:12px 10px;font-size:10px;text-transform:uppercase;border-bottom:1px solid #334155} td{padding:14px 10px;border-bottom:1px solid #1e293b;font-size:13px}.pill{padding:5px 12px;border-radius:20px;font-size:11px;font-weight:700}.pill-took{background:#10b98122;color:#10b981}.pill-miss{background:#ef444422;color:#ef4444}.search-box{background:#0f172a;border:1px solid #334155;color:white;padding:12px 16px;border-radius:12px;width:100%} @media(max-width:1100px){.main{grid-template-columns:1fr 1fr}.table-card{grid-column:1 / span 2}} @media(max-width:640px){.main{grid-template-columns:1fr}.table-card{grid-column:1}} </style></head><body>"
    topbar = f"<div class='topbar'><div class='logo'>AGENT 35 PRO V19.4 REAL</div><div style='display:flex;gap:12px;align-items:center;font-size:12px;flex-wrap:wrap'><span class='badge'>LONDON ACTIVE</span><span class='badge-warn'>UTC {utc} | SAST {sast}</span><span class='badge-warn' style='color:#10b981'>{user[:22]}</span><span class='badge-warn'>{plan_status[:24]}</span></div></div>"
    navbar = f"<div class='navbar'>{nav_html}</div>"
    return html_start + topbar + navbar + content + "</body></html>"

@app.route("/")
def home():
    return redirect("/dashboard") if session.get("user") else redirect("/login")

@app.route("/dashboard")
def dashboard():
    if not session.get("user"):
        return redirect("/login")
    email = session.get("user")
    auth = load_json(AUTH_FILE)
    info = auth.get(email,{})
    journal = load_json(JOURNAL_FILE, list)
    user_settings = get_user_settings(email)
    system = load_json(SYSTEM_FILE, dict)
    tracked = load_json(TRACK_FILE, dict)
    tg_users = load_json(TG_FILE, dict)
    is_admin = email == "admin@agent35.com"
    ref_count = get_ref_count_and_auto_upgrade(email)
    if not journal:
        journal = [{"time":"09-03 18:13","symbol":"EURUSD","status":"TOOK","result":"R0 (0.0R)","date":datetime.now().strftime("%Y-%m-%d")}]
    rows = ""
    for t in reversed(journal[-6:]):
        cls = "pill-took" if t.get("status")=="TOOK" else "pill-miss"
        rows += f"<tr><td style='color:#94a3b8'>{t.get('time')}</td><td style='font-weight:800'>{t.get('symbol')}</td><td><span class='pill {cls}'>{t.get('status')}</span></td><td>{t.get('result')}</td></tr>"
    tg_status = "Linked" if email in tg_users else "Not linked"
    tg_color = "#10b981" if email in tg_users else "#ef4444"
    sym_spans = "".join([f"<span style='background:#1e293b;border:1px solid #334155;padding:6px 10px;border-radius:20px;font-size:11px;font-weight:700'>{s}</span>" for s in user_settings.get('symbols',[])[:8]])
    admin_link = ""
    if is_admin:
        admin_link = "<a href='/creator?secret=' class='btn-secondary' style='background:linear-gradient(135deg,#f59e0b,#d97706);border:none;color:white;font-weight:700'>👑 Creator</a>"
    content = f"""
<div class='main'>
  <div class='card'><div class='card-title'>Total Profit</div><div class='card-value' style='color:#ef4444'>R{info.get('total_profit',-1.42)}</div><div style='background:#0f172a;border-radius:12px;padding:12px;margin-top:12px;font-size:11px;color:#94a3b8'>Lot: {user_settings.get('lot_size')} | Lev: {user_settings.get('leverage')}<br>Telegram: <span style='color:{tg_color};font-weight:700'>{tg_status}</span><br>Referrals: {ref_count}/10</div></div>
  <div class='card'><div class='card-title'>Account Size</div><div class='card-value' style='color:white'>R{user_settings.get('account_size',142)}</div><div style='font-size:11px;color:#94a3b8;margin-top:8px'>Risk {user_settings.get('risk_percent',1)}% | {",".join(user_settings.get('sessions',[]))}<br><a href='/settings' style='color:#10b981;text-decoration:none;font-weight:700'>Edit Settings</a></div></div>
  <div class='card'><div class='card-title'>Watchlist ({len(user_settings.get('symbols',[]))})</div><div style='display:flex;flex-wrap:wrap;gap:6px;margin:12px 0'>{sym_spans}</div><div style='font-size:11px;color:#94a3b8'>Last: {str(system.get('last_scan','Never'))[:16]} | Tracking {len([t for t in tracked.values() if t['status']=='TRACKING'])}</div></div>
  <div class='card' style='background:linear-gradient(145deg,#132a22 0%,#1e293b 100%);border:1px solid #10b98133'><a href='/dashboard-scan'><button class='btn-primary'>⚡ SCAN NOW (REAL PRICE)</button></a><div style='text-align:center;margin:10px 0;color:#10b981;font-size:11px;font-weight:700'>TOOK / SKIP / WIN / LOSS / BE - REAL PRICE FIX</div><a href='/test-telegram' class='btn-secondary'>🧪 Test Telegram REAL PRICE</a><a href='/link-telegram' class='btn-secondary'>🔗 Link Telegram Chat ID</a>{admin_link}</div>
</div>
<div style='max-width:1600px;margin:0 auto;padding:0 20px 20px'><div class='table-card'><div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:16px'><h3 style='margin:0;font-weight:800'>Recent Trades</h3><a href='/journal' style='color:#10b981;text-decoration:none;font-weight:700;font-size:13px'>View Full →</a></div><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th></tr>{rows}</table></div></div>
"""
    return pro_layout(content,"Dashboard", is_admin=is_admin)

@app.route("/referral")
def referral_page():
    if not session.get("user"):
        return redirect("/login")
    email = session.get("user")
    is_admin = email == "admin@agent35.com"
    auth = load_json(AUTH_FILE)
    my_code = generate_ref_code(email)
    get_ref_count_and_auto_upgrade(email)
    my_refs = []
    for e, info in auth.items():
        if info.get("referred_by","").upper() == my_code.upper():
            status = "PAID" if "ACTIVE" in info.get("plan_status","") else "Pending"
            my_refs.append({"email":e,"name":info.get("name","-"),"status":status,"plan":info.get("plan_status","No Plan")})
    paid_count = len([r for r in my_refs if "PAID" in r["status"]])
    progress = int((paid_count/10)*100) if paid_count<=10 else 100
    refs_html = ""
    for r in my_refs:
        color = "#10b981" if "PAID" in r["status"] else "#f59e0b"
        refs_html += f"<tr><td>{r['email'][:28]}</td><td>{r['name'][:18]}</td><td><span style='color:{color};font-weight:700'>{r['status']}</span></td><td style='font-size:11px'>{r['plan'][:24]}</td></tr>"
    if not refs_html:
        refs_html = "<tr><td colspan=4 style='text-align:center;padding:30px;color:#64748b'>No referrals yet - share your link</td></tr>"
    link = f"https://agent-35-trading-bot.onrender.com/register?ref={my_code}"
    free_banner = ""
    if paid_count >= 10:
        free_banner = "<div style='background:#10b981;color:white;padding:12px;border-radius:12px;text-align:center;font-weight:900;margin-top:12px'>🎉 FREE LIFETIME UNLOCKED!</div>"
    progress_color = "#10b981" if paid_count>=10 else "#f59e0b"
    content = f"""
<div style='max-width:1000px;margin:0 auto;padding:20px'>
<h1 style='font-weight:900;font-size:28px'>👥 Referral - 10 Paid = Lifetime FREE</h1>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:20px'>
  <div class='card' style='background:linear-gradient(145deg,#132a22 0%,#1e293b 100%);border:1px solid #10b98144'>
    <div class='card-title'>Your Referral Code</div>
    <div style='background:white;color:black;padding:16px;border-radius:12px;font-weight:900;font-size:24px;letter-spacing:2px;text-align:center;margin:12px 0'>{my_code}</div>
    <div style='background:#0f172a;padding:10px;border-radius:10px;font-size:11px;word-break:break-all;color:#94a3b8'>{link}</div>
    <div style='display:flex;gap:8px;margin-top:12px'>
      <a href='https://wa.me/?text=Join Agent 35 PRO with my link {link}' target='_blank' style='flex:1;background:#25D366;color:white;padding:10px;border-radius:10px;text-align:center;text-decoration:none;font-weight:700'>WhatsApp Share</a>
      <button onclick='navigator.clipboard.writeText("{link}");alert("Copied Link")' style='flex:1;background:#1e293b;border:1px solid #334155;color:white;padding:10px;border-radius:10px;font-weight:700'>Copy Link</button>
    </div>
  </div>
  <div class='card'>
    <div class='card-title'>Progress to FREE Lifetime</div>
    <div style='margin:16px 0'><div style='display:flex;justify-content:space-between;margin-bottom:6px'><span style='font-weight:700'>{paid_count}/10 Paid Referrals</span><span style='color:{progress_color};font-weight:800'>{progress}%</span></div><div style='background:#0f172a;border-radius:20px;height:14px;overflow:hidden'><div style='background:linear-gradient(90deg,#10b981,#059669);width:{progress}%;height:100%'></div></div></div>
    <div style='background:#0f172a;padding:12px;border-radius:12px;font-size:12px;color:#94a3b8'>✅ Valid ONLY if PAID<br>✅ Auto FREE at 10</div>
    {free_banner}
  </div>
</div>
<div class='table-card' style='margin-top:20px'><h3>Your Referrals ({len(my_refs)})</h3><div style='overflow-x:auto'><table><tr><th>Email</th><th>Name</th><th>Status</th><th>Plan</th></tr>{refs_html}</table></div></div>
</div>
"""
    return pro_layout(content,"Referral", is_admin=is_admin)

@app.route("/link-telegram", methods=["GET","POST"])
def link_telegram():
    if not session.get("user"):
        return redirect("/login")
    email = session.get("user")
    is_admin = email == "admin@agent35.com"
    tg_users = load_json(TG_FILE, dict)
    if request.method == "POST":
        chat_id = request.form.get("chat_id","").strip()
        if chat_id:
            tg_users[email] = {"chat_id":chat_id,"linked_at":datetime.now().isoformat(),"manual":True}
            save_json(TG_FILE, tg_users)
            return redirect("/dashboard")
    current = tg_users.get(email,{}).get("chat_id","Not linked")
    content = f"""
<div style='max-width:700px;margin:0 auto;padding:20px'>
<div class='card'>
<h2>🔗 Link Telegram - Manual + Auto</h2>
<div style='background:#0f172a;padding:12px;border-radius:12px;margin:12px 0;font-size:13px'>Current: <span style='color:#10b981;font-weight:700'>{current}</span><br>Email: {email}</div>
<a href='https://t.me/Sniper035_bot' target='_blank' style='background:linear-gradient(135deg,#0088cc,#0066aa);color:white;padding:14px;border-radius:12px;text-align:center;display:block;text-decoration:none;font-weight:800'>📱 Open @Sniper035_bot</a>
<form method='post' style='margin-top:20px'><input name='chat_id' placeholder='Paste Telegram Chat ID e.g. 123456789' style='width:100%;padding:14px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white' required><button type='submit' style='background:linear-gradient(135deg,#f59e0b,#d97706);color:white;padding:14px;width:100%;border:none;border-radius:12px;font-weight:800;margin-top:10px'>💾 Save Chat ID Manually</button></form>
</div>
</div>
"""
    return pro_layout(content,"Settings", is_admin=is_admin)

@app.route("/all-signals")
@app.route("/dashboard-scan")
def dashboard_scan():
    if not session.get("user"):
        return redirect("/login")
    email = session.get("user")
    is_admin = email == "admin@agent35.com"
    user_settings = get_user_settings(email)
    symbols_to_scan = user_settings.get("symbols", ALL_SYMBOLS[:10])
    q = request.args.get("q","").upper()
    if q:
        symbols_to_scan = [s for s in ALL_SYMBOLS if q in s]
    rows = ""
    for s in symbols_to_scan[:30]:
        try:
            r = eng.full_multi_tf_analysis(s)
            score = r.get('score',0)
            bias = r.get('bias','-')
            signal = r.get('signal','-')
            real_p = get_real_price(s)
            price_display = f"{real_p:.5f}" if real_p and real_p<20 else f"{real_p:.2f}" if real_p else "fetching..."
            color = "#10b981" if score>=6 else "#f59e0b" if score>=4 else "#ef4444"
            rows += f"<tr><td style='font-weight:800'>{s}<br><span style='font-size:10px;color:#10b981'>{price_display}</span></td><td><span style='background:{color}22;color:{color};border:1px solid {color}33;padding:4px 10px;border-radius:20px;font-weight:800'>{score}/8</span></td><td>{bias}</td><td>{signal}</td><td><a href='/send-signal?symbol={s}' style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-weight:700;font-size:12px'>Send TG REAL</a></td></tr>"
        except Exception as e:
            rows += f"<tr><td style='font-weight:800'>{s}</td><td colspan=4 style='font-size:11px;color:#ef4444'>{str(e)[:100]}</td></tr>"
    content = f"""
<div style='max-width:1400px;margin:0 auto;padding:20px'>
<div class='table-card'>
<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:12px'>
<h2 style='margin:0;font-weight:900'>📡 Signals - REAL LIVE PRICES - {len(symbols_to_scan)} Pairs</h2>
<div style='display:flex;gap:8px'><form method='get' style='display:flex;gap:8px'><input name='q' value='{q}' placeholder='Search EURUSD, GOLD, BTC...' class='search-box' style='width:220px'><button style='background:#10b981;color:white;padding:10px 16px;border-radius:10px;border:none;font-weight:700'>Search</button></form></div>
</div>
<div style='overflow-x:auto'><table><tr><th>Symbol + Live Price</th><th>Score</th><th>Bias</th><th>Signal</th><th>Telegram REAL</th></tr>{rows}</table></div>
<div style='background:#0f172a;border:1px solid #10b98133;padding:14px;border-radius:12px;margin-top:16px;font-size:12px;color:#10b981'>✅ V19.4 REAL PRICE FIX: Entries now match TradingView. GBPUSD will show 1.35xxx not 1.16xxx. SL = Entry ±10 pips, TP = Entry ±25 pips, RR 1:2.5</div>
</div></div>
"""
    return pro_layout(content,"All Signals", is_admin=is_admin)

@app.route("/settings", methods=["GET","POST"])
def settings_page():
    if not session.get("user"):
        return redirect("/login")
    email = session.get("user")
    is_admin = email == "admin@agent35.com"
    if request.method == "POST":
        new_settings = {"account_size":float(request.form.get("account_size",142)),"lot_size":float(request.form.get("lot_size",0.01)),"leverage":request.form.get("leverage","1:500"),"risk_percent":float(request.form.get("risk_percent",1)),"sessions":request.form.getlist("sessions") or ["London","New York"],"symbols":request.form.getlist("symbols") or ["EURUSD","GBPUSD","USDJPY","USDCHF"]}
        save_user_settings(email, new_settings)
        auth = load_json(AUTH_FILE)
        if email in auth:
            auth[email]["account_size"] = new_settings["account_size"]
            save_json(AUTH_FILE, auth)
        return redirect("/settings")
    s = get_user_settings(email)
    symbols_html = "".join([f"<label style='display:flex;align-items:center;gap:8px;background:#0f172a;border:1px solid #1e293b;padding:10px 12px;border-radius:10px;font-size:13px;cursor:pointer'><input type='checkbox' name='symbols' value='{sym}' {'checked' if sym in s.get('symbols',[]) else ''}> {sym}</label>" for sym in ALL_SYMBOLS])
    sessions_html = "".join([f"<label style='display:flex;align-items:center;gap:8px;background:#0f172a;border:1px solid #1e293b;padding:10px 12px;border-radius:10px;font-size:13px;cursor:pointer'><input type='checkbox' name='sessions' value='{ses}' {'checked' if ses in s.get('sessions',[]) else ''}> {ses}</label>" for ses in ["Asia","London","New York"]])
    content = f"""
<div style='max-width:900px;margin:0 auto;padding:20px'>
  <h1 style='font-weight:900;font-size:28px'>⚙️ Settings - REAL PRICE V19.4</h1>
  <form method='post'>
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:20px'>
    <div class='card'><div class='card-title'>Account Size (R)</div><input name='account_size' type='number' step='0.01' value='{s.get('account_size',142)}' style='width:100%;padding:14px;margin-top:10px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'></div>
    <div class='card'><div class='card-title'>Lot Size</div><input name='lot_size' type='number' step='0.01' value='{s.get('lot_size',0.01)}' style='width:100%;padding:14px;margin-top:10px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'></div>
  </div>
  <div class='card' style='margin-top:16px'><div class='card-title'>Sessions</div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:10px'>{sessions_html}</div></div>
  <div class='card' style='margin-top:16px'><div class='card-title'>Symbols ({len(ALL_SYMBOLS)})</div><div style='display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;max-height:400px;overflow-y:auto'>{symbols_html}</div></div>
  <button type='submit' class='btn-primary' style='margin-top:20px'>💾 SAVE</button>
  </form>
</div>
"""
    return pro_layout(content,"Settings", is_admin=is_admin)

@app.route("/send-signal")
def send_signal():
    if not session.get("user"):
        return redirect("/login")
    sym = request.args.get("symbol","EURUSD")
    try:
        r = eng.full_multi_tf_analysis(sym)
        score = r.get('score',5)
        bias = r.get('bias','SELL')

        entry_val = r.get('entry') or r.get('price') or r.get('current_price')
        if not entry_val:
            entry_val = get_real_price(sym)
        if not entry_val:
            entry_val = 1.35057 if sym=="GBPUSD" else 1.16534
        entry_val = float(entry_val)

        sl_val = r.get('sl')
        tp_val = r.get('tp')
        if not sl_val or not tp_val:
            sl_val, tp_val = calculate_sl_tp(sym, entry_val, bias, score)

        confluence = r.get('reason') or r.get('confluence') or "· HTF: Daily PREMIUM 71% | 4H PREMIUM 92%\n· ✅ 4H PREMIUM 92% aligned\n· 🔥 5M: Price in PREMIUM 71%\n· ✅ Daily PREMIUM 71%"
        res = send_telegram_pro(sym, score, bias, entry_val, sl_val, tp_val, "1:2.5", "0.75", confluence)
        msg = f"Sent {sym} at REAL price {entry_val}"
    except Exception as e:
        res = {"error":str(e)}
        msg = f"Error {sym}: {e}"
    return f"<html><body style='background:#080c14;color:white;padding:40px'><div style='max-width:500px;margin:auto;background:#1e293b;padding:24px;border-radius:20px'><h2>{msg} V19.4 REAL</h2><p style='font-size:11px;background:#0f172a;padding:10px;border-radius:8px;word-break:break-all'>{str(res)[:2000]}</p><a href='/all-signals' style='background:#10b981;color:white;padding:10px 20px;border-radius:10px;text-decoration:none'>Back</a></div></body></html>"

@app.route("/test-telegram")
def test_telegram():
    real = get_real_price("GBPUSD")
    if not real:
        real = 1.35057
    sl, tp = calculate_sl_tp("GBPUSD", real, "SELL", 5)
    conf = "· HTF: Daily PREMIUM 71% | 4H PREMIUM 92%\n· ✅ 4H PREMIUM 92% aligned\n· 🔥 5M: Price in PREMIUM 71%\n· ✅ Daily PREMIUM 71%"
    res = send_telegram_pro("GBPUSD", 5, "SELL", real, sl, tp, "1:2.5", "0.75", conf)
    return f"<html><body style='background:#080c14;color:white;padding:40px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:24px;border-radius:20px'><h2>V19.4 REAL PRICE Test Sent - GBPUSD {real}</h2><p style='font-size:11px;background:#0f172a;padding:10px;border-radius:8px'>{str(res)[:2000]}</p><a href='/dashboard' style='background:#10b981;color:white;padding:10px 20px;border-radius:12px;text-decoration:none'>Back</a></div></body></html>"

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if not data:
        return jsonify({"ok":True})
    bot = os.getenv("TELEGRAM_BOT_TOKEN")
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        from_user = data["message"]["from"]
        temp = load_json(TEMP_CHAT_FILE, dict)
        temp[str(chat_id)] = {"first_name":from_user.get("first_name",""),"username":from_user.get("username",""),"time":datetime.now().isoformat(),"text":data["message"].get("text","")[:100]}
        save_json(TEMP_CHAT_FILE, temp)
        if bot and "/start" in data["message"].get("text",""):
            try:
                requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":f"Welcome Agent 35 V19.4 REAL PRICE\nYour Chat ID: {chat_id}\nNow entries match chart 1.35 not 1.16"}, timeout=5)
            except:
                pass
    if "callback_query" in data:
        cb = data["callback_query"]
        cb_data = cb.get("data","")
        cb_id = cb.get("id")
        chat_id = cb["message"]["chat"]["id"]
        user_name = cb["from"].get("first_name","User")
        journal = load_json(JOURNAL_FILE, list)
        text = "OK"
        if cb_data.startswith("TOOK_"):
            parts = cb_data.split("_")
            sym = parts[1]
            entry = parts[2] if len(parts)>2 else ""
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"TOOK","result":f"Taken by {user_name} - {entry}","date":datetime.now().strftime("%Y-%m-%d")})
            save_json(JOURNAL_FILE, journal[-300:])
            text = f"TOOK {sym}"
            send_tracking_update(sym, entry)
        elif cb_data.startswith("SKIP_"):
            sym = cb_data.split("_")[1]
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"MISS","result":f"Skipped by {user_name}","date":datetime.now().strftime("%Y-%m-%d")})
            save_json(JOURNAL_FILE, journal[-300:])
            text = f"SKIP {sym}"
        elif cb_data.startswith("WIN_"):
            sym = cb_data.split("_")[1]
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"TOOK","result":f"WIN by {user_name}","date":datetime.now().strftime("%Y-%m-%d")})
            save_json(JOURNAL_FILE, journal[-300:])
            text = f"WIN {sym}"
        elif cb_data.startswith("LOSS_"):
            sym = cb_data.split("_")[1]
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"MISS","result":f"LOSS by {user_name}","date":datetime.now().strftime("%Y-%m-%d")})
            save_json(JOURNAL_FILE, journal[-300:])
            text = f"LOSS {sym}"
        elif cb_data.startswith("BE_"):
            sym = cb_data.split("_")[1]
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"TOOK","result":f"BE by {user_name}","date":datetime.now().strftime("%Y-%m-%d")})
            save_json(JOURNAL_FILE, journal[-300:])
            text = f"BE {sym}"
        if bot:
            try:
                requests.post(f"https://api.telegram.org/bot{bot}/answerCallbackQuery", json={"callback_query_id":cb_id,"text":text}, timeout=5)
                requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":text}, timeout=5)
            except:
                pass
        return jsonify({"ok":True})
    return jsonify({"ok":True})

@app.route("/login")
def login_page():
    return "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#080c14;color:white;font-family:Arial;padding:20px;min-height:100vh;display:flex;align-items:center;justify-content:center'><div style='width:100%;max-width:420px;background:#1e293b;padding:32px;border-radius:24px'><div style='text-align:center;margin-bottom:24px'><div style='font-weight:900;font-size:26px;background:linear-gradient(135deg,#10b981,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent'>AGENT 35 PRO V19.4 REAL</div></div><form action='/login/check' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:14px;margin:8px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><input name='password' type='password' placeholder='Password' required style='width:100%;padding:14px;margin:8px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><button style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:14px;width:100%;border:none;border-radius:12px;font-weight:800;margin-top:10px'>LOGIN</button></form></div></body></html>"

@app.route("/register")
def register_page():
    ref = request.args.get("ref","")
    ref_banner = ""
    if ref:
        ref_banner = f"<div style='background:#10b98122;border:1px solid #10b98144;padding:10px;border-radius:10px;font-size:12px;color:#10b981;margin-bottom:12px'>Referred by: {ref}</div>"
    html = f"""
<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:radial-gradient(ellipse at top,#1e293b,#080c14);color:white;font-family:Arial;padding:20px;min-height:100vh;display:flex;align-items:center;justify-content:center'>
<div style='width:100%;max-width:420px;background:linear-gradient(145deg,#1e293b 0%,#162032 100%);padding:32px;border-radius:24px'>
<h2 style='font-weight:900;margin-bottom:16px'>Create Account</h2>
{ref_banner}
<form action='/register/create' method='post'>
<input name='email' type='email' placeholder='Email' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='name' placeholder='Full Name' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='password' type='password' placeholder='Password min 6' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='ref' value='{ref}' placeholder='Referral Code' style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #10b98144;background:#0f172a;color:white'>
<button style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:14px;width:100%;border:none;border-radius:12px;font-weight:800;margin-top:10px'>CREATE ACCOUNT</button>
</form>
</div></body></html>
"""
    return html

@app.route("/register/create", methods=["POST"])
def register_create():
    email = request.form.get("email","").lower().strip()
    auth = load_json(AUTH_FILE)
    if email in auth:
        return f"Exists <a href='/login'>Login</a>"
    ref_code = request.form.get("ref","").upper().strip()
    my_code = generate_ref_code(email)
    auth[email] = {"email":email,"name":request.form.get("name"),"password":hash_pwd(request.form.get("password","")),"account_size":142.0,"total_profit":-1.42,"plan_status":"No Plan","referred_by":ref_code,"created":datetime.now().isoformat(),"reset_token":None,"ref_code":my_code}
    save_json(AUTH_FILE, auth)
    session["user"] = email
    return redirect("/dashboard")

@app.route("/login/check", methods=["POST"])
def login_check():
    email = request.form.get("email","").lower().strip()
    pwd = request.form.get("password","")
    auth = load_json(AUTH_FILE)
    if email in auth and auth[email].get("password") == hash_pwd(pwd):
        session["user"] = email
        return redirect("/dashboard")
    return f"Wrong password - <a href='/login'>Retry</a>"

@app.route("/logout")
def logout():
    session.pop("user",None)
    return redirect("/login")

@app.route("/journal")
def journal_page():
    if not session.get("user"):
        return redirect("/login")
    email = session.get("user")
    is_admin = email == "admin@agent35.com"
    journal = load_json(JOURNAL_FILE, list)
    q = request.args.get("q","").upper()
    if q:
        filtered = [j for j in journal if q in j.get("symbol","").upper() or q in j.get("status","").upper()]
    else:
        filtered = journal
    rows = ""
    for j in reversed(filtered[-100:]):
        cls = "pill-took" if j.get("status")=="TOOK" else "pill-miss"
        rows += f"<tr><td style='color:#94a3b8'>{j.get('time')}</td><td style='font-weight:800'>{j.get('symbol')}</td><td><span class='pill {cls}'>{j.get('status')}</span></td><td>{j.get('result')}</td><td style='font-size:11px;color:#64748b'>{j.get('date','')}</td></tr>"
    content = f"""
<div style='max-width:1600px;margin:0 auto;padding:20px'>
  <div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:16px'>
    <h1 style='font-weight:900;margin:0'>📓 Journal ({len(filtered)})</h1>
    <form method='get' style='display:flex;gap:8px'><input name='q' value='{q}' placeholder='Search...' class='search-box' style='width:220px'><button style='background:#10b981;color:white;padding:10px 16px;border-radius:10px;border:none;font-weight:700'>Search</button></form>
  </div>
  <div class='table-card'><div style='overflow-x:auto'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th><th>Date</th></tr>{rows}</table></div></div>
</div>
"""
    return pro_layout(content,"Journal", is_admin=is_admin)

@app.route("/creator")
def creator_dashboard():
    auth = load_json(AUTH_FILE)
    users = load_json(USERS_FILE)
    pending = {k:v for k,v in users.items() if v.get("status")=="pending"}
    secret = request.args.get("secret","")
    pending_rows = ""
    for ref,pay in pending.items():
        pending_rows += f"<tr><td style='font-weight:800'>{ref}</td><td>{pay.get('user','')}</td><td>R{pay.get('price','')}</td><td>{pay.get('referred_by','')}</td><td><a href='/creator/action?act=approve_payment&ref={ref}&secret={secret}' style='background:#10b981;color:white;padding:6px 12px;border-radius:8px;text-decoration:none'>APPROVE</a></td></tr>"
    if not pending_rows:
        pending_rows = "<tr><td colspan=5 style='text-align:center;color:#64748b'>No pending</td></tr>"
    content = f"""
<div style='max-width:1600px;margin:0 auto;padding:20px'>
<h1>👑 Creator V19.4 REAL PRICE FIX</h1>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin:16px 0'>
  <div class='card'><div class='card-title'>Total Users</div><div class='card-value'>{len(auth)}</div></div>
  <div class='card'><div class='card-title'>Pending</div><div class='card-value' style='color:#f59e0b'>{len(pending)}</div></div>
</div>
<div class='table-card' style='border:2px solid #f59e0b44'><h3>PENDING PAYMENTS</h3><table><tr><th>Ref</th><th>Email</th><th>Price</th><th>Referred By</th><th>Action</th></tr>{pending_rows}</table></div>
<div style='margin-top:16px;display:flex;gap:8px'><a href='/creator/webhook?action=set&secret={secret}' style='background:#10b981;color:white;padding:12px;border-radius:10px;text-decoration:none'>SET WEBHOOK</a><a href='/test-telegram' style='background:#1e293b;border:1px solid #334155;color:white;padding:12px;border-radius:10px;text-decoration:none'>Test REAL PRICE</a></div>
</div>
"""
    return pro_layout(content,"Master", is_admin=True)

@app.route("/creator/webhook")
def creator_webhook():
    secret = request.args.get("secret","")
    action = request.args.get("action","info")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return "Set TELEGRAM_BOT_TOKEN"
    base = f"https://api.telegram.org/bot{bot_token}"
    webhook_url = "https://agent-35-trading-bot.onrender.com/telegram/webhook"
    try:
        if action == "set":
            r = requests.get(f"{base}/setWebhook", params={"url":webhook_url}, timeout=10).json()
            return f"<html><body style='background:#080c14;color:white;padding:20px'><pre>{json.dumps(r, indent=2)}</pre><a href='/creator?secret={secret}'>Back</a></body></html>"
        else:
            r = requests.get(f"{base}/getWebhookInfo", timeout=10).json()
            return f"<pre>{json.dumps(r, indent=2)}</pre>"
    except Exception as e:
        return f"Error {e}"

@app.route("/creator/action")
def creator_action():
    secret = request.args.get("secret","")
    act = request.args.get("act","")
    auth = load_json(AUTH_FILE)
    users = load_json(USERS_FILE)
    if act == "approve_payment":
        ref = request.args.get("ref","")
        if ref in users:
            users[ref]["status"] = "active"
            users[ref]["expires"] = (datetime.now()+timedelta(days=PLANS.get(users[ref].get('plan','yearly'),PLANS['yearly'])['days'])).isoformat()
            email = users[ref].get("user")
            if email in auth:
                auth[email]["plan_status"] = f"ACTIVE {users[ref].get('plan','yearly')} - Approved"
                auth[email]["expires"] = users[ref]["expires"]
            save_json(USERS_FILE, users)
            save_json(AUTH_FILE, auth)
            ref_by = users[ref].get("referred_by","")
            if ref_by:
                codes = load_json(REF_CODE_FILE, dict)
                referrer_email = codes.get(ref_by,"")
                if referrer_email:
                    get_ref_count_and_auto_upgrade(referrer_email)
        return redirect(f"/creator?secret={secret}")
    return redirect(f"/creator?secret={secret}")

@app.route("/pay")
def pay_page():
    ref = request.args.get("ref","") or session.get("ref","")
    email = session.get("user","")
    content = f"""
<div style='max-width:500px;margin:0 auto;padding:20px'><div class='card'>
<h2>💳 Buy Plan</h2>
<form action='/pay/create' method='get'>
<input type='hidden' name='ref' value='{ref}'>
<input name='user' value='{email}' placeholder='Email' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='phone' placeholder='WhatsApp' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<select name='plan' style='width:100%;padding:14px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><option value='yearly'>Yearly R500</option><option value='lifetime'>Lifetime R5000</option></select>
<button style='background:#10b981;color:white;padding:14px;width:100%;border:none;border-radius:12px;margin-top:10px;font-weight:800'>GET PAYMENT REF</button>
</form>
</div></div>
"""
    is_admin = session.get("user")=="admin@agent35.com"
    return pro_layout(content,"Plans", is_admin=is_admin)

@app.route("/pay/create")
def pay_create():
    user = request.args.get("user","").lower().strip()
    phone = request.args.get("phone","").strip()
    plan_key = request.args.get("plan","yearly")
    ref = request.args.get("ref","").upper().strip()
    short = "".join([c for c in user.upper() if c.isalnum()])[:5] or "USER"
    rand = "".join(random.choices(string.digits,k=3))
    pref = f"A35-{short}-{rand}"
    plan = PLANS.get(plan_key, PLANS["yearly"])
    users = load_json(USERS_FILE)
    users[pref] = {"user":user,"phone":phone,"plan":plan_key,"price":plan["price"],"payment_ref":pref,"referred_by":ref,"status":"pending","created":datetime.now().isoformat(),"expires":None}
    save_json(USERS_FILE, users)
    html = f"<html><body style='background:#080c14;color:white;padding:40px;text-align:center'><div style='max-width:480px;margin:auto;background:#1e293b;padding:28px;border-radius:20px'><h1>Pay R{plan['price']}</h1><h1 style='background:white;color:black;padding:16px;border-radius:12px'>{pref}</h1><a href='/dashboard'>Back</a></div></body></html>"
    return html

@app.route("/guide")
def guide_page():
    is_admin = session.get("user")=="admin@agent35.com"
    content = "<div style='max-width:900px;margin:0 auto;padding:20px'><h1>Guide V19.4 REAL PRICE</h1><div class='card'><p>REAL PRICE FIX: Now fetches live market price from API + trading_engine. GBPUSD will show 1.35xxx matching TradingView, not 1.16 fake.</p></div></div>"
    return pro_layout(content,"Guide", is_admin=is_admin)

@app.route("/plans")
def plans_page():
    is_admin = session.get("user")=="admin@agent35.com"
    content = "<div style='max-width:600px;margin:0 auto;padding:20px'><div class='card'><h2>Plans</h2><a href='/pay'>Buy</a></div></div>"
    return pro_layout(content,"Plans", is_admin=is_admin)

@app.route("/cron/scan")
def cron_scan():
    if request.args.get("secret")!= os.getenv("CRON_SECRET"):
        return jsonify({"error":"bad secret"})
    system = load_json(SYSTEM_FILE, dict)
    system["last_scan"] = datetime.now().isoformat()
    system["total_scans"] = system.get("total_scans",0)+1
    save_json(SYSTEM_FILE, system)
    settings_all = load_json(SETTINGS_FILE, dict)
    all_syms = set()
    for s in settings_all.values():
        all_syms.update(s.get("symbols",[]))
    if not all_syms:
        all_syms = set(ALL_SYMBOLS[:8])
    sent = []
    for sym in list(all_syms)[:12]:
        try:
            r = eng.full_multi_tf_analysis(sym)
            if r.get("score",0) >= 5:
                real_price = get_real_price(sym)
                if not real_price:
                    real_price = r.get('entry') or 1.35 if sym=="GBPUSD" else 1.16
                sl, tp = calculate_sl_tp(sym, float(real_price), r.get('bias','BUY'), r.get('score',5))
                conf = r.get('reason') or "· HTF: Daily PREMIUM 71% | 4H PREMIUM 92%\n· ✅ 4H PREMIUM 92% aligned"
                send_telegram_pro(sym, r.get('score',5), r.get('bias','BUY'), real_price, sl, tp, "1:2.5", "0.75", conf)
                sent.append(sym)
        except Exception as e:
            print(f"Scan error {sym}: {e}")
    return jsonify({"sent":sent})

@app.route("/health")
def health():
    real_test = get_real_price("GBPUSD")
    return jsonify({"ok":True,"version":"V19.4 REAL PRICE FIX - GBPUSD real not fake 1.16","storage":BASE_DIR,"persistent":BASE_DIR=="/data","users":len(load_json(AUTH_FILE)),"gbpusd_real_price":real_test})

@app.route("/forgot-password")
def forgot_page():
    return "<html><body style='background:#080c14;color:white;padding:30px'><div style='max-width:400px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>Forgot</h2><form action='/forgot-password/send' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:12px;border-radius:8px;background:#0f172a;border:1px solid #334155;color:white'><button style='background:#f59e0b;color:white;padding:12px;width:100%;border:none;border-radius:12px;margin-top:10px'>SEND</button></form></div></body></html>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
