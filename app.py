from flask import Flask, request, jsonify, session, redirect
import os, json, hashlib, requests, random, string
from dotenv import load_dotenv
import trading_engine as eng
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "agent35-v18-clean")

BASE_DIR = "/data" if os.path.exists("/data") else "."
AUTH_FILE = os.path.join(BASE_DIR, "auth_users.json")
USERS_FILE = os.path.join(BASE_DIR, "users_data.json")
DATA_FILE = os.path.join(BASE_DIR, "referrals_data.json")
JOURNAL_FILE = os.path.join(BASE_DIR, "journal.json")
TRACK_FILE = os.path.join(BASE_DIR, "tracked_trades.json")
SYSTEM_FILE = os.path.join(BASE_DIR, "system_status.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "user_settings.json")

CAPITEC = {"bank":"Capitec","holder":"Agent 35 Trading Bot","acc":"2586572676","branch":"470010","ref_prefix":"A35"}
PLANS = {"yearly":{"name":"Yearly","price":500,"days":365},"lifetime":{"name":"Lifetime","price":5000,"days":36500}}

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
        save_json(AUTH_FILE, {"admin@agent35.com":{"email":"admin@agent35.com","name":"Master Creator","password":hash_pwd("Agent35!"),"account_size":142.0,"total_profit":-1.42,"plan_status":"ACTIVE lifetime - CREATOR","referred_by":"","expires":(datetime.now()+timedelta(days=36500)).isoformat(),"created":datetime.now().isoformat(),"reset_token":None}})
    for p in [USERS_FILE, DATA_FILE, SETTINGS_FILE]:
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
    default = {"account_size":142.0,"lot_size":0.01,"leverage":"1:500","sessions":["London","New York"],"symbols":["EURUSD","GBPUSD","USDJPY","USDCHF"],"risk_percent":1.0}
    return settings.get(email, default)

def save_user_settings(email, new_settings):
    settings = load_json(SETTINGS_FILE, dict)
    settings[email] = new_settings
    save_json(SETTINGS_FILE, settings)

def send_telegram_signal(symbol, score, bias, signal, sl, tp, reason):
    bot=os.getenv("TELEGRAM_BOT_TOKEN")
    chat=os.getenv("TELEGRAM_CHAT_ID")
    if not bot or not chat:
        return {"error":"no env"}
    text=f"AGENT 35 SIGNAL\n\nSymbol: {symbol}\nScore: {score}/10\nBias: {bias}\nSignal: {signal}\nSL: {sl}\nTP: {tp}\nReason: {reason}\nTime: {datetime.utcnow().strftime('%H:%M')} UTC"
    keyboard={"inline_keyboard":[[{"text":"TAKE TRADE","callback_data":f"TAKE_{symbol}_{score}"},{"text":"MISS","callback_data":f"MISS_{symbol}"}],[{"text":"TRACK TO SL/TP","callback_data":f"TRACK_{symbol}_{sl}_{tp}"}]]}
    try:
        r=requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat,"text":text,"parse_mode":"Markdown","reply_markup":keyboard}, timeout=10)
        return r.json()
    except Exception as e:
        return {"error":str(e)}

def pro_layout(content, active="Dashboard", is_admin=False):
    utc=datetime.utcnow().strftime("%H:%M:%S")
    sast=(datetime.utcnow()+timedelta(hours=2)).strftime("%H:%M:%S")
    user=session.get("user","Guest")
    auth=load_json(AUTH_FILE)
    plan_status=auth.get(user,{}).get("plan_status","No Plan") if user!="Guest" else "No Plan"

    # USER TABS - clean, no Master for normal users
    if is_admin:
        tabs=[("Dashboard","📊"),("Journal","📓"),("All Signals","📡"),("Settings","⚙️"),("Plans","💳"),("Guide","📖"),("Master","👑")]
    else:
        tabs=[("Dashboard","📊"),("Journal","📓"),("All Signals","📡"),("Settings","⚙️"),("Plans","💳"),("Guide","📖")]

    nav_html=""
    for t,icon in tabs:
        url=f"/{t.lower().replace(' ','-')}"
        if active==t:
            nav_html+=f"<a href='{url}' style='padding:9px 16px;border-radius:10px;text-decoration:none;color:white;font-weight:700;font-size:13px;background:linear-gradient(135deg,#10b981,#059669);box-shadow:0 4px 12px rgba(16,185,129,0.3);white-space:nowrap;display:inline-flex;gap:6px;align-items:center;margin-right:6px'>{icon} {t}</a>"
        else:
            nav_html+=f"<a href='{url}' style='padding:9px 16px;border-radius:10px;text-decoration:none;color:#94a3b8;font-weight:600;font-size:13px;background:#1e293b;border:1px solid #1e293b;white-space:nowrap;display:inline-flex;gap:6px;align-items:center;margin-right:6px'>{icon} {t}</a>"

    html = """
<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>AGENT 35 PRO</title>
<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap' rel='stylesheet'>
<style>
body{background:#080c14;color:#e2e8f0;font-family:'Inter',Arial,sans-serif;margin:0;min-height:100vh}
.topbar{background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);border-bottom:1px solid #1e293b;padding:14px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}
.logo{font-weight:900;font-size:20px;background:linear-gradient(135deg,#10b981,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:1px}
.top-right{display:flex;gap:12px;align-items:center;font-size:12px;flex-wrap:wrap}
.badge{background:linear-gradient(135deg,#10b981,#059669);padding:4px 10px;border-radius:20px;font-weight:700;font-size:11px;color:white}
.badge-warn{background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:4px 10px;border-radius:20px;font-size:11px}
.navbar{background:#0f172a;border-bottom:1px solid #1e293b;padding:12px 20px;display:flex;gap:8px;overflow-x:auto;position:sticky;top:60px;z-index:90}
.main{padding:20px;display:grid;grid-template-columns:1fr 1fr 1fr 320px;gap:16px;max-width:1600px;margin:0 auto}
.card{background:linear-gradient(145deg,#1e293b 0%,#162032 100%);border-radius:20px;padding:20px;border:1px solid #2a3a52;box-shadow:0 8px 32px rgba(0,0,0,0.4)}
.card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.card-title{color:#94a3b8;font-size:11px;letter-spacing:1px;font-weight:700;text-transform:uppercase}
.card-value{font-size:28px;font-weight:900}
.profit-neg{color:#ef4444}.profit-pos{color:#10b981}
.btn-primary{background:linear-gradient(135deg,#10b981,#059669);color:white;padding:14px;border-radius:14px;font-weight:800;border:none;width:100%;cursor:pointer;box-shadow:0 6px 20px rgba(16,185,129,0.3);font-size:14px}
.btn-secondary{background:#1e293b;border:1px solid #334155;color:white;padding:12px;border-radius:12px;text-align:center;display:block;text-decoration:none;font-weight:600;margin-top:10px}
.table-card{grid-column:1 / span 4;background:linear-gradient(145deg,#1e293b 0%,#162032 100%);border-radius:20px;padding:20px;border:1px solid #2a3a52}
table{width:100%;border-collapse:collapse}th{color:#64748b;text-align:left;padding:12px 10px;font-size:10px;letter-spacing:1px;text-transform:uppercase;font-weight:700;border-bottom:1px solid #334155}td{padding:14px 10px;border-bottom:1px solid #1e293b;font-size:13px}
.pill{padding:5px 12px;border-radius:20px;font-size:11px;font-weight:700;display:inline-block}
.pill-took{background:#10b98122;color:#10b981;border:1px solid #10b98133}
.pill-miss{background:#ef444422;color:#ef4444;border:1px solid #ef444433}
.pro-stat{background:#0f172a;border-radius:12px;padding:12px;border:1px solid #1e293b}
@media(max-width:1100px){.main{grid-template-columns:1fr 1fr}.table-card{grid-column:1 / span 2}}
@media(max-width:640px){.main{grid-template-columns:1fr}.table-card{grid-column:1}}
</style></head><body>
<div class='topbar'>
  <div class='logo'>AGENT 35 PRO</div>
  <div class='top-right'>
    <span class='badge'>LONDON ACTIVE</span>
    <span class='badge-warn'>UTC """ + utc + """ | SAST """ + sast + """</span>
    <span class='badge-warn' style='color:#10b981'>""" + user[:22] + """</span>
    <span class='badge-warn'>""" + plan_status[:24] + """</span>
  </div>
</div>
<div class='navbar'>""" + nav_html + """</div>
""" + content + """
</body></html>
"""
    return html

