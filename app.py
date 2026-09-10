from flask import Flask, request, jsonify, session, redirect
import os, json, hashlib, requests, random, string
from dotenv import load_dotenv
import trading_engine as eng
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "agent35-v17-pro-edition")

BASE_DIR = "/data" if os.path.exists("/data") else "."
AUTH_FILE = os.path.join(BASE_DIR, "auth_users.json")
USERS_FILE = os.path.join(BASE_DIR, "users_data.json")
DATA_FILE = os.path.join(BASE_DIR, "referrals_data.json")
JOURNAL_FILE = os.path.join(BASE_DIR, "journal.json")
TRACK_FILE = os.path.join(BASE_DIR, "tracked_trades.json")
SYSTEM_FILE = os.path.join(BASE_DIR, "system_status.json")

CAPITEC = {"bank":"Capitec","holder":"Agent 35 Trading Bot","acc":"2586572676","branch":"470010","ref_prefix":"A35"}
PLANS = {"yearly":{"name":"Yearly","price":500,"days":365},"lifetime":{"name":"Lifetime","price":5000,"days":36500}}

def load_json(p, default_type=dict):
    if not os.path.exists(p): return {} if default_type==dict else []
    try:
        with open(p,"r") as f: return json.load(f)
    except: return {} if default_type==dict else []

def save_json(p, data):
    with open(p,"w") as f: json.dump(f, data, indent=2)

def hash_pwd(p): return hashlib.sha256(p.encode()).hexdigest()

def backup_to_telegram():
    bot=os.getenv("TELEGRAM_BOT_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
    if not bot or not chat: return
    auth=load_json(AUTH_FILE)
    if len(auth)<=1: return
    try:
        url=f"https://api.telegram.org/bot{bot}/sendDocument"
        files={'document':('backup.json', json.dumps({"auth_users":auth,"payments":load_json(USERS_FILE),"time":datetime.now().isoformat()}, indent=2).encode())}
        requests.post(url, files=files, data={'chat_id':chat,'caption':f"🔐 Backup {datetime.now().strftime('%m-%d %H:%M')} - {len(auth)} users"}, timeout=10)
    except: pass

def ensure_files():
    if not os.path.exists(AUTH_FILE):
        save_json(AUTH_FILE, {"admin@agent35.com":{"email":"admin@agent35.com","name":"Master Creator","password":hash_pwd("Agent35!"),"account_size":142.0,"total_profit":-1.42,"plan_status":"ACTIVE lifetime - CREATOR","referred_by":"","expires":(datetime.now()+timedelta(days=36500)).isoformat(),"created":datetime.now().isoformat(),"reset_token":None}})
    for p in [USERS_FILE, DATA_FILE]:
        if not os.path.exists(p): save_json(p, {})
    if not os.path.exists(JOURNAL_FILE): save_json(JOURNAL_FILE, [])
    if not os.path.exists(TRACK_FILE): save_json(TRACK_FILE, {})
    if not os.path.exists(SYSTEM_FILE): save_json(SYSTEM_FILE, {"last_scan":None,"total_scans":0,"total_signals":0,"system_up_since":datetime.now().isoformat(),"webhook_set":False})

ensure_files()

def send_telegram_signal(symbol, score, bias, signal, sl, tp, reason):
    bot=os.getenv("TELEGRAM_BOT_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
    if not bot or not chat: return {"error":"no env"}
    text=f"🎯 *AGENT 35 SIGNAL*\n\nSymbol: {symbol}\nScore: {score}/10\nBias: {bias}\nSignal: {signal}\nSL: {sl}\nTP: {tp}\nReason: {reason}\nTime: {datetime.utcnow().strftime('%H:%M')} UTC"
    keyboard={"inline_keyboard":[[{"text":"✅ TAKE TRADE","callback_data":f"TAKE_{symbol}_{score}"},{"text":"❌ MISS","callback_data":f"MISS_{symbol}"}],[{"text":"📈 TRACK TO SL/TP","callback_data":f"TRACK_{symbol}_{sl}_{tp}"}]]}
    try:
        r=requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat,"text":text,"parse_mode":"Markdown","reply_markup":keyboard}, timeout=10)
        return r.json()
    except Exception as e: return {"error":str(e)}

