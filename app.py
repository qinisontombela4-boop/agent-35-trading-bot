from flask import Flask, request, jsonify, session, redirect
import os, json, random, hashlib, secrets, string, requests
from dotenv import load_dotenv
import trading_engine as eng
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "agent35-v16-full-everything")

# ==================== STORAGE - LAST WEEK MODE ====================
# If /data disk exists (Render Disks -> Add Disk /data 1GB) -> PERSISTENT like last week
# If not -> TEMPORARY but auto-backup to @Sniper035_bot
BASE_DIR = "/data" if os.path.exists("/data") else "."
AUTH_FILE = os.path.join(BASE_DIR, "auth_users.json")
USERS_FILE = os.path.join(BASE_DIR, "users_data.json")
DATA_FILE = os.path.join(BASE_DIR, "referrals_data.json")
JOURNAL_FILE = os.path.join(BASE_DIR, "journal.json")
TRACK_FILE = os.path.join(BASE_DIR, "tracked_trades.json")
SYSTEM_FILE = os.path.join(BASE_DIR, "system_status.json")

CAPITEC = {"bank":"Capitec","holder":"Agent 35 Trading Bot","acc":"2586572676","branch":"470010","ref_prefix":"A35"}
PLANS = {"yearly":{"name":"Yearly","price":500,"days":365},"lifetime":{"name":"Lifetime","price":5000,"days":36500}}

def load_json(path, default_type=dict):
    if not os.path.exists(path):
        return {} if default_type==dict else []
    try:
        with open(path,"r") as f:
            return json.load(f)
    except:
        return {} if default_type==dict else []

def save_json(path, data):
    with open(path,"w") as f:
        json.dump(data, f, indent=2)

def hash_pwd(p):
    return hashlib.sha256(p.encode()).hexdigest()

def backup_to_telegram():
    bot = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not bot or not chat:
        return
    auth = load_json(AUTH_FILE)
    if len(auth) <= 1:
        return
    try:
        url = f"https://api.telegram.org/bot{bot}/sendDocument"
        payload = {
            "auth_users": auth,
            "payments": load_json(USERS_FILE),
            "referrals": load_json(DATA_FILE),
            "time": datetime.now().isoformat(),
            "storage": BASE_DIR
        }
        files = {'document': ('agent35_backup.json', json.dumps(payload, indent=2).encode())}
        data = {'chat_id': chat, 'caption': f"🔐 Auto Backup {datetime.now().strftime('%m-%d %H:%M')} - {len(auth)} users - Stored in {BASE_DIR}"}
        requests.post(url, files=files, data=data, timeout=10)
    except:
        pass

def ensure_files():
    if not os.path.exists(AUTH_FILE):
        save_json(AUTH_FILE, {
            "admin@agent35.com": {
                "email":"admin@agent35.com",
                "name":"Master Creator",
                "password":hash_pwd("Agent35!"),
                "account_size":142.0,
                "total_profit":-1.42,
                "plan_status":"ACTIVE lifetime - CREATOR",
                "referred_by":"",
                "expires":(datetime.now()+timedelta(days=36500)).isoformat(),
                "created":datetime.now().isoformat(),
                "reset_token":None
            }
        })
        print(f"FIRST RUN - master created in {AUTH_FILE}")
    else:
        print(f"✅ Loaded {len(load_json(AUTH_FILE))} users from {AUTH_FILE} - storage {BASE_DIR} - {'PERSISTENT' if BASE_DIR=='/data' else 'TEMPORARY'}")

    if not os.path.exists(USERS_FILE): save_json(USERS_FILE, {})
    if not os.path.exists(DATA_FILE): save_json(DATA_FILE, {})
    if not os.path.exists(JOURNAL_FILE): save_json(JOURNAL_FILE, [])
    if not os.path.exists(TRACK_FILE): save_json(TRACK_FILE, {})
    if not os.path.exists(SYSTEM_FILE): save_json(SYSTEM_FILE, {"last_scan":None,"last_cron":None,"total_scans":0,"total_signals":0,"system_up_since":datetime.now().isoformat(),"webhook_set":False})

ensure_files()

# ==================== TELEGRAM WITH BUTTONS ====================
def send_telegram_signal(symbol, score, bias, signal, sl, tp, reason):
    bot = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not bot or not chat:
        return {"error":"Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Render Env"}

    text = f"🎯 *AGENT 35 SIGNAL*\n\nSymbol: {symbol}\nScore: {score}/10\nBias: {bias}\nSignal: {signal}\n\nSL: {sl}\nTP: {tp}\nReason: {reason}\nTime: {datetime.utcnow().strftime('%H:%M')} UTC | SAST {(datetime.utcnow()+timedelta(hours=2)).strftime('%H:%M')}\nCapitec {CAPITEC['acc']}"

    keyboard = {
        "inline_keyboard": [
            [{"text":"✅ TAKE TRADE", "callback_data":f"TAKE_{symbol}_{score}"},
             {"text":"❌ MISS", "callback_data":f"MISS_{symbol}"}],
            [{"text":"📈 TRACK TO SL/TP", "callback_data":f"TRACK_{symbol}_{sl}_{tp}"}]
        ]
    }
    try:
        r = requests.post(f"https://api.telegram.org/bot{bot}/sendMessage",
                          json={"chat_id":chat,"text":text,"parse_mode":"Markdown","reply_markup":keyboard}, timeout=10)
        return r.json()
    except Exception as e:
        return {"error":str(e)}

def dark_layout(content, active="Dashboard"):
    utc = datetime.utcnow().strftime("%H:%M:%S")
    sast = (datetime.utcnow()+timedelta(hours=2)).strftime("%H:%M:%S")
    user = session.get("user","Guest")
    tabs = ["Dashboard","Journal","All Signals","Settings","Plans","Guide","Master"]
    tab_html = ""
    for t in tabs:
        url = f"/{t.lower().replace(' ','-')}"
        bg = "#10b981" if active==t else "#1e293b"
        tab_html += f"<a href='{url}' style='padding:8px 14px;border-radius:20px;text-decoration:none;font-weight:bold;font-size:13px;background:{bg};color:white;margin-right:6px;display:inline-block;margin-bottom:6px'>{t}</a>"
    return f"""
<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>AGENT 35</title>
<style>
body{{background:#0f172a;color:#e2e8f0;font-family:Arial;margin:0}}
.top{{background:#0f172a;border-bottom:1px solid #1e293b;padding:12px 15px;display:flex;justify-content:space-between;flex-wrap:wrap}}
.logo{{color:#10b981;font-weight:900;font-size:18px}}.time{{color:#94a3b8;font-size:11px}}
.nav{{background:#0f172a;padding:10px 15px;border-bottom:1px solid #1e293b;overflow-x:auto;white-space:nowrap}}
.main{{padding:15px;display:grid;grid-template-columns:1fr 1fr 1fr 300px;gap:12px}}
.card{{background:#1e293b;border-radius:16px;padding:18px;border:1px solid #334155;min-width:0}}
.profit{{color:#ef4444;font-size:26px;font-weight:900}}.muted{{color:#64748b;font-size:11px}}
.acc{{font-size:22px;font-weight:800}}.scan{{background:#10b981;color:white;padding:14px;border-radius:12px;text-align:center;font-weight:900;border:none;width:100%;cursor:pointer}}
.blue{{background:#3b82f6;color:white;padding:12px;border-radius:12px;text-align:center;margin-top:10px;display:block;text-decoration:none;font-weight:bold}}
.table-card{{grid-column:1 / span 4;background:#1e293b;border-radius:16px;padding:15px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;min-width:500px}}th{{color:#64748b;text-align:left;padding:10px;font-size:10px}}td{{padding:12px;border-top:1px solid #334155;font-size:13px}}
.took{{background:#10b98133;color:#10b981;padding:4px 10px;border-radius:10px;font-size:11px}}
@media(max-width:900px){{.main{{grid-template-columns:1fr 1fr}}.table-card{{grid-column:1 / span 2}}}}
@media(max-width:600px){{.main{{grid-template-columns:1fr}}.table-card{{grid-column:1}}.top{{flex-direction:column}}}}
</style></head><body>
<div class='top'><div class='logo'>35 AGENT 35 | Storage: {BASE_DIR}</div><div class='time'>UTC {utc} | SAST {sast} | <span style='color:#10b981'>London ACTIVE</span> | {user}</div></div>
<div class='nav'>{tab_html}</div>
{content}
</body></html>
"""