@app.route("/")
def home():
    return redirect("/dashboard") if session.get("user") else redirect("/login")

@app.route("/dashboard")
def dashboard():
    if not session.get("user"):
        return redirect("/login")
    email = session.get("user")
    auth=load_json(AUTH_FILE)
    info=auth.get(email,{})
    journal=load_json(JOURNAL_FILE, list)
    user_settings = get_user_settings(email)
    system=load_json(SYSTEM_FILE, dict)
    tracked=load_json(TRACK_FILE, dict)

    if not journal:
        journal=[{"time":"09-03 18:13","symbol":"EURUSD","status":"TOOK","result":"R0 (0.0R)","date":datetime.now().strftime("%Y-%m-%d")}]

    rows=""
    for t in reversed(journal[-8:]):
        cls = "pill-took" if t.get("status")=="TOOK" else "pill-miss"
        rows+=f"<tr><td style='color:#94a3b8'>{t.get('time')}</td><td style='font-weight:800'>{t.get('symbol')}</td><td><span class='pill {cls}'>{t.get('status')}</span></td><td style='color:#cbd5e1'>{t.get('result')}</td></tr>"

    is_admin = email == "admin@agent35.com"
    lot = user_settings.get("lot_size",0.01)
    lev = user_settings.get("leverage","1:500")
    sess = ",".join(user_settings.get("sessions",[]))

    content=f"""
<div class='main'>
  <div class='card'>
    <div class='card-header'><div class='card-title'>Total Profit</div><div class='badge-warn'>{len(journal)} trades</div></div>
    <div class='card-value profit-neg'>R{info.get('total_profit',-1.42)}</div>
    <div class='pro-stat' style='margin-top:12px;font-size:12px;color:#94a3b8'>Lot: {lot} | Lev: {lev}<br>Sessions: {sess}<br>Symbols: {len(user_settings.get('symbols',[]))} pairs</div>
  </div>
  <div class='card'>
    <div class='card-header'><div class='card-title'>Account Settings</div><div class='badge-warn' style='color:#10b981'>Live</div></div>
    <div class='card-value' style='color:white'>R{user_settings.get('account_size',142)}</div>
    <div class='pro-stat' style='margin-top:12px;font-size:11px'>Risk {user_settings.get('risk_percent',1)}% | Lot {lot}<br><a href='/settings' style='color:#10b981;text-decoration:none;font-weight:700'>Edit in Settings →</a></div>
  </div>
  <div class='card'>
    <div class='card-header'><div class='card-title'>Your Watchlist</div><div class='badge'>6/10</div></div>
    <div style='display:flex;flex-wrap:wrap;gap:8px;margin:14px 0'>
      {"".join([f"<span style='background:#1e293b;border:1px solid #334155;padding:8px 14px;border-radius:20px;font-size:12px;font-weight:700'>{s}</span>" for s in user_settings.get('symbols',["EURUSD","GBPUSD","USDJPY","USDCHF"])[:6]])}
    </div>
    <div class='pro-stat' style='font-size:11px;color:#94a3b8'>Last scan: {str(system.get('last_scan','Never'))[:19]}<br>Tracking {len([t for t in tracked.values() if t['status']=='TRACKING'])} trades</div>
  </div>
  <div class='card' style='background:linear-gradient(145deg,#132a22 0%,#1e293b 100%);border:1px solid #10b98133'>
    <a href='/dashboard-scan'><button class='btn-primary'>⚡ SCAN NOW</button></a>
    <div style='text-align:center;margin:12px 0;color:#10b981;font-size:11px;font-weight:700'>TAKE / MISS / TRACK in Telegram</div>
    <a href='/test-telegram' class='btn-secondary'>🧪 Test Telegram</a>
    {f"<a href='/creator?secret=' class='btn-secondary' style='background:linear-gradient(135deg,#f59e0b,#d97706);border:none;color:white;font-weight:700'>👑 Creator</a>" if is_admin else ""}
  </div>
</div>
<div style='max-width:1600px;margin:0 auto;padding:0 20px 20px'><div class='table-card'>
  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:16px'><h3 style='margin:0;font-weight:800'>Recent Trades</h3><a href='/journal' style='color:#10b981;text-decoration:none;font-weight:700;font-size:13px'>View Full →</a></div>
  <table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th></tr>{rows}</table>
</div></div>
"""
    return pro_layout(content,"Dashboard", is_admin=is_admin)