# ===== PREMIUM PRO LAYOUT =====
def pro_layout(content, active="Dashboard"):
    utc=datetime.utcnow().strftime("%H:%M:%S")
    sast=(datetime.utcnow()+timedelta(hours=2)).strftime("%H:%M:%S")
    user=session.get("user","Guest")
    auth=load_json(AUTH_FILE)
    plan_status=auth.get(user,{}).get("plan_status","No Plan") if user!="Guest" else "No Plan"

    tabs=[
        ("Dashboard","📊"),("Journal","📓"),("All Signals","📡"),("Settings","⚙️"),("Plans","💳"),("Guide","📖"),("Master","👑")
    ]
    nav_html=""
    for t,icon in tabs:
        url=f"/{t.lower().replace(' ','-')}"
        is_active = active==t
        nav_html+=f"<a href='{url}' class='{'nav-active' if is_active else 'nav-link'}'><span>{icon}</span> {t}</a>"

    return f"""
<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>AGENT 35 PRO</title>
<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap' rel='stylesheet'>
<style>
*{*margin:0;*padding:0;box-sizing:border-box}
body{{background:#080c14;color:#e2e8f0;font-family:'Inter',Arial,sans-serif;margin:0;min-height:100vh}}
.topbar{{background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);border-bottom:1px solid #1e293b;padding:14px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100;backdrop-filter:blur(12px)}}
.logo{{font-weight:900;font-size:20px;background:linear-gradient(135deg,#10b981,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:1px}}
.top-right{{display:flex;gap:12px;align-items:center;font-size:12px}}
.badge{{background:linear-gradient(135deg,#10b981,#059669);padding:4px 10px;border-radius:20px;font-weight:700;font-size:11px}}
.badge-warn{{background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:4px 10px;border-radius:20px;font-size:11px}}
.navbar{{background:#0f172a;border-bottom:1px solid #1e293b;padding:12px 20px;display:flex;gap:8px;overflow-x:auto;position:sticky;top:60px;z-index:90}}
.nav-link{{padding:9px 16px;border-radius:10px;text-decoration:none;color:#94a3b8;font-weight:600;font-size:13px;background:#1e293b;border:1px solid transparent;transition:all 0.2s;white-space:nowrap;display:flex;gap:6px;align-items:center}}
.nav-link:hover{{background:#334155;color:white;border-color:#475569;transform:translateY(-1px)}}
.nav-active{{padding:9px 16px;border-radius:10px;text-decoration:none;color:white;font-weight:700;font-size:13px;background:linear-gradient(135deg,#10b981,#059669);box-shadow:0 4px 12px rgba(16,185,129,0.3);white-space:nowrap;display:flex;gap:6px;align-items:center}}
.main{{padding:20px;display:grid;grid-template-columns:1fr 1fr 1fr 320px;gap:16px;max-width:1600px;margin:0 auto}}
.card{{background:linear-gradient(145deg,#1e293b 0%,#162032 100%);border-radius:20px;padding:20px;border:1px solid #2a3a52;box-shadow:0 8px 32px rgba(0,0,0,0.4);transition:transform 0.2s}}
.card:hover{{transform:translateY(-2px);border-color:#334155}}
.card-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}}
.card-title{{color:#94a3b8;font-size:11px;letter-spacing:1px;font-weight:700;text-transform:uppercase}}
.card-value{{font-size:28px;font-weight:900;letter-spacing:-0.5px}}
.profit-neg{{color:#ef4444}}.profit-pos{{color:#10b981}}
.btn-primary{{background:linear-gradient(135deg,#10b981,#059669);color:white;padding:14px;border-radius:14px;font-weight:800;border:none;width:100%;cursor:pointer;box-shadow:0 6px 20px rgba(16,185,129,0.3);transition:all 0.2s;font-size:14px;letter-spacing:0.5px}}
.btn-primary:hover{{transform:translateY(-2px);box-shadow:0 8px 28px rgba(16,185,129,0.4)}}
.btn-secondary{{background:#1e293b;border:1px solid #334155;color:white;padding:12px;border-radius:12px;text-align:center;display:block;text-decoration:none;font-weight:600;margin-top:10px;transition:all 0.2s}}
.btn-secondary:hover{{background:#334155;border-color:#475569}}
.table-card{{grid-column:1 / span 4;background:linear-gradient(145deg,#1e293b 0%,#162032 100%);border-radius:20px;padding:20px;border:1px solid #2a3a52;box-shadow:0 8px 32px rgba(0,0,0,0.4)}}
table{{width:100%;border-collapse:collapse}}th{{color:#64748b;text-align:left;padding:12px 10px;font-size:10px;letter-spacing:1px;text-transform:uppercase;font-weight:700;border-bottom:1px solid #334155}}td{{padding:14px 10px;border-bottom:1px solid #1e293b;font-size:13px}}
.pill{{padding:5px 12px;border-radius:20px;font-size:11px;font-weight:700;display:inline-block}}
.pill-took{{background:linear-gradient(135deg,#10b98122,#05966922);color:#10b981;border:1px solid #10b98133}}
.pill-miss{{background:#ef444422;color:#ef4444;border:1px solid #ef444433}}
.pro-stat{{background:#0f172a;border-radius:12px;padding:12px;border:1px solid #1e293b}}
@media(max-width:1100px){{.main{{grid-template-columns:1fr 1fr}}.table-card{{grid-column:1 / span 2}}}}
@media(max-width:640px){{.main{{grid-template-columns:1fr}}.table-card{{grid-column:1}}.topbar{{flex-direction:column;gap:10px;align-items:flex-start}}.navbar{{top:88px}}}}
.glow{{box-shadow:0 0 20px rgba(16,185,129,0.15)}}
</style></head><body>
<div class='topbar'>
  <div class='logo'>⬢ AGENT 35 PRO</div>
  <div class='top-right'>
    <span class='badge'>LONDON ACTIVE</span>
    <span class='badge-warn'>UTC {utc} | SAST {sast}</span>
    <span class='badge-warn' style='color:#10b981'>{user[:22]}</span>
    <span class='badge-warn' style='max-width:200px;overflow:hidden;text-overflow:ellipsis'>{plan_status[:30]}</span>
  </div>
</div>
<div class='navbar'>{nav_html}</div>
{content}
</body></html>
"""

@app.route("/")
def home(): return redirect("/dashboard") if session.get("user") else redirect("/login")

@app.route("/dashboard")
def dashboard():
    if not session.get("user"): return redirect("/login")
    auth=load_json(AUTH_FILE); info=auth.get(session.get("user"),{}); journal=load_json(JOURNAL_FILE, list)
    acc_size=info.get("account_size",142.0); profit=info.get("total_profit",-1.42)
    system=load_json(SYSTEM_FILE, dict); tracked=load_json(TRACK_FILE, dict)

    if not journal:
        journal=[{"time":"09-03 18:13","symbol":"EURUSD","status":"TOOK","result":"R0 (0.0R)","date":datetime.now().strftime("%Y-%m-%d")}]

    rows="".join([f"<tr><td style='color:#94a3b8'>{t.get('time')}</td><td style='font-weight:800;letter-spacing:0.5px'>{t.get('symbol')}</td><td><span class='pill { 'pill-took' if t.get('status')=='TOOK' else 'pill-miss'}'>{t.get('status')}</span></td><td style='color:#cbd5e1'>{t.get('result')}</td></tr>" for t in reversed(journal[-8:])])
    track_count=len([t for t in tracked.values() if t.get('status')=='TRACKING'])
    persistent="PERSISTENT /data" if BASE_DIR=="/data" else "Add Disk /data for last-week mode"

    content=f"""
<div class='main'>
  <div class='card glow'>
    <div class='card-header'><div class='card-title'>Total Profit</div><div class='badge-warn'>WR Tracking</div></div>
    <div class='card-value profit-neg'>R{profit}</div>
    <div style='margin-top:12px' class='pro-stat'><div style='font-size:11px;color:#64748b'>Storage: {persistent} | Users: {len(auth)} | Scans: {system.get('total_scans',0)}</div></div>
  </div>
  <div class='card'>
    <div class='card-header'><div class='card-title'>Account Size</div><div class='badge-warn' style='color:#10b981'>Live</div></div>
    <div class='card-value' style='color:white'>R{acc_size}</div>
    <form action='/account/edit' method='post' style='margin-top:14px;display:flex;gap:8px'>
      <input name='size' value='{acc_size}' style='flex:1;background:#0f172a;border:1px solid #334155;color:white;padding:10px;border-radius:10px'>
      <button type='submit' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px 16px;border-radius:10px;font-weight:700'>Update</button>
    </form>
  </div>
  <div class='card'>
    <div class='card-header'><div class='card-title'>Watchlist 4/5</div><div class='badge'>6/10 Fix</div></div>
    <div style='display:flex;flex-wrap:wrap;gap:8px;margin:14px 0'>
      <span style='background:linear-gradient(135deg,#1e293b,#334155);border:1px solid #334155;padding:8px 14px;border-radius:20px;font-size:12px;font-weight:700'>EURUSD</span>
      <span style='background:linear-gradient(135deg,#1e293b,#334155);border:1px solid #334155;padding:8px 14px;border-radius:20px;font-size:12px;font-weight:700'>GBPUSD</span>
      <span style='background:linear-gradient(135deg,#1e293b,#334155);border:1px solid #334155;padding:8px 14px;border-radius:20px;font-size:12px;font-weight:700'>USDJPY</span>
      <span style='background:linear-gradient(135deg,#1e293b,#334155);border:1px solid #334155;padding:8px 14px;border-radius:20px;font-size:12px;font-weight:700'>USDCHF</span>
    </div>
    <div class='pro-stat' style='font-size:11px;color:#94a3b8'>Capitec • {CAPITEC['acc']} • {CAPITEC['holder']}<br>Last: {system.get('last_scan','Never')[:19] if system.get('last_scan') else 'Never'} • Tracking {track_count}</div>
  </div>
  <div class='card' style='background:linear-gradient(145deg,#132a22 0%,#1e293b 100%);border:1px solid #10b98133'>
    <a href='/dashboard-scan'><button class='btn-primary'>⚡ SCAN NOW</button></a>
    <div style='text-align:center;margin:12px 0;color:#10b981;font-size:11px;font-weight:700;letter-spacing:1px'>TELEGRAM BUTTONS • TAKE / MISS / TRACK</div>
    <a href='/test-telegram' class='btn-secondary'>🧪 Test Telegram + Buttons</a>
    <a href='/creator?secret=' class='btn-secondary' style='background:linear-gradient(135deg,#f59e0b,#d97706);border:none;color:white;font-weight:700'>👑 Creator + Webhook Control</a>
  </div>
</div>
<div style='max-width:1600px;margin:0 auto;padding:0 20px 20px'><div class='table-card'>
  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:16px'><h3 style='margin:0;font-weight:800;letter-spacing:-0.5px'>Recent Trades Journal</h3><a href='/journal' style='color:#10b981;text-decoration:none;font-weight:700;font-size:13px'>View Full →</a></div>
  <table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th></tr>{rows}</table>
</div></div>
"""
    return pro_layout(content,"Dashboard")