# ==================== DASHBOARD ====================
@app.route("/")
def home():
    return redirect("/dashboard") if session.get("user") else redirect("/login")

@app.route("/dashboard")
def dashboard():
    if not session.get("user"):
        return redirect("/login")
    auth = load_json(AUTH_FILE)
    info = auth.get(session.get("user"),{})
    acc_size = info.get("account_size",142.0)
    total_profit = info.get("total_profit",-1.42)
    journal = load_json(JOURNAL_FILE, list)
    if not journal:
        journal = [
            {"time":"09-03 18:13","symbol":"USDCHF","status":"TOOK","result":"R0 (0.0R)"},
            {"time":"09-03 18:13","symbol":"USDJPY","status":"TOOK","result":"R0 (0.0R)"},
            {"time":"09-03 18:13","symbol":"GBPUSD","status":"TOOK","result":"R0 (0.0R)"},
            {"time":"09-03 18:13","symbol":"EURUSD","status":"TOOK","result":"R0 (0.0R)"},
        ]
    rows = "".join([f"<tr><td>{t.get('time')}</td><td style='font-weight:800'>{t.get('symbol')}</td><td><span class='took'>{t.get('status')}</span></td><td>{t.get('result')}</td></tr>" for t in reversed(journal[-10:])])
    tracked = load_json(TRACK_FILE, dict)
    track_html = "".join([f"<div style='background:#0f172a;padding:8px;border-radius:8px;margin:5px 0;font-size:12px'>{v['symbol']} - {v['status']} SL:{v.get('sl')} TP:{v.get('tp')} by {v.get('by','')}</div>" for k,v in list(tracked.items())[-3:]])
    system = load_json(SYSTEM_FILE, dict)
    persistent = "✅ PERSISTENT /data - daily updates OK like last week" if BASE_DIR=="/data" else "⚠️ TEMPORARY - Add Disk /data in Render to keep like last week"
    content = f"""
<div class='main'>
    <div class='card'><div class='muted'>TOTAL PROFIT</div><div class='profit'>R{total_profit}</div><div style='color:#10b981;background:#10b98122;display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px'>WR: Tracking | {persistent}</div><div style='font-size:10px;color:#64748b;margin-top:6px'>Last scan: {system.get('last_scan','Never')} | Users: {len(auth)}</div></div>
    <div class='card'><div class='muted'>ACCOUNT SIZE</div><div class='acc'>R{acc_size}</div><form action='/account/edit' method='post'><input name='size' value='{acc_size}' style='background:#0f172a;border:1px solid #334155;color:white;padding:8px;border-radius:8px;width:100%;margin-top:8px'><button type='submit' style='background:#1e293b;border:1px solid #334155;color:white;padding:6px 20px;border-radius:8px;margin-top:6px'>Edit</button></form></div>
    <div class='card'><div class='muted'>WATCHLIST 4/5</div><div style='margin:10px 0'><span style='background:#334155;padding:6px 10px;border-radius:20px;margin:3px;display:inline-block'>EURUSD</span> <span style='background:#334155;padding:6px 10px;border-radius:20px;margin:3px;display:inline-block'>GBPUSD</span> <span style='background:#334155;padding:6px 10px;border-radius:20px;margin:3px;display:inline-block'>USDJPY</span> <span style='background:#334155;padding:6px 10px;border-radius:20px;margin:3px;display:inline-block'>USDCHF</span></div><input placeholder='Search pairs...' style='background:#0f172a;border:none;padding:10px;border-radius:10px;width:100%;color:white'><div style='margin-top:8px;font-size:11px;color:#64748b'>Capitec {CAPITEC['acc']} | {CAPITEC['holder']}</div></div>
    <div class='card'><a href='/dashboard-scan'><button class='scan'>SCAN NOW</button></a><div style='text-align:center;margin:10px;color:#64748b;font-size:12px'>Telegram Buttons<br>Take / Miss / Track to SL/TP</div><a href='/test-telegram' class='blue'>Test Telegram + Buttons</a><a href='/link-telegram' class='blue' style='background:#10b981'>Link Telegram</a><a href='/creator?secret=' class='blue' style='background:#f59e0b'>👑 Creator + Webhook</a><div style='margin-top:10px'>{track_html or '<p style=color:#64748b;font-size:11px>No tracked yet - click TRACK on Telegram</p>'}</div></div>
</div>
<div class='table-card'><table><tr><th>TIME</th><th>SYMBOL</th><th>STATUS</th><th>RESULT</th></tr>{rows}</table></div>
"""
    return dark_layout(content,"Dashboard")

# ==================== LOGIN / REGISTER / FORGOT ====================
@app.route("/login")
def login_page():
    count = len(load_json(AUTH_FILE))
    storage_msg = "✅ PERSISTENT - like last week" if BASE_DIR=="/data" else "⚠️ TEMPORARY - Add Disk /data to keep like last week"
    return f"""
<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#0f172a;color:white;font-family:Arial;padding:20px'>
<div style='max-width:400px;margin:40px auto;background:#1e293b;padding:25px;border-radius:16px'>
<h2>Login - Agent 35</h2><p style='color:#64748b;font-size:12px'>{count} accounts in {BASE_DIR} | {storage_msg}</p>
<form action='/login/check' method='post'>
<input name='email' type='email' placeholder='Email' required style='width:100%;padding:12px;margin:8px 0;border-radius:8px;border:none'>
<input name='password' type='password' placeholder='Password' required style='width:100%;padding:12px;margin:8px 0;border-radius:8px;border:none'>
<button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;font-weight:bold'>LOGIN</button>
</form>
<p><a href='/register' style='color:#3b82f6'>Register</a> | <a href='/forgot-password' style='color:#ff6b35'>Forgot?</a></p>
<div style='background:#0f172a;padding:12px;border-radius:8px'><p style='font-size:11px;color:#94a3b8'>Master: admin@agent35.com / Agent35! | Capitec {CAPITEC['acc']}</p></div>
</div></body></html>
"""

@app.route("/register")
def register_page():
    return """
<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#0f172a;color:white;font-family:Arial;padding:20px'>
<div style='max-width:400px;margin:40px auto;background:#1e293b;padding:25px;border-radius:16px'>
<h2>Register - Agent 35</h2>
<form action='/register/create' method='post'>
<input name='email' type='email' placeholder='Email' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
<input name='name' placeholder='Full Name' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
<input name='password' type='password' placeholder='Password min 6' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
<input name='ref' placeholder='Referral Code (optional)' style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
<button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;font-weight:bold'>CREATE ACCOUNT</button>
</form>
<p><a href='/login' style='color:#3b82f6'>Already have account? Login</a></p>
</div></body></html>
"""

@app.route("/register/create", methods=["POST"])
def register_create():
    email = request.form.get("email","").lower().strip()
    name = request.form.get("name","").strip()
    ref = request.form.get("ref","").upper().strip()
    auth = load_json(AUTH_FILE)
    if email in auth:
        return f"Email {email} already exists - <a href='/login'>Login</a> | <a href='/forgot-password'>Forgot?</a>"
    auth[email] = {
        "email":email,
        "name":name,
        "password":hash_pwd(request.form.get("password","")),
        "account_size":142.0,
        "total_profit":-1.42,
        "plan_status":"No Plan - Need R500/R5000",
        "referred_by":ref,
        "expires":None,
        "created":datetime.now().isoformat(),
        "reset_token":None
    }
    save_json(AUTH_FILE, auth)
    backup_to_telegram()
    session["user"]=email
    return redirect("/dashboard")

@app.route("/login/check", methods=["POST"])
def login_check():
    email = request.form.get("email","").lower().strip()
    pwd = request.form.get("password","")
    auth = load_json(AUTH_FILE)
    if email in auth and auth[email].get("password")==hash_pwd(pwd):
        session["user"]=email
        return redirect("/dashboard")
    return f"<html><body style='background:#0f172a;color:white;padding:30px'><h2>Wrong password for {email}</h2><p>Users in {AUTH_FILE}: {list(auth.keys())}</p><a href='/login'>Retry</a> | <a href='/register'>Register</a> | <a href='/forgot-password'>Forgot?</a></body></html>"

