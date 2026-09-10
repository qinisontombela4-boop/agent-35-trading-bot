from flask import Flask, request, jsonify, session, redirect
import os, json, random, hashlib, secrets, string
from dotenv import load_dotenv
import trading_engine as eng
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "agent35-last-week-stable-key")

# ===== LAST WEEK FILES - SAME AS BEFORE - STAYS UNTIL DEPLOY =====
AUTH_FILE = "auth_users.json"
USERS_FILE = "users_data.json"
DATA_FILE = "referrals_data.json"
JOURNAL_FILE = "journal.json"
WATCHLIST_FILE = "watchlist.json"

CAPITEC = {
    "bank": "Capitec",
    "holder": "Agent 35 Trading Bot",
    "acc": "2586572676",
    "branch": "470010",
    "ref_prefix": "A35"
}

PLANS = {
    "yearly": {"name": "Yearly", "price": 500, "days": 365},
    "lifetime": {"name": "Lifetime", "price": 5000, "days": 36500}
}

def load_json(path, default=dict):
    if not os.path.exists(path):
        return {} if default == dict else []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {} if default == dict else []

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(f, data, indent=2)

def hash_pwd(p):
    return hashlib.sha256(p.encode()).hexdigest()

# ===== LAST WEEK LOGIC: CREATE MASTER ONLY IF FILE MISSING, NEVER WIPE =====
def ensure_files():
    if not os.path.exists(AUTH_FILE):
        auth = {
            "admin@agent35.com": {
                "email": "admin@agent35.com",
                "name": "Master Admin",
                "password": hash_pwd("Agent35!"),
                "phone": "",
                "account_size": 142.0,
                "total_profit": -1.42,
                "plan_status": "ACTIVE lifetime - MASTER",
                "referred_by": "",
                "expires": (datetime.now() + timedelta(days=36500)).isoformat(),
                "created": datetime.now().isoformat(),
                "reset_token": None,
                "reset_expiry": None
            }
        }
        save_json(AUTH_FILE, auth)
        print("FIRST RUN - Master created: admin@agent35.com / Agent35!")
    else:
        print(f"Auth exists - keeping {len(load_json(AUTH_FILE))} users - like last week")

    if not os.path.exists(USERS_FILE):
        save_json(USERS_FILE, {})
    if not os.path.exists(DATA_FILE):
        save_json(DATA_FILE, {})
    if not os.path.exists(JOURNAL_FILE):
        save_json(JOURNAL_FILE, [])

ensure_files()

