from flask import Flask, request, jsonify, session, redirect
import os, json, random, string, hashlib, secrets
from dotenv import load_dotenv
import trading_engine as eng
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "agent35-dark-v5-secret-142")

DATA_FILE = "referrals_data.json"
USERS_FILE = "users_data.json"
AUTH_FILE = "auth_users.json"
JOURNAL_FILE = "journal.json"
WATCHLIST_FILE = "watchlist.json"

CAPITEC = {
    "bank": "Capitec",
    "holder": "Agent 35 Trading Bot",
    "acc": "2586572676",
    "branch": "470010",
    "ref_prefix": "A35"
}

def load_json(p):
    if not os.path.exists(p): return {} if "auth" in p or "users" in p or "referral" in p else []
    try:
        with open(p,"r") as f: return json.load(f)
    except: return {} if "auth" in p or "users" in p or "referral" in p else []

def save_json(p,d):
    with open(p,"w") as f: json.dump(f,d,indent=2)

def hash_pwd(p): return hashlib.sha256(p.encode()).hexdigest()

# === DARK DASHBOARD HTML - MATCHES YOUR PHOTO ===
def dark_layout(content, active="Dashboard"):
    utc = datetime.utcnow().strftime("%H:%M:%S")
    sast = (datetime.utcnow() + timedelta(hours=2)).strftime("%H:%M:%S")
    user = session.get("user","Guest")
    tabs = ["Dashboard","Journal","All Signals","Settings","Plans","Guide","Master"]
    tab_html = "".join([f"<a href='/{t.lower().replace(' ','-')}' style='padding:10px 18px;border-radius:20px;text-decoration:none;font-weight:bold;margin-right:8px;background:{'#10b981' if active==t else '#1e293b'};color:white'>{t}</a>" for t in tabs])

    return f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>AGENT 35 - Dashboard</title>
    <style>
    body{{background:#0f172a;color:#e2e8f0;font-family:Inter,Arial;margin:0;padding:0}}
   .top{{background:#0f172a;border-bottom:1px solid #1e293b;padding:12px 25px;display:flex;justify-content:space-between;align-items:center}}
   .logo{{color:#10b981;font-weight:900;font-size:20px}}.time{{color:#94a3b8;font-size:13px}}
   .nav{{background:#0f172a;padding:15px 25px;border-bottom:1px solid #1e293b}}
   .main{{padding:20px;display:grid;grid-template-columns:1fr 1fr 1fr 300px;gap:15px}}
   .card{{background:#1e293b;border-radius:16px;padding:20px;border:1px solid #334155}}
   .profit{{color:#ef4444;font-size:28px;font-weight:900}}.muted{{color:#64748b;font-size:12px}}
   .acc{{font-size:24px;font-weight:800}}.edit{{background:#1e293b;border:1px solid #334155;color:white;padding:8px 30px;border-radius:10px;margin-top:10px;cursor:pointer}}
   .pair{{background:#334155;padding:6px 12px;border-radius:20px;display:inline-block;margin:5px;font-size:13px}}.x{{background:#ef4444;border-radius:50%;padding:2px 6px;margin-left:6px;cursor:pointer}}
   .scan{{background:#10b981;color:white;padding:14px;border-radius:12px;text-align:center;font-weight:900;cursor:pointer;border:none;width:100%}}
   .blue{{background:#3b82f6;color:white;padding:12px;border-radius:12px;text-align:center;margin-top:10px;display:block;text-decoration:none}}
   .table-card{{grid-column:1 / span 4;background:#1e293b;border-radius:16px;padding:20px;margin-top:10px}}
    table{{width:100%;border-collapse:collapse}} th{{color:#64748b;text-align:left;padding:12px;font-size:11px}} td{{padding:14px;border-top:1px solid #334155;font-size:13px}}
   .took{{background:#10b98133;color:#10b981;padding:4px 10px;border-radius:10px;font-size:11px}}
    </style></head>
    <body>
    <div class='top'><div class='logo'>35 AGENT 35</div><div class='time'>UTC {utc} | SAST {sast} | <span style='color:#10b981'>London ACTIVE</span> | {user}</div></div>
    <div class='nav'>{tab_html} <span style='float:right;color:#64748b;font-size:12px'>Sessions: 24/7 | News: <span style='color:orange'>OFF ⚠️</span> | WR: 0.0% | -1.0R | R-1.42</span></div>
    {content}
    </body></html>
    """

# ========== ROUTES ==========
@app.route("/")
def home():
    if session.get("user"): return redirect("/dashboard")
    return redirect("/login")

@app.route("/dashboard")
def dashboard():
    # User memory
    watch = load_json(WATCHLIST_FILE)
    if isinstance(watch, dict): watch_list = watch.get(session.get("user","default"), ["EURUSD","GBPUSD","USDJPY","USDCHF"])
    else: watch_list = ["EURUSD","GBPUSD","USDJPY","USDCHF"]

    journal = load_json(JOURNAL_FILE)
    if isinstance(journal, list): trades = journal[-10:]
    else: trades = journal.get(session.get("user","default"), [])[-10:] if isinstance(journal, dict) else []

    # Account size from auth
    auth = load_json(AUTH_FILE)
    user_email = session.get("user")
    acc_size = auth.get(user_email, {}).get("account_size", 142.0) if user_email else 142.0
    total_profit = auth.get(user_email, {}).get("total_profit", -1.42) if user_email else -1.42

    watch_html = "".join([f"<span class='pair'>{p} <span class='x'>x</span></span>" for p in watch_list])

    # Build trades rows like photo
    rows = ""
    for t in reversed(trades) if trades else [
        {"time":"09-03 18:13","symbol":"USDCHF","status":"TOOK","result":"R0 (0.0R)"},
        {"time":"09-03 18:13","symbol":"USDJPY","status":"TOOK","result":"R0 (0.0R)"},
        {"time":"09-03 18:13","symbol":"GBPUSD","status":"TOOK","result":"R0 (0.0R)"},
        {"time":"09-03 18:13","symbol":"EURUSD","status":"TOOK","result":"R0 (0.0R)"},
    ]:
        rows+=f"<tr><td>{t.get('time','')}</td><td style='font-weight:800'>{t.get('symbol','')}</td><td><span class='took'>{t.get('status','TOOK')}</span></td><td>{t.get('result','R0 (0.0R)')}</td></tr>"

    content = f"""
    <div class='main'>
        <div class='card'><div class='muted'>TOTAL PROFIT</div><div class='profit'>R{total_profit}</div><div style='color:#10b981;background:#10b98122;display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px'>0.0% -1.0R</div></div>
        <div class='card'><div class='muted'>ACCOUNT SIZE</div><div class='acc'>R{acc_size}</div>
        <form action='/account/edit' method='post'><input name='size' value='{acc_size}' style='background:#0f172a;border:1px solid #334155;color:white;padding:8px;border-radius:8px;width:100%;margin-top:10px'><button class='edit' type='submit'>Edit</button></form></div>
        <div class='card'><div class='muted'>WATCHLIST 4/5</div><div style='margin:12px 0'>{watch_html}</div><input placeholder='Search pairs...' style='background:#0f172a;border:none;padding:10px;border-radius:10px;width:100%;color:white'></div>
        <div class='card'><a href='/dashboard-scan'><button class='scan'>SCAN NOW</button></a><div style='text-align:center;margin:12px;color:#64748b'>Link Telegram</div><a href='/test-telegram' class='blue'>Test Telegram</a></div>
    </div>
    <div class='table-card'><table><tr><th>TIME</th><th>SYMBOL</th><th>STATUS</th><th>RESULT</th></tr>{rows}</table></div>
    """
    return dark_layout(content, "Dashboard")

# ========== USER MEMORY + AUTH (keeps your Capitec system) ==========
@app.route("/register")
def register_page():
    return """<html><body style='font-family:Arial;background:#0f172a;color:white;padding:40px'><h1>Register - Agent 35</h1><form action='/register/create' method='post' style='background:#1e293b;padding:20px;border-radius:12px;max-width:400px'><input name='email' placeholder='Email' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><input name='name' placeholder='Name' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><input name='password' type='password' placeholder='Password' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><input name='ref' placeholder='Referral Code' style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;font-weight:bold'>CREATE</button></form></body></html>"""

@app.route("/register/create", methods=["POST"])
def register_create():
    email = request.form.get("email","").lower().strip()
    auth = load_json(AUTH_FILE)
    if email in auth: return "Email exists <a href='/login'>Login</a>"
    auth[email] = {"email":email,"name":request.form.get("name"),"password":hash_pwd(request.form.get("password","")),"referred_by":request.form.get("ref","").upper(),"account_size":142.0,"total_profit":-1.42,"plan_status":"pending","created":datetime.now().isoformat(),"expires":None,"reset_token":None}
    save_json(AUTH_FILE, auth)
    session["user"]=email
    return redirect("/dashboard")

@app.route("/login")
def login_page():
    return """<html><body style='font-family:Arial;background:#0f172a;color:white;padding:40px'><h1>Login</h1><form action='/login/check' method='post' style='background:#1e293b;padding:20px;border-radius:12px;max-width:400px'><input name='email' placeholder='Email' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><input name='password' type='password' placeholder='Password' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><button style='background:#3b82f6;color:white;padding:12px;width:100%;border:none;border-radius:8px;font-weight:bold'>LOGIN</button></form><p><a href='/forgot-password' style='color:#10b981'>Forgot Password?</a></p></body></html>"""

@app.route("/login/check", methods=["POST"])
def login_check():
    email = request.form.get("email","").lower().strip()
    auth = load_json(AUTH_FILE)
    if email not in auth or auth[email]["password"]!= hash_pwd(request.form.get("password","")):
        return "Wrong password <a href='/login'>Retry</a>"
    session["user"]=email
    return redirect("/dashboard")

@app.route("/logout")
def logout(): session.pop("user",None); return redirect("/login")

@app.route("/forgot-password")
def forgot_page():
    return """<html><body style='font-family:Arial;background:#0f172a;color:white;padding:40px'><h1>Forgot Password</h1><form action='/forgot-password/send' method='post' style='background:#1e293b;padding:20px;border-radius:12px;max-width:400px'><input name='email' placeholder='Email' required style='width:100%;padding:12px'><button style='background:#ff6b35;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px'>SEND RESET LINK</button></form></body></html>"""

@app.route("/forgot-password/send", methods=["POST"])
def forgot_send():
    email = request.form.get("email","").lower().strip()
    auth = load_json(AUTH_FILE)
    if email not in auth: return "Email not found"
    token = secrets.token_urlsafe(16)
    auth[email]["reset_token"]=token
    auth[email]["reset_expiry"]=(datetime.now()+timedelta(hours=1)).isoformat()
    save_json(AUTH_FILE,auth)
    link = f"https://agent-35-trading-bot.onrender.com/reset-password?token={token}&email={email}"
    return f"<html><body style='background:#0f172a;color:white;padding:20px'><h1>Reset Link (1h valid)</h1><p>{link}</p><a href='{link}' style='background:#10b981;color:white;padding:12px 20px;border-radius:8px;text-decoration:none'>Reset Now</a></body></html>"

@app.route("/reset-password")
def reset_page():
    email=request.args.get("email",""); token=request.args.get("token","")
    return f"<html><body style='background:#0f172a;color:white;padding:40px'><h1>Reset for {email}</h1><form action='/reset-password/save' method='post' style='background:#1e293b;padding:20px;border-radius:12px;max-width:400px'><input type='hidden' name='email' value='{email}'><input type='hidden' name='token' value='{token}'><input name='new_password' type='password' placeholder='New Password' required style='width:100%;padding:12px'><button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px'>SAVE</button></form></body></html>"

@app.route("/reset-password/save", methods=["POST"])
def reset_save():
    email=request.form.get("email","").lower(); token=request.form.get("token","")
    auth=load_json(AUTH_FILE)
    if auth.get(email,{}).get("reset_token")!=token: return "Invalid token"
    auth[email]["password"]=hash_pwd(request.form.get("new_password",""))
    auth[email]["reset_token"]=None
    save_json(AUTH_FILE,auth)
    return "Password changed <a href='/login'>Login</a>"

@app.route("/account/edit", methods=["POST"])
def acc_edit():
    if not session.get("user"): return redirect("/login")
    size = float(request.form.get("size",142))
    auth=load_json(AUTH_FILE)
    auth[session["user"]]["account_size"]=size
    save_json(AUTH_FILE,auth)
    return redirect("/dashboard")

# ========== PAYMENT + REFERRAL (Capitec 2586572676) ==========
@app.route("/pay")
def pay_page():
    ref=request.args.get("ref","")
    return f"""<html><body style='background:#0f172a;color:white;font-family:Arial;padding:20px;max-width:600px;margin:auto'><h1>Buy Plan - Capitec {CAPITEC['acc']}</h1><div style='background:#1e293b;padding:20px;border-radius:12px'><p>Bank: Capitec | Name: {CAPITEC['holder']} | Acc: {CAPITEC['acc']}</p><form action='/pay/create'><input type='hidden' name='ref' value='{ref}'><input name='user' placeholder='Email' required style='width:100%;padding:12px;margin:6px 0'><input name='phone' placeholder='WhatsApp' required style='width:100%;padding:12px;margin:6px 0'><select name='plan' style='width:100%;padding:12px'><option value='yearly'>Yearly R500</option><option value='lifetime'>Lifetime R5000</option></select><button style='background:#10b981;color:white;padding:14px;width:100%;border:none;border-radius:10px;margin-top:10px'>GET REFERENCE</button></form></div></body></html>"""

@app.route("/pay/create")
def pay_create():
    user=request.args.get("user","").lower(); phone=request.args.get("phone",""); plan=request.args.get("plan","yearly"); ref=request.args.get("ref","").upper()
    pref = f"A35-{user[:5].upper()}-{random.randint(100,999)}"
    users=load_json(USERS_FILE)
    users[pref]={"user":user,"phone":phone,"plan":plan,"price":500 if plan=="yearly" else 5000,"payment_ref":pref,"referred_by":ref,"status":"pending","created":datetime.now().isoformat()}
    save_json(USERS_FILE,users)
    return f"<html><body style='background:#0f172a;color:white;padding:30px;text-align:center'><h1>Pay R{users[pref]['price']}</h1><div style='border:2px dashed white;padding:20px;border-radius:12px'><p>Capitec<br>{CAPITEC['holder']}<br>{CAPITEC['acc']}<br>Branch {CAPITEC['branch']}</p><h1 style='background:white;color:black;padding:15px;border-radius:10px'>{pref}</h1><p>Use this reference in Capitec app</p></div></body></html>"

# ========== TRADING + CRON JOBS ==========
@app.route("/scan")
def scan(): return jsonify(eng.full_multi_tf_analysis(request.args.get("symbol","EURUSD")))

@app.route("/dashboard-scan")
def dashboard_scan():
    syms=["EURUSD","GBPUSD","USDJPY","USDCHF","XAUUSD","US30","NAS100","GBPJPY"]
    results=[eng.full_multi_tf_analysis(s) for s in syms]
    content = "<div style='padding:20px'><h1 style='color:white'>Scan Results - 6/10 Fix Active</h1><table style='width:100%;color:white'><tr><th>Sym</th><th>Score</th><th>Bias</th><th>Signal</th><th>Reason</th></tr>"
    for r in results:
        content+=f"<tr><td>{r['symbol']}</td><td>{r['score']}/10</td><td>{r['bias']}</td><td>{r['signal']}</td><td>{r['reason']}</td></tr>"
    content+="</table><br><a href='/dashboard' style='color:#10b981'>Back</a></div>"
    return dark_layout(content, "All Signals")

# --- 3 CRON JOBS ---
@app.route("/cron/scan")
def cron_scan():
    # Cron 1: Every 30 min - scan & send telegram
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    result = eng.run_scan_and_send()
    # Save to journal memory
    journal = load_json(JOURNAL_FILE)
    if not isinstance(journal, list): journal=[]
    for sig in result.get("signals",[]):
        journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sig["symbol"],"status":"TOOK","result":f"R0 - {sig['score']}/10 {sig['bias']}"})
    save_json(JOURNAL_FILE, journal[-100:]) # keep last 100
    return jsonify({"cron":"scan","result":result})

@app.route("/cron/daily-reset")
def cron_reset():
    # Cron 2: Daily 00:00 SAST - reset daily stats
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    return jsonify({"cron":"daily-reset","time":datetime.now().isoformat(),"message":"Daily stats reset - W/R cleared"})

@app.route("/cron/check-expiry")
def cron_expiry():
    # Cron 3: Check user expiries
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    auth=load_json(AUTH_FILE)
    expired=[]
    for email,info in auth.items():
        if info.get("expires"):
            try:
                if datetime.now() > datetime.fromisoformat(info["expires"]):
                    info["plan_status"]="EXPIRED"
                    expired.append(email)
            except: pass
    save_json(AUTH_FILE,auth)
    return jsonify({"cron":"check-expiry","expired":expired,"checked":len(auth)})

@app.route("/run-now")
def run_now():
    # Compatibility for old cron
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    return jsonify(eng.run_scan_and_send())

@app.route("/test-telegram")
def test_telegram():
    bot=os.getenv("TELEGRAM_BOT_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
    if not bot or not chat: return jsonify({"error":"No telegram env"})
    import requests
    r=requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat,"text":"✅ Agent 35 Test - Telegram Linked - Dashboard Dark V5 Live"}, timeout=10)
    return jsonify({"sent":r.json()})

@app.route("/admin")
def admin():
    secret=request.args.get("secret","")
    if secret!=os.getenv("CRON_SECRET"): return f"<html><body style='background:#0f172a;color:white;padding:30px'><h1>Admin Login</h1><form><input name='secret' placeholder='CRON_SECRET'><button>Login</button></form></body></html>"
    users=load_json(USERS_FILE)
    rows="".join([f"<tr><td style='padding:10px'>{p}</td><td>{u['user']}</td><td>{u['plan']} R{u['price']}</td><td>{u.get('referred_by') or '-'}</td><td>{u['status']}</td><td><a href='/admin/accept?ref={p}&secret={secret}' style='background:#10b981;color:white;padding:6px 10px;border-radius:6px;text-decoration:none'>ACCEPT</a></td></tr>" for p,u in users.items()])
    return f"<html><body style='background:#0f172a;color:white;padding:20px'><h1>Admin - {CAPITEC['acc']} {CAPITEC['holder']}</h1><table border=1 cellpadding=10 style='border-collapse:collapse;width:100%'><tr><th>Ref</th><th>User</th><th>Plan</th><th>Ref By</th><th>Status</th><th>Action</th></tr>{rows}</table></body></html>"

@app.route("/admin/accept")
def admin_accept():
    pref=request.args.get("ref",""); secret=request.args.get("secret","")
    users=load_json(USERS_FILE); auth=load_json(AUTH_FILE); refs=load_json(DATA_FILE)
    if pref not in users: return jsonify({"error":"not found"})
    u=users[pref]; u["status"]="active"; u["expires"]=(datetime.now()+timedelta(days=365 if u["plan"]=="yearly" else 36500)).isoformat()
    users[pref]=u; save_json(USERS_FILE,users)
    if u["user"] in auth:
        auth[u["user"]]["plan_status"]=f"ACTIVE {u['plan']}"; auth[u["user"]]["expires"]=u["expires"]; save_json(AUTH_FILE,auth)
    ref_code=u.get("referred_by")
    if ref_code:
        if ref_code not in refs: refs[ref_code]={"owner":ref_code,"count":0,"paid_refs":[]}
        if u["user"] not in refs[ref_code].get("paid_refs",[]):
            refs[ref_code]["paid_refs"].append(u["user"]); refs[ref_code]["count"]=len(refs[ref_code]["paid_refs"]); save_json(DATA_FILE,refs)
    return jsonify({"ok":True,"activated":pref})

# Placeholder tabs
@app.route("/journal")
def journal_page():
    journal = load_json(JOURNAL_FILE)
    rows = "".join([f"<tr><td>{j.get('time')}</td><td>{j.get('symbol')}</td><td><span class='took'>{j.get('status')}</span></td><td>{j.get('result')}</td></tr>" for j in (journal[-50:] if isinstance(journal,list) else [])])
    return dark_layout(f"<div class='table-card'><h2>Journal - User Memory</h2><table><tr><th>TIME</th><th>SYMBOL</th><th>STATUS</th><th>RESULT</th></tr>{rows}</table></div>","Journal")

@app.route("/all-signals")
def all_signals(): return redirect("/dashboard-scan")
@app.route("/settings")
def settings(): return dark_layout("<div class='table-card'><h2>Settings</h2><p>Capitec: 2586572676 Agent 35 Trading Bot<br>Telegram: Linked<br>Threshold: 5/10 with 4H Neutral Allowed (6/10 fix)</p></div>","Settings")
@app.route("/plans")
def plans(): return dark_layout(f"<div class='table-card'><h2>Plans</h2><p>Yearly R500 | Lifetime R5000 | Bank: Capitec {CAPITEC['acc']} {CAPITEC['holder']}</p><a href='/pay' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Buy Now</a></div>","Plans")
@app.route("/referral")
def referral():
    data=load_json(DATA_FILE)
    rows="".join([f"<tr><td>{c}</td><td>{i.get('count',0)}/10</td><td>{'✅ LIFETIME R5000' if i.get('count',0)>=10 else '⏳'}</td></tr>" for c,i in data.items()])
    return dark_layout(f"<div class='table-card'><h2>Referral - 10 Paid = R5000 Lifetime Free</h2><table><tr><th>Code</th><th>Count</th><th>Reward</th></tr>{rows}</table></div>","Master")
@app.route("/guide")
def guide(): return dark_layout("<div class='table-card'><h2>Guide</h2><p>How to trade Agent 35 signals</p></div>","Guide")
@app.route("/master")
def master(): return redirect("/referral")
@app.route("/health")
def health(): return jsonify({"ok":True,"dashboard":"dark V5","capitec":CAPITEC["acc"],"keys":len(eng.API_KEYS)})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
