from flask import Flask, request, jsonify, session, redirect
import os, json, random, hashlib, secrets, string, requests
from dotenv import load_dotenv
import trading_engine as eng
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "agent35-v10-full-integrated")

# ===== FILES - LAST WEEK LOGIC - NEVER WIPE IF EXISTS =====
AUTH_FILE = "auth_users.json"
USERS_FILE = "users_data.json"
DATA_FILE = "referrals_data.json"
JOURNAL_FILE = "journal.json"
TRACK_FILE = "tracked_trades.json"

CAPITEC = {"bank":"Capitec","holder":"Agent 35 Trading Bot","acc":"2586572676","branch":"470010","ref_prefix":"A35"}
PLANS = {"yearly":{"name":"Yearly","price":500,"days":365},"lifetime":{"name":"Lifetime","price":5000,"days":36500}}

def load_json(path, default_type=dict):
    if not os.path.exists(path):
        return {} if default_type==dict else []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {} if default_type==dict else []

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def hash_pwd(p): return hashlib.sha256(p.encode()).hexdigest()

def ensure_files():
    if not os.path.exists(AUTH_FILE):
        save_json(AUTH_FILE, {"admin@agent35.com": {"email":"admin@agent35.com","name":"Master Admin","password":hash_pwd("Agent35!"),"account_size":142.0,"total_profit":-1.42,"plan_status":"ACTIVE lifetime - MASTER","referred_by":"","expires":(datetime.now()+timedelta(days=36500)).isoformat(),"created":datetime.now().isoformat(),"reset_token":None}})
        print("FIRST RUN - master admin@agent35.com / Agent35!")
    if not os.path.exists(USERS_FILE): save_json(USERS_FILE, {})
    if not os.path.exists(DATA_FILE): save_json(DATA_FILE, {})
    if not os.path.exists(JOURNAL_FILE): save_json(JOURNAL_FILE, [])
    if not os.path.exists(TRACK_FILE): save_json(TRACK_FILE, {})

ensure_files()