@app.route("/settings", methods=["GET","POST"])
def settings_page():
    if not session.get("user"):
        return redirect("/login")
    email = session.get("user")
    is_admin = email == "admin@agent35.com"

    if request.method == "POST":
        account_size = float(request.form.get("account_size",142))
        lot_size = float(request.form.get("lot_size",0.01))
        leverage = request.form.get("leverage","1:500")
        risk_percent = float(request.form.get("risk_percent",1))
        sessions = request.form.getlist("sessions")
        symbols = request.form.getlist("symbols")
        if not sessions:
            sessions=["London","New York"]
        if not symbols:
            symbols=["EURUSD","GBPUSD","USDJPY","USDCHF"]
        new_settings = {"account_size":account_size,"lot_size":lot_size,"leverage":leverage,"risk_percent":risk_percent,"sessions":sessions,"symbols":symbols}
        save_user_settings(email, new_settings)
        # Also update auth file account_size for compatibility
        auth=load_json(AUTH_FILE)
        if email in auth:
            auth[email]["account_size"]=account_size
            save_json(AUTH_FILE, auth)
        return redirect("/settings")

    s = get_user_settings(email)
    all_symbols = ["EURUSD","GBPUSD","USDJPY","USDCHF","XAUUSD","US30","NAS100","GBPJPY","AUDUSD","EURJPY"]
    all_sessions = ["Asia","London","New York"]

    symbols_checkboxes = "".join([f"<label style='display:flex;align-items:center;gap:8px;background:#0f172a;border:1px solid #1e293b;padding:10px 12px;border-radius:10px;font-size:13px;cursor:pointer'><input type='checkbox' name='symbols' value='{sym}' {'checked' if sym in s.get('symbols',[]) else ''}> {sym}</label>" for sym in all_symbols])
    sessions_checkboxes = "".join([f"<label style='display:flex;align-items:center;gap:8px;background:#0f172a;border:1px solid #1e293b;padding:10px 12px;border-radius:10px;font-size:13px;cursor:pointer'><input type='checkbox' name='sessions' value='{ses}' {'checked' if ses in s.get('sessions',[]) else ''}> {ses}</label>" for ses in all_sessions])

    content=f"""
<div style='max-width:900px;margin:0 auto;padding:20px'>
  <h1 style='font-weight:900;font-size:28px'>⚙️ Trading Settings</h1>
  <p style='color:#94a3b8;font-size:13px'>Configure your account - these affect your signals and lot calculations</p>

  <form method='post'>
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:20px'>
    <div class='card'>
      <div class='card-title'>Account Size (R)</div>
      <input name='account_size' type='number' step='0.01' value='{s.get('account_size',142)}' style='width:100%;padding:14px;margin-top:10px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white;font-size:16px;font-weight:700'>
      <div style='font-size:11px;color:#64748b;margin-top:8px'>Your real account balance</div>
    </div>
    <div class='card'>
      <div class='card-title'>Lot Size</div>
      <input name='lot_size' type='number' step='0.01' value='{s.get('lot_size',0.01)}' style='width:100%;padding:14px;margin-top:10px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white;font-size:16px;font-weight:700'>
      <div style='font-size:11px;color:#64748b;margin-top:8px'>Default lot per trade</div>
    </div>
    <div class='card'>
      <div class='card-title'>Leverage</div>
      <select name='leverage' style='width:100%;padding:14px;margin-top:10px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white;font-size:14px'>
        <option value='1:100' {'selected' if s.get('leverage')=='1:100' else ''}>1:100</option>
        <option value='1:200' {'selected' if s.get('leverage')=='1:200' else ''}>1:200</option>
        <option value='1:500' {'selected' if s.get('leverage')=='1:500' else ''}>1:500</option>
        <option value='1:1000' {'selected' if s.get('leverage')=='1:1000' else ''}>1:1000</option>
        <option value='1:2000' {'selected' if s.get('leverage')=='1:2000' else ''}>1:2000</option>
      </select>
    </div>
    <div class='card'>
      <div class='card-title'>Risk Per Trade (%)</div>
      <input name='risk_percent' type='number' step='0.1' value='{s.get('risk_percent',1)}' style='width:100%;padding:14px;margin-top:10px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white;font-size:16px;font-weight:700'>
    </div>
  </div>

  <div class='card' style='margin-top:16px'>
    <div class='card-title' style='margin-bottom:12px'>Trading Sessions You Trade</div>
    <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px'>{sessions_checkboxes}</div>
  </div>

  <div class='card' style='margin-top:16px'>
    <div class='card-title' style='margin-bottom:12px'>Symbols You Want Signals For</div>
    <div style='display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px'>{symbols_checkboxes}</div>
    <div style='font-size:11px;color:#64748b;margin-top:10px'>Cron will only scan your selected symbols</div>
  </div>

  <button type='submit' class='btn-primary' style='margin-top:20px;padding:16px;font-size:16px'>💾 SAVE SETTINGS</button>
  </form>

  {f"<div class='card' style='margin-top:20px;border:1px solid #f59e0b'><h3>Admin Info</h3><p style='font-size:12px;color:#94a3b8'>Storage: {BASE_DIR} | Users: {len(load_json(AUTH_FILE))} | <a href='/creator?secret=' style='color:#f59e0b'>Go Creator</a></p></div>" if is_admin else ""}
</div>
"""
    return pro_layout(content,"Settings", is_admin=is_admin)

@app.route("/login")
def login_page():
    count=len(load_json(AUTH_FILE))
    return f"""
<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
<body style='background:radial-gradient(ellipse at top,#1e293b,#080c14);color:white;font-family:Arial;padding:20px;min-height:100vh;display:flex;align-items:center;justify-content:center'>
<div style='width:100%;max-width:420px;background:linear-gradient(145deg,#1e293b 0%,#162032 100%);padding:32px;border-radius:24px;border:1px solid #2a3a52;box-shadow:0 24px 64px rgba(0,0,0,0.6)'>
<div style='text-align:center;margin-bottom:24px'><div style='font-weight:900;font-size:26px;background:linear-gradient(135deg,#10b981,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent'>AGENT 35 PRO</div><div style='color:#64748b;font-size:12px;margin-top:6px'>Professional Trading Signals</div></div>
<form action='/login/check' method='post'>
<input name='email' type='email' placeholder='Email address' required style='width:100%;padding:14px;margin:8px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='password' type='password' placeholder='Password' required style='width:100%;padding:14px;margin:8px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<button style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:14px;width:100%;border:none;border-radius:12px;font-weight:800;margin-top:10px'>LOGIN</button>
</form>
<div style='display:flex;justify-content:space-between;margin-top:16px;font-size:13px'><a href='/register' style='color:#3b82f6;text-decoration:none'>Create account</a><a href='/forgot-password' style='color:#94a3b8;text-decoration:none'>Forgot password?</a></div>
</div></body></html>
"""

@app.route("/register")
def register_page():
    return """
<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
<body style='background:radial-gradient(ellipse at top,#1e293b,#080c14);color:white;font-family:Arial;padding:20px;min-height:100vh;display:flex;align-items:center;justify-content:center'>
<div style='width:100%;max-width:420px;background:linear-gradient(145deg,#1e293b 0%,#162032 100%);padding:32px;border-radius:24px;border:1px solid #2a3a52'>
<h2 style='font-weight:900;margin-bottom:16px'>Create Account</h2>
<form action='/register/create' method='post'>
<input name='email' type='email' placeholder='Email' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='name' placeholder='Full Name' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='password' type='password' placeholder='Password min 6' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='ref' placeholder='Referral Code (optional)' style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<button style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:14px;width:100%;border:none;border-radius:12px;font-weight:800;margin-top:10px'>CREATE ACCOUNT</button>
</form>
<p style='text-align:center;margin-top:14px'><a href='/login' style='color:#3b82f6;text-decoration:none;font-size:13px'>Already have account? Login</a></p>
</div></body></html>
"""

@app.route("/register/create", methods=["POST"])
def register_create():
    email=request.form.get("email","").lower().strip()
    auth=load_json(AUTH_FILE)
    if email in auth:
        return f"Exists <a href='/login'>Login</a>"
    auth[email]={"email":email,"name":request.form.get("name"),"password":hash_pwd(request.form.get("password","")),"account_size":142.0,"total_profit":-1.42,"plan_status":"No Plan","referred_by":request.form.get("ref","").upper(),"created":datetime.now().isoformat(),"reset_token":None}
    save_json(AUTH_FILE, auth)
    session["user"]=email
    return redirect("/dashboard")