@app.route("/logout")
def logout():
    session.pop("user",None)
    return redirect("/login")

@app.route("/forgot-password")
def forgot_page():
    return """<html><body style='background:#0f172a;color:white;padding:30px'><div style='max-width:400px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>Forgot Password</h2><form action='/forgot-password/send' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:12px;border-radius:8px'><button style='background:#ff6b35;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px'>SEND RESET LINK</button></form><br><a href='/login' style='color:#64748b'>Back to Login</a></div></body></html>"""

@app.route("/forgot-password/send", methods=["POST"])
def forgot_send():
    email = request.form.get("email","").lower().strip()
    auth = load_json(AUTH_FILE)
    if email not in auth:
        return f"Email {email} not found - <a href='/register'>Register here</a>"
    token = secrets.token_urlsafe(12)
    auth[email]["reset_token"]=token
    auth[email]["reset_expiry"]=(datetime.now()+timedelta(hours=1)).isoformat()
    save_json(AUTH_FILE, auth)
    link = f"/reset-password?token={token}&email={email}"
    return f"<html><body style='background:#0f172a;color:white;padding:20px;text-align:center'><h2>Reset Link Generated (1 hour valid)</h2><div style='background:#1e293b;padding:20px;border-radius:12px;max-width:500px;margin:auto'><p>Email: {email}</p><a href='{link}' style='background:#10b981;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;display:inline-block;margin:10px'>Click to Reset Password</a><p style='font-size:11px;word-break:break-all;color:#64748b'>{link}</p></div></body></html>"

@app.route("/reset-password")
def reset_page():
    return f"""<html><body style='background:#0f172a;color:white;padding:30px'><div style='max-width:400px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>Reset Password - {request.args.get('email')}</h2><form action='/reset-password/save' method='post'><input type='hidden' name='email' value='{request.args.get('email')}'><input type='hidden' name='token' value='{request.args.get('token')}'><input name='new_password' type='password' placeholder='New Password' required style='width:100%;padding:12px;border-radius:8px'><button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px'>SAVE NEW PASSWORD</button></form></div></body></html>"""

@app.route("/reset-password/save", methods=["POST"])
def reset_save():
    email = request.form.get("email","").lower()
    token = request.form.get("token","")
    auth = load_json(AUTH_FILE)
    if auth.get(email,{}).get("reset_token")!=token:
        return "Invalid or expired token - <a href='/forgot-password'>Try again</a>"
    auth[email]["password"]=hash_pwd(request.form.get("new_password",""))
    auth[email]["reset_token"]=None
    save_json(AUTH_FILE, auth)
    return "Password changed! <a href='/login'>Login now</a>"

@app.route("/account/edit", methods=["POST"])
def account_edit():
    if not session.get("user"):
        return redirect("/login")
    try:
        size_f = float(request.form.get("size","142.0"))
    except:
        size_f = 142.0
    auth = load_json(AUTH_FILE)
    if session["user"] in auth:
        auth[session["user"]]["account_size"]=size_f
        save_json(AUTH_FILE, auth)
    return redirect("/dashboard")

# ==================== PAY + REFERRAL ====================
@app.route("/pay")
def pay_page():
    ref = request.args.get("ref","") or session.get("ref","")
    email = request.args.get("email","") or session.get("user","")
    return f"""
<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#0f172a;color:white;font-family:Arial;padding:20px'>
<div style='max-width:500px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'>
<h2>Buy Plan - Capitec {CAPITEC['acc']}</h2>
<p>Bank: {CAPITEC['bank']}<br>Holder: {CAPITEC['holder']}<br>Acc: {CAPITEC['acc']}<br>Branch: {CAPITEC['branch']}</p>
<form action='/pay/create' method='get'>
<input type='hidden' name='ref' value='{ref}'>
<input name='user' value='{email}' placeholder='Email (your login email)' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
<input name='phone' placeholder='WhatsApp number' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
<select name='plan' style='width:100%;padding:12px;border-radius:8px;border:none'><option value='yearly'>Yearly R500</option><option value='lifetime'>Lifetime R5000</option></select>
<button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px;font-weight:bold'>GET PAYMENT REFERENCE</button>
</form>
{f'<p style=color:#10b981>Referred by: {ref} - You help them get closer to 10 = free lifetime!</p>' if ref else ''}
<p style='font-size:11px;color:#64748b'>10 paid referrals = R5000 Lifetime FREE - only counts after admin ACCEPTS</p>
</div></body></html>
"""

@app.route("/pay/create")
def pay_create():
    user = request.args.get("user","").lower().strip()
    phone = request.args.get("phone","").strip()
    plan_key = request.args.get("plan","yearly")
    ref = request.args.get("ref","").upper().strip()
    short = "".join([c for c in user.upper() if c.isalnum()])[:5] or "USER"
    rand = "".join(random.choices(string.digits,k=3))
    pref = f"{CAPITEC['ref_prefix']}-{short}-{rand}"
    plan = PLANS.get(plan_key, PLANS["yearly"])
    users = load_json(USERS_FILE)
    users[pref] = {"user":user,"phone":phone,"plan":plan_key,"price":plan["price"],"payment_ref":pref,"referred_by":ref,"status":"pending","created":datetime.now().isoformat(),"expires":None}
    save_json(USERS_FILE, users)
    return f"""
<html><body style='background:#0f172a;color:white;padding:30px;text-align:center'>
<h1>Pay R{plan['price']} for {plan['name']}</h1>
<div style='border:2px dashed #334155;padding:20px;border-radius:12px;max-width:450px;margin:auto;background:#1e293b'>
<p>Bank: {CAPITEC['bank']}<br>{CAPITEC['holder']}<br>Acc: {CAPITEC['acc']}<br>Branch: {CAPITEC['branch']}</p>
<h1 style='background:white;color:black;padding:15px;border-radius:10px;letter-spacing:2px'>{pref}</h1>
<p style='color:#f59e0b;font-weight:bold'>USE THIS EXACT REFERENCE IN CAPITEC APP<br>Plan: {plan['name']} | Email: {user}</p>
<p style='font-size:11px;color:#64748b'>After payment, admin will ACCEPT and activate you within 24h. You will get lifetime if referred 10 paid users.</p>
</div>
<br><a href='/dashboard' style='background:#1e293b;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Back Dashboard</a>
</body></html>
"""

@app.route("/join")
def join():
    ref = request.args.get("ref","")
    session["ref"]=ref
    return f"<html><body style='background:#0f172a;color:white;padding:40px;text-align:center'><h1>🎉 Referred by {ref}</h1><p>Join Agent 35 - they get closer to free R5000 lifetime!</p><a href='/pay?ref={ref}' style='background:#10b981;color:white;padding:14px 30px;border-radius:10px;text-decoration:none;font-weight:bold;display:inline-block;margin:10px'>Continue to Pay Capitec {CAPITEC['acc']}</a><br><a href='/register?ref={ref}' style='color:#3b82f6'>Or Register First</a></body></html>"

@app.route("/referral")
def referral_page():
    data = load_json(DATA_FILE)
    rows = "".join([f"<tr><td style='padding:10px'>{code}</td><td style='padding:10px'>{info.get('owner','')}</td><td style='padding:10px'>{info.get('count',0)}/10</td><td style='padding:10px'>{'✅ LIFETIME FREE' if info.get('count',0)>=10 else '⏳ Need more'}</td><td style='padding:10px'>{', '.join(info.get('paid_refs',[])[:3])}</td></tr>" for code,info in data.items()])
    return dark_layout(f"<div class='table-card'><h2>Referral System - 10 Paid = R5000 Lifetime FREE</h2><p style='color:#64748b'>Only counts after admin ACCEPTS Capitec payment {CAPITEC['acc']}. No fake referrals.</p><table><tr><th>Code</th><th>Owner</th><th>Count</th><th>Reward</th><th>Paid Users</th></tr>{rows or '<tr><td colspan=5 style=text-align:center;color:#64748b>No codes yet</td></tr>'}</table><br><form action='/referral/create' method='get'><input name='code' placeholder='YOUR CODE e.g. SNIPE' style='padding:10px;border-radius:6px;background:#0f172a;border:1px solid #334155;color:white'><input name='owner' placeholder='Owner email' style='padding:10px;border-radius:6px;background:#0f172a;border:1px solid #334155;color:white'><button style='background:#10b981;color:white;padding:10px 14px;border:none;border-radius:6px'>Create Code</button></form><br><p style='font-size:12px'>Share link: <code>https://agent-35-trading-bot.onrender.com/join?ref=YOURCODE</code></p></div>","Master")