@app.route("/login")
def login_page():
    count=len(load_json(AUTH_FILE))
    return f"""
<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><link href='https://fonts.googleapis.com/css2?family=Inter:wght@600;900&display=swap' rel='stylesheet'></head>
<body style='background:radial-gradient(ellipse at top,#1e293b,#080c14);color:white;font-family:Inter,Arial;padding:20px;min-height:100vh;display:flex;align-items:center;justify-content:center'>
<div style='width:100%;max-width:420px;background:linear-gradient(145deg,#1e293b 0%,#162032 100%);padding:32px;border-radius:24px;border:1px solid #2a3a52;box-shadow:0 24px 64px rgba(0,0,0,0.6)'>
<div style='text-align:center;margin-bottom:24px'><div style='font-weight:900;font-size:26px;letter-spacing:1px;background:linear-gradient(135deg,#10b981,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent'>AGENT 35 PRO</div><div style='color:#64748b;font-size:12px;margin-top:6px'>{count} accounts • {BASE_DIR} • Capitec {CAPITEC['acc']}</div></div>
<form action='/login/check' method='post'>
<input name='email' type='email' placeholder='Email address' required style='width:100%;padding:14px;margin:8px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white;font-size:14px'>
<input name='password' type='password' placeholder='Password' required style='width:100%;padding:14px;margin:8px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white;font-size:14px'>
<button style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:14px;width:100%;border:none;border-radius:12px;font-weight:800;margin-top:10px;box-shadow:0 6px 20px rgba(16,185,129,0.3)'>LOGIN TO PRO DASHBOARD</button>
</form>
<div style='display:flex;justify-content:space-between;margin-top:16px;font-size:13px'><a href='/register' style='color:#3b82f6;text-decoration:none;font-weight:600'>Create account</a><a href='/forgot-password' style='color:#f59e0b;text-decoration:none;font-weight:600'>Forgot password?</a></div>
<div style='background:#0f172a;border:1px solid #1e293b;padding:12px;border-radius:12px;margin-top:20px;font-size:11px;color:#94a3b8'>Master: admin@agent35.com / Agent35! • 6/10 Fix • @Sniper035_bot • Buttons Take/Miss/Track</div>
</div></body></html>
"""

@app.route("/register")
def register_page():
    return """
<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><link href='https://fonts.googleapis.com/css2?family=Inter:wght@600;900&display=swap' rel='stylesheet'></head>
<body style='background:radial-gradient(ellipse at top,#1e293b,#080c14);color:white;font-family:Inter,Arial;padding:20px;min-height:100vh;display:flex;align-items:center;justify-content:center'>
<div style='width:100%;max-width:420px;background:linear-gradient(145deg,#1e293b 0%,#162032 100%);padding:32px;border-radius:24px;border:1px solid #2a3a52;box-shadow:0 24px 64px rgba(0,0,0,0.6)'>
<h2 style='font-weight:900;margin-bottom:16px'>Create Account</h2>
<form action='/register/create' method='post'>
<input name='email' type='email' placeholder='Email' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='name' placeholder='Full Name' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='password' type='password' placeholder='Password min 6' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='ref' placeholder='Referral Code (optional)' style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<button style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:14px;width:100%;border:none;border-radius:12px;font-weight:800;margin-top:10px'>CREATE PRO ACCOUNT</button>
</form>
<p style='text-align:center;margin-top:14px'><a href='/login' style='color:#3b82f6;text-decoration:none;font-size:13px'>Already have account? Login</a></p>
</div></body></html>
"""

@app.route("/register/create", methods=["POST"])
def register_create():
    email=request.form.get("email","").lower().strip()
    auth=load_json(AUTH_FILE)
    if email in auth: return f"Exists <a href='/login'>Login</a>"
    auth[email]={"email":email,"name":request.form.get("name"),"password":hash_pwd(request.form.get("password","")),"account_size":142.0,"total_profit":-1.42,"plan_status":"No Plan","referred_by":request.form.get("ref","").upper(),"created":datetime.now().isoformat(),"reset_token":None}
    save_json(AUTH_FILE, auth); backup_to_telegram(); session["user"]=email; return redirect("/dashboard")

@app.route("/login/check", methods=["POST"])
def login_check():
    email=request.form.get("email","").lower().strip(); pwd=request.form.get("password",""); auth=load_json(AUTH_FILE)
    if email in auth and auth[email].get("password")==hash_pwd(pwd): session["user"]=email; return redirect("/dashboard")
    return f"Wrong - <a href='/login'>Retry</a>"

@app.route("/logout")
def logout(): session.pop("user",None); return redirect("/login")

@app.route("/account/edit", methods=["POST"])
def account_edit():
    if not session.get("user"): return redirect("/login")
    auth=load_json(AUTH_FILE); auth[session["user"]]["account_size"]=float(request.form.get("size","142")); save_json(AUTH_FILE, auth); return redirect("/dashboard")