@app.route("/login/check", methods=["POST"])
def login_check():
    email=request.form.get("email","").lower().strip()
    pwd=request.form.get("password","")
    auth=load_json(AUTH_FILE)
    if email in auth and auth[email].get("password")==hash_pwd(pwd):
        session["user"]=email
        return redirect("/dashboard")
    return f"Wrong - <a href='/login'>Retry</a>"

@app.route("/logout")
def logout():
    session.pop("user",None)
    return redirect("/login")

@app.route("/journal")
def journal_page():
    if not session.get("user"):
        return redirect("/login")
    email=session.get("user")
    is_admin = email=="admin@agent35.com"
    journal=load_json(JOURNAL_FILE, list)
    tracked=load_json(TRACK_FILE, dict)
    today_str=datetime.now().strftime("%Y-%m-%d")
    month_str=datetime.now().strftime("%Y-%m")
    year_str=datetime.now().strftime("%Y")
    today_count=len([j for j in journal if j.get("date","")==today_str or today_str in j.get("time","")])
    month_count=len([j for j in journal if j.get("date","").startswith(month_str)])
    year_count=len([j for j in journal if j.get("date","").startswith(year_str)])
    j_rows=""
    for j in reversed(journal[-100:]):
        cls = "pill-took" if j.get("status")=="TOOK" else "pill-miss"
        j_rows+=f"<tr><td style='color:#94a3b8'>{j.get('time')}</td><td style='font-weight:800'>{j.get('symbol')}</td><td><span class='pill {cls}'>{j.get('status')}</span></td><td>{j.get('result')}</td><td style='font-size:11px;color:#64748b'>{j.get('date','')}</td></tr>"
    t_rows=""
    for v in tracked.values():
        t_rows+=f"<tr><td style='font-weight:700'>{v.get('symbol')}</td><td><span class='pill pill-took'>TRACKING</span></td><td>{v.get('sl')}</td><td>{v.get('tp')}</td><td>{v.get('by')}</td><td style='font-size:11px'>{v.get('started','')[:16]}</td></tr>"
    if not t_rows:
        t_rows="<tr><td colspan=6 style='text-align:center;color:#64748b;padding:30px'>No tracked yet</td></tr>"
    if not j_rows:
        j_rows="<tr><td colspan=5 style='text-align:center;padding:40px;color:#64748b'>No trades yet</td></tr>"
    content=f"""
<div style='max-width:1600px;margin:0 auto;padding:20px'>
  <div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:20px'>
    <h1 style='font-weight:900;margin:0'>📓 Journal ({len(journal)})</h1>
    <div style='display:flex;gap:8px;flex-wrap:wrap'>
      <a href='/journal/clear?period=today' onclick='return confirm("Clear TODAY {today_count}?")' style='background:#1e293b;border:1px solid #334155;color:#f59e0b;padding:10px 16px;border-radius:12px;text-decoration:none;font-weight:700;font-size:12px'>Today ({today_count})</a>
      <a href='/journal/clear?period=month' onclick='return confirm("Clear MONTH {month_count}?")' style='background:#1e293b;border:1px solid #334155;color:#f59e0b;padding:10px 16px;border-radius:12px;text-decoration:none;font-weight:700;font-size:12px'>Month ({month_count})</a>
      <a href='/journal/clear?period=year' onclick='return confirm("Clear YEAR {year_count}?")' style='background:#1e293b;border:1px solid #334155;color:#ef4444;padding:10px 16px;border-radius:12px;text-decoration:none;font-weight:700;font-size:12px'>Year ({year_count})</a>
      <a href='/journal/clear?period=all' onclick='return confirm("Clear ALL {len(journal)}?")' style='background:linear-gradient(135deg,#ef4444,#dc2626);color:white;padding:10px 16px;border-radius:12px;text-decoration:none;font-weight:800;font-size:12px'>All ({len(journal)})</a>
    </div>
  </div>
  <div class='table-card' style='margin-bottom:20px'><div style='overflow-x:auto'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th><th>Date</th></tr>{j_rows}</table></div></div>
  <div class='table-card'>
    <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:16px'><h3 style='margin:0;font-weight:800'>Tracked to SL/TP</h3><a href='/journal/clear-tracked?period=all' onclick='return confirm("Clear tracked?")' style='background:#ef444433;border:1px solid #ef444433;color:#ef4444;padding:8px 14px;border-radius:10px;text-decoration:none;font-weight:700;font-size:12px'>Clear Tracked ({len(tracked)})</a></div>
    <div style='overflow-x:auto'><table><tr><th>Symbol</th><th>Status</th><th>SL</th><th>TP</th><th>By</th><th>Started</th></tr>{t_rows}</table></div>
  </div>
</div>
"""
    return pro_layout(content,"Journal", is_admin=is_admin)

@app.route("/journal/clear")
def journal_clear():
    if not session.get("user"):
        return redirect("/login")
    period=request.args.get("period","all")
    journal=load_json(JOURNAL_FILE, list)
    today_str=datetime.now().strftime("%Y-%m-%d")
    month_str=datetime.now().strftime("%Y-%m")
    year_str=datetime.now().strftime("%Y")
    if period=="today":
        journal=[j for j in journal if not (j.get("date","")==today_str or today_str in j.get("time",""))]
    elif period=="month":
        journal=[j for j in journal if not j.get("date","").startswith(month_str)]
    elif period=="year":
        journal=[j for j in journal if not j.get("date","").startswith(year_str)]
    elif period=="all":
        journal=[]
    save_json(JOURNAL_FILE, journal)
    return redirect("/journal")

@app.route("/journal/clear-tracked")
def journal_clear_tracked():
    save_json(TRACK_FILE, {})
    return redirect("/journal")

@app.route("/dashboard-scan")
@app.route("/all-signals")
def dashboard_scan():
    if not session.get("user"):
        return redirect("/login")
    email=session.get("user")
    is_admin = email=="admin@agent35.com"
    user_settings = get_user_settings(email)
    symbols_to_scan = user_settings.get("symbols", ["EURUSD","GBPUSD","USDJPY","USDCHF","XAUUSD","US30"])
    rows=""
    for s in symbols_to_scan:
        try:
            r=eng.full_multi_tf_analysis(s)
            score = r.get('score',0)
            bias = r.get('bias','-')
            signal = r.get('signal','-')
            score_color="#10b981" if score>=6 else "#f59e0b" if score>=4 else "#ef4444"
            rows+=f"<tr><td style='font-weight:800'>{s}</td><td><span style='background:{score_color}22;color:{score_color};border:1px solid {score_color}33;padding:4px 10px;border-radius:20px;font-weight:800'>{score}/10</span></td><td>{bias}</td><td>{signal}</td><td><a href='/send-signal?symbol={s}' style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-weight:700;font-size:12px'>Send TG</a></td></tr>"
        except Exception as e:
            rows+=f"<tr><td style='font-weight:800'>{s}</td><td><span style='background:#ef444422;color:#ef4444;padding:4px 10px;border-radius:20px'>Error</span></td><td colspan=3 style='font-size:11px;color:#ef4444'>{str(e)[:100]}</td></tr>"

    content=f"""
<div style='max-width:1400px;margin:0 auto;padding:20px'>
<div class='table-card'>
<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:12px'>
<h2 style='margin:0;font-weight:900'>📡 Your Signals - {len(symbols_to_scan)} Pairs</h2>
<div style='display:flex;gap:8px'><a href='/settings' style='background:#1e293b;border:1px solid #334155;color:white;padding:8px 14px;border-radius:10px;text-decoration:none;font-size:12px'>⚙️ Edit Symbols</a><a href='/dashboard-scan' style='background:#10b981;color:white;padding:8px 14px;border-radius:10px;text-decoration:none;font-size:12px;font-weight:700'>🔄 Refresh Scan</a></div>
</div>
<div style='overflow-x:auto'><table><tr><th>Symbol</th><th>Score</th><th>Bias</th><th>Signal</th><th>Action</th></tr>{rows}</table></div>
<div style='background:#0f172a;border:1px solid #1e293b;padding:14px;border-radius:12px;margin-top:16px;font-size:12px;color:#94a3b8'>Your settings: Lot {user_settings.get('lot_size')} | Lev {user_settings.get('leverage')} | Sessions {",".join(user_settings.get('sessions',[]))} | Change in <a href='/settings' style='color:#10b981'>Settings</a></div>
</div></div>
"""
    return pro_layout(content,"All Signals", is_admin=is_admin)