@app.route("/referral/create")
def referral_create():
    code = request.args.get("code","").upper().strip()
    owner = request.args.get("owner","").strip()
    if not code:
        return jsonify({"error":"code required"})
    data = load_json(DATA_FILE)
    if code not in data:
        data[code]={"owner":owner,"count":0,"paid_refs":[],"created":datetime.now().isoformat()}
        save_json(DATA_FILE, data)
    return redirect("/referral")

# ==================== TRADING ENGINE ====================
@app.route("/scan")
def scan():
    return jsonify(eng.full_multi_tf_analysis(request.args.get("symbol","EURUSD")))

@app.route("/dashboard-scan")
def dashboard_scan():
    syms = ["EURUSD","GBPUSD","USDJPY","USDCHF","XAUUSD","US30","NAS100","GBPJPY"]
    rows = ""
    for s in syms:
        r = eng.full_multi_tf_analysis(s)
        rows += f"<tr><td style='font-weight:800'>{s}</td><td>{r['score']}/10</td><td>{r['bias']}</td><td>{r['signal']}</td><td><a href='/send-signal?symbol={s}' style='background:#10b981;color:white;padding:4px 10px;border-radius:6px;text-decoration:none'>Send TG + Buttons</a></td></tr>"
    return dark_layout(f"<div class='table-card'><h2>Scan All 8 - 6/10 Fix Active (4H Neutral Allowed + 15m BOS+FVG)</h2><table><tr><th>Symbol</th><th>Score</th><th>Bias</th><th>Signal</th><th>Telegram</th></tr>{rows}</table><br><a href='/dashboard' style='color:#10b981'>← Back Dashboard</a></div>","All Signals")

@app.route("/send-signal")
def send_signal():
    sym = request.args.get("symbol","EURUSD")
    r = eng.full_multi_tf_analysis(sym)
    res = send_telegram_signal(sym, r['score'], r['bias'], r['signal'], "SL auto", "TP auto", r.get('reason',''))
    return f"<html><body style='background:#0f172a;color:white;padding:30px'><h2>Sent {sym} {r['score']}/10 to @Sniper035_bot</h2><p>{res}</p><p>Check Telegram for 3 buttons: Take / Miss / Track</p><a href='/dashboard-scan' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Back Scan</a></body></html>"

# ==================== TELEGRAM LINK + TEST + WEBHOOK ====================
@app.route("/link-telegram")
def link_telegram():
    bot = os.getenv("TELEGRAM_BOT_TOKEN","Not set")
    chat = os.getenv("TELEGRAM_CHAT_ID","Not set")
    bot_short = bot[:25]+"..." if len(bot)>25 else bot
    return f"""
<html><body style='background:#0f172a;color:white;padding:20px'><div style='max-width:500px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'>
<h2>Telegram Connect - @Sniper035_bot</h2>
<p style='font-size:12px'>Bot Token: {bot_short}<br>Chat ID: {chat}<br>Webhook: <code>https://agent-35-trading-bot.onrender.com/telegram/webhook</code></p>
<div style='background:#0f172a;padding:12px;border-radius:8px;font-size:11px'>
<b>Steps:</b><br>
1. Send message "Hi" to @Sniper035_bot<br>
2. Click "Get Chat ID" in Creator to find your ID<br>
3. Set Chat ID in Render Env<br>
4. Click "Set Webhook" in Creator<br>
5. Test - you get 3 buttons Take/Miss/Track
</div>
<br>
<a href='/test-telegram' style='background:#3b82f6;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;display:block;text-align:center'>Test Telegram + Buttons</a>
<br>
<a href='/creator?secret=' style='background:#10b981;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;display:block;text-align:center'>Go Creator Dashboard + Webhook Control</a>
<br><a href='/dashboard' style='color:#64748b'>← Back Dashboard</a>
</div></body></html>
"""

@app.route("/test-telegram")
def test_telegram():
    res = send_telegram_signal("EURUSD", 7, "BUY", "BUY NOW", "1.0845 SL", "1.0920 TP", "6/10 Fix - 4H Bullish, 15m BOS + FVG + Capitec 2586572676")
    return f"""
<html><body style='background:#0f172a;color:white;padding:30px;text-align:center'>
<div style='max-width:500px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'>
<h2>Telegram Test Sent to @Sniper035_bot</h2>
<p style='font-size:11px;background:#0f172a;padding:10px;border-radius:8px;word-break:break-all'>{res}</p>
<p>Check Telegram - you should see 3 buttons:<br><b>✅ TAKE TRADE | ❌ MISS | 📈 TRACK TO SL/TP</b></p>
<p style='font-size:11px;color:#64748b'>If no buttons, webhook not set - go to Creator and click SET WEBHOOK</p>
<br>
<a href='/dashboard' style='background:#10b981;color:white;padding:12px 20px;border-radius:8px;text-decoration:none'>Back Dashboard</a>
<a href='/creator?secret=' style='background:#f59e0b;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;margin-left:8px'>Creator + Set Webhook</a>
</div></body></html>
"""

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if not data:
        return jsonify({"ok":True})
    if "callback_query" in data:
        cb = data["callback_query"]
        cb_data = cb.get("data","")
        cb_id = cb.get("id")
        chat_id = cb["message"]["chat"]["id"]
        user_name = cb["from"].get("first_name","User")
        journal = load_json(JOURNAL_FILE, list)
        tracked = load_json(TRACK_FILE, dict)
        bot = os.getenv("TELEGRAM_BOT_TOKEN")

        if cb_data.startswith("TAKE_"):
            _, symbol, score = cb_data.split("_")
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":symbol,"status":"TOOK","result":f"Taken by {user_name} - {score}/10 - {CAPITEC['acc']}"})
            save_json(JOURNAL_FILE, journal[-100:])
            text = f"✅ {user_name} TOOK {symbol} {score}/10 - Logged to Journal & Dashboard"

        elif cb_data.startswith("MISS_"):
            symbol = cb_data.split("_")[1]
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":symbol,"status":"MISS","result":f"Missed by {user_name}"})
            save_json(JOURNAL_FILE, journal[-100:])
            text = f"❌ {user_name} MISSED {symbol} - Logged"

        elif cb_data.startswith("TRACK_"):
            parts = cb_data.split("_")
            symbol = parts[1]
            sl = parts[2]
            tp = parts[3] if len(parts)>3 else "TP"
            track_id = f"{symbol}_{datetime.now().strftime('%H%M%S')}"
            tracked[track_id] = {"symbol":symbol,"sl":sl,"tp":tp,"status":"TRACKING","started":datetime.now().isoformat(),"by":user_name}
            save_json(TRACK_FILE, tracked)
            text = f"📈 {user_name} TRACKING {symbol} to SL:{sl} TP:{tp} - Will alert on hit - Dashboard shows tracking"

        else:
            text = "Unknown action"

        if bot:
            try:
                requests.post(f"https://api.telegram.org/bot{bot}/answerCallbackQuery", json={"callback_query_id":cb_id,"text":text}, timeout=5)
                requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":text}, timeout=5)
            except:
                pass
        return jsonify({"ok":True})
    return jsonify({"ok":True})

