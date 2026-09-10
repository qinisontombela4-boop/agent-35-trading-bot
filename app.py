from flask import Flask, request, jsonify
import os, json, random, string
from dotenv import load_dotenv
import trading_engine as eng
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)

DATA_FILE = "referrals_data.json"
USERS_FILE = "users_data.json"

# ==== CAPITEC DETAILS - YOURS ====
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

@app.route("/")
def home():
    keys=len(eng.API_KEYS)
    users=load_json(USERS_FILE)
    refs=load_json(DATA_FILE)
    pending=len([u for u in users.values() if u.get("status")=="pending"])
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><style>
    body{{font-family:Arial;background:#fff;padding:20px;max-width:1000px;margin:auto}}
  .h{{background:#0f172a;color:white;padding:20px;border-radius:12px}}.c{{border:1px solid #e5e7eb;padding:20px;border-radius:12px;margin:15px 0}}
  .btn{{background:#3b82f6;color:white;padding:12px 18px;border-radius:8px;text-decoration:none;display:inline-block;margin:4px;font-weight:bold;border:none}}
  .g{{background:#10b981}}.d{{background:#1e293b}}.o{{background:#ff6b35}}
    </style></head><body>
    <div class='h'><h1>AGENT 35 V3 - BASE LIVE</h1><p>Capitec 2586572676 | Keys:{keys}/3 | Pending: {pending} | {datetime.now().strftime('%H:%M SAST')}</p></div>
    <div class='c'>
    <a class='btn' href='/dashboard-scan'>SCAN ALL 8</a>
    <a class='btn d' href='/scan?symbol=EURUSD'>EURUSD 6/10</a>
    <a class='btn g' href='/pay'>BUY PLAN</a>
    <a class='btn o' href='/admin?secret='>ADMIN</a>
    <a class='btn' style='background:#8b5cf6' href='/referral'>REFERRAL 10=R5000 FREE</a>
    </div>
    <div class='c' style='background:#f0fdf4;border:2px solid #10b981'><h3>✅ Capitec System Active</h3><p>Account: <b>Agent 35 Trading Bot - 2586572676</b></p><p>Yearly R500 | Lifetime R5000 | Referral: 10 Paid = Lifetime Free</p></div>
    </body></html>
    """
    return html

@app.route("/health")
def health(): return jsonify({"ok":True,"keys":len(eng.API_KEYS),"capitec":"2586572676 Agent 35 Trading Bot"})

@app.route("/scan")
def scan(): return jsonify(eng.full_multi_tf_analysis(request.args.get("symbol","EURUSD")))

@app.route("/dashboard-scan")
def dash_scan():
    syms=["EURUSD","GBPUSD","USDJPY","XAUUSD","US30","NAS100","GBPJPY","EURJPY"]
    rows=""
    for s in syms:
        r=eng.full_multi_tf_analysis(s)
        rows+=f"<tr><td>{s}</td><td>{r['score']}/10</td><td>{r['bias']}</td><td>{r['signal']}</td><td>{r['reason']}</td></tr>"
    return f"<html><body style='font-family:Arial;padding:20px'><h1>Scan All 8 - 6/10 Fix Active</h1><table border=1 cellpadding=10><tr><th>Sym</th><th>Score</th><th>Bias</th><th>Signal</th><th>Reason</th></tr>{rows}</table><br><a href='/'>Back</a></body></html>"

@app.route("/pay")
def pay_page():
    ref_code=request.args.get("ref","")
    return f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>
    <body style='font-family:Arial;padding:20px;max-width:600px;margin:auto'>
    <h1>Buy Agent 35 Plan</h1>
    <div style='border:2px solid #0f172a;padding:20px;border-radius:12px'>
    <form action='/pay/create' method='get'>
    <input type='hidden' name='ref' value='{ref_code}'>
    <label>Your Name: <input name='user' required style='padding:12px;width:100%;margin:8px 0;border:2px solid #e5e7eb;border-radius:8px'></label><br>
    <label>WhatsApp: <input name='phone' required style='padding:12px;width:100%;margin:8px 0;border:2px solid #e5e7eb;border-radius:8px'></label><br>
    <label>Plan:</label><select name='plan' style='padding:12px;width:100%;margin:8px 0;border-radius:8px'><option value='yearly'>Yearly - R500</option><option value='lifetime'>Lifetime - R5000</option></select><br>
    <button type='submit' style='background:#10b981;color:white;padding:14px;width:100%;border:none;border-radius:10px;font-weight:bold;font-size:16px'>GET CAPITEC PAYMENT DETAILS</button>
    </form>
    {f"<p>Referred by: <b>{ref_code}</b></p>" if ref_code else ""}
    </div></body></html>"""

@app.route("/pay/create")
def pay_create():
    user=request.args.get("user","").strip()
    phone=request.args.get("phone","").strip()
    plan_key=request.args.get("plan","yearly")
    ref=request.args.get("ref","").upper().strip()
    if not user: return jsonify({"error":"user required"})
    short = "".join([c for c in user.upper() if c.isalnum()])[:5] or "USER"
    rand = "".join(random.choices(string.digits, k=3))
    payment_ref = f"{CAPITEC_DETAILS['reference_prefix']}-{short}-{rand}"
    plan = PLANS.get(plan_key, PLANS["yearly"])
    users = load_json(USERS_FILE)
    users[payment_ref] = {"user":user,"phone":phone,"plan":plan_key,"price":plan["price"],"payment_ref":payment_ref,"referred_by":ref,"status":"pending","created":datetime.now().isoformat(),"expires":None}
    save_json(USERS_FILE, users)
    return f"""
    <html><body style='font-family:Arial;padding:20px;max-width:600px;margin:auto;text-align:center'>
    <h1 style='color:#10b981'>Pay Now - Use This Reference</h1>
    <div style='background:#f8fafc;border:2px dashed #0f172a;padding:20px;border-radius:12px'>
    <h2>Pay R{plan['price']} to:</h2>
    <p style='font-size:20px;line-height:1.6'><b>Bank:</b> Capitec<br><b>Name:</b> Agent 35 Trading Bot<br><b>Acc No:</b> 2586572676<br><b>Branch:</b> 470010</p>
    <h1 style='background:#0f172a;color:white;padding:15px;border-radius:10px;letter-spacing:3px'>{payment_ref}</h1>
    <p><b>USE THIS REFERENCE IN CAPITEC APP</b><br>Plan: {plan['name']} | User: {user}<br>Referred by: {ref or 'None'}</p>
    </div>
    <p>After payment, send proof to Admin. Admin will approve.</p>
    <a href='/' style='display:inline-block;margin-top:20px;background:#0f172a;color:white;padding:12px 20px;border-radius:8px;text-decoration:none'>Home</a>
    </body></html>"""

@app.route("/admin")
def admin():
    secret = request.args.get("secret","")
    real = os.getenv("CRON_SECRET","")
    if real and secret!=real:
        return f"<html><body style='font-family:Arial;padding:30px'><h1>Admin Login</h1><p>Enter CRON_SECRET from Render</p><form><input name='secret' placeholder='CRON_SECRET' style='padding:12px'><button type='submit'>Login</button></form></body></html>"
    users = load_json(USERS_FILE)
    rows=""
    for pref, u in users.items():
        color = "#10b981" if u["status"]=="active" else "#f59e0b" if u["status"]=="pending" else "#ef4444"
        accept = f"<a href='/admin/accept?ref={pref}&secret={secret}' style='background:#10b981;color:white;padding:8px 12px;border-radius:6px;text-decoration:none'>ACCEPT</a>" if u["status"]=="pending" else ""
        reject = f"<a href='/admin/reject?ref={pref}&secret={secret}' style='background:#ef4444;color:white;padding:8px 12px;border-radius:6px;text-decoration:none'>REJECT</a>" if u["status"]=="pending" else ""
        rows+=f"<tr><td>{pref}</td><td>{u['user']}<br>{u['phone']}</td><td>{u['plan']} R{u['price']}</td><td>{u.get('referred_by') or '-'}</td><td style='color:{color};font-weight:bold'>{u['status']}</td><td>{u['created'][:16]}</td><td>{accept} {reject}</td></tr>"
    return f"<html><body style='font-family:Arial;padding:20px'><h1>Admin - Capitec 2586572676</h1><p>Check Capitec app for reference, then ACCEPT. Referral counts only after ACCEPT.</p><table border=1 cellpadding=10 style='border-collapse:collapse;width:100%'><tr><th>Ref</th><th>User</th><th>Plan</th><th>Referred By</th><th>Status</th><th>Date</th><th>Action</th></tr>{rows}</table><br><a href='/'>Home</a></body></html>"

@app.route("/admin/accept")
def admin_accept():
    pref=request.args.get("ref","")
    secret=request.args.get("secret","")
    users=load_json(USERS_FILE)
    refs=load_json(DATA_FILE)
    if pref not in users: return jsonify({"error":"not found"})
    u=users[pref]
    u["status"]="active"
    plan=PLANS.get(u["plan"], PLANS["yearly"])
    u["expires"]=(datetime.now()+timedelta(days=plan["duration_days"])).isoformat()
    users[pref]=u
    save_json(USERS_FILE,users)
    ref_code = u.get("referred_by")
    msg=""
    if ref_code:
        if ref_code not in refs: refs[ref_code]={"owner":ref_code,"count":0,"paid_refs":[],"reward_claimed":False}
        if u["user"] not in refs[ref_code].get("paid_refs",[]):
            refs[ref_code]["paid_refs"].append(u["user"])
            refs[ref_code]["count"]=len(refs[ref_code]["paid_refs"])
            save_json(DATA_FILE,refs)
            msg=f"Referral {u['user']} -> {ref_code} = {refs[ref_code]['count']}/10"
            if refs[ref_code]["count"]>=10: msg+= " 🎉 10 REACHED - GIVE LIFETIME R5000 FREE!"
    return jsonify({"ok":True,"activated":pref,"user":u,"referral":msg,"admin_link":f"/admin?secret={secret}"})

@app.route("/admin/reject")
def admin_reject():
    pref=request.args.get("ref","")
    users=load_json(USERS_FILE)
    if pref in users:
        users[pref]["status"]="rejected"
        save_json(USERS_FILE,users)
    return jsonify({"ok":True,"rejected":pref})

@app.route("/referral")
def referral():
    data=load_json(DATA_FILE)
    rows="".join([f"<tr><td>{code}</td><td>{info.get('owner')}</td><td>{info.get('count',0)}/10</td><td>{'✅ LIFETIME R5000' if info.get('count',0)>=10 else '⏳'}</td><td>{', '.join(info.get('paid_refs',[])[:2])}</td></tr>" for code,info in data.items()])
    return f"<html><body style='font-family:Arial;padding:20px'><h1>Referral - 10 Paid = R5000 Lifetime</h1><p>Rule: Only counts AFTER admin ACCEPTS payment</p><form action='/referral/create'><input name='code' placeholder='CODE e.g. THABO'><input name='owner' placeholder='Owner'><button>Create</button></form><table border=1 cellpadding=10><tr><th>Code</th><th>Owner</th><th>Count</th><th>Reward</th><th>Paid Users</th></tr>{rows}</table><br><a href='/'>Home</a></body></html>"

@app.route("/referral/create")
def ref_create():
    code=request.args.get("code","").upper().strip()
    owner=request.args.get("owner","").strip()
    data=load_json(DATA_FILE)
    if code and code not in data:
        data[code]={"owner":owner,"count":0,"paid_refs":[],"reward_claimed":False}
        save_json(DATA_FILE,data)
    return jsonify({"ok":True,"code":code,"link":f"/join?ref={code}"})

@app.route("/join")
def join():
    ref=request.args.get("ref","")
    return f"<html><body style='font-family:Arial;padding:30px;text-align:center'><h1>Referred by {ref}</h1><p>Pay and admin approval counts as PAID referral</p><a href='/pay?ref={ref}' style='background:#10b981;color:white;padding:14px 30px;border-radius:10px;text-decoration:none'>Buy Plan R500 / R5000 - Capitec 2586572676</a></body></html>"

@app.route("/run-now")
def run_now():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    return jsonify(eng.run_scan_and_send())

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