@app.route("/send-signal")
def send_signal():
    if not session.get("user"):
        return redirect("/login")
    sym=request.args.get("symbol","EURUSD")
    try:
        r=eng.full_multi_tf_analysis(sym)
        res=send_telegram_signal(sym,r['score'],r['bias'],r['signal'],"SL auto","TP auto",r.get('reason',''))
        msg = f"Sent {sym} {r['score']}/10"
    except Exception as e:
        res = {"error":str(e)}
        msg = f"Error {sym}"
    return f"<html><body style='background:#080c14;color:white;padding:40px'><div style='max-width:500px;margin:auto;background:#1e293b;padding:24px;border-radius:20px'><h2>{msg} to @Sniper035_bot</h2><p style='font-size:12px;background:#0f172a;padding:10px;border-radius:8px;word-break:break-all'>{res}</p><a href='/all-signals' style='background:#10b981;color:white;padding:10px 20px;border-radius:10px;text-decoration:none'>Back</a></div></body></html>"

# ========== CREATOR DASHBOARD WITH ALL USERS + APPROVE/DECLINE ==========
@app.route("/creator")
@app.route("/master")
def creator_dashboard():
    secret=request.args.get("secret","")
    # Simple secret check - creator only
    if os.getenv("CRON_SECRET") and secret!= os.getenv("CRON_SECRET") and secret!= "":
        # allow if logged in as admin
        if session.get("user")!= "admin@agent35.com" and secret!= "":
            return "Wrong secret"

    auth=load_json(AUTH_FILE)
    users=load_json(USERS_FILE)
    tracked=load_json(TRACK_FILE, dict)
    system=load_json(SYSTEM_FILE, dict)
    settings_all=load_json(SETTINGS_FILE, dict)
    bot_token=os.getenv("TELEGRAM_BOT_TOKEN","Not set")
    chat_id=os.getenv("TELEGRAM_CHAT_ID","Not set")
    bot_short=bot_token[:20]+"..." if len(bot_token)>20 else bot_token

    webhook_info={}
    if len(bot_token)>20:
        try:
            webhook_info=requests.get(f"https://api.telegram.org/bot{bot_token}/getWebhookInfo",timeout=5).json()
        except:
            webhook_info={}

    pending_payments = {k:v for k,v in users.items() if v.get("status")=="pending"}
    active_payments = {k:v for k,v in users.items() if v.get("status")=="active"}

    # Build users table with Approve/Decline
    users_rows=""
    for email, info in list(auth.items())[:100]:
        # Find pending payment for this email
        related_pending = [k for k,v in pending_payments.items() if v.get("user")==email]
        plan = info.get("plan_status","No Plan")
        is_pending = len(related_pending)>0
        users_rows+=f"""
<tr>
<td style='font-weight:700'>{email[:30]}</td>
<td>{info.get('name','-')[:20]}</td>
<td><span style='background:{"#10b98122;color:#10b981" if "ACTIVE" in plan else "#ef444422;color:#ef4444"};padding:4px 10px;border-radius:20px;font-size:11px'>{plan[:30]}</span></td>
<td style='font-size:11px'>{info.get('created','')[:10]}</td>
<td>{info.get('account_size','-')}</td>
<td>
<div style='display:flex;gap:4px;flex-wrap:wrap'>
<a href='/creator/action?act=make_active&email={email}&secret={secret}' style='background:#10b981;color:white;padding:4px 8px;border-radius:6px;text-decoration:none;font-size:11px;font-weight:700'>✅ Approve</a>
<a href='/creator/action?act=delete_user&email={email}&secret={secret}' onclick='return confirm("Delete {email}?")' style='background:#ef4444;color:white;padding:4px 8px;border-radius:6px;text-decoration:none;font-size:11px'>❌ Decline</a>
<a href='/creator/action?act=make_active&email={email}&secret={secret}&plan=lifetime' style='background:#f59e0b;color:white;padding:4px 8px;border-radius:6px;text-decoration:none;font-size:11px'>👑 Lifetime</a>
</div>
</td>
</tr>
"""

    pending_rows=""
    for ref, pay in pending_payments.items():
        pending_rows+=f"""
<tr>
<td style='font-weight:800'>{ref}</td>
<td>{pay.get('user','')}</td>
<td>{pay.get('phone','')}</td>
<td>R{pay.get('price','')}</td>
<td>{pay.get('plan','')}</td>
<td>{pay.get('referred_by','')}</td>
<td style='font-size:11px'>{pay.get('created','')[:16]}</td>
<td>
<div style='display:flex;gap:4px'>
<a href='/creator/action?act=approve_payment&ref={ref}&secret={secret}' style='background:#10b981;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:12px;font-weight:800'>✅ APPROVE</a>
<a href='/creator/action?act=decline_payment&ref={ref}&secret={secret}' style='background:#ef4444;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:12px'>❌ DECLINE</a>
</div>
</td>
</tr>
"""
    if not pending_rows:
        pending_rows="<tr><td colspan=8 style='text-align:center;padding:30px;color:#64748b'>No pending payments - all approved ✅</td></tr>"

    content=f"""
<div style='max-width:1600px;margin:0 auto;padding:20px'>
<h1 style='font-weight:900;font-size:28px'>👑 Creator Dashboard • Clean V18</h1>

<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:16px 0'>
  <div class='card'><div class='card-title'>Total Users</div><div class='card-value' style='color:white'>{len(auth)}</div></div>
  <div class='card'><div class='card-title'>Pending Payments</div><div class='card-value' style='color:#f59e0b'>{len(pending_payments)}</div></div>
  <div class='card'><div class='card-title'>Active Payments</div><div class='card-value' style='color:#10b981'>{len(active_payments)}</div></div>
  <div class='card'><div class='card-title'>Tracking</div><div class='card-value' style='color:#8b5cf6'>{len([t for t in tracked.values() if t['status']=='TRACKING'])}</div></div>
</div>

<div style='display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px'>
  <div class='card'>
    <h3 style='color:#10b981;font-weight:800'>🔗 Webhook + Telegram</h3>
    <p style='font-size:11px;color:#94a3b8'>Bot: {bot_short}<br>Chat: {chat_id}<br>URL: https://agent-35-trading-bot.onrender.com/telegram/webhook<br><br>Info: {str(webhook_info.get('result',''))[:300]}</p>
    <div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px'>
      <a href='/creator/webhook?action=set&secret={secret}' style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:12px;border-radius:12px;text-align:center;text-decoration:none;font-weight:800'>SET WEBHOOK NOW</a>
      <a href='/creator/webhook?action=getUpdates&secret={secret}' style='background:#8b5cf6;color:white;padding:12px;border-radius:12px;text-align:center;text-decoration:none'>📩 Get Chat ID</a>
      <a href='/creator/webhook?action=info&secret={secret}' style='background:#3b82f6;color:white;padding:12px;border-radius:12px;text-align:center;text-decoration:none'>Check Info</a>
      <a href='/test-telegram' style='background:#1e293b;border:1px solid #334155;color:white;padding:12px;border-radius:12px;text-align:center;text-decoration:none'>Test Buttons</a>
    </div>
  </div>
  <div class='card'>
    <h3 style='color:#f59e0b;font-weight:800'>💾 System</h3>
    <p style='font-size:11px;color:#94a3b8'>Storage: {BASE_DIR} {"PERSISTENT ✅" if BASE_DIR=="/data" else "Add Disk /data ❌"}<br>Users: {len(auth)} | Settings: {len(settings_all)}<br>Last scan: {str(system.get('last_scan','Never'))[:19]}<br>Scans: {system.get('total_scans',0)}</p>
    <div style='display:grid;grid-template-columns:1fr 1fr;gap:8px'>
      <a href='/creator/action?act=backup&secret={secret}' style='background:#10b981;color:white;padding:12px;border-radius:12px;text-align:center;text-decoration:none;font-weight:700'>⬇️ Backup</a>
      <a href='/creator/backup-restore' style='background:#f59e0b;color:white;padding:12px;border-radius:12px;text-align:center;text-decoration:none;font-weight:700'>⬆️ Restore</a>
      <a href='/run-now?secret={secret}' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px;border-radius:10px;text-align:center;text-decoration:none'>Run Scan</a>
      <a href='/health' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px;border-radius:10px;text-align:center;text-decoration:none'>/health</a>
    </div>
  </div>
</div>

<div class='table-card' style='margin-bottom:20px;border:2px solid #f59e0b44'>
  <h3 style='color:#f59e0b;font-weight:900'>💳 PENDING PAYMENTS - APPROVE / DECLINE ({len(pending_payments)})</h3>
  <div style='overflow-x:auto'><table><tr><th>Ref</th><th>Email</th><th>Phone</th><th>Price</th><th>Plan</th><th>Referred By</th><th>Date</th><th>Action</th></tr>{pending_rows}</table></div>
</div>

<div class='table-card'>
  <h3 style='font-weight:900'>👥 ALL USERS ({len(auth)}) - Approve / Decline / Lifetime</h3>
  <div style='overflow-x:auto'><table><tr><th>Email</th><th>Name</th><th>Plan</th><th>Created</th><th>Acc Size</th><th>Actions</th></tr>{users_rows}</table></div>
</div>

</div>
"""
    return pro_layout(content,"Master", is_admin=True)