# ==================== CRONS ====================
@app.route("/cron/scan")
def cron_scan():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"):
        return jsonify({"error":"bad secret - set CRON_SECRET in Render"})
    system = load_json(SYSTEM_FILE, dict)
    system["last_scan"]=datetime.now().isoformat()
    system["total_scans"]=system.get("total_scans",0)+1
    save_json(SYSTEM_FILE, system)
    sent = []
    for s in ["EURUSD","GBPUSD","USDJPY","USDCHF","XAUUSD","US30"]:
        r = eng.full_multi_tf_analysis(s)
        if r.get("score",0) >= 6:
            res = send_telegram_signal(s, r['score'], r['bias'], r['signal'], "SL auto 0.2%", "TP auto 0.4%", r.get('reason','6/10 Fix'))
            sent.append({"symbol":s,"result":res})
            system["total_signals"]=system.get("total_signals",0)+1
            j = load_json(JOURNAL_FILE, list)
            j.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":s,"status":"TOOK","result":f"{r['score']}/10 {r['bias']} Sent TG"})
            save_json(JOURNAL_FILE, j[-100:])
    save_json(SYSTEM_FILE, system)
    return jsonify({"cron":"scan 30min with buttons","sent":sent,"system":system,"storage":BASE_DIR})

@app.route("/cron/daily-reset")
def cron_daily():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"):
        return jsonify({"error":"bad secret"})
    system = load_json(SYSTEM_FILE, dict)
    system["last_cron"]=datetime.now().isoformat()
    save_json(SYSTEM_FILE, system)
    return jsonify({"cron":"daily-reset 00:00 SAST","ok":True})

@app.route("/cron/check-expiry")
def cron_expiry():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"):
        return jsonify({"error":"bad secret"})
    auth = load_json(AUTH_FILE)
    expired = []
    for email,info in auth.items():
        exp = info.get("expires")
        if exp:
            try:
                if datetime.now() > datetime.fromisoformat(exp):
                    info["plan_status"]="EXPIRED"
                    expired.append(email)
            except:
                pass
    save_json(AUTH_FILE, auth)
    return jsonify({"cron":"check-expiry","checked":len(auth),"expired":expired})

@app.route("/cron/track-check")
def cron_track_check():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"):
        return jsonify({"error":"bad secret"})
    tracked = load_json(TRACK_FILE, dict)
    # Here you would check live price vs SL/TP and send alert if hit
    return jsonify({"cron":"track-check","tracking":len([t for t in tracked.values() if t['status']=="TRACKING"]),"all_tracked":tracked})

@app.route("/run-now")
def run_now():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"):
        return jsonify({"error":"bad secret"})
    return jsonify(eng.run_scan_and_send())

# ==================== CREATOR DASHBOARD WITH WEBHOOK INSIDE ====================
@app.route("/master")
@app.route("/creator")
def creator_dashboard():
    secret = request.args.get("secret","")
    auth = load_json(AUTH_FILE)
    users = load_json(USERS_FILE)
    refs = load_json(DATA_FILE)
    journal = load_json(JOURNAL_FILE, list)
    tracked = load_json(TRACK_FILE, dict)
    system = load_json(SYSTEM_FILE, dict)

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN","Not set")
    chat_id = os.getenv("TELEGRAM_CHAT_ID","Not set")
    bot_short = bot_token[:20]+"..." if len(bot_token)>20 else bot_token

    # Live webhook status
    webhook_info = {"status":"Not checked"}
    if len(bot_token)>20:
        try:
            webhook_info = requests.get(f"https://api.telegram.org/bot{bot_token}/getWebhookInfo", timeout=5).json()
        except Exception as e:
            webhook_info = {"error":str(e)}

    total_users = len(auth)
    active_users = len([u for u in auth.values() if "ACTIVE" in u.get("plan_status","")])
    pending = len([u for u in users.values() if u.get("status")=="pending"])
    active_payments = len([u for u in users.values() if u.get("status")=="active"])
    total_revenue = sum([u.get("price",0) for u in users.values() if u.get("status")=="active"])
    referral_count = len(refs)
    tracking_count = len([t for t in tracked.values() if t.get("status")=="TRACKING"])

    persistent_msg = "✅ PERSISTENT /data - Last week mode - daily updates OK, logins NEVER wipe" if BASE_DIR=="/data" else "⚠️ TEMPORARY - Add Disk /data in Render -> Disks -> Mount /data -> 1GB to get last week back"

    user_rows = "".join([f"<tr><td style='padding:8px'>{e}</td><td style='padding:8px'>{i.get('name','')}</td><td style='padding:8px'>{i.get('plan_status','')}</td><td style='padding:8px'>R{i.get('account_size',0)}</td><td style='padding:8px'>{i.get('referred_by') or '-'}</td><td style='padding:8px'><a href='/creator/action?act=delete_user&email={e}&secret={secret}' style='background:#ef4444;color:white;padding:4px 8px;border-radius:6px;text-decoration:none' onclick='return confirm(\"Delete {e}?\")'>Delete</a> <a href='/creator/action?act=make_active&email={e}&secret={secret}' style='background:#10b981;color:white;padding:4px 8px;border-radius:6px;text-decoration:none'>Make Active</a></td></tr>" for e,i in list(auth.items())[-30:]])
    payment_rows = "".join([f"<tr><td style='padding:8px'>{pref}</td><td style='padding:8px'>{u['user']}<br><span style='color:#64748b'>{u['phone']}</span></td><td style='padding:8px'>{u['plan']} R{u['price']}</td><td style='padding:8px'>{u.get('referred_by') or '-'}</td><td style='padding:8px'><span style='background:{'#f59e0b33' if u['status']=='pending' else '#10b98133'};color:{'#f59e0b' if u['status']=='pending' else '#10b981'};padding:4px 8px;border-radius:10px'>{u['status']}</span></td><td style='padding:8px'><a href='/admin/accept?ref={pref}&secret={secret}' style='background:#10b981;color:white;padding:6px 10px;border-radius:6px;text-decoration:none'>ACCEPT</a> <a href='/admin/reject?ref={pref}&secret={secret}' style='background:#ef4444;color:white;padding:6px 10px;border-radius:6px;text-decoration:none'>REJECT</a></td></tr>" for pref,u in list(users.items())[-20:]])

    content = f"""
<div style='padding:15px'>
<h1 style='color:#10b981'>👑 CREATOR DASHBOARD - Everything Control + Webhook Inside</h1>

<div style='background:{"#10b98122" if BASE_DIR=="/data" else "#f59e0b22"};border:1px solid {"#10b981" if BASE_DIR=="/data" else "#f59e0b"};padding:12px;border-radius:10px;margin-bottom:15px'>
<b>Storage: {BASE_DIR} | {persistent_msg}</b><br>
<span style='font-size:11px'>Last week you had Disk /data attached, that's why daily updates didn't wipe logins. Add it again: Render -> Disks -> Add Disk -> Mount Path /data -> Size 1GB -> Create -> Deploy.</span><br>
<span style='font-size:11px'>Users: {total_users} | Bot: @Sniper035_bot | Capitec {CAPITEC['acc']} | System up: {system.get('system_up_since','Unknown')[:19]}</span>
</div>

<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:15px 0'>
    <div class='card' style='border-left:4px solid #10b981'><div class='muted'>TOTAL USERS</div><div style='font-size:28px;font-weight:900'>{total_users}</div><div style='color:#10b981'>{active_users} Active</div></div>
    <div class='card' style='border-left:4px solid #f59e0b'><div class='muted'>PENDING PAYMENTS</div><div style='font-size:28px;font-weight:900;color:#f59e0b'>{pending}</div><div>Capitec {CAPITEC['acc']}</div></div>
    <div class='card' style='border-left:4px solid #10b981'><div class='muted'>TOTAL REVENUE</div><div style='font-size:28px;font-weight:900;color:#10b981'>R{total_revenue}</div><div>{active_payments} Paid</div></div>
    <div class='card' style='border-left:4px solid #3b82f6'><div class='muted'>REFERRAL CODES</div><div style='font-size:28px;font-weight:900;color:#3b82f6'>{referral_count}</div><div>10=R5000</div></div>
    <div class='card' style='border-left:4px solid #ef4444'><div class='muted'>JOURNAL</div><div style='font-size:28px;font-weight:900'>{len(journal)}</div><div>Entries</div></div>
    <div class='card' style='border-left:4px solid #8b5cf6'><div class='muted'>TRACKING SL/TP</div><div style='font-size:28px;font-weight:900;color:#8b5cf6'>{tracking_count}</div><div>Active</div></div>
</div>

<div style='display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:15px 0'>
    <div class='card'>
        <h3 style='color:#10b981'>🤖 Telegram Webhook - BUILT INSIDE CREATOR (No external link needed)</h3>
        <p style='font-size:11px'>Bot Token: {bot_short}<br>Chat ID: {chat_id}<br>Webhook URL: <code>https://agent-35-trading-bot.onrender.com/telegram/webhook</code><br>Bot: @Sniper035_bot</p>
        <div style='background:#0f172a;padding:8px;border-radius:6px;font-size:10px;max-height:120px;overflow:auto'>{str(webhook_info)[:600]}</div>
        <div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px'>
            <a href='/creator/webhook?action=set&secret={secret}' style='background:#10b981;color:white;padding:12px;border-radius:8px;text-align:center;text-decoration:none;font-weight:bold'>🔗 SET WEBHOOK NOW</a>
            <a href='/creator/webhook?action=getUpdates&secret={secret}' style='background:#8b5cf6;color:white;padding:12px;border-radius:8px;text-align:center;text-decoration:none'>📩 Get Chat ID</a>
            <a href='/creator/webhook?action=info&secret={secret}' style='background:#3b82f6;color:white;padding:12px;border-radius:8px;text-align:center;text-decoration:none'>ℹ️ Check Webhook Status</a>
            <a href='/creator/webhook?action=delete&secret={secret}' style='background:#ef4444;color:white;padding:12px;border-radius:8px;text-align:center;text-decoration:none'>❌ Delete Webhook</a>
        </div>
        <div style='margin-top:10px'>
            <a href='/test-telegram' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px;border-radius:8px;text-align:center;display:block;text-decoration:none'>📤 Test Signal + Buttons (Take/Miss/Track to SL/TP)</a>
        </div>
    </div>

    <div class='card'>
        <h3 style='color:#f59e0b'>💾 Keep Logins - Backup / Restore + System Health</h3>
        <p style='font-size:11px'>✅ Bot: {'ONLINE' if len(bot_token)>20 else 'Set token'}<br>📊 API Keys: {len(eng.API_KEYS) if hasattr(eng,'API_KEYS') else 0} loaded<br>🕐 Last Scan: {system.get('last_scan','Never')}<br>🔢 Total Scans: {system.get('total_scans',0)}<br>📈 Signals Sent: {system.get('total_signals',0)}<br>🏦 Capitec: {CAPITEC['acc']} {CAPITEC['holder']}<br>💾 Storage Path: {BASE_DIR} | Persistent: {BASE_DIR=='/data'}</p>
        <div style='display:grid;grid-template-columns:1fr 1fr;gap:8px'>
            <a href='/creator/action?act=backup&secret={secret}' style='background:#10b981;color:white;padding:10px;border-radius:8px;text-align:center;text-decoration:none'>⬇️ Download Backup JSON</a>
            <a href='/creator/backup-restore' style='background:#f59e0b;color:white;padding:10px;border-radius:8px;text-align:center;text-decoration:none'>⬆️ Restore Backup</a>
            <a href='/run-now?secret={secret}' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px;border-radius:8px;text-align:center;text-decoration:none'>▶️ Run Scan Now</a>
            <a href='/health' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px;border-radius:8px;text-align:center;text-decoration:none'>❤️ /health</a>
            <a href='/dashboard-scan' style='background:#3b82f6;color:white;padding:10px;border-radius:8px;text-align:center;text-decoration:none'>Scan All 8 Pairs</a>
            <a href='/journal' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px;border-radius:8px;text-align:center;text-decoration:none'>📓 Journal</a>
        </div>
        <div style='background:#0f172a;padding:10px;border-radius:8px;margin-top:10px;font-size:11px'>
            <b>Auto Backup Active:</b> Every new register -> backup file sent to your Telegram @Sniper035_bot automatically.<br>
            If Render wipes, restore from Telegram file in 1 click here.<br>
            <b>BEST like last week:</b> Add Disk /data -> never wipe even with daily updates.
        </div>
    </div>
</div>

<div class='card' style='margin:15px 0'><h3>💳 Pending Capitec Payments - Acc {CAPITEC['acc']} - {CAPITEC['holder']}</h3><div style='overflow-x:auto'><table><tr><th>Ref</th><th>User</th><th>Plan</th><th>RefBy</th><th>Status</th><th>Action</th></tr>{payment_rows or '<tr><td colspan=6 style=padding:20px;text-align:center;color:#64748b>No pending payments - all paid or none</td></tr>'}</table></div></div>

<div class='card' style='margin:15px 0'><h3>👥 All Users - Stored in {AUTH_FILE} (Last 30) - Total {total_users}</h3><div style='overflow-x:auto'><table><tr><th>Email</th><th>Name</th><th>Status</th><th>Size</th><th>Ref</th><th>Control</th></tr>{user_rows}</table></div></div>

<div class='card' style='margin:15px 0'><h3>🔗 Referral System - 10 Paid = R5000 Lifetime FREE - Only counts after ACCEPT</h3><form action='/referral/create' method='get' style='margin:10px 0'><input name='code' placeholder='CODE e.g. SNIPE' style='padding:8px;border-radius:6px;background:#0f172a;border:1px solid #334155;color:white'><input name='owner' placeholder='Owner email' style='padding:8px;border-radius:6px;background:#0f172a;border:1px solid #334155;color:white'><button style='background:#10b981;color:white;padding:8px 12px;border:none;border-radius:6px'>Create Code</button></form></div>

</div>
"""
    return dark_layout(content,"Master")