# ==================== JOURNAL PRO WITH DAY/MONTH/YEAR CLEAR ====================
@app.route("/journal")
def journal_page():
    journal=load_json(JOURNAL_FILE, list)
    tracked=load_json(TRACK_FILE, dict)

    # Group by date
    today_str=datetime.now().strftime("%Y-%m-%d")
    month_str=datetime.now().strftime("%Y-%m")
    year_str=datetime.now().strftime("%Y")

    today_count=len([j for j in journal if j.get("date","")==today_str or today_str in j.get("time","")])
    month_count=len([j for j in journal if j.get("date","").startswith(month_str)])
    year_count=len([j for j in journal if j.get("date","").startswith(year_str)])

    j_rows="".join([f"<tr><td style='color:#94a3b8'>{j.get('time')}</td><td style='font-weight:800'>{j.get('symbol')}</td><td><span class='pill { 'pill-took' if j.get('status')=='TOOK' else 'pill-miss'}'>{j.get('status')}</span></td><td>{j.get('result')}</td><td style='font-size:11px;color:#64748b'>{j.get('date','')}</td></tr>" for j in reversed(journal[-100:])])
    t_rows="".join([f"<tr><td style='font-weight:700'>{v.get('symbol')}</td><td><span class='pill pill-took'>TRACKING</span></td><td>{v.get('sl')}</td><td>{v.get('tp')}</td><td>{v.get('by')}</td><td style='font-size:11px'>{v.get('started','')[:16]}</td></tr>" for v in tracked.values()]) or "<tr><td colspan=6 style='text-align:center;color:#64748b;padding:30px'>No tracked trades - click 📈 TRACK TO SL/TP on Telegram @Sniper035_bot</td></tr>"

    content=f"""
<div style='max-width:1600px;margin:0 auto;padding:20px'>
  <div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:20px'>
    <h1 style='font-weight:900;letter-spacing:-1px;margin:0'>📓 Journal Pro • {len(journal)} Entries • Storage {BASE_DIR}</h1>
    <div style='display:flex;gap:8px;flex-wrap:wrap'>
      <a href='/journal/clear?period=today' onclick='return confirm("Clear TODAY {today_count} entries?")' style='background:#1e293b;border:1px solid #334155;color:#f59e0b;padding:10px 16px;border-radius:12px;text-decoration:none;font-weight:700;font-size:12px'>🗑️ Clear Today ({today_count})</a>
      <a href='/journal/clear?period=month' onclick='return confirm("Clear THIS MONTH {month_count} entries?")' style='background:#1e293b;border:1px solid #334155;color:#f59e0b;padding:10px 16px;border-radius:12px;text-decoration:none;font-weight:700;font-size:12px'>🗑️ Clear Month ({month_count})</a>
      <a href='/journal/clear?period=year' onclick='return confirm("Clear THIS YEAR {year_count} entries?")' style='background:#1e293b;border:1px solid #334155;color:#ef4444;padding:10px 16px;border-radius:12px;text-decoration:none;font-weight:700;font-size:12px'>🗑️ Clear Year ({year_count})</a>
      <a href='/journal/clear?period=all' onclick='return confirm("Clear ALL {len(journal)} entries? This cannot be undone!")' style='background:linear-gradient(135deg,#ef4444,#dc2626);color:white;padding:10px 16px;border-radius:12px;text-decoration:none;font-weight:800;font-size:12px;box-shadow:0 4px 12px rgba(239,68,68,0.3)'>💥 Clear All ({len(journal)})</a>
    </div>
  </div>

  <div class='table-card' style='margin-bottom:20px'>
    <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:16px'>
      <h3 style='margin:0;font-weight:800'>Trade History - Day / Month / Year Tracking</h3>
      <span style='background:#0f172a;border:1px solid #1e293b;padding:6px 12px;border-radius:20px;font-size:11px;color:#94a3b8'>Today {today_str} • Month {month_str} • Year {year_str}</span>
    </div>
    <div style='overflow-x:auto'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th><th>Date</th></tr>{j_rows or '<tr><td colspan=5 style=text-align:center;padding:40px;color:#64748b>No trades yet - scan and send Telegram signals, then click TAKE on @Sniper035_bot</td></tr>'}</table></div>
  </div>

  <div class='table-card'>
    <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:16px'>
      <h3 style='margin:0;font-weight:800'>📈 Tracked Trades to SL/TP - Live Monitoring</h3>
      <a href='/journal/clear-tracked?period=all' onclick='return confirm("Clear all tracked trades?")' style='background:#ef444433;border:1px solid #ef444433;color:#ef4444;padding:8px 14px;border-radius:10px;text-decoration:none;font-weight:700;font-size:12px'>Clear Tracked ({len(tracked)})</a>
    </div>
    <div style='overflow-x:auto'><table><tr><th>Symbol</th><th>Status</th><th>SL</th><th>TP</th><th>By</th><th>Started</th></tr>{t_rows}</table></div>
    <div style='background:#0f172a;border:1px solid #1e293b;padding:14px;border-radius:12px;margin-top:16px;font-size:12px;color:#94a3b8'>
      <b style='color:#10b981'>How Tracking Works:</b> Click 📈 TRACK TO SL/TP on Telegram @Sniper035_bot -> trade added here -> cron checks every 5 min if SL/TP hit -> you get Telegram alert when hit. Clear tracked when done.
    </div>
  </div>
</div>
"""
    return pro_layout(content,"Journal")

@app.route("/journal/clear")
def journal_clear():
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