@app.route("/creator/webhook")
def creator_webhook():
    secret=request.args.get("secret","")
    action=request.args.get("action","info")
    bot_token=os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return "Set TELEGRAM_BOT_TOKEN in Render Env"
    base_url=f"https://api.telegram.org/bot{bot_token}"
    webhook_url="https://agent-35-trading-bot.onrender.com/telegram/webhook"
    try:
        if action=="set":
            r=requests.get(f"{base_url}/setWebhook", params={"url":webhook_url}, timeout=10).json()
            return f"<html><body style='background:#080c14;color:white;padding:20px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:20px;border-radius:16px'><h2>Set Webhook</h2><pre style='background:#0f172a;padding:15px;border-radius:12px'>{json.dumps(r, indent=2)}</pre><a href='/creator?secret={secret}' style='background:#10b981;color:white;padding:10px 20px;border-radius:12px;text-decoration:none'>Back Creator</a></div></body></html>"
        elif action=="info":
            r=requests.get(f"{base_url}/getWebhookInfo", timeout=10).json()
            return f"<html><body style='background:#080c14;color:white;padding:20px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:20px;border-radius:16px'><h2>Webhook Info</h2><pre style='background:#0f172a;padding:15px;border-radius:12px'>{json.dumps(r, indent=2)}</pre><a href='/creator?secret={secret}' style='background:#10b981;color:white;padding:10px 20px;border-radius:12px;text-decoration:none'>Back</a></div></body></html>"
        elif action=="getUpdates":
            r=requests.get(f"{base_url}/getUpdates", timeout=10).json()
            chats=[]
            for upd in r.get("result",[]):
                if "message" in upd:
                    chats.append(f"Chat ID: {upd['message']['chat']['id']} - {upd['message']['chat'].get('first_name','')}")
            chat_text="<br>".join(chats) or "Send Hi to @Sniper035_bot then click again"
            return f"<html><body style='background:#080c14;color:white;padding:20px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:20px;border-radius:16px'><h2>Chat IDs</h2><div style='background:#10b98122;padding:12px;border-radius:10px'>{chat_text}</div><pre style='max-height:300px;overflow:auto;background:#0f172a;padding:10px;border-radius:10px;font-size:11px'>{json.dumps(r, indent=2)[:3000]}</pre><a href='/creator?secret={secret}' style='background:#10b981;color:white;padding:10px 20px;border-radius:10px;text-decoration:none'>Back</a></div></body></html>"
    except Exception as e:
        return f"Error {e}"
    return redirect(f"/creator?secret={secret}")

@app.route("/creator/action")
def creator_action():
    secret=request.args.get("secret","")
    act=request.args.get("act","")
    auth=load_json(AUTH_FILE)
    users=load_json(USERS_FILE)

    if act=="backup":
        return jsonify({"auth_users":auth,"payments":users,"settings":load_json(SETTINGS_FILE, dict),"time":datetime.now().isoformat(),"storage":BASE_DIR})

    if act=="approve_payment":
        ref=request.args.get("ref","")
        if ref in users:
            users[ref]["status"]="active"
            users[ref]["expires"]=(datetime.now()+timedelta(days=PLANS.get(users[ref].get('plan','yearly'),PLANS['yearly'])['days'])).isoformat()
            # Also activate user account
            email = users[ref].get("user")
            if email in auth:
                auth[email]["plan_status"]=f"ACTIVE {users[ref].get('plan','yearly')} - Approved"
                auth[email]["expires"]=users[ref]["expires"]
            save_json(USERS_FILE, users)
            save_json(AUTH_FILE, auth)
        return redirect(f"/creator?secret={secret}")

    if act=="decline_payment":
        ref=request.args.get("ref","")
        if ref in users:
            del users[ref]
            save_json(USERS_FILE, users)
        return redirect(f"/creator?secret={secret}")

    if act=="delete_user":
        email=request.args.get("email","")
        if email in auth and email!="admin@agent35.com":
            del auth[email]
            save_json(AUTH_FILE, auth)
        return redirect(f"/creator?secret={secret}")

    if act=="make_active":
        email=request.args.get("email","")
        plan = request.args.get("plan","lifetime")
        days = 36500 if plan=="lifetime" else 365
        if email in auth:
            auth[email]["plan_status"]=f"ACTIVE {plan} - By Creator"
            auth[email]["expires"]=(datetime.now()+timedelta(days=days)).isoformat()
            save_json(AUTH_FILE, auth)
        return redirect(f"/creator?secret={secret}")

    return redirect(f"/creator?secret={secret}")

