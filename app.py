from flask import Flask, request, jsonify, session, redirect
import os, json, random, hashlib, secrets
from dotenv import load_dotenv
import trading_engine as eng
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "agent35-v6-responsive")

# Files - User Memory
DATA_FILE = "referrals_data.json"
USERS_FILE = "users_data.json"
AUTH_FILE = "auth_users.json"
JOURNAL_FILE = "journal.json"

CAPITEC = {"bank":"Capitec","holder":"Agent 35 Trading Bot","acc":"2586572676","branch":"470010","ref_prefix":"A35"}

def load_json(p):
    if not os.path.exists(p):
        return {} if "auth" in p or "users" in p or "referral" in p else []
    try:
        with open(p,"r") as f: return json.load(f)
    except: return {} if "auth" in p or "users" in p or "referral" in p else []

def save_json(p,d):
    with open(p,"w") as f: json.dump(f,d,indent=2)

def hash_pwd(p): return hashlib.sha256(p.encode()).hexdigest()

# ===== RESPONSIVE DARK LAYOUT - ADAPTIVE =====
def dark_layout(content, active="Dashboard"):
    utc = datetime.utcnow().strftime("%H:%M:%S")
    sast = (datetime.utcnow() + timedelta(hours=2)).strftime("%H:%M:%S")
    user = session.get("user","Guest")
    tabs = ["Dashboard","Journal","All Signals","Settings","Plans","Guide","Master"]
    tab_html = "".join([f"<a href='/{t.lower().replace(' ','-')}' class='tab { 'active' if active==t else ''}'>{t}</a>" for t in tabs])

    return f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>AGENT 35</title>
    <style>
    body{{background:#0f172a;color:#e2e8f0;font-family:Inter,Arial;margin:0;padding:0}}
   .top{{background:#0f172a;border-bottom:1px solid #1e293b;padding:12px 15px;display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center}}
   .logo{{color:#10b981;font-weight:900;font-size:18px}}.time{{color:#94a3b8;font-size:11px;margin-top:4px}}
   .nav{{background:#0f172a;padding:10px 15px;border-bottom:1px solid #1e293b;display:flex;overflow-x:auto;white-space:nowrap;gap:8px}}
   .tab{{padding:8px 14px;border-radius:20px;text-decoration:none;font-weight:bold;font-size:13px;background:#1e293b;color:white;flex-shrink:0}}
   .tab.active{{background:#10b981}}
   .main{{padding:15px;display:grid;grid-template-columns:1fr 1fr 1fr 300px;gap:12px}}
   .card{{background:#1e293b;border-radius:16px;padding:18px;border:1px solid #334155;min-width:0}}
   .profit{{color:#ef4444;font-size:26px;font-weight:900}}.muted{{color:#64748b;font-size:11px}}
   .acc{{font-size:22px;font-weight:800}}.edit{{background:#0f172a;border:1px solid #334155;color:white;padding:8px 20px;border-radius:8px;margin-top:8px}}
   .pair{{background:#334155;padding:6px 10px;border-radius:20px;display:inline-block;margin:4px;font-size:12px}}
   .scan{{background:#10b981;color:white;padding:14px;border-radius:12px;text-align:center;font-weight:900;cursor:pointer;border:none;width:100%}}
   .blue{{background:#3b82f6;color:white;padding:12px;border-radius:12px;text-align:center;margin-top:10px;display:block;text-decoration:none;font-weight:bold}}
   .table-card{{grid-column:1 / span 4;background:#1e293b;border-radius:16px;padding:15px;overflow-x:auto}}
    table{{width:100%;border-collapse:collapse;min-width:500px}} th{{color:#64748b;text-align:left;padding:10px;font-size:10px}} td{{padding:12px;border-top:1px solid #334155;font-size:13px}}
   .took{{background:#10b98133;color:#10b981;padding:4px 10px;border-radius:10px;font-size:11px}}

    /* ==== ADAPTIVE PHONE FIX ==== */
    @media(max-width: 900px){{
       .main{{grid-template-columns:1fr 1fr;}}
       .table-card{{grid-column:1 / span 2;}}
    }}
    @media(max-width: 600px){{
       .main{{grid-template-columns:1fr;}}
       .table-card{{grid-column:1;}}
       .top{{flex-direction:column;align-items:flex-start}}
       .nav{{padding:10px 10px}}
       .card{{padding:15px}}
    }}
    </style></head>
    <body>
    <div class='top'><div class='logo'>35 AGENT 35</div><div class='time'>UTC {utc} | SAST {sast} | <span style='color:#10b981'>London ACTIVE</span> | {user} | Sessions: 24/7 | News: <span style='color:orange'>OFF ⚠️</span></div></div>
    <div class='nav'>{tab_html}</div>
    {content}
    </body></html>
    """

@app.route("/")
def home(): return redirect("/dashboard") if session.get("user") else redirect("/login")

@app.route("/dashboard")
def dashboard():
    auth = load_json(AUTH_FILE)
    user_email = session.get("user")
    acc_size = auth.get(user_email, {}).get("account_size", 142.0) if user_email else 142.0
    total_profit = auth.get(user_email, {}).get("total_profit", -1.42) if user_email else -1.42
    journal = load_json(JOURNAL_FILE)
    trades = journal[-10:] if isinstance(journal,list) else []
    if not trades:
        trades = [
            {{"time":"09-03 18:13","symbol":"USDCHF","status":"TOOK","result":"R0 (0.0R)"}},
            {{"time":"09-03 18:13","symbol":"USDJPY","status":"TOOK","result":"R0 (0.0R)"}},
            {{"time":"09-03 18:13","symbol":"GBPUSD","status":"TOOK","result":"R0 (0.0R)"}},
            {{"time":"09-03 18:13","symbol":"EURUSD","status":"TOOK","result":"R0 (0.0R)"}},
        ]
    rows = "".join([f"<tr><td>{t.get('time')}</td><td style='font-weight:800'>{t.get('symbol')}</td><td><span class='took'>{t.get('status')}</span></td><td>{t.get('result')}</td></tr>" for t in reversed(trades)])
    watch_html = "<span class='pair'>EURUSD <span style='background:#ef4444;border-radius:50%;padding:1px 5px'>x</span></span> <span class='pair'>GBPUSD <span style='background:#ef4444;border-radius:50%;padding:1px 5px'>x</span></span> <span class='pair'>USDJPY <span style='background:#ef4444;border-radius:50%;padding:1px 5px'>x</span></span> <span class='pair'>USDCHF <span style='background:#ef4444;border-radius:50%;padding:1px 5px'>x</span></span>"
    content = f"""<div class='main'>
        <div class='card'><div class='muted'>TOTAL PROFIT</div><div class='profit'>R{total_profit}</div><div style='color:#10b981;background:#10b98122;display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px'>0.0% -1.0R</div></div>
        <div class='card'><div class='muted'>ACCOUNT SIZE</div><div class='acc'>R{acc_size}</div><form action='/account/edit' method='post'><input name='size' value='{acc_size}' style='background:#0f172a;border:1px solid #334155;color:white;padding:8px;border-radius:8px;width:100%;margin-top:8px'><button class='edit' type='submit'>Edit</button></form></div>
        <div class='card'><div class='muted'>WATCHLIST 4/5</div><div style='margin:10px 0'>{watch_html}</div><input placeholder='Search pairs...' style='background:#0f172a;border:none;padding:10px;border-radius:10px;width:100%;color:white'></div>
        <div class='card'><a href='/dashboard-scan'><button class='scan'>SCAN NOW</button></a><div style='text-align:center;margin:10px;color:#64748b'>Link Telegram</div><a href='/test-telegram' class='blue'>Test Telegram</a></div>
    </div><div class='table-card'><table><tr><th>TIME</th><th>SYMBOL</th><th>STATUS</th><th>RESULT</th></tr>{rows}</table></div>"""
    return dark_layout(content,"Dashboard")

# ===== LOGIN FIX =====
@app.route("/login")
def login_page():
    return """<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
    <body style='background:#0f172a;color:white;font-family:Arial;padding:20px'><div style='max-width:400px;margin:40px auto;background:#1e293b;padding:25px;border-radius:16px'><h2>Login - Agent 35</h2>
    <form action='/login/check' method='post'><input name='email' placeholder='Email' required style='width:100%;padding:12px;margin:8px 0;border-radius:8px;border:none'><input name='password' type='password' placeholder='Password' required style='width:100%;padding:12px;margin:8px 0;border-radius:8px;border:none'><button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;font-weight:bold'>LOGIN</button></form>
    <p><a href='/register' style='color:#3b82f6'>Register</a> | <a href='/forgot-password' style='color:#ff6b35'>Forgot?</a> | <a href='/admin/reset-all?secret=RESET123' style='color:#64748b'>Reset Accounts</a></p></div></body></html>"""

@app.route("/register")
def reg_page():
    return """<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
    <body style='background:#0f172a;color:white;font-family:Arial;padding:20px'><div style='max-width:400px;margin:40px auto;background:#1e293b;padding:25px;border-radius:16px'><h2>Register</h2>
    <form action='/register/create' method='post'><input name='email' placeholder='Email' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><input name='name' placeholder='Name' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><input name='password' type='password' placeholder='Password min 6' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><input name='ref' placeholder='Referral Code' style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;font-weight:bold'>CREATE</button></form></div></body></html>"""

@app.route("/register/create", methods=["POST"])
def reg_create():
    email=request.form.get("email","").lower().strip()
    auth=load_json(AUTH_FILE)
    # FIX: Allow re-register if old file wiped - overwrite
    auth[email]={"email":email,"name":request.form.get("name"),"password":hash_pwd(request.form.get("password","")),"referred_by":request.form.get("ref","").upper(),"account_size":142.0,"total_profit":-1.42,"plan_status":"No Plan","created":datetime.now().isoformat(),"reset_token":None}
    save_json(AUTH_FILE,auth)
    session["user"]=email
    return redirect("/dashboard")

@app.route("/login/check", methods=["POST"])
def login_check():
    email=request.form.get("email","").lower().strip()
    pwd=request.form.get("password","")
    auth=load_json(AUTH_FILE)
    # FIX: Check both hashed and plain (for old accounts)
    if email in auth:
        stored = auth[email].get("password","")
        if stored==hash_pwd(pwd) or stored==pwd:
            session["user"]=email
            return redirect("/dashboard")
    # If not found, allow to register automatically with same password
    return f"<html><body style='background:#0f172a;color:white;padding:30px'><h2>❌ Login failed for {email}</h2><p>Your old account was wiped on last deploy (Render deletes files).</p><p><a href='/register' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Re-Register Same Email</a> - use same email + new password, it will restore R142.0 balance</p><br><p>Or Admin Reset: <a href='/admin/reset-all?secret=RESET123' style='color:#ff6b35'>/admin/reset-all?secret=RESET123</a></p></body></html>"

@app.route("/logout")
def logout(): session.pop("user",None); return redirect("/login")

@app.route("/forgot-password")
def forgot_page(): return """<html><body style='background:#0f172a;color:white;padding:30px'><div style='max-width:400px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>Forgot Password</h2><form action='/forgot-password/send' method='post'><input name='email' placeholder='Email' required style='width:100%;padding:12px'><button style='background:#ff6b35;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px'>SEND RESET LINK</button></form></div></body></html>"""

@app.route("/forgot-password/send", methods=["POST"])
def forgot_send():
    email=request.form.get("email","").lower().strip()
    auth=load_json(AUTH_FILE)
    if email not in auth: return f"Email {email} not found - <a href='/register'>Register again</a> (old data wiped)"
    token=secrets.token_urlsafe(16)
    auth[email]["reset_token"]=token; auth[email]["reset_expiry"]=(datetime.now()+timedelta(hours=1)).isoformat()
    save_json(AUTH_FILE,auth)
    link=f"https://agent-35-trading-bot.onrender.com/reset-password?token={token}&email={email}"
    return f"<html><body style='background:#0f172a;color:white;padding:20px'><h2>Reset Link</h2><p><a href='{link}' style='color:#10b981'>{link}</a></p><a href='{link}' style='background:#10b981;color:white;padding:12px 20px;border-radius:8px;text-decoration:none'>Reset Now</a></body></html>"

@app.route("/reset-password")
def reset_page():
    return f"""<html><body style='background:#0f172a;color:white;padding:30px'><div style='max-width:400px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>Reset for {request.args.get('email')}</h2><form action='/reset-password/save' method='post'><input type='hidden' name='email' value='{request.args.get('email')}'><input type='hidden' name='token' value='{request.args.get('token')}'><input name='new_password' type='password' placeholder='New Password' required style='width:100%;padding:12px'><button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px'>SAVE</button></form></div></body></html>"""

@app.route("/reset-password/save", methods=["POST"])
def reset_save():
    email=request.form.get("email","").lower(); token=request.form.get("token","")
    auth=load_json(AUTH_FILE)
    if auth.get(email,{}).get("reset_token")!=token: return "Invalid token"
    auth[email]["password"]=hash_pwd(request.form.get("new_password",""))
    auth[email]["reset_token"]=None; save_json(AUTH_FILE,auth)
    return "Password changed <a href='/login'>Login</a>"

@app.route("/account/edit", methods=["POST"])
def acc_edit():
    if not session.get("user"): return redirect("/login")
    auth=load_json(AUTH_FILE)
    try: auth[session["user"]]["account_size"]=float(request.form.get("size",142))
    except: pass
    save_json(AUTH_FILE,auth); return redirect("/dashboard")

@app.route("/scan")
def scan(): return jsonify(eng.full_multi_tf_analysis(request.args.get("symbol","EURUSD")))
@app.route("/dashboard-scan")
def dash_scan():
    syms=["EURUSD","GBPUSD","USDJPY","USDCHF","XAUUSD","US30","NAS100","GBPJPY"]
    rows="".join([f"<tr><td>{s}</td><td>{(r:=eng.full_multi_tf_analysis(s))['score']}/10</td><td>{r['bias']}</td><td>{r['signal']}</td></tr>" for s in syms])
    return dark_layout(f"<div class='table-card'><h2>Scan All 8 - 6/10 Fix</h2><table><tr><th>Sym</th><th>Score</th><th>Bias</th><th>Signal</th></tr>{rows}</table><br><a href='/dashboard' style='color:#10b981'>Back Dashboard</a></div>","All Signals")

# 3 CRONS + ADMIN
@app.route("/cron/scan")
def cron_scan():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    res=eng.run_scan_and_send()
    j=load_json(JOURNAL_FILE);
    if not isinstance(j,list): j=[]
    for s in res.get("signals",[]): j.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":s["symbol"],"status":"TOOK","result":f"R0 {s['score']}/10"})
    save_json(JOURNAL_FILE, j[-100:])
    return jsonify(res)

@app.route("/cron/daily-reset")
def cron_reset():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    return jsonify({"cron":"daily-reset"})

@app.route("/cron/check-expiry")
def cron_expiry():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    return jsonify({"cron":"expiry checked"})

@app.route("/run-now")
def run_now():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    return jsonify(eng.run_scan_and_send())

@app.route("/admin/reset-all")
def admin_reset():
    if request.args.get("secret")!="RESET123": return "Need secret RESET123"
    save_json(AUTH_FILE, {}); save_json(USERS_FILE, {}); save_json(JOURNAL_FILE, [])
    return "All wiped - now <a href='/register'>Register new account</a> with your old email"

@app.route("/health")
def health(): return jsonify({"ok":True,"responsive":True,"capitec":CAPITEC["acc"],"users":len(load_json(AUTH_FILE))})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