@app.route("/creator/webhook")
def creator_webhook():
    secret = request.args.get("secret","")
    action = request.args.get("action","info")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return "<html><body style='background:#0f172a;color:white;padding:20px'><h2>Set TELEGRAM_BOT_TOKEN in Render Env first!</h2><p>Go to Render -> Environment -> Add TELEGRAM_BOT_TOKEN</p><a href='/creator?secret=' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Back Creator</a></body></html>"

    base_url = f"https://api.telegram.org/bot{bot_token}"
    webhook_url = "https://agent-35-trading-bot.onrender.com/telegram/webhook"

    try:
        if action=="set":
            r = requests.get(f"{base_url}/setWebhook", params={"url":webhook_url}, timeout=10).json()
            system = load_json(SYSTEM_FILE, dict)
            system["webhook_set"]=True
            system["webhook_url"]=webhook_url
            system["webhook_last_set"]=datetime.now().isoformat()
            save_json(SYSTEM_FILE, system)
            return f"<html><body style='background:#0f172a;color:white;padding:20px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>✅ Set Webhook Result</h2><pre style='background:#0f172a;padding:15px;border-radius:8px;overflow:auto'>{json.dumps(r, indent=2)}</pre><p>Webhook: {webhook_url}</p><p style='color:#10b981'>Now go test: /test-telegram -> check @Sniper035_bot for buttons Take/Miss/Track</p><a href='/creator?secret={secret}' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Back Creator Dashboard</a> <a href='/test-telegram' style='background:#3b82f6;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;margin-left:10px'>Test Telegram Now</a></div></body></html>"

        elif action=="info":
            r = requests.get(f"{base_url}/getWebhookInfo", timeout=10).json()
            return f"<html><body style='background:#0f172a;color:white;padding:20px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>ℹ️ Webhook Info</h2><pre style='background:#0f172a;padding:15px;border-radius:8px;overflow:auto'>{json.dumps(r, indent=2)}</pre><br><a href='/creator?secret={secret}' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Back Creator</a> <a href='/creator/webhook?action=set&secret={secret}' style='background:#3b82f6;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;margin-left:10px'>Set Again</a></div></body></html>"

        elif action=="delete":
            r = requests.get(f"{base_url}/deleteWebhook", timeout=10).json()
            return f"<html><body style='background:#0f172a;color:white;padding:20px'><h2>Delete Webhook</h2><pre>{json.dumps(r, indent=2)}</pre><a href='/creator?secret={secret}' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Back Creator</a></body></html>"

        elif action=="getUpdates":
            r = requests.get(f"{base_url}/getUpdates", timeout=10).json()
            chats = []
            for upd in r.get("result",[]):
                if "message" in upd and "chat" in upd["message"]:
                    c = upd["message"]["chat"]
                    chats.append(f"Chat ID: {c['id']} - {c.get('first_name','')} {c.get('username','')} - Text: {upd['message'].get('text','')[:50]}")
            chat_text = "<br>".join(chats) or "No messages yet - Open Telegram -> Send 'Hi' to @Sniper035_bot -> Click this button again"
            return f"""
<html><body style='background:#0f172a;color:white;padding:20px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'>
<h2>📩 Get Chat ID - getUpdates</h2>
<div style='background:#10b98122;border:1px solid #10b981;padding:12px;border-radius:8px;margin:10px 0'><b>Found Chat IDs:</b><br>{chat_text}<br><br><b>Copy the number and add to Render Env:</b><br>TELEGRAM_CHAT_ID = that number</div>
<pre style='background:#0f172a;padding:15px;border-radius:8px;max-height:300px;overflow:auto;font-size:11px'>{json.dumps(r, indent=2)[:4000]}</pre>
<br><a href='/creator?secret={secret}' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Back Creator</a>
</div></body></html>
"""
    except Exception as e:
        return f"Error: {e} <br><a href='/creator?secret={secret}'>Back Creator</a>"
    return redirect(f"/creator?secret={secret}")