@app.route("/creator/backup-restore", methods=["GET","POST"])
def backup_restore():
    if request.method=="GET":
        return "<html><body style='background:#080c14;color:white;padding:20px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:20px;border-radius:16px'><h2>Restore Backup</h2><form method='post' enctype='multipart/form-data'><input type='file' name='backup' required style='width:100%;padding:12px;margin:10px 0;background:#0f172a;border-radius:10px;border:1px solid #334155'><button style='background:#f59e0b;color:white;padding:12px;width:100%;border:none;border-radius:12px;font-weight:800'>RESTORE NOW</button></form></div></body></html>"
    else:
        file=request.files.get('backup')
        try:
            data=json.load(file)
            if "auth_users" in data:
                save_json(AUTH_FILE, data["auth_users"])
            else:
                save_json(AUTH_FILE, data)
            return f"<html><body style='background:#080c14;color:white;padding:30px;text-align:center'><h2>Restored {len(load_json(AUTH_FILE))} users</h2><a href='/login' style='background:#10b981;color:white;padding:12px 20px;border-radius:12px;text-decoration:none'>Login</a></body></html>"
        except Exception as e:
            return f"Error {e}"

@app.route("/pay")
def pay_page():
    ref=request.args.get("ref","") or session.get("ref","")
    email=request.args.get("email","") or session.get("user","")
    content=f"""
<div style='max-width:500px;margin:0 auto;padding:20px'><div class='card'>
<h2>💳 Buy Plan - Capitec</h2>
<div style='background:#0f172a;padding:12px;border-radius:12px;margin:12px 0;font-size:13px'>Bank: Capitec<br>Holder: Agent 35 Trading Bot<br>Acc: 2586572676<br>Branch: 470010</div>
<form action='/pay/create' method='get'>
<input type='hidden' name='ref' value='{ref}'>
<input name='user' value='{email}' placeholder='Your login email' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='phone' placeholder='WhatsApp number' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<select name='plan' style='width:100%;padding:14px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><option value='yearly'>Yearly R500 - 365 Days</option><option value='lifetime'>Lifetime R5000 - Forever</option></select>
<button style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:14px;width:100%;border:none;border-radius:12px;margin-top:10px;font-weight:800'>GET PAYMENT REFERENCE</button>
</form>
</div></div>
"""
    is_admin = session.get("user")=="admin@agent35.com"
    return pro_layout(content,"Plans", is_admin=is_admin)

@app.route("/pay/create")
def pay_create():
    user=request.args.get("user","").lower().strip()
    phone=request.args.get("phone","").strip()
    plan_key=request.args.get("plan","yearly")
    ref=request.args.get("ref","").upper().strip()
    short="".join([c for c in user.upper() if c.isalnum()])[:5] or "USER"
    rand="".join(random.choices(string.digits,k=3))
    pref=f"{CAPITEC['ref_prefix']}-{short}-{rand}"
    plan=PLANS.get(plan_key, PLANS["yearly"])
    users=load_json(USERS_FILE)
    users[pref]={"user":user,"phone":phone,"plan":plan_key,"price":plan["price"],"payment_ref":pref,"referred_by":ref,"status":"pending","created":datetime.now().isoformat(),"expires":None}
    save_json(USERS_FILE, users)
    return f"<html><body style='background:#080c14;color:white;padding:40px;text-align:center'><div style='max-width:480px;margin:auto;background:#1e293b;padding:28px;border-radius:20px'><h1>Pay R{plan['price']} {plan['name']}</h1><div style='border:2px dashed #334155;padding:20px;border-radius:16px;background:#0f172a;margin:16px 0'><p>Bank: Capitec<br>Agent 35 Trading Bot<br>Acc: 2586572676 Branch: 470010</p><h1 style='background:white;color:black;padding:16px;border-radius:12px'>{pref}</h1><p style='color:#f59e0b;font-weight:800'>USE EXACT REFERENCE IN CAPITEC</p></div><a href='/dashboard' style='background:#1e293b;color:white;padding:10px 20px;border-radius:10px;text-decoration:none'>Back Dashboard</a></div></body></html>"

@app.route("/guide")
def guide_page():
    is_admin = session.get("user")=="admin@agent35.com"
    content=f"""
<div style='max-width:900px;margin:0 auto;padding:20px'>
<h1 style='font-weight:900;font-size:28px'>📖 Guide - From Pay to Signal</h1>
<div style='display:grid;gap:12px;margin-top:16px'>
<div class='card' style='border-left:4px solid #10b981'><h3>1 Pay</h3><p style='color:#94a3b8;font-size:13px'>Go /pay -> Enter email + WhatsApp -> Get ref A35-XXX-123 -> Capitec App Transfer R500/R5000 to 2586572676 with exact ref</p></div>
<div class='card' style='border-left:4px solid #3b82f6'><h3>2 Approve</h3><p style='color:#94a3b8;font-size:13px'>Creator checks Capitec -> Creator Dashboard -> APPROVE button -> You become ACTIVE</p></div>
<div class='card' style='border-left:4px solid #8b5cf6'><h3>3 Settings</h3><p style='color:#94a3b8;font-size:13px'>Go /settings -> Set Account Size, Lot Size, Leverage, Risk %, Sessions (London/NY/Asia), Symbols you want</p></div>
<div class='card' style='border-left:4px solid #f59e0b'><h3>4 Signals</h3><p style='color:#94a3b8;font-size:13px'>Cron scans your symbols every 30 min -> Telegram @Sniper035_bot -> Buttons TAKE / MISS / TRACK TO SL/TP</p></div>
<div class='card' style='border-left:4px solid #10b981'><h3>5 Journal</h3><p style='color:#94a3b8;font-size:13px'>TAKE logs as TOOK, TRACK logs tracking, MISS logs miss. Clear by Today/Month/Year/All in /journal</p></div>
</div>
</div>
"""
    return pro_layout(content,"Guide", is_admin=is_admin)