# ==================== GUIDE PRO - FROM PAY TO SIGNAL ====================
@app.route("/guide")
def guide_page():
    content=f"""
<div style='max-width:1000px;margin:0 auto;padding:20px'>
  <div style='text-align:center;margin-bottom:32px'>
    <h1 style='font-weight:900;font-size:32px;letter-spacing:-1px;margin-bottom:8px;background:linear-gradient(135deg,#10b981,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent'>📖 Agent 35 Pro - Complete User Guide</h1>
    <p style='color:#94a3b8;font-size:14px'>From Payment to First Real Signal - Everything you need to know</p>
  </div>

  <div style='display:grid;gap:16px'>

    <div class='card' style='border-left:4px solid #10b981'>
      <div style='display:flex;gap:14px;align-items:flex-start'>
        <div style='background:linear-gradient(135deg,#10b981,#059669);width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:900;flex-shrink:0'>1</div>
        <div style='flex:1'>
          <h3 style='margin:0 0 8px 0;font-weight:800'>💳 Step 1: Pay Capitec {CAPITEC['acc']}</h3>
          <p style='color:#94a3b8;font-size:13px;line-height:1.6;margin:0'>
            • Go to <b style='color:white'>/pay</b> -> Enter email + WhatsApp + choose Yearly R500 or Lifetime R5000<br>
            • System gives you unique reference like <code style='background:#0f172a;padding:2px 6px;border-radius:4px'>A35-JOHN-123</code><br>
            • Open Capitec App -> Transfer R500 or R5000 to <b style='color:white'>Acc: {CAPITEC['acc']} Holder: {CAPITEC['holder']} Branch: {CAPITEC['branch']}</b><br>
            • <b style='color:#f59e0b'>MUST use exact reference</b> in Capitec reference field<br>
            • Share proof to admin via Telegram @Sniper035_bot
          </p>
        </div>
      </div>
    </div>

    <div class='card' style='border-left:4px solid #3b82f6'>
      <div style='display:flex;gap:14px;align-items:flex-start'>
        <div style='background:linear-gradient(135deg,#3b82f6,#2563eb);width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:900;flex-shrink:0'>2</div>
        <div style='flex:1'>
          <h3 style='margin:0 0 8px 0;font-weight:800'>✅ Step 2: Admin Accepts (24h)</h3>
          <p style='color:#94a3b8;font-size:13px;line-height:1.6;margin:0'>
            • Admin checks Capitec App for your payment + reference<br>
            • Go to <code>/admin?secret=YOUR_SECRET</code> -> Click <b style='color:#10b981'>ACCEPT</b> on your reference<br>
            • Your login <b style='color:white'>email becomes ACTIVE</b> instantly<br>
            • If you used referral code, your friend gets +1 towards 10 = free R5000 Lifetime<br>
            • You get Telegram message if chat ID set
          </p>
        </div>
      </div>
    </div>

    <div class='card' style='border-left:4px solid #8b5cf6'>
      <div style='display:flex;gap:14px;align-items:flex-start'>
        <div style='background:linear-gradient(135deg,#8b5cf6,#7c3aed);width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:900;flex-shrink:0'>3</div>
        <div style='flex:1'>
          <h3 style='margin:0 0 8px 0;font-weight:800'>🔐 Step 3: Login & Setup</h3>
          <p style='color:#94a3b8;font-size:13px;line-height:1.6;margin:0'>
            • Login at <b style='color:white'>/login</b> with your email + password<br>
            • Dashboard shows <b style='color:white'>Account Size R142</b> -> Edit to your real account size<br>
            • Watchlist: EURUSD GBPUSD USDJPY USDCHF (4 major)<br>
            • Go to <b style='color:white'>/link-telegram</b> -> Follow steps to link your Telegram for signals<br>
            • Your plan shows <b style='color:#10b981'>ACTIVE Yearly / Lifetime</b> at top
          </p>
        </div>
      </div>
    </div>

    <div class='card' style='border-left:4px solid #f59e0b'>
      <div style='display:flex;gap:14px;align-items:flex-start'>
        <div style='background:linear-gradient(135deg,#f59e0b,#d97706);width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:900;flex-shrink:0'>4</div>
        <div style='flex:1'>
          <h3 style='margin:0 0 8px 0;font-weight:800'>📡 Step 4: How Signals Work (6/10 Fix)</h3>
          <p style='color:#94a3b8;font-size:13px;line-height:1.6;margin:0'>
            • Engine scans 4H trend: Bullish / Bearish / <b style='color:white'>Neutral allowed</b><br>
            • 15m looks for BOS (Break of Structure) + FVG (Fair Value Gap)<br>
            • 5m confirms entry with 6/10 scoring<br>
            • If score >=6, bot sends signal to <b style='color:white'>@Sniper035_bot</b> with 3 buttons:<br>
            <span style='background:#10b98122;border:1px solid #10b98133;padding:3px 8px;border-radius:6px;color:#10b981'>✅ TAKE TRADE</span> <span style='background:#1e293b;border:1px solid #334155;padding:3px 8px;border-radius:6px'>❌ MISS</span> <span style='background:#8b5cf622;border:1px solid #8b5cf633;padding:3px 8px;border-radius:6px;color:#8b5cf6'>📈 TRACK TO SL/TP</span><br>
            • Cron scans every 30 min automatically - no manual scan needed
          </p>
        </div>
      </div>
    </div>

    <div class='card' style='border-left:4px solid #10b981'>
      <div style='display:flex;gap:14px;align-items:flex-start'>
        <div style='background:linear-gradient(135deg,#10b981,#059669);width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:900;flex-shrink:0'>5</div>
        <div style='flex:1'>
          <h3 style='margin:0 0 8px 0;font-weight:800'>🎯 Step 5: Taking Trades & Journal</h3>
          <p style='color:#94a3b8;font-size:13px;line-height:1.6;margin:0'>
            • When signal arrives in Telegram: Check chart, if you like it -> click <b style='color:#10b981'>TAKE TRADE</b><br>
            • Trade logged to <b style='color:white'>Journal</b> + Dashboard as TOOK with R0<br>
            • Update result later in journal: R+1.5, R-0.5, etc.<br>
            • Click <b style='color:#8b5cf6'>TRACK TO SL/TP</b> -> trade goes to tracked list -> cron checks every 5 min if SL/TP hit -> you get alert<br>
            • Click <b style='color:#ef4444'>MISS</b> if you skip -> logged as MISS<br>
            • <b style='color:white'>Clear options:</b> In Journal you can clear Today / This Month / This Year / All separately to manage your stats
          </p>
        </div>
      </div>
    </div>

    <div class='card' style='border-left:4px solid #06b6d4'>
      <div style='display:flex;gap:14px;align-items:flex-start'>
        <div style='background:linear-gradient(135deg,#06b6d4,#0891b2);width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:900;flex-shrink:0'>6</div>
        <div style='flex:1'>
          <h3 style='margin:0 0 8px 0;font-weight:800'>🔗 Step 6: Referral - 10 Paid = R5000 FREE</h3>
          <p style='color:#94a3b8;font-size:13px;line-height:1.6;margin:0'>
            • Go to <b style='color:white'>/referral</b> -> Create code e.g. SNIPE<br>
            • Share link: <code style='background:#0f172a;padding:2px 6px;border-radius:4px'>https://agent-35-trading-bot.onrender.com/join?ref=SNIPE</code><br>
            • Friend pays Capitec with your code in referral field<br>
            • After admin ACCEPTS their payment, you get +1 count<br>
            • <b style='color:#10b981'>10 paid referrals = Lifetime R5000 FREE</b> - auto upgraded<br>
            • Only counts after ACCEPT - no fake referrals - tracked in Creator Dashboard
          </p>
        </div>
      </div>
    </div>

    <div class='card' style='background:linear-gradient(145deg,#132a22 0%,#1e293b 100%);border:1px solid #10b98133'>
      <h3 style='margin:0 0 12px 0;font-weight:800;color:#10b981'>🚀 Quick Start Checklist - Do This Now</h3>
      <div style='display:grid;gap:8px;font-size:13px'>
        <div style='display:flex;gap:8px'><span>✅</span><span>Pay Capitec {CAPITEC['acc']} with ref from /pay</span></div>
        <div style='display:flex;gap:8px'><span>✅</span><span>Wait admin ACCEPT in /admin (24h max)</span></div>
        <div style='display:flex;gap:8px'><span>✅</span><span>Login /login -> Edit Account Size</span></div>
        <div style='display:flex;gap:8px'><span>✅</span><span>Link Telegram /link-telegram -> Send Hi to @Sniper035_bot -> Set webhook in /creator</span></div>
        <div style='display:flex;gap:8px'><span>✅</span><span>Wait for signal (30 min scan) -> Click TAKE / TRACK on Telegram</span></div>
        <div style='display:flex;gap:8px'><span>✅</span><span>Check Journal /journal -> Clear by Day/Month/Year when needed</span></div>
        <div style='display:flex;gap:8px'><span>✅</span><span>Share referral /join?ref=YOURCODE -> Get 10 paid = Lifetime FREE</span></div>
      </div>
      <div style='margin-top:16px;display:flex;gap:8px;flex-wrap:wrap'>
        <a href='/pay' style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:10px 18px;border-radius:10px;text-decoration:none;font-weight:700'>💳 Pay Now - Capitec {CAPITEC['acc']}</a>
        <a href='/dashboard-scan' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px 18px;border-radius:10px;text-decoration:none;font-weight:700'>📡 Scan Signals</a>
        <a href='/creator?secret=' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px 18px;border-radius:10px;text-decoration:none;font-weight:700'>👑 Creator Dashboard</a>
      </div>
    </div>

  </div>
</div>
"""
    return pro_layout(content,"Guide")