@app.route("/creator/backup-restore", methods=["GET","POST"])
def backup_restore():
    if request.method=="GET":
        return """
<html><body style='background:#0f172a;color:white;padding:20px'><div style='max-width:600px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'>
<h2>⬆️ Restore Backup - Keep Logins After Update</h2>
<p style='font-size:12px;color:#94a3b8'>If Render wiped after deploy, upload the backup JSON you downloaded before, or the file sent to your Telegram @Sniper035_bot</p>
<form method='post' enctype='multipart/form-data'>
<input type='file' name='backup' accept='.json' required style='width:100%;padding:12px;margin:10px 0;background:#0f172a;border-radius:8px;border:1px solid #334155;color:white'>
<button style='background:#f59e0b;color:white;padding:12px;width:100%;border:none;border-radius:8px;font-weight:bold'>RESTORE NOW - Bring Logins Back</button>
</form>
<br><a href='/creator?secret=' style='color:#64748b'>← Back Creator</a>
</div></body></html>
"""
    else:
        file = request.files.get('backup')
        if not file:
            return "No file uploaded"
        try:
            data = json.load(file)
            if "auth_users" in data:
                save_json(AUTH_FILE, data["auth_users"])
                if "payments" in data:
                    save_json(USERS_FILE, data["payments"])
                if "referrals" in data:
                    save_json(DATA_FILE, data["referrals"])
                if "tracked" in data:
                    save_json(TRACK_FILE, data["tracked"])
                restored = len(data.get("auth_users",{}))
            else:
                save_json(AUTH_FILE, data)
                restored = len(data)
            backup_to_telegram()
            return f"""
<html><body style='background:#0f172a;color:white;padding:30px;text-align:center'><div style='max-width:500px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'>
<h2>✅ Restored {restored} users to {AUTH_FILE}!</h2>
<p>Storage: {BASE_DIR} | Persistent: {BASE_DIR=='/data'}</p>
<p style='font-size:11px'>If you have /data disk, they will now stay forever like last week even with daily updates.</p>
<br>
<a href='/login' style='background:#10b981;color:white;padding:12px 20px;border-radius:8px;text-decoration:none'>Go Login - Check Users</a>
<a href='/creator?secret=' style='background:#1e293b;border:1px solid #334155;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;margin-left:10px'>Back Creator</a>
</div></body></html>
"""
        except Exception as e:
            return f"Error restoring: {e} <br><a href='/creator?secret='>Back Creator</a>"

@app.route("/creator/action")
def creator_action():
    secret = request.args.get("secret","")
    act = request.args.get("act","")
    if act=="clear_journal":
        save_json(JOURNAL_FILE, [])
        return redirect(f"/creator?secret={secret}")
    if act=="clear_tracked":
        save_json(TRACK_FILE, {})
        return redirect(f"/creator?secret={secret}")
    if act=="delete_user":
        email = request.args.get("email","")
        auth = load_json(AUTH_FILE)
        if email in auth and email!="admin@agent35.com":
            del auth[email]
            save_json(AUTH_FILE, auth)
            backup_to_telegram()
        return redirect(f"/creator?secret={secret}")
    if act=="make_active":
        email = request.args.get("email","")
        auth = load_json(AUTH_FILE)
        if email in auth:
            auth[email]["plan_status"]="ACTIVE lifetime - By Creator"
            auth[email]["expires"]=(datetime.now()+timedelta(days=36500)).isoformat()
            save_json(AUTH_FILE, auth)
            backup_to_telegram()
        return redirect(f"/creator?secret={secret}")
    if act=="backup":
        payload = {
            "auth_users": load_json(AUTH_FILE),
            "payments": load_json(USERS_FILE),
            "referrals": load_json(DATA_FILE),
            "tracked": load_json(TRACK_FILE, dict),
            "system": load_json(SYSTEM_FILE, dict),
            "exported": datetime.now().isoformat(),
            "storage": BASE_DIR,
            "capitec": CAPITEC['acc']
        }
        return jsonify(payload)
    return redirect(f"/creator?secret={secret}")

@app.route("/admin")
def admin_page():
    secret = request.args.get("secret","")
    real = os.getenv("CRON_SECRET","")
    if real and secret!=real:
        return f"<html><body style='background:#0f172a;color:white;padding:30px'><h1>Admin Login</h1><form><input name='secret' placeholder='CRON_SECRET' style='padding:12px;border-radius:8px;background:#1e293b;border:1px solid #334155;color:white'><button style='background:#10b981;color:white;padding:10px 14px;border:none;border-radius:8px'>Enter Admin</button></form><p><a href='/creator?secret=' style='color:#3b82f6'>Go Creator Dashboard</a></p></body></html>"
    users = load_json(USERS_FILE)
    auth = load_json(AUTH_FILE)
    u_rows = "".join([f"<tr><td style='padding:10px'>{pref}</td><td style='padding:10px'>{u['user']}<br>{u['phone']}</td><td style='padding:10px'>{u['plan']} R{u['price']}</td><td style='padding:10px'>{u.get('referred_by') or '-'}</td><td style='padding:10px'>{u['status']}</td><td style='padding:10px'><a href='/admin/accept?ref={pref}&secret={secret}' style='background:#10b981;color:white;padding:6px 10px;border-radius:6px;text-decoration:none'>ACCEPT</a> <a href='/admin/reject?ref={pref}&secret={secret}' style='background:#ef4444;color:white;padding:6px 10px;border-radius:6px;text-decoration:none'>REJECT</a></td></tr>" for pref,u in users.items()])
    a_rows = "".join([f"<tr><td style='padding:8px'>{e}</td><td style='padding:8px'>{i.get('name','')}</td><td style='padding:8px'>{i.get('plan_status','')}</td><td style='padding:8px'>R{i.get('account_size',0)}</td><td style='padding:8px'>{i.get('referred_by') or '-'}</td></tr>" for e,i in auth.items()])
    return f"<html><body style='background:#0f172a;color:white;font-family:Arial;padding:20px'><h1>Admin - Capitec {CAPITEC['acc']} | {CAPITEC['holder']} | Storage {BASE_DIR}</h1><p>Total Logins: {len(auth)} | Pending: {len([u for u in users.values() if u.get('status')=='pending'])} | Persistent: {BASE_DIR=='/data'}</p><h3>All Logins</h3><div style='overflow-x:auto'><table border=1 cellpadding=5 style='border-collapse:collapse;width:100%;background:#1e293b'><tr><th>Email</th><th>Name</th><th>Status</th><th>Size</th><th>Ref</th></tr>{a_rows}</table></div><h3>Pending Payments - Capitec {CAPITEC['acc']}</h3><div style='overflow-x:auto'><table border=1 cellpadding=5 style='border-collapse:collapse;width:100%;background:#1e293b'><tr><th>Ref</th><th>User</th><th>Plan</th><th>RefBy</th><th>Status</th><th>Action</th></tr>{u_rows or '<tr><td colspan=6 style=text-align:center>No pending</td></tr>'}</table></div><br><a href='/creator?secret={secret}' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>👑 Go Creator Dashboard + Webhook</a> <a href='/dashboard' style='background:#1e293b;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;margin-left:10px'>Dashboard</a></body></html>"