@app.route("/plans")
def plans_page():
    is_admin = session.get("user")=="admin@agent35.com"
    content=f"<div style='max-width:600px;margin:0 auto;padding:20px'><div class='card'><h2>Plans</h2><p>Yearly R500 - 365 days<br>Lifetime R5000 - forever<br>10 referrals = FREE Lifetime</p><a href='/pay' style='background:#10b981;color:white;padding:10px 20px;border-radius:12px;text-decoration:none;font-weight:700'>Buy Now</a></div></div>"
    return pro_layout(content,"Plans", is_admin=is_admin)

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data=request.get_json()
    if not data:
        return jsonify({"ok":True})
    if "callback_query" in data:
        cb=data["callback_query"]
        cb_data=cb.get("data","")
        cb_id=cb.get("id")
        chat_id=cb["message"]["chat"]["id"]
        user_name=cb["from"].get("first_name","User")
        journal=load_json(JOURNAL_FILE, list)
        tracked=load_json(TRACK_FILE, dict)
        bot=os.getenv("TELEGRAM_BOT_TOKEN")
        text="OK"
        if cb_data.startswith("TAKE_"):
            _,sym,score=cb_data.split("_")
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"TOOK","result":f"Taken by {user_name} {score}/10","date":datetime.now().strftime("%Y-%m-%d")})
            save_json(JOURNAL_FILE, journal[-200:])
            text=f"TOOK {sym}"
        elif cb_data.startswith("MISS_"):
            sym=cb_data.split("_")[1]
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"MISS","result":"Missed","date":datetime.now().strftime("%Y-%m-%d")})
            save_json(JOURNAL_FILE, journal[-200:])
            text=f"MISSED {sym}"
        elif cb_data.startswith("TRACK_"):
            parts=cb_data.split("_")
            sym=parts[1]
            sl=parts[2]
            tp=parts[3] if len(parts)>3 else "TP"
            tid=f"{sym}_{datetime.now().strftime('%H%M%S')}"
            tracked[tid]={"symbol":sym,"sl":sl,"tp":tp,"status":"TRACKING","started":datetime.now().isoformat(),"by":user_name}
            save_json(TRACK_FILE, tracked)
            text=f"TRACKING {sym}"
        if bot:
            try:
                requests.post(f"https://api.telegram.org/bot{bot}/answerCallbackQuery", json={"callback_query_id":cb_id,"text":text}, timeout=5)
                requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":text}, timeout=5)
            except:
                pass
        return jsonify({"ok":True})
    return jsonify({"ok":True})

@app.route("/test-telegram")
def test_telegram():
    res=send_telegram_signal("EURUSD",7,"BUY","BUY NOW","1.0845 SL","1.0920 TP","V18 Clean Fix")
    return f"<html><body style='background:#080c14;color:white;padding:40px'><div style='max-width:500px;margin:auto;background:#1e293b;padding:24px;border-radius:20px'><h2>Sent to @Sniper035_bot</h2><p style='font-size:11px;background:#0f172a;padding:10px;border-radius:8px;word-break:break-all'>{res}</p><a href='/creator?secret=' style='background:#10b981;color:white;padding:10px 20px;border-radius:12px;text-decoration:none'>Back</a></div></body></html>"

@app.route("/link-telegram")
def link_telegram():
    return redirect("/creator?secret=")

@app.route("/cron/scan")
def cron_scan():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"):
        return jsonify({"error":"bad secret"})
    system=load_json(SYSTEM_FILE, dict)
    system["last_scan"]=datetime.now().isoformat()
    system["total_scans"]=system.get("total_scans",0)+1
    save_json(SYSTEM_FILE, system)
    # Get all users settings to build unique symbol list
    settings_all=load_json(SETTINGS_FILE, dict)
    all_syms=set()
    for s in settings_all.values():
        all_syms.update(s.get("symbols",[]))
    if not all_syms:
        all_syms={"EURUSD","GBPUSD","USDJPY","USDCHF","XAUUSD","US30"}
    sent=[]
    for sym in list(all_syms)[:8]:
        try:
            r=eng.full_multi_tf_analysis(sym)
            if r.get("score",0)>=6:
                send_telegram_signal(sym,r['score'],r['bias'],r['signal'],"SL auto","TP auto",r.get('reason',''))
                sent.append(sym)
                j=load_json(JOURNAL_FILE, list)
                j.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"TOOK","result":f"{r['score']}/10 {r['bias']} auto","date":datetime.now().strftime("%Y-%m-%d")})
                save_json(JOURNAL_FILE, j[-200:])
        except Exception as e:
            print(f"Scan error {sym}: {e}")
    return jsonify({"sent":sent,"scanned":list(all_syms)})

@app.route("/cron/track-check")
def cron_track_check():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"):
        return jsonify({"error":"bad secret"})
    tracked=load_json(TRACK_FILE, dict)
    return jsonify({"tracking":len([t for t in tracked.values() if t['status']=="TRACKING"])})

@app.route("/health")
def health():
    return jsonify({"ok":True,"version":"V18 CLEAN - Settings lot/lev/session/symbols + Creator Approve/Decline","storage":BASE_DIR,"persistent":BASE_DIR=="/data","users":len(load_json(AUTH_FILE))})

@app.route("/forgot-password")
def forgot_page():
    return "<html><body style='background:#080c14;color:white;padding:30px'><div style='max-width:400px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>Forgot Password</h2><form action='/forgot-password/send' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:12px;border-radius:8px;background:#0f172a;border:1px solid #334155;color:white'><button style='background:#f59e0b;color:white;padding:12px;width:100%;border:none;border-radius:12px;margin-top:10px'>SEND RESET LINK</button></form></div></body></html>"

@app.route("/forgot-password/send", methods=["POST"])
def forgot_send():
    import secrets
    email=request.form.get("email","").lower().strip()
    auth=load_json(AUTH_FILE)
    if email not in auth:
        return f"Not found <a href='/register'>Register</a>"
    token=secrets.token_urlsafe(12)
    auth[email]["reset_token"]=token
    save_json(AUTH_FILE, auth)
    link=f"/reset-password?token={token}&email={email}"
    return f"<html><body style='background:#080c14;color:white;padding:20px;text-align:center'><h2>Reset Link</h2><a href='{link}' style='background:#10b981;color:white;padding:12px 20px;border-radius:12px;text-decoration:none'>Click to Reset</a><p style='font-size:11px'>{link}</p></body></html>"

@app.route("/reset-password")
def reset_page():
    return f"<html><body style='background:#080c14;color:white;padding:30px'><div style='max-width:400px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>Reset {request.args.get('email')}</h2><form action='/reset-password/save' method='post'><input type='hidden' name='email' value='{request.args.get('email')}'><input type='hidden' name='token' value='{request.args.get('token')}'><input name='new_password' type='password' placeholder='New Password' required style='width:100%;padding:12px;border-radius:8px;background:#0f172a;border:1px solid #334155;color:white'><button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:12px;margin-top:10px'>SAVE</button></form></div></body></html>"

@app.route("/reset-password/save", methods=["POST"])
def reset_save():
    email=request.form.get("email","").lower()
    token=request.form.get("token","")
    auth=load_json(AUTH_FILE)
    if auth.get(email,{}).get("reset_token")!=token:
        return "Invalid token"
    auth[email]["password"]=hash_pwd(request.form.get("new_password",""))
    auth[email]["reset_token"]=None
    save_json(AUTH_FILE, auth)
    return "Changed <a href='/login'>Login</a>"

@app.route("/run-now")
def run_now():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"):
        return jsonify({"error":"bad secret"})
    return jsonify(eng.run_scan_and_send())

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000)