# ==================== OTHER PAGES KEEP PRO STYLE ====================
@app.route("/dashboard-scan")
def dashboard_scan():
    syms=["EURUSD","GBPUSD","USDJPY","USDCHF","XAUUSD","US30","NAS100","GBPJPY"]
    rows=""
    for s in syms:
        r=eng.full_multi_tf_analysis(s)
        score_color="#10b981" if r['score']>=6 else "#f59e0b" if r['score']>=4 else "#ef4444"
        rows+=f"<tr><td style='font-weight:800'>{s}</td><td><span style='background:{score_color}22;color:{score_color};border:1px solid {score_color}33;padding:4px 10px;border-radius:20px;font-weight:800'>{r['score']}/10</span></td><td>{r['bias']}</td><td>{r['signal']}</td><td><a href='/send-signal?symbol={s}' style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-weight:700;font-size:12px'>Send TG</a></td></tr>"
    content=f"<div style='max-width:1400px;margin:0 auto;padding:20px'><div class='table-card'><div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:16px'><h2 style='margin:0;font-weight:900'>📡 Scan All 8 Pairs - 6/10 Fix</h2><span style='background:#10b98122;color:#10b981;padding:6px 12px;border-radius:20px;font-size:11px;font-weight:700'>4H Neutral Allowed + 15m BOS+FVG</span></div><div style='overflow-x:auto'><table><tr><th>Symbol</th><th>Score</th><th>Bias</th><th>Signal</th><th>Telegram</th></tr>{rows}</table></div></div></div>"
    return pro_layout(content,"All Signals")

@app.route("/send-signal")
def send_signal():
    sym=request.args.get("symbol","EURUSD"); r=eng.full_multi_tf_analysis(sym); res=send_telegram_signal(sym,r['score'],r['bias'],r['signal'],"SL auto","TP auto",r.get('reason',''))
    return f"<html><body style='background:#080c14;color:white;padding:40px;font-family:Inter'><div style='max-width:500px;margin:auto;background:#1e293b;padding:24px;border-radius:20px'><h2>Sent {sym} {r['score']}/10 to @Sniper035_bot</h2><p style='font-size:12px;background:#0f172a;padding:10px;border-radius:8px'>{res}</p><a href='/dashboard-scan' style='background:#10b981;color:white;padding:10px 20px;border-radius:10px;text-decoration:none'>Back</a></div></body></html>"

@app.route("/link-telegram")
def link_telegram():
    bot=os.getenv("TELEGRAM_BOT_TOKEN","Not set")[:25]; chat=os.getenv("TELEGRAM_CHAT_ID","Not set")
    content=f"<div style='max-width:600px;margin:0 auto;padding:20px'><div class='card'><h2 style='font-weight:900'>🔗 Telegram Connect - @Sniper035_bot</h2><div class='pro-stat' style='margin:12px 0;font-size:12px'>Bot: {bot}...<br>Chat: {chat}<br>Webhook: https://agent-35-trading-bot.onrender.com/telegram/webhook</div><div style='background:#0f172a;padding:14px;border-radius:12px;font-size:12px;line-height:1.6;color:#94a3b8'>1. Send 'Hi' to @Sniper035_bot<br>2. Creator -> Get Chat ID -> Copy number -> Set in Render Env TELEGRAM_CHAT_ID<br>3. Creator -> SET WEBHOOK -> ok True<br>4. Test Telegram -> Check 3 buttons Take/Miss/Track</div><a href='/test-telegram' style='background:linear-gradient(135deg,#3b82f6,#2563eb);color:white;padding:12px;border-radius:12px;text-align:center;display:block;text-decoration:none;font-weight:700;margin-top:14px'>Test Telegram + Buttons</a><a href='/creator?secret=' style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:12px;border-radius:12px;text-align:center;display:block;text-decoration:none;font-weight:700;margin-top:10px'>Go Creator + Set Webhook Inside</a></div></div>"
    return pro_layout(content,"Settings")

@app.route("/test-telegram")
def test_telegram():
    res=send_telegram_signal("EURUSD",7,"BUY","BUY NOW","1.0845 SL","1.0920 TP","6/10 Fix Pro Edition")
    content=f"<div style='max-width:600px;margin:0 auto;padding:40px;text-align:center'><div class='card'><h2>Test Sent to @Sniper035_bot</h2><p style='font-size:11px;background:#0f172a;padding:10px;border-radius:8px;word-break:break-all'>{res}</p><p>Check Telegram for 3 buttons: ✅ TAKE | ❌ MISS | 📈 TRACK</p><a href='/creator?secret=' style='background:#10b981;color:white;padding:10px 20px;border-radius:12px;text-decoration:none;font-weight:700'>Back Creator</a></div></div>"
    return pro_layout(content,"Settings")

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data=request.get_json()
    if not data: return jsonify({"ok":True})
    if "callback_query" in data:
        cb=data["callback_query"]; cb_data=cb.get("data",""); cb_id=cb.get("id"); chat_id=cb["message"]["chat"]["id"]; user_name=cb["from"].get("first_name","User")
        journal=load_json(JOURNAL_FILE, list); tracked=load_json(TRACK_FILE, dict); bot=os.getenv("TELEGRAM_BOT_TOKEN")
        if cb_data.startswith("TAKE_"): _,sym,score=cb_data.split("_"); journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"TOOK","result":f"Taken by {user_name} {score}/10","date":datetime.now().strftime("%Y-%m-%d")}); save_json(JOURNAL_FILE, journal[-200:]); text=f"✅ {user_name} TOOK {sym}"
        elif cb_data.startswith("MISS_"): sym=cb_data.split("_")[1]; journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"MISS","result":"Missed","date":datetime.now().strftime("%Y-%m-%d")}); save_json(JOURNAL_FILE, journal[-200:]); text=f"❌ MISSED {sym}"
        elif cb_data.startswith("TRACK_"): parts=cb_data.split("_"); sym=parts[1]; sl=parts[2]; tp=parts[3] if len(parts)>3 else "TP"; tid=f"{sym}_{datetime.now().strftime('%H%M%S')}"; tracked[tid]={"symbol":sym,"sl":sl,"tp":tp,"status":"TRACKING","started":datetime.now().isoformat(),"by":user_name}; save_json(TRACK_FILE, tracked); text=f"📈 TRACKING {sym}"
        else: text="Unknown"
        if bot:
            try: requests.post(f"https://api.telegram.org/bot{bot}/answerCallbackQuery", json={"callback_query_id":cb_id,"text":text}, timeout=5); requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":text}, timeout=5)
            except: pass
        return jsonify({"ok":True})
    return jsonify({"ok":True})

@app.route("/pay")
def pay_page():
    ref=request.args.get("ref","") or session.get("ref","")
    email=request.args.get("email","") or session.get("user","")
    content=f"""
<div style='max-width:500px;margin:0 auto;padding:20px'><div class='card'>
<h2 style='font-weight:900'>💳 Buy Pro Plan - Capitec {CAPITEC['acc']}</h2>
<div class='pro-stat' style='margin:12px 0'><b>Bank:</b> {CAPITEC['bank']}<br><b>Holder:</b> {CAPITEC['holder']}<br><b>Acc:</b> {CAPITEC['acc']}<br><b>Branch:</b> {CAPITEC['branch']}</div>
<form action='/pay/create' method='get'>
<input type='hidden' name='ref' value='{ref}'>
<input name='user' value='{email}' placeholder='Email (your login email)' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<input name='phone' placeholder='WhatsApp number' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'>
<select name='plan' style='width:100%;padding:14px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><option value='yearly'>Yearly R500 - 365 Days</option><option value='lifetime'>Lifetime R5000 - Forever</option></select>
<button style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:14px;width:100%;border:none;border-radius:12px;margin-top:10px;font-weight:800'>GET PAYMENT REFERENCE</button>
</form>
{f'<p style=color:#10b981;font-size:12px;margin-top:10px>Referred by: {ref} - You help them get 10 = free lifetime!</p>' if ref else ''}
</div></div>
"""
    return pro_layout(content,"Plans")