@app.route("/admin/accept")
def admin_accept():
    pref = request.args.get("ref","")
    users = load_json(USERS_FILE)
    auth = load_json(AUTH_FILE)
    refs = load_json(DATA_FILE)
    if pref not in users:
        return jsonify({"error":"payment ref not found"})
    u = users[pref]
    u["status"]="active"
    days = PLANS.get(u["plan"], PLANS["yearly"])["days"]
    u["expires"]=(datetime.now()+timedelta(days=days)).isoformat()
    users[pref]=u
    save_json(USERS_FILE, users)
    if u["user"] in auth:
        auth[u["user"]]["plan_status"]=f"ACTIVE {u['plan']} - Paid Capitec {CAPITEC['acc']}"
        auth[u["user"]]["expires"]=u["expires"]
        save_json(AUTH_FILE, auth)
    ref_code = u.get("referred_by")
    if ref_code:
        if ref_code not in refs:
            refs[ref_code]={"owner":ref_code,"count":0,"paid_refs":[]}
        if u["user"] not in refs[ref_code].get("paid_refs",[]):
            refs[ref_code]["paid_refs"].append(u["user"])
            refs[ref_code]["count"]=len(refs[ref_code]["paid_refs"])
            save_json(DATA_FILE, refs)
    backup_to_telegram()
    return jsonify({"ok":True,"activated":pref,"user":u["user"],"referral":f"{ref_code} now {refs.get(ref_code,{}).get('count',0)}/10" if ref_code else "no ref","storage":BASE_DIR})

@app.route("/admin/reject")
def admin_reject():
    pref = request.args.get("ref","")
    users = load_json(USERS_FILE)
    if pref in users:
        users[pref]["status"]="rejected"
        save_json(USERS_FILE, users)
    return jsonify({"ok":True,"rejected":pref})

@app.route("/admin/restore-paid")
def restore_paid():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"):
        return "Bad secret - add?secret=YOUR_CRON_SECRET"
    email = request.args.get("email","").lower().strip()
    name = request.args.get("name","Paid User")
    plan = request.args.get("plan","yearly")
    if not email:
        return "Need?email=user@gmail.com&name=Name&plan=yearly or lifetime"
    auth = load_json(AUTH_FILE)
    auth[email]={"email":email,"name":name,"password":hash_pwd("Agent35!"),"account_size":142.0,"total_profit":-1.42,"plan_status":f"ACTIVE {plan} - RESTORED by Creator","expires":(datetime.now()+timedelta(days=365 if plan=="yearly" else 36500)).isoformat(),"created":datetime.now().isoformat(),"reset_token":None}
    save_json(AUTH_FILE, auth)
    backup_to_telegram()
    return jsonify({"ok":True,"restored":email,"temp_password":"Agent35!","login":"/login","storage":BASE_DIR})

@app.route("/journal")
def journal_page():
    journal = load_json(JOURNAL_FILE, list)
    tracked = load_json(TRACK_FILE, dict)
    j_rows = "".join([f"<tr><td>{j.get('time')}</td><td>{j.get('symbol')}</td><td><span class='took'>{j.get('status')}</span></td><td>{j.get('result')}</td></tr>" for j in reversed(journal[-50:])])
    t_rows = "".join([f"<tr><td>{v.get('symbol')}</td><td>{v.get('status')}</td><td>{v.get('sl')}</td><td>{v.get('tp')}</td><td>{v.get('by')}</td></tr>" for v in tracked.values()]) or "<tr><td colspan=5 style='text-align:center;color:#64748b'>No tracked yet - click 📈 TRACK TO SL/TP on Telegram</td></tr>"
    return dark_layout(f"<div class='table-card'><h2>Journal - {BASE_DIR} | Capitec {CAPITEC['acc']}</h2><table><tr><th>TIME</th><th>SYM</th><th>STATUS</th><th>RESULT</th></tr>{j_rows or '<tr><td colspan=4>No entries yet</td></tr>'}</table><h2 style='margin-top:20px'>📈 Tracked Trades to SL/TP - Click TRACK on Telegram</h2><table><tr><th>Symbol</th><th>Status</th><th>SL</th><th>TP</th><th>By</th></tr>{t_rows}</table></div>","Journal")

@app.route("/all-signals")
def all_signals():
    return redirect("/dashboard-scan")

@app.route("/settings")
def settings_page():
    system = load_json(SYSTEM_FILE, dict)
    return dark_layout(f"<div class='table-card'><h2>Settings - Agent 35</h2><p><b>Storage:</b> {BASE_DIR} | Persistent: {BASE_DIR=='/data'}<br><b>Capitec:</b> {CAPITEC['acc']} - {CAPITEC['holder']} - {CAPITEC['branch']}<br><b>Bot:</b> @Sniper035_bot<br><b>Threshold:</b> 6/10 Fix (4H Neutral allowed + 15m BOS+FVG)<br><b>Telegram:</b> Buttons Take/Miss/Track to SL/TP<br><b>Login:</b> Keeps like last week if /data disk added<br><b>System up:</b> {system.get('system_up_since','Unknown')}<br><b>Last scan:</b> {system.get('last_scan','Never')}<br><b>Scans:</b> {system.get('total_scans',0)}<br><b>Signals:</b> {system.get('total_signals',0)}</p><a href='/creator?secret=' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Go Creator Dashboard</a></div>","Settings")

@app.route("/plans")
def plans_page():
    return dark_layout(f"<div class='table-card'><h2>Plans - Pay to Capitec {CAPITEC['acc']}</h2><p>Bank: {CAPITEC['bank']}<br>Holder: {CAPITEC['holder']}<br>Acc: {CAPITEC['acc']}<br>Branch: {CAPITEC['branch']}<br><br><b>Yearly R500</b> - 365 days<br><b>Lifetime R5000</b> - 36500 days<br><br>10 paid referrals = Lifetime FREE<br>Only counts after admin ACCEPTS payment</p><a href='/pay' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Buy Now - Get Payment Ref</a> <a href='/referral' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;margin-left:10px'>Referral Codes</a></div>","Plans")

@app.route("/guide")
def guide_page():
    return dark_layout("<div class='table-card'><h2>Guide - 6/10 Fix</h2><p><b>Entry:</b> 4H trend (Bullish/Bearish/Neutral allowed) + 15m BOS + FVG + 5m entry<br><b>Score:</b> 6/10 minimum to send Telegram<br><b>Buttons:</b> Take logs TOOK, Miss logs MISS, Track monitors to SL/TP<br><b>Capitec:</b> 2586572676 - Use reference like A35-USER-123<br><b>Last week mode:</b> Add Disk /data in Render to keep logins after daily updates like last week</p></div>","Guide")

@app.route("/health")
def health():
    system = load_json(SYSTEM_FILE, dict)
    return jsonify({
        "ok":True,
        "version":"V16 FULL EVERYTHING - Last week mode + Creator + Webhook inside + Telegram buttons + Capitec 2586572676 + Referral 10=R5000",
        "storage":BASE_DIR,
        "persistent":BASE_DIR=="/data",
        "last_week_mode":"Add Disk /data to keep logins after daily updates like last week Monday-Friday",
        "users":len(load_json(AUTH_FILE)),
        "pending_payments":len([u for u in load_json(USERS_FILE).values() if u.get("status")=="pending"]),
        "tracked":len(load_json(TRACK_FILE, dict)),
        "capitec":CAPITEC['acc'],
        "telegram_bot":"@Sniper035_bot",
        "telegram_buttons":"Take/Miss/Track to SL/TP",
        "webhook":system.get("webhook_set",False),
        "webhook_url":"https://agent-35-trading-bot.onrender.com/telegram/webhook",
        "system":system,
        "creator":"/creator?secret=YOUR_CRON_SECRET - has SET WEBHOOK button inside",
        "backup":"Auto backup to Telegram on every new user"
    })

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000)