# ===== DARK DASHBOARD - SAME AS YOUR PHOTO + ADAPTIVE PHONE =====
def dark_layout(content, active="Dashboard"):
    utc = datetime.utcnow().strftime("%H:%M:%S")
    sast = (datetime.utcnow() + timedelta(hours=2)).strftime("%H:%M:%S")
    user = session.get("user", "Guest")
    tabs = ["Dashboard", "Journal", "All Signals", "Settings", "Plans", "Guide", "Master"]
    tab_html = ""
    for t in tabs:
        url = f"/{t.lower().replace(' ', '-')}"
        bg = "#10b981" if active == t else "#1e293b"
        tab_html += f"<a href='{url}' style='padding:8px 14px;border-radius:20px;text-decoration:none;font-weight:bold;font-size:13px;background:{bg};color:white;margin-right:6px;display:inline-block;margin-bottom:6px'>{t}</a>"

    return f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>AGENT 35</title>
    <style>
    body{{background:#0f172a;color:#e2e8f0;font-family:Inter,Arial;margin:0}}
 .top{{background:#0f172a;border-bottom:1px solid #1e293b;padding:12px 15px;display:flex;justify-content:space-between;flex-wrap:wrap}}
 .logo{{color:#10b981;font-weight:900;font-size:18px}}.time{{color:#94a3b8;font-size:11px}}
 .nav{{background:#0f172a;padding:10px 15px;border-bottom:1px solid #1e293b;overflow-x:auto;white-space:nowrap}}
 .main{{padding:15px;display:grid;grid-template-columns:1fr 1fr 1fr 300px;gap:12px}}
 .card{{background:#1e293b;border-radius:16px;padding:18px;border:1px solid #334155;min-width:0}}
 .profit{{color:#ef4444;font-size:26px;font-weight:900}}.muted{{color:#64748b;font-size:11px}}
 .acc{{font-size:22px;font-weight:800}}.edit{{background:#0f172a;border:1px solid #334155;color:white;padding:8px 20px;border-radius:8px;margin-top:8px;cursor:pointer}}
 .pair{{background:#334155;padding:6px 10px;border-radius:20px;display:inline-block;margin:4px;font-size:12px}}
 .scan{{background:#10b981;color:white;padding:14px;border-radius:12px;text-align:center;font-weight:900;border:none;width:100%;cursor:pointer}}
 .blue{{background:#3b82f6;color:white;padding:12px;border-radius:12px;text-align:center;margin-top:10px;display:block;text-decoration:none;font-weight:bold}}
 .table-card{{grid-column:1 / span 4;background:#1e293b;border-radius:16px;padding:15px;overflow-x:auto}}
    table{{width:100%;border-collapse:collapse;min-width:500px}} th{{color:#64748b;text-align:left;padding:10px;font-size:10px}} td{{padding:12px;border-top:1px solid #334155;font-size:13px}}
 .took{{background:#10b98133;color:#10b981;padding:4px 10px;border-radius:10px;font-size:11px}}
    @media(max-width:900px){{.main{{grid-template-columns:1fr 1fr}}.table-card{{grid-column:1 / span 2}}}}
    @media(max-width:600px){{.main{{grid-template-columns:1fr}}.table-card{{grid-column:1}}.top{{flex-direction:column;align-items:flex-start}}}}
    </style></head><body>
    <div class='top'><div class='logo'>35 AGENT 35</div><div class='time'>UTC {utc} | SAST {sast} | <span style='color:#10b981'>London ACTIVE</span> | {user} | Sessions: 24/7 | News: <span style='color:orange'>OFF</span></div></div>
    <div class='nav'>{tab_html}</div>
    {content}
    </body></html>
    """

@app.route("/")
def home():
    return redirect("/dashboard") if session.get("user") else redirect("/login")

@app.route("/dashboard")
def dashboard():
    if not session.get("user"):
        return redirect("/login")
    auth = load_json(AUTH_FILE)
    user_email = session.get("user")
    info = auth.get(user_email, {})
    acc_size = info.get("account_size", 142.0)
    total_profit = info.get("total_profit", -1.42)

    journal = load_json(JOURNAL_FILE, list)
    if not journal:
        journal = [
            {"time": "09-03 18:13", "symbol": "USDCHF", "status": "TOOK", "result": "R0 (0.0R)"},
            {"time": "09-03 18:13", "symbol": "USDJPY", "status": "TOOK", "result": "R0 (0.0R)"},
            {"time": "09-03 18:13", "symbol": "GBPUSD", "status": "TOOK", "result": "R0 (0.0R)"},
            {"time": "09-03 18:13", "symbol": "EURUSD", "status": "TOOK", "result": "R0 (0.0R)"},
        ]
    rows = "".join([f"<tr><td>{t.get('time')}</td><td style='font-weight:800'>{t.get('symbol')}</td><td><span class='took'>{t.get('status')}</span></td><td>{t.get('result')}</td></tr>" for t in reversed(journal[-10:])])

    watch = "<span class='pair'>EURUSD x</span> <span class='pair'>GBPUSD x</span> <span class='pair'>USDJPY x</span> <span class='pair'>USDCHF x</span>"

    content = f"""
    <div class='main'>
        <div class='card'><div class='muted'>TOTAL PROFIT</div><div class='profit'>R{total_profit}</div><div style='color:#10b981;background:#10b98122;display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px'>WR: 0.0% | -1.0R</div></div>
        <div class='card'><div class='muted'>ACCOUNT SIZE</div><div class='acc'>R{acc_size}</div>
        <form action='/account/edit' method='post'><input name='size' value='{acc_size}' style='background:#0f172a;border:1px solid #334155;color:white;padding:8px;border-radius:8px;width:100%;margin-top:8px'><button class='edit' type='submit'>Edit</button></form></div>
        <div class='card'><div class='muted'>WATCHLIST 4/5</div><div style='margin:10px 0'>{watch}</div><input placeholder='Search pairs...' style='background:#0f172a;border:none;padding:10px;border-radius:10px;width:100%;color:white'></div>
        <div class='card'><a href='/dashboard-scan'><button class='scan'>SCAN NOW</button></a><div style='text-align:center;margin:10px;color:#64748b;font-size:12px'>Link Telegram<br>Capitec {CAPITEC['acc']}</div><a href='/test-telegram' class='blue'>Test Telegram</a></div>
    </div>
    <div class='table-card'><table><tr><th>TIME</th><th>SYMBOL</th><th>STATUS</th><th>RESULT</th></tr>{rows}</table></div>
    """
    return dark_layout(content, "Dashboard")

# ===== LOGIN SYSTEM - LAST WEEK KEEP LOGINS =====
@app.route("/login")
def login_page():
    auth = load_json(AUTH_FILE)
    count = len(auth)
    return f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
    <body style='background:#0f172a;color:white;font-family:Arial;padding:20px'><div style='max-width:400px;margin:40px auto;background:#1e293b;padding:25px;border-radius:16px'>
    <h2>Login - Agent 35</h2><p style='color:#64748b;font-size:12px'>{count} accounts saved on this instance - stays for a week if no redeploy (like last week)</p>
    <form action='/login/check' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:12px;margin:8px 0;border-radius:8px;border:none'>
    <input name='password' type='password' placeholder='Password' required style='width:100%;padding:12px;margin:8px 0;border-radius:8px;border:none'>
    <button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;font-weight:bold'>LOGIN</button></form>
    <p><a href='/register' style='color:#3b82f6'>Register</a> | <a href='/forgot-password' style='color:#ff6b35'>Forgot Password?</a></p>
    <div style='background:#0f172a;padding:12px;border-radius:8px;margin-top:10px'><p style='font-size:11px;color:#94a3b8'>Master: admin@agent35.com / Agent35!</p></div></div></body></html>"""

@app.route("/register")
def register_page():
    return """<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
    <body style='background:#0f172a;color:white;font-family:Arial;padding:20px'><div style='max-width:400px;margin:40px auto;background:#1e293b;padding:25px;border-radius:16px'>
    <h2>Register</h2><form action='/register/create' method='post'>
    <input name='email' type='email' placeholder='Email' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
    <input name='name' placeholder='Full Name' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
    <input name='phone' placeholder='WhatsApp' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
    <input name='password' type='password' placeholder='Password min 6' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
    <input name='ref' placeholder='Referral Code (optional)' style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
    <button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;font-weight:bold'>CREATE ACCOUNT</button></form>
    <p><a href='/login' style='color:#3b82f6'>Already have account?</a></p></div></body></html>"""

@app.route("/register/create", methods=["POST"])
def register_create():
    email = request.form.get("email","").lower().strip()
    name = request.form.get("name","").strip()
    phone = request.form.get("phone","").strip()
    pwd = request.form.get("password","")
    ref = request.form.get("ref","").upper().strip()

    auth = load_json(AUTH_FILE)
    if email in auth:
        return f"Email {email} already exists - <a href='/login'>Login</a>"

    auth[email] = {
        "email": email,
        "name": name,
        "phone": phone,
        "password": hash_pwd(pwd),
        "account_size": 142.0,
        "total_profit": -1.42,
        "plan_status": "No Plan - Need R500/R5000",
        "referred_by": ref,
        "expires": None,
        "created": datetime.now().isoformat(),
        "reset_token": None,
        "reset_expiry": None
    }
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
    return f"<html><body style='background:#0f172a;color:white;padding:30px'><h2>❌ Wrong password for {email}</h2><p>Accounts on disk: {list(auth.keys())}</p><p><a href='/login'>Retry</a> | <a href='/register'>Register</a> | <a href='/forgot-password'>Forgot?</a></p></body></html>"

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

@app.route("/forgot-password")
def forgot_page():
    return """<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
    <body style='background:#0f172a;color:white;padding:30px'><div style='max-width:400px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'>
    <h2>Forgot Password</h2><form action='/forgot-password/send' method='post'>
    <input name='email' type='email' placeholder='Your Email' required style='width:100%;padding:12px;border-radius:8px;border:none'>
    <button style='background:#ff6b35;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px;font-weight:bold'>SEND RESET LINK</button></form>
    <p><a href='/login' style='color:#64748b'>Back to Login</a></p></div></body></html>"""

@app.route("/forgot-password/send", methods=["POST"])
def forgot_send():
    email = request.form.get("email","").lower().strip()
    auth = load_json(AUTH_FILE)
    if email not in auth:
        return f"Email {email} not found - <a href='/register'>Register</a>"
    token = secrets.token_urlsafe(16)
    auth[email]["reset_token"] = token
    auth[email]["reset_expiry"] = (datetime.now() + timedelta(hours=1)).isoformat()
    save_json(AUTH_FILE, auth)
    link = f"https://agent-35-trading-bot.onrender.com/reset-password?token={token}&email={email}"
    return f"<html><body style='background:#0f172a;color:white;padding:20px;text-align:center'><h2 style='color:#10b981'>Reset Link (1h valid)</h2><div style='background:#1e293b;padding:20px;border-radius:12px;max-width:500px;margin:auto'><p style='word-break:break-all'><a href='{link}' style='color:#10b981'>{link}</a></p><a href='{link}' style='background:#10b981;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;display:inline-block'>RESET NOW</a></div></body></html>"

@app.route("/reset-password")
def reset_page():
    email = request.args.get("email","")
    token = request.args.get("token","")
    return f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
    <body style='background:#0f172a;color:white;padding:30px'><div style='max-width:400px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'>
    <h2>Reset Password - {email}</h2><form action='/reset-password/save' method='post'>
    <input type='hidden' name='email' value='{email}'><input type='hidden' name='token' value='{token}'>
    <input name='new_password' type='password' placeholder='New Password min 6' required style='width:100%;padding:12px;border-radius:8px;border:none'>
    <input name='confirm' type='password' placeholder='Confirm' required style='width:100%;padding:12px;border-radius:8px;border:none;margin-top:8px'>
    <button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px;font-weight:bold'>SAVE NEW PASSWORD</button></form></div></body></html>"""

@app.route("/reset-password/save", methods=["POST"])
def reset_save():
    email = request.form.get("email","").lower().strip()
    token = request.form.get("token","")
    new_pwd = request.form.get("new_password","")
    confirm = request.form.get("confirm","")
    if new_pwd!= confirm or len(new_pwd) < 6:
        return "Passwords don't match or too short - <a href='/forgot-password'>Retry</a>"
    auth = load_json(AUTH_FILE)
    if auth.get(email,{}).get("reset_token")!= token:
        return "Invalid token - <a href='/forgot-password'>Request new</a>"
    auth[email]["password"] = hash_pwd(new_pwd)
    auth[email]["reset_token"] = None
    auth[email]["reset_expiry"] = None
    save_json(AUTH_FILE, auth)
    return f"<html><body style='background:#0f172a;color:white;padding:30px;text-align:center'><h2 style='color:#10b981'>✅ Password Changed for {email}</h2><a href='/login' style='background:#0f172a;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;border:1px solid #334155'>Login Now</a></body></html>"

@app.route("/account/edit", methods=["POST"])
def account_edit():
    if not session.get("user"):
        return redirect("/login")
    size = request.form.get("size","142.0")
    try:
        size_f = float(size)
    except:
        size_f = 142.0
    auth = load_json(AUTH_FILE)
    if session["user"] in auth:
        auth[session["user"]]["account_size"] = size_f
        save_json(AUTH_FILE, auth)
    return redirect("/dashboard")

# ===== PAYMENT + REFERRAL + CAPITEC 2586572676 =====
@app.route("/pay")
def pay_page():
    ref = request.args.get("ref","") or session.get("ref","")
    email = request.args.get("email","") or session.get("user","")
    return f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
    <body style='background:#0f172a;color:white;font-family:Arial;padding:20px'><div style='max-width:500px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'>
    <h2>Buy Plan - Capitec {CAPITEC['acc']}</h2><p>Holder: {CAPITEC['holder']}<br>Acc: {CAPITEC['acc']}<br>Branch: {CAPITEC['branch']}</p>
    <form action='/pay/create' method='get'><input type='hidden' name='ref' value='{ref}'>
    <input name='user' value='{email}' placeholder='Email (login email)' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
    <input name='phone' placeholder='WhatsApp' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'>
    <select name='plan' style='width:100%;padding:12px;border-radius:8px'><option value='yearly'>Yearly R500</option><option value='lifetime'>Lifetime R5000</option></select>
    <button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px;font-weight:bold'>GET PAYMENT REFERENCE</button></form>
    {f"<p>Referred by: {ref}</p>" if ref else ""}</div></body></html>"""

@app.route("/pay/create")
def pay_create():
    user = request.args.get("user","").lower().strip()
    phone = request.args.get("phone","").strip()
    plan_key = request.args.get("plan","yearly")
    ref = request.args.get("ref","").upper().strip()
    short = "".join([c for c in user.upper() if c.isalnum()])[:5] or "USER"
    rand = "".join(random.choices(string.digits, k=3))
    pref = f"{CAPITEC['ref_prefix']}-{short}-{rand}"
    plan = PLANS.get(plan_key, PLANS["yearly"])
    users = load_json(USERS_FILE)
    users[pref] = {"user": user, "phone": phone, "plan": plan_key, "price": plan["price"], "payment_ref": pref, "referred_by": ref, "status": "pending", "created": datetime.now().isoformat(), "expires": None}
    save_json(USERS_FILE, users)
    return f"<html><body style='background:#0f172a;color:white;font-family:Arial;padding:30px;text-align:center'><h1 style='color:#10b981'>Pay R{plan['price']}</h1><div style='border:2px dashed #334155;padding:20px;border-radius:12px;max-width:450px;margin:auto;background:#1e293b'><p style='font-size:18px'>Bank: Capitec<br>Name: {CAPITEC['holder']}<br>Acc No: {CAPITEC['acc']}<br>Branch: {CAPITEC['branch']}</p><h1 style='background:white;color:black;padding:15px;border-radius:10px;letter-spacing:2px'>{pref}</h1><p>USE THIS REFERENCE IN CAPITEC APP<br>Plan: {plan['name']} | User: {user}<br>Referred by: {ref or 'None'}</p></div><p>After paying, admin approves in /admin</p></body></html>"

@app.route("/join")
def join():
    ref = request.args.get("ref","")
    session["ref"] = ref
    return f"<html><body style='background:#0f172a;color:white;padding:40px;text-align:center'><h1>Referred by {ref}</h1><p>Sign up - referral counts AFTER you pay and admin accepts</p><a href='/pay?ref={ref}' style='background:#10b981;color:white;padding:14px 30px;border-radius:10px;text-decoration:none;font-weight:bold'>Continue to Pay R500 / R5000 - Capitec {CAPITEC['acc']}</a><br><br><a href='/register?ref={ref}' style='color:#3b82f6'>Or Register First</a></body></html>"

@app.route("/referral")
def referral_page():
    data = load_json(DATA_FILE)
    rows = "".join([f"<tr><td style='padding:10px'>{code}</td><td style='padding:10px'>{info.get('owner','')}</td><td style='padding:10px'>{info.get('count',0)}/10</td><td style='padding:10px'>{'✅ LIFETIME R5000' if info.get('count',0)>=10 else '⏳'}</td><td style='padding:10px'>{', '.join(info.get('paid_refs',[])[:2])}</td></tr>" for code, info in data.items()])
    return dark_layout(f"<div class='table-card'><h2>Referral - 10 Paid = R5000 Lifetime Free</h2><p>Rule: Only counts AFTER admin ACCEPTS Capitec payment</p><table><tr><th>Code</th><th>Owner</th><th>Count</th><th>Reward</th><th>Paid Users</th></tr>{rows}</table><br><form action='/referral/create' method='get'><input name='code' placeholder='CODE' style='padding:8px;border-radius:6px'><input name='owner' placeholder='Owner email' style='padding:8px;border-radius:6px'><button style='background:#10b981;color:white;padding:8px 12px;border:none;border-radius:6px'>Create Code</button></form></div>", "Master")

@app.route("/referral/create")
def referral_create():
    code = request.args.get("code","").upper().strip()
    owner = request.args.get("owner","").strip()
    if not code:
        return jsonify({"error": "code required"})
    data = load_json(DATA_FILE)
    if code not in data:
        data[code] = {"owner": owner, "count": 0, "paid_refs": [], "reward_claimed": False, "created": datetime.now().isoformat()}
        save_json(DATA_FILE, data)
    return redirect("/referral")

# ===== TRADING + 3 CRON JOBS (LIKE LAST WEEK) =====
@app.route("/scan")
def scan():
    return jsonify(eng.full_multi_tf_analysis(request.args.get("symbol", "EURUSD")))

@app.route("/dashboard-scan")
def dashboard_scan():
    syms = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "XAUUSD", "US30", "NAS100", "GBPJPY"]
    rows = ""
    for s in syms:
        r = eng.full_multi_tf_analysis(s)
        rows += f"<tr><td>{s}</td><td>{r['score']}/10</td><td>{r['bias']}</td><td>{r['signal']}</td><td>{r['reason']}</td></tr>"
    return dark_layout(f"<div class='table-card'><h2>Scan All 8 - 6/10 Fix Active</h2><table><tr><th>Symbol</th><th>Score</th><th>Bias</th><th>Signal</th><th>Reason</th></tr>{rows}</table><br><a href='/dashboard' style='color:#10b981'>Back Dashboard</a></div>", "All Signals")

@app.route("/cron/scan")
def cron_scan():
    if request.args.get("secret")!= os.getenv("CRON_SECRET"):
        return jsonify({"error": "bad secret"})
    result = eng.run_scan_and_send()
    journal = load_json(JOURNAL_FILE, list)
    for sig in result.get("signals", []):
        journal.append({"time": datetime.now().strftime("%m-%d %H:%M"), "symbol": sig.get("symbol",""), "status": "TOOK", "result": f"R0 - {sig.get('score')}/10 {sig.get('bias')}"})
    save_json(JOURNAL_FILE, journal[-100:])
    return jsonify({"cron": "scan - every 30min", "result": result})

@app.route("/cron/daily-reset")
def cron_daily():
    if request.args.get("secret")!= os.getenv("CRON_SECRET"):
        return jsonify({"error": "bad secret"})
    return jsonify({"cron": "daily-reset - 00:00 SAST", "ok": True, "time": datetime.now().isoformat()})

@app.route("/cron/check-expiry")
def cron_expiry():
    if request.args.get("secret")!= os.getenv("CRON_SECRET"):
        return jsonify({"error": "bad secret"})
    auth = load_json(AUTH_FILE)
    expired = []
    for email, info in auth.items():
        exp = info.get("expires")
        if exp:
            try:
                if datetime.now() > datetime.fromisoformat(exp):
                    info["plan_status"] = "EXPIRED"
                    expired.append(email)
            except:
                pass
    save_json(AUTH_FILE, auth)
    return jsonify({"cron": "check-expiry - 06:00 SAST", "checked": len(auth), "expired": expired})

@app.route("/run-now")
def run_now():
    if request.args.get("secret")!= os.getenv("CRON_SECRET"):
        return jsonify({"error": "bad secret"})
    return jsonify(eng.run_scan_and_send())

@app.route("/test-telegram")
def test_telegram():
    bot = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not bot or not chat:
        return jsonify({"error": "No TELEGRAM env set"})
    import requests
    r = requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id": chat, "text": "✅ Agent 35 Test - Dark Dashboard V8.1 - Login Keep Like Last Week - Capitec 2586572676 Live"}, timeout=10)
    return jsonify({"sent": r.json() if r else {}})

@app.route("/admin")
def admin_page():
    secret = request.args.get("secret","")
    real = os.getenv("CRON_SECRET","")
    if real and secret!= real:
        return f"<html><body style='background:#0f172a;color:white;padding:30px'><h1>Admin Login</h1><form><input name='secret' placeholder='CRON_SECRET' style='padding:12px;border-radius:8px'><button style='padding:12px'>Login</button></form></body></html>"
    users = load_json(USERS_FILE)
    auth = load_json(AUTH_FILE)
    refs = load_json(DATA_FILE)

    u_rows = "".join([f"<tr><td style='padding:10px'>{pref}</td><td style='padding:10px'>{u['user']}<br>{u['phone']}</td><td style='padding:10px'>{u['plan']} R{u['price']}</td><td style='padding:10px'>{u.get('referred_by') or '-'}</td><td style='padding:10px'>{u['status']}</td><td style='padding:10px'><a href='/admin/accept?ref={pref}&secret={secret}' style='background:#10b981;color:white;padding:6px 10px;border-radius:6px;text-decoration:none'>ACCEPT</a> <a href='/admin/reject?ref={pref}&secret={secret}' style='background:#ef4444;color:white;padding:6px 10px;border-radius:6px;text-decoration:none'>REJECT</a></td></tr>" for pref, u in users.items()])
    a_rows = "".join([f"<tr><td style='padding:8px'>{e}</td><td style='padding:8px'>{i.get('name','')}</td><td style='padding:8px'>{i.get('plan_status','')}</td><td style='padding:8px'>R{i.get('account_size',0)}</td><td style='padding:8px'>{i.get('referred_by') or '-'}</td></tr>" for e,i in auth.items()])
    r_rows = "".join([f"<tr><td style='padding:8px'>{c}</td><td style='padding:8px'>{i.get('count',0)}/10</td></tr>" for c,i in refs.items()])

    return f"<html><body style='background:#0f172a;color:white;font-family:Arial;padding:20px'><h1>Admin - Capitec {CAPITEC['acc']} {CAPITEC['holder']}</h1><p>Logins Saved: {len(auth)} - Like last week, stays until next deploy. Don't deploy for a week = stays a week.</p><h3>All Logins (User Memory)</h3><table border=1 cellpadding=5 style='border-collapse:collapse;width:100%'><tr><th>Email</th><th>Name</th><th>Status</th><th>Acc Size</th><th>Ref By</th></tr>{a_rows}</table><h3>Pending Capitec Payments</h3><table border=1 cellpadding=5 style='border-collapse:collapse;width:100%'><tr><th>Payment Ref</th><th>User</th><th>Plan</th><th>Ref By</th><th>Status</th><th>Action</th></tr>{u_rows}</table><h3>Referrals</h3><table border=1 cellpadding=5><tr><th>Code</th><th>Count</th></tr>{r_rows}</table><br><a href='/dashboard' style='color:#10b981'>Back Dashboard</a></body></html>"

@app.route("/admin/accept")
def admin_accept():
    pref = request.args.get("ref","")
    secret = request.args.get("secret","")
    users = load_json(USERS_FILE)
    auth = load_json(AUTH_FILE)
    refs = load_json(DATA_FILE)
    if pref not in users:
        return jsonify({"error": "not found"})
    u = users[pref]
    u["status"] = "active"
    plan_days = PLANS.get(u["plan"], PLANS["yearly"])["days"]
    u["expires"] = (datetime.now() + timedelta(days=plan_days)).isoformat()
    users[pref] = u
    save_json(USERS_FILE, users)

    if u["user"] in auth:
        auth[u["user"]]["plan_status"] = f"ACTIVE {u['plan']} - Paid Capitec"
        auth[u["user"]]["expires"] = u["expires"]
        save_json(AUTH_FILE, auth)

    ref_code = u.get("referred_by")
    msg = ""
    if ref_code:
        if ref_code not in refs:
            refs[ref_code] = {"owner": ref_code, "count": 0, "paid_refs": [], "reward_claimed": False}
        if u["user"] not in refs[ref_code].get("paid_refs", []):
            refs[ref_code]["paid_refs"].append(u["user"])
            refs[ref_code]["count"] = len(refs[ref_code]["paid_refs"])
            save_json(DATA_FILE, refs)
            msg = f"Referral counted: {u['user']} -> {ref_code} = {refs[ref_code]['count']}/10"
            if refs[ref_code]["count"] >= 10:
                msg += " 🎉 10 REACHED - GIVE LIFETIME R5000 FREE"

    return jsonify({"ok": True, "activated": pref, "user": u["user"], "referral": msg, "admin": f"/admin?secret={secret}"})

@app.route("/admin/reject")
def admin_reject():
    pref = request.args.get("ref","")
    secret = request.args.get("secret","")
    users = load_json(USERS_FILE)
    if pref in users:
        users[pref]["status"] = "rejected"
        save_json(USERS_FILE, users)
    return jsonify({"ok": True, "rejected": pref, "admin": f"/admin?secret={secret}"})

@app.route("/admin/restore-paid")
def restore_paid():
    if request.args.get("secret")!= os.getenv("CRON_SECRET"):
        return "Bad secret - use CRON_SECRET"
    email = request.args.get("email","").lower().strip()
    name = request.args.get("name","Paid User")
    plan = request.args.get("plan","yearly")
    if not email:
        return "Need?email=user@gmail.com&name=Name&plan=yearly/lifetime&secret=YOUR_CRON_SECRET"
    auth = load_json(AUTH_FILE)
    auth[email] = {
        "email": email,
        "name": name,
        "password": hash_pwd("Agent35!"),
        "phone": "",
        "account_size": 142.0,
        "total_profit": -1.42,
        "plan_status": f"ACTIVE {plan} - RESTORED PAID",
        "referred_by": "",
        "expires": (datetime.now() + timedelta(days=365 if plan=="yearly" else 36500)).isoformat(),
        "created": datetime.now().isoformat(),
        "reset_token": None,
        "reset_expiry": None
    }
    save_json(AUTH_FILE, auth)
    return jsonify({"ok": True, "restored": email, "temp_password": "Agent35!", "login": "/login", "message": f"{email} restored as {plan}. Tell them login with Agent35! then /forgot-password"})

@app.route("/journal")
def journal_page():
    journal = load_json(JOURNAL_FILE, list)
    rows = "".join([f"<tr><td style='padding:10px'>{j.get('time')}</td><td style='padding:10px'>{j.get('symbol')}</td><td style='padding:10px'><span class='took'>{j.get('status')}</span></td><td style='padding:10px'>{j.get('result')}</td></tr>" for j in reversed(journal[-50:])])
    return dark_layout(f"<div class='table-card'><h2>Journal - User Memory</h2><table><tr><th>TIME</th><th>SYMBOL</th><th>STATUS</th><th>RESULT</th></tr>{rows}</table></div>", "Journal")

@app.route("/all-signals")
def all_signals_page():
    return redirect("/dashboard-scan")

@app.route("/settings")
def settings_page():
    return dark_layout(f"<div class='table-card'><h2>Settings</h2><p>Capitec Bank: {CAPITEC['acc']} - {CAPITEC['holder']}<br>Branch: {CAPITEC['branch']}<br>Threshold: 6/10 Fix Active - 4H Neutral Allowed<br>Telegram: Linked</p><p>Login Memory: Last week structure - stays until next deploy</p></div>", "Settings")

@app.route("/plans")
def plans_page():
    return dark_layout(f"<div class='table-card'><h2>Plans - Capitec {CAPITEC['acc']}</h2><p>Yearly R500 | Lifetime R5000<br>Bank: Capitec<br>Acc Holder: {CAPITEC['holder']}<br>Acc No: {CAPITEC['acc']}<br>Branch: {CAPITEC['branch']}</p><a href='/pay' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Buy Now</a></div>", "Plans")

@app.route("/guide")
def guide_page():
    return dark_layout("<div class='table-card'><h2>Guide</h2><p>How to trade Agent 35 signals - 6/10 threshold</p></div>", "Guide")

@app.route("/master")
def master_page():
    return redirect("/referral")

@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "mode": "LAST WEEK STRUCTURE - Login keeps for a week if no deploy",
        "dashboard": "dark adaptive",
        "capitec": f"{CAPITEC['acc']} {CAPITEC['holder']}",
        "users": len(load_json(AUTH_FILE)),
        "pending_payments": len([u for u in load_json(USERS_FILE).values() if u.get("status")=="pending"]),
        "referral_codes": len(load_json(DATA_FILE)),
        "keys": len(eng.API_KEYS)
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