@app.route("/pay/create")
def pay_create():
    user=request.args.get("user","").lower().strip(); phone=request.args.get("phone","").strip(); plan_key=request.args.get("plan","yearly"); ref=request.args.get("ref","").upper().strip()
    short="".join([c for c in user.upper() if c.isalnum()])[:5] or "USER"; rand="".join(random.choices(string.digits,k=3)); pref=f"{CAPITEC['ref_prefix']}-{short}-{rand}"
    plan=PLANS.get(plan_key, PLANS["yearly"]); users=load_json(USERS_FILE); users[pref]={"user":user,"phone":phone,"plan":plan_key,"price":plan["price"],"payment_ref":pref,"referred_by":ref,"status":"pending","created":datetime.now().isoformat(),"expires":None}; save_json(USERS_FILE, users)
    return f"<html><body style='background:#080c14;color:white;font-family:Inter;padding:40px;text-align:center'><div style='max-width:480px;margin:auto;background:linear-gradient(145deg,#1e293b,#162032);padding:28px;border-radius:20px;border:1px solid #2a3a52'><h1>Pay R{plan['price']} for {plan['name']}</h1><div style='border:2px dashed #334155;padding:20px;border-radius:16px;background:#0f172a;margin:16px 0'><p>Bank: {CAPITEC['bank']}<br>{CAPITEC['holder']}<br>Acc: {CAPITEC['acc']} Branch: {CAPITEC['branch']}</p><h1 style='background:white;color:black;padding:16px;border-radius:12px;letter-spacing:2px'>{pref}</h1><p style='color:#f59e0b;font-weight:800'>USE THIS EXACT REFERENCE IN CAPITEC APP</p></div><a href='/dashboard' style='background:#1e293b;color:white;padding:10px 20px;border-radius:10px;text-decoration:none'>Back</a></div></body></html>"

@app.route("/creator")
@app.route("/master")
def creator_dashboard():
    secret=request.args.get("secret",""); auth=load_json(AUTH_FILE); users=load_json(USERS_FILE); refs=load_json(DATA_FILE); tracked=load_json(TRACK_FILE, dict); system=load_json(SYSTEM_FILE, dict)
    bot_token=os.getenv("TELEGRAM_BOT_TOKEN","Not set"); chat_id=os.getenv("TELEGRAM_CHAT_ID","Not set"); bot_short=bot_token[:20]+"..." if len(bot_token)>20 else bot_token
    webhook_info={}
    if len(bot_token)>20:
        try: webhook_info=requests.get(f"https://api.telegram.org/bot{bot_token}/getWebhookInfo",timeout=5).json()
        except: webhook_info={}
    total_users=len(auth); pending=len([u for u in users.values() if u.get("status")=="pending"]); revenue=sum([u.get("price",0) for u in users.values() if u.get("status")=="active"])
    content=f"""
<div style='max-width:1600px;margin:0 auto;padding:20px'>
<h1 style='font-weight:900;font-size:28px;letter-spacing:-1px'>👑 Creator Dashboard Pro • {BASE_DIR} • Capitec {CAPITEC['acc']}</h1>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:16px 0'>
  <div class='card'><div class='card-title'>Total Users</div><div class='card-value' style='color:white'>{total_users}</div></div>
  <div class='card'><div class='card-title'>Pending</div><div class='card-value' style='color:#f59e0b'>{pending}</div></div>
  <div class='card'><div class='card-title'>Revenue</div><div class='card-value' style='color:#10b981'>R{revenue}</div></div>
  <div class='card'><div class='card-title'>Tracking</div><div class='card-value' style='color:#8b5cf6'>{len([t for t in tracked.values() if t['status']=='TRACKING'])}</div></div>
</div>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:16px'>
  <div class='card'>
    <h3 style='color:#10b981;font-weight:800'>🤖 Webhook Inside Creator</h3>
    <p style='font-size:11px;color:#94a3b8'>Bot: {bot_short}<br>Chat: {chat_id}<br>https://agent-35-trading-bot.onrender.com/telegram/webhook<br><br>{str(webhook_info)[:500]}</p>
    <div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px'>
      <a href='/creator/webhook?action=set&secret={secret}' style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:12px;border-radius:12px;text-align:center;text-decoration:none;font-weight:800'>🔗 SET WEBHOOK NOW</a>
      <a href='/creator/webhook?action=getUpdates&secret={secret}' style='background:#8b5cf6;color:white;padding:12px;border-radius:12px;text-align:center;text-decoration:none;font-weight:700'>📩 Get Chat ID</a>
      <a href='/creator/webhook?action=info&secret={secret}' style='background:#3b82f6;color:white;padding:12px;border-radius:12px;text-align:center;text-decoration:none'>ℹ️ Check Info</a>
      <a href='/test-telegram' style='background:#1e293b;border:1px solid #334155;color:white;padding:12px;border-radius:12px;text-align:center;text-decoration:none'>Test Buttons</a>
    </div>
  </div>
  <div class='card'>
    <h3 style='color:#f59e0b;font-weight:800'>💾 Keep Logins Pro</h3>
    <p style='font-size:11px;color:#94a3b8'>Storage: {BASE_DIR} | {"✅ PERSISTENT like last week" if BASE_DIR=="/data" else "⚠️ Add Disk /data"}<br>Users: {total_users} | Last scan: {system.get('last_scan','Never')[:19] if system.get('last_scan') else 'Never'}</p>
    <div style='display:grid;grid-template-columns:1fr 1fr;gap:8px'>
      <a href='/creator/action?act=backup&secret={secret}' style='background:#10b981;color:white;padding:12px;border-radius:12px;text-align:center;text-decoration:none;font-weight:700'>⬇️ Download Backup</a>
      <a href='/creator/backup-restore' style='background:#f59e0b;color:white;padding:12px;border-radius:12px;text-align:center;text-decoration:none;font-weight:700'>⬆️ Restore Backup</a>
      <a href='/run-now?secret={secret}' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px;border-radius:10px;text-align:center;text-decoration:none'>Run Scan Now</a>
      <a href='/health' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px;border-radius:10px;text-align:center;text-decoration:none'>/health</a>
    </div>
  </div>
</div>
</div>
"""
    return pro_layout(content,"Master")