# ===== TELEGRAM WITH BUTTONS =====
def send_telegram_signal(symbol, score, bias, signal, sl, tp, reason):
    bot = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not bot or not chat:
        return {"error":"Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Render Env"}

    text = f"🎯 *AGENT 35 SIGNAL*\n\nSymbol: {symbol}\nScore: {score}/10\nBias: {bias}\nSignal: {signal}\n\nSL: {sl}\nTP: {tp}\nReason: {reason}\nTime: {datetime.utcnow().strftime('%H:%M')} UTC | SAST {(datetime.utcnow()+timedelta(hours=2)).strftime('%H:%M')}"

    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ TAKE TRADE", "callback_data": f"TAKE_{symbol}_{score}"},
             {"text": "❌ MISS", "callback_data": f"MISS_{symbol}"}],
            [{"text": "📈 TRACK TO SL/TP", "callback_data": f"TRACK_{symbol}_{sl}_{tp}"}]
        ]
    }
    try:
        r = requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id": chat, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard}, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def dark_layout(content, active="Dashboard"):
    utc = datetime.utcnow().strftime("%H:%M:%S")
    sast = (datetime.utcnow() + timedelta(hours=2)).strftime("%H:%M:%S")
    user = session.get("user","Guest")
    tabs = ["Dashboard","Journal","All Signals","Settings","Plans","Guide","Master"]
    tab_html = "".join([f"<a href='/{t.lower().replace(' ','-')}' style='padding:8px 14px;border-radius:20px;text-decoration:none;font-weight:bold;font-size:13px;background:{'#10b981' if active==t else '#1e293b'};color:white;margin-right:6px;display:inline-block;margin-bottom:6px'>{t}</a>" for t in tabs])
    return f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>AGENT 35</title>
    <style>body{{background:#0f172a;color:#e2e8f0;font-family:Arial;margin:0}}.top{{background:#0f172a;border-bottom:1px solid #1e293b;padding:12px 15px;display:flex;justify-content:space-between;flex-wrap:wrap}}.logo{{color:#10b981;font-weight:900;font-size:18px}}.time{{color:#94a3b8;font-size:11px}}.nav{{background:#0f172a;padding:10px 15px;border-bottom:1px solid #1e293b;overflow-x:auto;white-space:nowrap}}.main{{padding:15px;display:grid;grid-template-columns:1fr 1fr 1fr 300px;gap:12px}}.card{{background:#1e293b;border-radius:16px;padding:18px;border:1px solid #334155;min-width:0}}.profit{{color:#ef4444;font-size:26px;font-weight:900}}.muted{{color:#64748b;font-size:11px}}.acc{{font-size:22px;font-weight:800}}.scan{{background:#10b981;color:white;padding:14px;border-radius:12px;text-align:center;font-weight:900;border:none;width:100%;cursor:pointer}}.blue{{background:#3b82f6;color:white;padding:12px;border-radius:12px;text-align:center;margin-top:10px;display:block;text-decoration:none;font-weight:bold}}.table-card{{grid-column:1 / span 4;background:#1e293b;border-radius:16px;padding:15px;overflow-x:auto}}table{{width:100%;border-collapse:collapse;min-width:500px}}th{{color:#64748b;text-align:left;padding:10px;font-size:10px}}td{{padding:12px;border-top:1px solid #334155;font-size:13px}}.took{{background:#10b98133;color:#10b981;padding:4px 10px;border-radius:10px;font-size:11px}}@media(max-width:900px){{.main{{grid-template-columns:1fr 1fr}}.table-card{{grid-column:1 / span 2}}}}@media(max-width:600px){{.main{{grid-template-columns:1fr}}.table-card{{grid-column:1}}.top{{flex-direction:column}}}} </style></head><body>
    <div class='top'><div class='logo'>35 AGENT 35</div><div class='time'>UTC {utc} | SAST {sast} | <span style='color:#10b981'>London ACTIVE</span> | {user}</div></div>
    <div class='nav'>{tab_html}</div>{content}</body></html>"""

@app.route("/")
def home(): return redirect("/dashboard") if session.get("user") else redirect("/login")

@app.route("/dashboard")
def dashboard():
    if not session.get("user"): return redirect("/login")
    auth = load_json(AUTH_FILE)
    info = auth.get(session.get("user"),{})
    acc_size = info.get("account_size",142.0)
    total_profit = info.get("total_profit",-1.42)
    journal = load_json(JOURNAL_FILE, list)
    if not journal: journal = [{"time":"09-03 18:13","symbol":"USDCHF","status":"TOOK","result":"R0 (0.0R)"},{"time":"09-03 18:13","symbol":"USDJPY","status":"TOOK","result":"R0 (0.0R)"},{"time":"09-03 18:13","symbol":"GBPUSD","status":"TOOK","result":"R0 (0.0R)"},{"time":"09-03 18:13","symbol":"EURUSD","status":"TOOK","result":"R0 (0.0R)"}]
    rows = "".join([f"<tr><td>{t.get('time')}</td><td style='font-weight:800'>{t.get('symbol')}</td><td><span class='took'>{t.get('status')}</span></td><td>{t.get('result')}</td></tr>" for t in reversed(journal[-10:])])
    tracked = load_json(TRACK_FILE, dict)
    track_html = "".join([f"<div style='background:#0f172a;padding:8px;border-radius:8px;margin:5px 0;font-size:12px'>{v['symbol']} - {v['status']} - SL:{v.get('sl')} TP:{v.get('tp')} by {v.get('by','')}</div>" for k,v in list(tracked.items())[-3:]])
    content = f"""<div class='main'>
        <div class='card'><div class='muted'>TOTAL PROFIT</div><div class='profit'>R{total_profit}</div><div style='color:#10b981;background:#10b98122;display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px'>WR: Tracking</div></div>
        <div class='card'><div class='muted'>ACCOUNT SIZE</div><div class='acc'>R{acc_size}</div><form action='/account/edit' method='post'><input name='size' value='{acc_size}' style='background:#0f172a;border:1px solid #334155;color:white;padding:8px;border-radius:8px;width:100%;margin-top:8px'><button type='submit' style='background:#1e293b;border:1px solid #334155;color:white;padding:6px 20px;border-radius:8px;margin-top:6px'>Edit</button></form></div>
        <div class='card'><div class='muted'>WATCHLIST 4/5</div><div style='margin:10px 0'><span style='background:#334155;padding:6px 10px;border-radius:20px;margin:3px;display:inline-block'>EURUSD</span> <span style='background:#334155;padding:6px 10px;border-radius:20px;margin:3px;display:inline-block'>GBPUSD</span> <span style='background:#334155;padding:6px 10px;border-radius:20px;margin:3px;display:inline-block'>USDJPY</span> <span style='background:#334155;padding:6px 10px;border-radius:20px;margin:3px;display:inline-block'>USDCHF</span></div></div>
        <div class='card'><a href='/dashboard-scan'><button class='scan'>SCAN NOW</button></a><div style='text-align:center;margin:10px;color:#64748b;font-size:12px'>Telegram Buttons<br>Take / Miss / Track to SL/TP</div><a href='/test-telegram' class='blue'>Test Telegram + Buttons</a><a href='/link-telegram' class='blue' style='background:#10b981'>Link Telegram</a><div style='margin-top:10px'>{track_html or '<p style=color:#64748b;font-size:11px>No tracked yet</p>'}</div></div>
    </div><div class='table-card'><table><tr><th>TIME</th><th>SYMBOL</th><th>STATUS</th><th>RESULT</th></tr>{rows}</table></div>"""
    return dark_layout(content,"Dashboard")

# ===== LOGIN SYSTEM - LAST WEEK KEEP =====
@app.route("/login")
def login_page():
    count = len(load_json(AUTH_FILE))
    return f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#0f172a;color:white;font-family:Arial;padding:20px'><div style='max-width:400px;margin:40px auto;background:#1e293b;padding:25px;border-radius:16px'><h2>Login - Agent 35</h2><p style='color:#64748b;font-size:12px'>{count} accounts - stays like last week until next deploy</p><form action='/login/check' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:12px;margin:8px 0;border-radius:8px;border:none'><input name='password' type='password' placeholder='Password' required style='width:100%;padding:12px;margin:8px 0;border-radius:8px;border:none'><button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;font-weight:bold'>LOGIN</button></form><p><a href='/register' style='color:#3b82f6'>Register</a> | <a href='/forgot-password' style='color:#ff6b35'>Forgot?</a></p><div style='background:#0f172a;padding:12px;border-radius:8px'><p style='font-size:11px;color:#94a3b8'>Master: admin@agent35.com / Agent35!</p></div></div></body></html>"""

@app.route("/register")
def reg_page(): return """<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#0f172a;color:white;font-family:Arial;padding:20px'><div style='max-width:400px;margin:40px auto;background:#1e293b;padding:25px;border-radius:16px'><h2>Register</h2><form action='/register/create' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><input name='name' placeholder='Name' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><input name='password' type='password' placeholder='Password min 6' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><input name='ref' placeholder='Referral Code' style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;font-weight:bold'>CREATE</button></form></div></body></html>"""

@app.route("/register/create", methods=["POST"])
def reg_create():
    email=request.form.get("email","").lower().strip()
    auth=load_json(AUTH_FILE)
    if email in auth: return f"Exists <a href='/login'>Login</a>"
    auth[email]={"email":email,"name":request.form.get("name"),"password":hash_pwd(request.form.get("password","")),"account_size":142.0,"total_profit":-1.42,"plan_status":"No Plan - Need R500/R5000","referred_by":request.form.get("ref","").upper(),"expires":None,"created":datetime.now().isoformat(),"reset_token":None}
    save_json(AUTH_FILE, auth); session["user"]=email; return redirect("/dashboard")

@app.route("/login/check", methods=["POST"])
def login_check():
    email=request.form.get("email","").lower().strip(); pwd=request.form.get("password","")
    auth=load_json(AUTH_FILE)
    if email in auth and auth[email].get("password")==hash_pwd(pwd): session["user"]=email; return redirect("/dashboard")
    return f"<html><body style='background:#0f172a;color:white;padding:30px'><h2>Wrong for {email}</h2><p>Users: {list(auth.keys())}</p><a href='/login'>Retry</a> | <a href='/register'>Register</a></body></html>"

@app.route("/logout")
def logout(): session.pop("user",None); return redirect("/login")

@app.route("/forgot-password")
def forgot_page(): return """<html><body style='background:#0f172a;color:white;padding:30px'><div style='max-width:400px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>Forgot Password</h2><form action='/forgot-password/send' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:12px'><button style='background:#ff6b35;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px'>SEND RESET</button></form></div></body></html>"""

@app.route("/forgot-password/send", methods=["POST"])
def forgot_send():
    email=request.form.get("email","").lower().strip()
    auth=load_json(AUTH_FILE)
    if email not in auth: return f"Not found {email} <a href='/register'>Register</a>"
    token=secrets.token_urlsafe(12)
    auth[email]["reset_token"]=token; auth[email]["reset_expiry"]=(datetime.now()+timedelta(hours=1)).isoformat()
    save_json(AUTH_FILE, auth)
    link=f"/reset-password?token={token}&email={email}"
    return f"<html><body style='background:#0f172a;color:white;padding:20px;text-align:center'><h2>Reset Link (1h)</h2><a href='{link}' style='background:#10b981;color:white;padding:12px 20px;border-radius:8px;text-decoration:none'>Reset {email}</a><p>{link}</p></body></html>"

@app.route("/reset-password")
def reset_page(): return f"""<html><body style='background:#0f172a;color:white;padding:30px'><div style='max-width:400px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>Reset {request.args.get('email')}</h2><form action='/reset-password/save' method='post'><input type='hidden' name='email' value='{request.args.get('email')}'><input type='hidden' name='token' value='{request.args.get('token')}'><input name='new_password' type='password' placeholder='New Password' required style='width:100%;padding:12px'><button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px'>SAVE</button></form></div></body></html>"""

@app.route("/reset-password/save", methods=["POST"])
def reset_save():
    email=request.form.get("email","").lower(); token=request.form.get("token","")
    auth=load_json(AUTH_FILE)
    if auth.get(email,{}).get("reset_token")!=token: return "Invalid token"
    auth[email]["password"]=hash_pwd(request.form.get("new_password","")); auth[email]["reset_token"]=None; save_json(AUTH_FILE, auth)
    return "Changed <a href='/login'>Login</a>"

@app.route("/account/edit", methods=["POST"])
def acc_edit():
    if not session.get("user"): return redirect("/login")
    auth=load_json(AUTH_FILE); auth[session["user"]]["account_size"]=float(request.form.get("size","142.0")); save_json(AUTH_FILE, auth); return redirect("/dashboard")

# ===== PAY + REFERRAL + CAPITEC =====
@app.route("/pay")
def pay_page():
    ref=request.args.get("ref","") or session.get("ref","")
    email=request.args.get("email","") or session.get("user","")
    return f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#0f172a;color:white;font-family:Arial;padding:20px'><div style='max-width:500px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>Buy - Capitec {CAPITEC['acc']}</h2><p>{CAPITEC['holder']}<br>Acc: {CAPITEC['acc']} Branch: {CAPITEC['branch']}</p><form action='/pay/create' method='get'><input type='hidden' name='ref' value='{ref}'><input name='user' value='{email}' placeholder='Email (login email)' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><input name='phone' placeholder='WhatsApp' required style='width:100%;padding:12px;margin:6px 0;border-radius:8px;border:none'><select name='plan' style='width:100%;padding:12px;border-radius:8px'><option value='yearly'>Yearly R500</option><option value='lifetime'>Lifetime R5000</option></select><button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:8px;margin-top:10px;font-weight:bold'>GET PAYMENT REF</button></form>{f'<p>Referred by: {ref}</p>' if ref else ''}</div></body></html>"""

@app.route("/pay/create")
def pay_create():
    user=request.args.get("user","").lower().strip(); phone=request.args.get("phone","").strip(); plan_key=request.args.get("plan","yearly"); ref=request.args.get("ref","").upper().strip()
    short="".join([c for c in user.upper() if c.isalnum()])[:5] or "USER"; rand="".join(random.choices(string.digits,k=3)); pref=f"{CAPITEC['ref_prefix']}-{short}-{rand}"
    plan=PLANS.get(plan_key, PLANS["yearly"])
    users=load_json(USERS_FILE); users[pref]={"user":user,"phone":phone,"plan":plan_key,"price":plan["price"],"payment_ref":pref,"referred_by":ref,"status":"pending","created":datetime.now().isoformat(),"expires":None}; save_json(USERS_FILE, users)
    return f"<html><body style='background:#0f172a;color:white;padding:30px;text-align:center'><h1>Pay R{plan['price']}</h1><div style='border:2px dashed #334155;padding:20px;border-radius:12px;max-width:450px;margin:auto;background:#1e293b'><p>Bank: Capitec<br>{CAPITEC['holder']}<br>Acc: {CAPITEC['acc']}<br>Branch: {CAPITEC['branch']}</p><h1 style='background:white;color:black;padding:15px;border-radius:10px'>{pref}</h1><p>USE THIS REF IN CAPITEC APP<br>Plan: {plan['name']} | {user}</p></div></body></html>"

@app.route("/join")
def join(): ref=request.args.get("ref",""); session["ref"]=ref; return f"<html><body style='background:#0f172a;color:white;padding:40px;text-align:center'><h1>Referred by {ref}</h1><a href='/pay?ref={ref}' style='background:#10b981;color:white;padding:14px 30px;border-radius:10px;text-decoration:none'>Continue to Pay Capitec {CAPITEC['acc']}</a><br><br><a href='/register?ref={ref}' style='color:#3b82f6'>Or Register</a></body></html>"

@app.route("/referral")
def referral_page():
    data=load_json(DATA_FILE)
    rows="".join([f"<tr><td>{code}</td><td>{info.get('owner','')}</td><td>{info.get('count',0)}/10</td><td>{'✅ LIFETIME' if info.get('count',0)>=10 else '⏳'}</td><td>{', '.join(info.get('paid_refs',[])[:3])}</td></tr>" for code,info in data.items()])
    return dark_layout(f"<div class='table-card'><h2>Referral 10=R5000</h2><p>Only counts after admin ACCEPTS payment</p><table><tr><th>Code</th><th>Owner</th><th>Count</th><th>Reward</th><th>Paid Users</th></tr>{rows}</table><br><form action='/referral/create'><input name='code' placeholder='CODE' style='padding:8px'><input name='owner' placeholder='Owner email' style='padding:8px'><button style='background:#10b981;color:white;padding:8px 12px;border:none;border-radius:6px'>Create</button></form></div>","Master")

@app.route("/referral/create")
def referral_create():
    code=request.args.get("code","").upper().strip(); owner=request.args.get("owner","").strip()
    if not code: return jsonify({"error":"code required"})
    data=load_json(DATA_FILE)
    if code not in data: data[code]={"owner":owner,"count":0,"paid_refs":[],"created":datetime.now().isoformat()}; save_json(DATA_FILE, data)
    return redirect("/referral")

# ===== TRADING =====
@app.route("/scan")
def scan(): return jsonify(eng.full_multi_tf_analysis(request.args.get("symbol","EURUSD")))

@app.route("/dashboard-scan")
def dash_scan():
    syms=["EURUSD","GBPUSD","USDJPY","USDCHF","XAUUSD","US30","NAS100","GBPJPY"]
    rows="".join([f"<tr><td>{s}</td><td>{(r:=eng.full_multi_tf_analysis(s))['score']}/10</td><td>{r['bias']}</td><td>{r['signal']}</td><td><a href='/send-signal?symbol={s}' style='background:#10b981;color:white;padding:4px 8px;border-radius:6px;text-decoration:none'>Send TG + Buttons</a></td></tr>" for s in syms])
    return dark_layout(f"<div class='table-card'><h2>Scan 8 - 6/10 Fix</h2><table><tr><th>Sym</th><th>Score</th><th>Bias</th><th>Signal</th><th>Telegram</th></tr>{rows}</table><br><a href='/dashboard' style='color:#10b981'>Back</a></div>","All Signals")

@app.route("/send-signal")
def send_signal():
    sym=request.args.get("symbol","EURUSD"); r=eng.full_multi_tf_analysis(sym)
    res=send_telegram_signal(sym, r['score'], r['bias'], r['signal'], "SL 0.2%", "TP 0.4%", r.get('reason',''))
    return f"Sent {sym} {r['score']}/10 -> {res} <a href='/dashboard'>Back</a>"

@app.route("/link-telegram")
def link_telegram_route():
    bot=os.getenv("TELEGRAM_BOT_TOKEN","Not set"); chat=os.getenv("TELEGRAM_CHAT_ID","Not set")
    return f"""<html><body style='background:#0f172a;color:white;padding:20px'><div style='max-width:500px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>Telegram Connect</h2><p>Bot: {bot[:10]}...<br>Chat: {chat}</p><p>Set webhook to:<br><code>https://agent-35-trading-bot.onrender.com/telegram/webhook</code></p><a href='/test-telegram' style='background:#3b82f6;color:white;padding:12px 20px;border-radius:8px;text-decoration:none'>Test + Buttons</a><br><br><a href='/dashboard' style='color:#64748b'>Back</a></div></body></html>"""

@app.route("/test-telegram")
def test_telegram():
    res=send_telegram_signal("EURUSD",7,"BUY","BUY NOW","1.0845 SL","1.0920 TP","6/10 Fix - 4H Bullish, 15m BOS + FVG")
    return f"<html><body style='background:#0f172a;color:white;padding:30px;text-align:center'><h2>Telegram Test</h2><p>{res}</p><p>Check Telegram - 3 buttons should appear: TAKE / MISS / TRACK</p><a href='/dashboard' style='background:#10b981;color:white;padding:12px 20px;border-radius:8px;text-decoration:none'>Back</a></body></html>"

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data=request.get_json()
    if not data: return jsonify({"ok":True})
    if "callback_query" in data:
        cb=data["callback_query"]; cb_data=cb.get("data",""); cb_id=cb.get("id"); chat_id=cb["message"]["chat"]["id"]
        user_name=cb["from"].get("first_name","User")
        journal=load_json(JOURNAL_FILE, list); tracked=load_json(TRACK_FILE, dict); bot=os.getenv("TELEGRAM_BOT_TOKEN")
        if cb_data.startswith("TAKE_"):
            _, symbol, score = cb_data.split("_")
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":symbol,"status":"TOOK","result":f"Taken by {user_name} {score}/10"}); save_json(JOURNAL_FILE, journal[-100:]); text=f"✅ {user_name} TOOK {symbol} {score}/10 - Logged"
        elif cb_data.startswith("MISS_"):
            symbol=cb_data.split("_")[1]; journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":symbol,"status":"MISS","result":f"Missed by {user_name}"}); save_json(JOURNAL_FILE, journal[-100:]); text=f"❌ {user_name} MISSED {symbol}"
        elif cb_data.startswith("TRACK_"):
            parts=cb_data.split("_"); symbol=parts[1]; sl=parts[2]; tp=parts[3] if len(parts)>3 else "TP"; tid=f"{symbol}_{datetime.now().strftime('%H%M%S')}"
            tracked[tid]={"symbol":symbol,"sl":sl,"tp":tp,"status":"TRACKING","started":datetime.now().isoformat(),"by":user_name}; save_json(TRACK_FILE, tracked); text=f"📈 {user_name} TRACKING {symbol} SL:{sl} TP:{tp}"
        else:
            text="Unknown"
        if bot:
            requests.post(f"https://api.telegram.org/bot{bot}/answerCallbackQuery", json={"callback_query_id":cb_id,"text":text}, timeout=5)
            requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":text}, timeout=5)
        return jsonify({"ok":True})
    return jsonify({"ok":True})

# ===== 3 CRONS + TRACK CHECK =====
@app.route("/cron/scan")
def cron_scan():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    syms=["EURUSD","GBPUSD","USDJPY","USDCHF","XAUUSD","US30"]
    sent=[]
    for s in syms:
        r=eng.full_multi_tf_analysis(s)
        if r.get("score",0)>=6:
            res=send_telegram_signal(s, r['score'], r['bias'], r['signal'], "SL auto", "TP auto", r.get('reason',''))
            sent.append({"symbol":s,"res":res})
            j=load_json(JOURNAL_FILE, list); j.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":s,"status":"TOOK","result":f"{r['score']}/10 {r['bias']} Sent"}); save_json(JOURNAL_FILE, j[-100:])
    return jsonify({"cron":"scan 30min","sent":sent})

@app.route("/cron/daily-reset")
def cron_reset():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    return jsonify({"cron":"daily-reset 00:00 SAST","ok":True})

@app.route("/cron/check-expiry")
def cron_expiry():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    auth=load_json(AUTH_FILE); exp=[]
    for e,i in auth.items():
        if i.get("expires"):
            try:
                if datetime.now()>datetime.fromisoformat(i["expires"]): i["plan_status"]="EXPIRED"; exp.append(e)
            except: pass
    save_json(AUTH_FILE, auth)
    return jsonify({"checked":len(auth),"expired":exp})

@app.route("/cron/track-check")
def cron_track():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    tracked=load_json(TRACK_FILE, dict)
    return jsonify({"tracking":len([t for t in tracked.values() if t['status']=="TRACKING"]),"list":tracked})

@app.route("/run-now")
def run_now():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    return jsonify(eng.run_scan_and_send())

# ===== ADMIN =====
@app.route("/admin")
def admin_page():
    secret=request.args.get("secret",""); real=os.getenv("CRON_SECRET","")
    if real and secret!=real: return f"<html><body style='background:#0f172a;color:white;padding:30px'><h1>Admin</h1><form><input name='secret' placeholder='CRON_SECRET' style='padding:12px'><button>Login</button></form></body></html>"
    users=load_json(USERS_FILE); auth=load_json(AUTH_FILE); refs=load_json(DATA_FILE)
    u_rows="".join([f"<tr><td>{pref}</td><td>{u['user']}<br>{u['phone']}</td><td>{u['plan']} R{u['price']}</td><td>{u.get('referred_by') or '-'}</td><td>{u['status']}</td><td><a href='/admin/accept?ref={pref}&secret={secret}' style='background:#10b981;color:white;padding:6px 10px;border-radius:6px;text-decoration:none'>ACCEPT</a> <a href='/admin/reject?ref={pref}&secret={secret}' style='background:#ef4444;color:white;padding:6px 10px;border-radius:6px;text-decoration:none'>REJECT</a></td></tr>" for pref,u in users.items()])
    a_rows="".join([f"<tr><td>{e}</td><td>{i.get('name','')}</td><td>{i.get('plan_status','')}</td><td>R{i.get('account_size',0)}</td><td>{i.get('referred_by') or '-'}</td></tr>" for e,i in auth.items()])
    return f"<html><body style='background:#0f172a;color:white;padding:20px;font-family:Arial'><h1>Admin - Capitec {CAPITEC['acc']} {CAPITEC['holder']}</h1><p>Logins: {len(auth)} - Last week logic, stays until deploy</p><h3>All Logins</h3><table border=1 cellpadding=5 style='border-collapse:collapse;width:100%'><tr><th>Email</th><th>Name</th><th>Status</th><th>Size</th><th>Ref</th></tr>{a_rows}</table><h3>Pending Payments</h3><table border=1 cellpadding=5 style='border-collapse:collapse;width:100%'><tr><th>Ref</th><th>User</th><th>Plan</th><th>RefBy</th><th>Status</th><th>Action</th></tr>{u_rows}</table><br><a href='/dashboard' style='color:#10b981'>Back Dashboard</a></body></html>"

@app.route("/admin/accept")
def admin_accept():
    pref=request.args.get("ref",""); secret=request.args.get("secret",""); users=load_json(USERS_FILE); auth=load_json(AUTH_FILE); refs=load_json(DATA_FILE)
    if pref not in users: return jsonify({"error":"not found"})
    u=users[pref]; u["status"]="active"; days=PLANS.get(u["plan"], PLANS["yearly"])["days"]; u["expires"]=(datetime.now()+timedelta(days=days)).isoformat(); users[pref]=u; save_json(USERS_FILE, users)
    if u["user"] in auth: auth[u["user"]]["plan_status"]=f"ACTIVE {u['plan']} - Paid Capitec"; auth[u["user"]]["expires"]=u["expires"]; save_json(AUTH_FILE, auth)
    ref_code=u.get("referred_by")
    if ref_code:
        if ref_code not in refs: refs[ref_code]={"owner":ref_code,"count":0,"paid_refs":[]}
        if u["user"] not in refs[ref_code].get("paid_refs",[]): refs[ref_code]["paid_refs"].append(u["user"]); refs[ref_code]["count"]=len(refs[ref_code]["paid_refs"]); save_json(DATA_FILE, refs)
    return jsonify({"ok":True,"activated":pref,"user":u["user"],"referral":f"{ref_code} now {refs.get(ref_code,{}).get('count',0)}/10" if ref_code else "no ref"})

@app.route("/admin/reject")
def admin_reject():
    pref=request.args.get("ref",""); users=load_json(USERS_FILE)
    if pref in users: users[pref]["status"]="rejected"; save_json(USERS_FILE, users)
    return jsonify({"ok":True,"rejected":pref})

@app.route("/admin/restore-paid")
def restore_paid():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return "Bad secret"
    email=request.args.get("email","").lower().strip(); name=request.args.get("name","Paid User"); plan=request.args.get("plan","yearly")
    if not email: return "Need?email=user@gmail.com&name=Name&plan=yearly"
    auth=load_json(AUTH_FILE); auth[email]={"email":email,"name":name,"password":hash_pwd("Agent35!"),"account_size":142.0,"total_profit":-1.42,"plan_status":f"ACTIVE {plan} - RESTORED","expires":(datetime.now()+timedelta(days=365 if plan=="yearly" else 36500)).isoformat(),"created":datetime.now().isoformat(),"reset_token":None}; save_json(AUTH_FILE, auth)
    return jsonify({"ok":True,"restored":email,"temp_pass":"Agent35!","login":"/login"})

@app.route("/journal")
def journal_page():
    journal=load_json(JOURNAL_FILE, list); tracked=load_json(TRACK_FILE, dict)
    j_rows="".join([f"<tr><td>{j.get('time')}</td><td>{j.get('symbol')}</td><td><span class='took'>{j.get('status')}</span></td><td>{j.get('result')}</td></tr>" for j in reversed(journal[-50:])])
    t_rows="".join([f"<tr><td>{v.get('symbol')}</td><td>{v.get('status')}</td><td>{v.get('sl')}</td><td>{v.get('tp')}</td><td>{v.get('by')}</td></tr>" for v in tracked.values()]) or "<tr><td colspan=5>No tracked yet - click TRACK on Telegram</td></tr>"
    return dark_layout(f"<div class='table-card'><h2>Journal</h2><table><tr><th>TIME</th><th>SYM</th><th>STATUS</th><th>RESULT</th></tr>{j_rows}</table><h2 style='margin-top:20px'>Tracked to SL/TP</h2><table><tr><th>Symbol</th><th>Status</th><th>SL</th><th>TP</th><th>By</th></tr>{t_rows}</table></div>","Journal")

@app.route("/all-signals")
def all_signals(): return redirect("/dashboard-scan")
@app.route("/settings")
def settings(): return dark_layout(f"<div class='table-card'><h2>Settings</h2><p>Capitec {CAPITEC['acc']} - {CAPITEC['holder']}<br>Threshold 6/10 Fix<br>Telegram buttons Take/Miss/Track<br>Login keeps like last week</p></div>","Settings")
@app.route("/plans")
def plans(): return dark_layout(f"<div class='table-card'><h2>Plans - Capitec {CAPITEC['acc']}</h2><p>Yearly R500 | Lifetime R5000<br>Acc Holder: {CAPITEC['holder']}<br>Acc: {CAPITEC['acc']}<br>Branch: {CAPITEC['branch']}</p><a href='/pay' style='background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none'>Buy Now</a></div>","Plans")
@app.route("/guide")
def guide(): return dark_layout("<div class='table-card'><h2>Guide</h2><p>6/10 Fix - 4H Neutral allowed - 15m BOS+FVG</p></div>","Guide")
@app.route("/master")
def master(): return redirect("/referral")

@app.route("/health")
def health(): return jsonify({"ok":True,"mode":"V10 FULL INTEGRATED - last week login + telegram buttons + referral + capitec 2586572676","users":len(load_json(AUTH_FILE)),"pending":len([u for u in load_json(USERS_FILE).values() if u.get('status')=='pending']),"tracked":len(load_json(TRACK_FILE, dict))})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
