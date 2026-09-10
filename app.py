from flask import Flask, request, jsonify, session, redirect
import os, json, random, string, hashlib, secrets
from dotenv import load_dotenv
import trading_engine as eng
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "agent35-secret-key-change-this-12345")

DATA_FILE = "referrals_data.json"
USERS_FILE = "users_data.json"
AUTH_FILE = "auth_users.json" # login system

CAPITEC_DETAILS = {
    "bank": "Capitec",
    "account_holder": "Agent 35 Trading Bot",
    "account_number": "2586572676",
    "branch_code": "470010",
    "reference_prefix": "A35"
}

PLANS = {
    "yearly": {"name": "Yearly Plan", "price": 500, "duration_days": 365},
    "lifetime": {"name": "Lifetime Plan", "price": 5000, "duration_days": 36500}
}

def load_json(path):
    if not os.path.exists(path): return {}
    try:
        with open(path,"r") as f: return json.load(f)
    except: return {}
def save_json(path,data):
    with open(path,"w") as f: json.dump(f,data,indent=2)

def hash_pwd(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

# ========== HOME ==========
@app.route("/")
def home():
    keys=len(eng.API_KEYS)
    auth = load_json(AUTH_FILE)
    user_email = session.get("user")
    user_info = auth.get(user_email) if user_email else None

    login_section = f"<p>Logged in as <b>{user_email}</b> | Plan: {user_info.get('plan_status','No Plan')} | <a href='/logout'>Logout</a></p>" if user_email else "<a class='btn g' href='/login'>LOGIN</a> <a class='btn' href='/register'>REGISTER</a> <a class='btn' href='/forgot-password'>Forgot Password?</a>"

    return f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><style>
    body{{font-family:Arial;background:#fff;padding:20px;max-width:1000px;margin:auto}}
 .h{{background:#0f172a;color:white;padding:20px;border-radius:12px}}.c{{border:1px solid #e5e7eb;padding:20px;border-radius:12px;margin:15px 0}}
 .btn{{background:#3b82f6;color:white;padding:12px 18px;border-radius:8px;text-decoration:none;display:inline-block;margin:4px;font-weight:bold;border:none;cursor:pointer}}
 .g{{background:#10b981}}.d{{background:#1e293b}}.o{{background:#ff6b35}} input{{padding:12px;border-radius:8px;border:2px solid #e2e8f0;width:100%;margin:6px 0}}
    </style></head><body>
    <div class='h'><h1>AGENT 35 V4 - LOGIN SYSTEM</h1><p>Capitec 2586572676 | Keys:{keys}/3 | {datetime.now().strftime('%H:%M SAST')}</p></div>
    <div class='c'>{login_section}</div>
    <div class='c'><a class='btn' href='/dashboard-scan'>SCAN ALL 8</a><a class='btn d' href='/scan?symbol=EURUSD'>EURUSD 6/10</a><a class='btn g' href='/pay'>BUY PLAN R500/R5000</a><a class='btn o' href='/admin?secret='>ADMIN</a><a class='btn' style='background:#8b5cf6' href='/referral'>REFERRAL 10=R5000</a></div>
    {f"<div class='c' style='background:#f0fdf4'><h3>Your Subscription</h3><p>Status: {user_info.get('plan_status')} | Expires: {user_info.get('expires','-')}</p></div>" if user_info else ""}
    </body></html>
    """

# ========== AUTH SYSTEM ==========
@app.route("/register")
def register_page():
    return """
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
    <body style='font-family:Arial;padding:20px;max-width:450px;margin:auto'>
    <h1>Register - Agent 35</h1>
    <div style='border:1px solid #e5e7eb;padding:20px;border-radius:12px'>
    <form action='/register/create' method='post'>
    <input name='email' type='email' placeholder='Email' required>
    <input name='name' placeholder='Full Name' required>
    <input name='phone' placeholder='WhatsApp Number' required>
    <input name='password' type='password' placeholder='Password (min 6)' required>
    <input name='ref' placeholder='Referral Code (optional)'>
    <button type='submit' style='background:#10b981;color:white;padding:14px;width:100%;border:none;border-radius:10px;font-weight:bold;margin-top:10px'>CREATE ACCOUNT</button>
    </form>
    <p><a href='/login'>Already have account? Login</a></p>
    </div></body></html>
    """

@app.route("/register/create", methods=["POST","GET"])
def register_create():
    email = (request.form.get("email") or request.args.get("email","")).lower().strip()
    name = request.form.get("name") or request.args.get("name","")
    phone = request.form.get("phone") or request.args.get("phone","")
    pwd = request.form.get("password") or request.args.get("password","")
    ref = (request.form.get("ref") or request.args.get("ref","")).upper().strip()

    if not email or len(pwd)<6: return jsonify({"error":"email and password min 6 required"})

    auth = load_json(AUTH_FILE)
    if email in auth: return f"<html><body><h1>Email already exists</h1><a href='/login'>Login</a></body></html>"

    auth[email] = {
        "email": email,
        "name": name,
        "phone": phone,
        "password": hash_pwd(pwd),
        "referred_by": ref,
        "plan_status": "No Plan - Pending Payment",
        "expires": None,
        "created": datetime.now().isoformat(),
        "reset_token": None,
        "reset_expiry": None
    }
    save_json(AUTH_FILE, auth)

    # Auto login
    session["user"] = email
    return redirect(f"/pay?ref={ref}&email={email}" if ref else "/pay")

@app.route("/login")
def login_page():
    return """
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
    <body style='font-family:Arial;padding:20px;max-width:450px;margin:auto'>
    <h1>Login - Agent 35</h1>
    <div style='border:1px solid #e5e7eb;padding:20px;border-radius:12px'>
    <form action='/login/check' method='post'>
    <input name='email' type='email' placeholder='Email' required>
    <input name='password' type='password' placeholder='Password' required>
    <button type='submit' style='background:#0f172a;color:white;padding:14px;width:100%;border:none;border-radius:10px;font-weight:bold;margin-top:10px'>LOGIN</button>
    </form>
    <p><a href='/register'>No account? Register</a> | <a href='/forgot-password'>Forgot Password?</a></p>
    </div></body></html>
    """

@app.route("/login/check", methods=["POST","GET"])
def login_check():
    email = (request.form.get("email") or request.args.get("email","")).lower().strip()
    pwd = request.form.get("password") or request.args.get("password","")
    auth = load_json(AUTH_FILE)
    if email not in auth or auth[email]["password"]!= hash_pwd(pwd):
        return f"<html><body><h1>❌ Wrong email or password</h1><a href='/login'>Try Again</a> | <a href='/forgot-password'>Forgot?</a></body></html>"
    session["user"] = email
    return redirect("/")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")

# ========== FORGOT PASSWORD ==========
@app.route("/forgot-password")
def forgot_page():
    return """
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
    <body style='font-family:Arial;padding:20px;max-width:450px;margin:auto'>
    <h1>Forgot Password</h1>
    <div style='border:1px solid #e5e7eb;padding:20px;border-radius:12px'>
    <p>Enter your email, we will generate a reset link (valid 1 hour)</p>
    <form action='/forgot-password/send' method='post'>
    <input name='email' type='email' placeholder='Your email' required>
    <button type='submit' style='background:#ff6b35;color:white;padding:14px;width:100%;border:none;border-radius:10px;font-weight:bold;margin-top:10px'>SEND RESET LINK</button>
    </form>
    <p><a href='/login'>Back to Login</a></p>
    </div></body></html>
    """

@app.route("/forgot-password/send", methods=["POST","GET"])
def forgot_send():
    email = (request.form.get("email") or request.args.get("email","")).lower().strip()
    auth = load_json(AUTH_FILE)
    if email not in auth:
        return f"<html><body><h1>Email not found</h1><p>{email} not registered</p><a href='/register'>Register</a></body></html>"

    token = secrets.token_urlsafe(32)
    auth[email]["reset_token"] = token
    auth[email]["reset_expiry"] = (datetime.now()+timedelta(hours=1)).isoformat()
    save_json(AUTH_FILE, auth)

    reset_link = f"https://agent-35-trading-bot.onrender.com/reset-password?token={token}&email={email}"

    return f"""
    <html><body style='font-family:Arial;padding:20px;max-width:600px;margin:auto;text-align:center'>
    <h1 style='color:#10b981'>Reset Link Generated (1 hour valid)</h1>
    <div style='background:#fff3cd;border:2px solid #ff6b35;padding:20px;border-radius:12px'>
    <p>Since we don't have email server yet, copy this link:</p>
    <p style='background:white;padding:15px;border-radius:8px;word-break:break-all'><a href='{reset_link}'>{reset_link}</a></p>
    <p><b>For production:</b> This would be sent to {email} via email/WhatsApp automatically.</p>
    <a href='{reset_link}' style='background:#ff6b35;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;display:inline-block;margin-top:15px'>RESET MY PASSWORD NOW</a>
    </div>
    <br><a href='/login'>Back to Login</a>
    </body></html>
    """

@app.route("/reset-password")
def reset_page():
    token = request.args.get("token","")
    email = request.args.get("email","").lower().strip()
    auth = load_json(AUTH_FILE)
    if email not in auth or auth[email].get("reset_token")!= token:
        return "<html><body><h1>Invalid or expired link</h1><a href='/forgot-password'>Request new link</a></body></html>"
    expiry = datetime.fromisoformat(auth[email].get("reset_expiry","2000-01-01"))
    if datetime.now() > expiry:
        return "<html><body><h1>Link expired (1 hour)</h1><a href='/forgot-password'>Request new</a></body></html>"

    return f"""
    <html><body style='font-family:Arial;padding:20px;max-width:450px;margin:auto'>
    <h1>Reset Password for {email}</h1>
    <div style='border:1px solid #e5e7eb;padding:20px;border-radius:12px'>
    <form action='/reset-password/save' method='post'>
    <input type='hidden' name='email' value='{email}'>
    <input type='hidden' name='token' value='{token}'>
    <input name='new_password' type='password' placeholder='New Password (min 6)' required>
    <input name='confirm' type='password' placeholder='Confirm New Password' required>
    <button type='submit' style='background:#10b981;color:white;padding:14px;width:100%;border:none;border-radius:10px;font-weight:bold;margin-top:10px'>SAVE NEW PASSWORD</button>
    </form>
    </div></body></html>
    """

@app.route("/reset-password/save", methods=["POST"])
def reset_save():
    email = request.form.get("email","").lower().strip()
    token = request.form.get("token","")
    new_pwd = request.form.get("new_password","")
    confirm = request.form.get("confirm","")

    if new_pwd!= confirm or len(new_pwd)<6:
        return "<html><body><h1>Passwords don't match or too short</h1><a href='/forgot-password'>Try again</a></body></html>"

    auth = load_json(AUTH_FILE)
    if email not in auth or auth[email].get("reset_token")!= token:
        return "<html><body><h1>Invalid token</h1></body></html>"

    auth[email]["password"] = hash_pwd(new_pwd)
    auth[email]["reset_token"] = None
    auth[email]["reset_expiry"] = None
    save_json(AUTH_FILE, auth)

    return f"<html><body style='font-family:Arial;padding:30px;text-align:center'><h1 style='color:#10b981'>✅ Password Reset Success</h1><p>Password for {email} changed</p><a href='/login' style='background:#0f172a;color:white;padding:12px 20px;border-radius:8px;text-decoration:none'>Login Now</a></body></html>"

# ========== TRADING + PAY + ADMIN (same as V3) ==========
@app.route("/health")
def health(): return jsonify({"ok":True,"keys":len(eng.API_KEYS),"users":len(load_json(AUTH_FILE))})

@app.route("/scan")
def scan(): return jsonify(eng.full_multi_tf_analysis(request.args.get("symbol","EURUSD")))

@app.route("/dashboard-scan")
def dash_scan():
    syms=["EURUSD","GBPUSD","USDJPY","XAUUSD","US30","NAS100","GBPJPY","EURJPY"]
    rows="".join([f"<tr><td>{s}</td><td>{r['score']}/10</td><td>{r['bias']}</td><td>{r['signal']}</td></tr>" for s in syms for r in [eng.full_multi_tf_analysis(s)]])
    return f"<html><body style='font-family:Arial;padding:20px'><table border=1 cellpadding=10><tr><th>Sym</th><th>Score</th><th>Bias</th><th>Signal</th></tr>{rows}</table><br><a href='/'>Back</a></body></html>"

@app.route("/pay")
def pay_page():
    ref_code=request.args.get("ref","") or session.get("ref","")
    email=request.args.get("email","") or session.get("user","")
    return f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
    <body style='font-family:Arial;padding:20px;max-width:600px;margin:auto'>
    <h1>Buy Plan - Capitec 2586572676</h1>
    <div style='border:2px solid #0f172a;padding:20px;border-radius:12px'>
    <form action='/pay/create' method='get'>
    <input type='hidden' name='ref' value='{ref_code}'>
    <label>Email (login): <input name='user' value='{email}' required style='padding:12px;width:100%;margin:8px 0;border:2px solid #e5e7eb;border-radius:8px'></label>
    <label>WhatsApp: <input name='phone' required style='padding:12px;width:100%;margin:8px 0;border:2px solid #e5e7eb;border-radius:8px'></label>
    <select name='plan' style='padding:12px;width:100%;margin:8px 0'><option value='yearly'>Yearly R500</option><option value='lifetime'>Lifetime R5000</option></select>
    <button type='submit' style='background:#10b981;color:white;padding:14px;width:100%;border:none;border-radius:10px;font-weight:bold'>GET PAYMENT REF</button>
    </form>
    </div></body></html>"""

@app.route("/pay/create")
def pay_create():
    user=(request.args.get("user") or "").strip().lower()
    phone=request.args.get("phone","").strip()
    plan_key=request.args.get("plan","yearly")
    ref=request.args.get("ref","").upper().strip()
    short = "".join([c for c in user.upper() if c.isalnum()])[:5] or "USER"
    rand = "".join(random.choices(string.digits, k=3))
    pref = f"{CAPITEC_DETAILS['reference_prefix']}-{short}-{rand}"
    plan = PLANS.get(plan_key, PLANS["yearly"])
    users = load_json(USERS_FILE)
    users[pref] = {"user":user,"phone":phone,"plan":plan_key,"price":plan["price"],"payment_ref":pref,"referred_by":ref,"status":"pending","created":datetime.now().isoformat()}
    save_json(USERS_FILE, users)
    return f"<html><body style='font-family:Arial;padding:20px;max-width:600px;margin:auto;text-align:center'><h1>Pay R{plan['price']}</h1><div style='border:2px dashed #0f172a;padding:20px;border-radius:12px'><p><b>Bank:</b> Capitec<br><b>Name:</b> Agent 35 Trading Bot<br><b>Acc:</b> 2586572676<br><b>Branch:</b> 470010</p><h1 style='background:#0f172a;color:white;padding:15px;border-radius:10px'>{pref}</h1><p>Use this reference in Capitec App</p></div></body></html>"

@app.route("/admin")
def admin():
    secret = request.args.get("secret","")
    real = os.getenv("CRON_SECRET","")
    if real and secret!=real:
        return f"<html><body style='font-family:Arial;padding:30px'><h1>Admin Login</h1><form><input name='secret' placeholder='CRON_SECRET'><button>Login</button></form></body></html>"
    users = load_json(USERS_FILE)
    auth = load_json(AUTH_FILE)
    rows=""
    for pref, u in users.items():
        accept = f"<a href='/admin/accept?ref={pref}&secret={secret}' style='background:#10b981;color:white;padding:8px 12px;border-radius:6px;text-decoration:none'>ACCEPT</a>" if u["status"]=="pending" else ""
        rows+=f"<tr><td>{pref}</td><td>{u['user']}</td><td>{u['plan']} R{u['price']}</td><td>{u.get('referred_by') or '-'}</td><td>{u['status']}</td><td>{accept}</td></tr>"
    auth_rows="".join([f"<tr><td>{e}</td><td>{info.get('name')}</td><td>{info.get('plan_status')}</td><td>{info.get('referred_by') or '-'}</td></tr>" for e,info in auth.items()])
    return f"<html><body style='font-family:Arial;padding:20px'><h1>Admin - Capitec 2586572676</h1><h3>Pending Payments</h3><table border=1 cellpadding=10><tr><th>Ref</th><th>User</th><th>Plan</th><th>Referred By</th><th>Status</th><th>Action</th></tr>{rows}</table><h3>All Login Users ({len(auth)})</h3><table border=1 cellpadding=10><tr><th>Email</th><th>Name</th><th>Plan Status</th><th>Referred By</th></tr>{auth_rows}</table></body></html>"

@app.route("/admin/accept")
def admin_accept():
    pref=request.args.get("ref","")
    secret=request.args.get("secret","")
    users=load_json(USERS_FILE)
    auth=load_json(AUTH_FILE)
    refs=load_json(DATA_FILE)
    if pref not in users: return jsonify({"error":"not found"})
    u=users[pref]
    u["status"]="active"
    plan=PLANS.get(u["plan"], PLANS["yearly"])
    u["expires"]=(datetime.now()+timedelta(days=plan["duration_days"])).isoformat()
    users[pref]=u
    save_json(USERS_FILE,users)
    # Update auth user plan
    if u["user"] in auth:
        auth[u["user"]]["plan_status"]=f"ACTIVE {u['plan']} - Expires {u['expires'][:10]}"
        auth[u["user"]]["expires"]=u["expires"]
        save_json(AUTH_FILE,auth)
    # Referral count
    ref_code = u.get("referred_by")
    if ref_code:
        if ref_code not in refs: refs[ref_code]={"owner":ref_code,"count":0,"paid_refs":[]}
        if u["user"] not in refs[ref_code].get("paid_refs",[]):
            refs[ref_code]["paid_refs"].append(u["user"])
            refs[ref_code]["count"]=len(refs[ref_code]["paid_refs"])
            save_json(DATA_FILE,refs)
    return jsonify({"ok":True,"activated":pref,"admin":f"/admin?secret={secret}"})

@app.route("/referral")
def referral():
    data=load_json(DATA_FILE)
    rows="".join([f"<tr><td>{c}</td><td>{i.get('count',0)}/10</td><td>{'✅ R5000 LIFETIME' if i.get('count',0)>=10 else '⏳'}</td></tr>" for c,i in data.items()])
    return f"<html><body style='font-family:Arial;padding:20px'><h1>Referral 10=R5000</h1><table border=1 cellpadding=10><tr><th>Code</th><th>Count</th><th>Reward</th></tr>{rows}</table><a href='/'>Home</a></body></html>"

@app.route("/run-now")
def run_now():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    return jsonify(eng.run_scan_and_send())

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