@app.route("/creator/webhook")
def creator_webhook():
    secret=request.args.get("secret",""); action=request.args.get("action","info"); bot_token=os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token: return "Set TELEGRAM_BOT_TOKEN"
    base_url=f"https://api.telegram.org/bot{bot_token}"; webhook_url="https://agent-35-trading-bot.onrender.com/telegram/webhook"
    try:
        if action=="set": r=requests.get(f"{base_url}/setWebhook", params={"url":webhook_url}, timeout=10).json(); return f"<html><body style='background:#080c14;color:white;padding:20px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:20px;border-radius:16px'><h2>Set Webhook</h2><pre style='background:#0f172a;padding:15px;border-radius:12px'>{json.dumps(r, indent=2)}</pre><a href='/creator?secret={secret}' style='background:#10b981;color:white;padding:10px 20px;border-radius:12px;text-decoration:none'>Back Creator</a></div></body></html>"
        elif action=="info": r=requests.get(f"{base_url}/getWebhookInfo", timeout=10).json(); return f"<html><body style='background:#080c14;color:white;padding:20px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:20px;border-radius:16px'><h2>Webhook Info</h2><pre style='background:#0f172a;padding:15px;border-radius:12px'>{json.dumps(r, indent=2)}</pre><a href='/creator?secret={secret}' style='background:#10b981;color:white;padding:10px 20px;border-radius:12px;text-decoration:none'>Back</a></div></body></html>"
        elif action=="getUpdates": r=requests.get(f"{base_url}/getUpdates", timeout=10).json(); chats=[];
        for upd in r.get("result",[]):
            if "message" in upd: chats.append(f"Chat ID: {upd['message']['chat']['id']} - {upd['message']['chat'].get('first_name','')}")
        chat_text="<br>".join(chats) or "Send Hi to @Sniper035_bot then click again"
        return f"<html><body style='background:#080c14;color:white;padding:20px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:20px;border-radius:16px'><h2>Chat IDs</h2><div style='background:#10b98122;padding:12px;border-radius:10px'>{chat_text}</div><pre style='max-height:300px;overflow:auto;background:#0f172a;padding:10px;border-radius:10px;font-size:11px'>{json.dumps(r, indent=2)[:3000]}</pre><a href='/creator?secret={secret}' style='background:#10b981;color:white;padding:10px 20px;border-radius:10px;text-decoration:none'>Back</a></div></body></html>"
    except Exception as e: return f"Error {e}"
    return redirect(f"/creator?secret={secret}")

@app.route("/creator/backup-restore", methods=["GET","POST"])
def backup_restore():
    if request.method=="GET":
        return "<html><body style='background:#080c14;color:white;padding:20px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:20px;border-radius:16px'><h2>Restore Backup</h2><form method='post' enctype='multipart/form-data'><input type='file' name='backup' required style='width:100%;padding:12px;margin:10px 0;background:#0f172a;border-radius:10px;border:1px solid #334155'><button style='background:#f59e0b;color:white;padding:12px;width:100%;border:none;border-radius:12px;font-weight:800'>RESTORE NOW</button></form></div></body></html>"
    else:
        file=request.files.get('backup')
        try:
            data=json.load(file)
            if "auth_users" in data: save_json(AUTH_FILE, data["auth_users"])
            else: save_json(AUTH_FILE, data)
            return f"<html><body style='background:#080c14;color:white;padding:30px;text-align:center'><h2>✅ Restored {len(load_json(AUTH_FILE))} users to {AUTH_FILE}</h2><a href='/login' style='background:#10b981;color:white;padding:12px 20px;border-radius:12px;text-decoration:none'>Login</a></body></html>"
        except Exception as e: return f"Error {e}"

@app.route("/creator/action")
def creator_action():
    secret=request.args.get("secret",""); act=request.args.get("act","")
    if act=="backup": return jsonify({"auth_users":load_json(AUTH_FILE),"payments":load_json(USERS_FILE),"time":datetime.now().isoformat(),"storage":BASE_DIR})
    if act=="delete_user":
        email=request.args.get("email",""); auth=load_json(AUTH_FILE)
        if email in auth and email!="admin@agent35.com": del auth[email]; save_json(AUTH_FILE, auth); backup_to_telegram()
        return redirect(f"/creator?secret={secret}")
    if act=="make_active":
        email=request.args.get("email",""); auth=load_json(AUTH_FILE)
        if email in auth: auth[email]["plan_status"]="ACTIVE lifetime - By Creator"; auth[email]["expires"]=(datetime.now()+timedelta(days=36500)).isoformat(); save_json(AUTH_FILE, auth); backup_to_telegram()
        return redirect(f"/creator?secret={secret}")
    return redirect(f"/creator?secret={secret}")

@app.route("/cron/scan")
def cron_scan():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    system=load_json(SYSTEM_FILE, dict); system["last_scan"]=datetime.now().isoformat(); system["total_scans"]=system.get("total_scans",0)+1; save_json(SYSTEM_FILE, system)
    sent=[]
    for s in ["EURUSD","GBPUSD","USDJPY","USDCHF","XAUUSD","US30"]:
        r=eng.full_multi_tf_analysis(s)
        if r.get("score",0)>=6: send_telegram_signal(s,r['score'],r['bias'],r['signal'],"SL auto","TP auto",r.get('reason','')); sent.append(s); j=load_json(JOURNAL_FILE, list); j.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":s,"status":"TOOK","result":f"{r['score']}/10 {r['bias']}","date":datetime.now().strftime("%Y-%m-%d")}); save_json(JOURNAL_FILE, j[-200:])
    return jsonify({"sent":sent})

@app.route("/health")
def health(): return jsonify({"ok":True,"version":"V17 PRO - Professional look + Journal day/month/year clear + Guide pay to signal","storage":BASE_DIR,"persistent":BASE_DIR=="/data","users":len(load_json(AUTH_FILE)),"capitec":CAPITEC['acc']})

@app.route("/settings")
def settings_page():
    system=load_json(SYSTEM_FILE, dict)
    content=f"<div style='max-width:800px;margin:0 auto;padding:20px'><div class='card'><h2 style='font-weight:900'>⚙️ Settings Pro</h2><div class='pro-stat' style='margin-top:12px'>Storage: {BASE_DIR}<br>Capitec: {CAPITEC['acc']}<br>Bot: @Sniper035_bot<br>Threshold: 6/10 Fix<br>System up: {system.get('system_up_since','')[:19]}<br>Scans: {system.get('total_scans',0)}<br>Signals: {system.get('total_signals',0)}</div><a href='/creator?secret=' style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:10px 20px;border-radius:12px;text-decoration:none;display:inline-block;margin-top:12px;font-weight:700'>Go Creator Dashboard</a></div></div>"
    return pro_layout(content,"Settings")

@app.route("/plans")
def plans_page():
    content=f"<div style='max-width:800px;margin:0 auto;padding:20px'><div class='card'><h2 style='font-weight:900'>💳 Plans - Capitec {CAPITEC['acc']}</h2><p>Bank: {CAPITEC['bank']} Holder: {CAPITEC['holder']}<br>Acc: {CAPITEC['acc']} Branch: {CAPITEC['branch']}<br><br><b>Yearly R500</b> - 365 days<br><b>Lifetime R5000</b> - forever<br>10 paid referrals = FREE Lifetime</p><a href='/pay' style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:10px 20px;border-radius:12px;text-decoration:none;font-weight:700'>Buy Now</a></div></div>"
    return pro_layout(content,"Plans")

@app.route("/run-now")
def run_now():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    return jsonify(eng.run_scan_and_send())

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000)
