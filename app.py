import os, hashlib, requests, psycopg
from psycopg.rows import dict_row
from flask import Flask, request, redirect, session, render_template_string, jsonify
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'agent35-secret-2025')
DATABASE_URL = os.environ.get('DATABASE_URL','').strip()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN','')
TELEGRAM_CHAT = os.environ.get('TELEGRAM_CHAT_ID','')
CAPITEC_ACC = "2586572676"

def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode='require', connect_timeout=20)

def init_db():
    try:
        conn = get_conn(); cur = conn.cursor()
        # Users Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS agent35_users (
            id SERIAL PRIMARY KEY, email TEXT UNIQUE, password TEXT,
            is_creator BOOLEAN DEFAULT FALSE, plan TEXT DEFAULT 'none',
            payment_ref TEXT, payment_status TEXT DEFAULT 'pending',
            risk_reward TEXT DEFAULT '1:3', symbols TEXT DEFAULT 'EURUSD,XAUUSD,BTCUSD',
            sessions TEXT DEFAULT 'London,New York', account_size FLOAT DEFAULT 10000,
            lot_size FLOAT DEFAULT 0.1, leverage TEXT DEFAULT '1:500',
            telegram_id TEXT, created_at TIMESTAMP DEFAULT NOW()
        );""")
        # Trades Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS agent35_trades (
            id SERIAL PRIMARY KEY, user_email TEXT, symbol TEXT,
            direction TEXT, entry FLOAT, sl FLOAT, tp FLOAT,
            status TEXT DEFAULT 'sent', pnl FLOAT DEFAULT 0,
            timeframe_bias TEXT, confluence TEXT, created_at TIMESTAMP DEFAULT NOW()
        );""")
        # Payments Table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS agent35_payments (
            id SERIAL PRIMARY KEY, user_email TEXT, plan TEXT,
            ref_code TEXT UNIQUE, amount INT, status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        );""")
        conn.commit()
        # Create Creator + Test User
        cur.execute("SELECT * FROM agent35_users WHERE email='creator@agent35.com'")
        if not cur.fetchone():
            pw = hashlib.sha256('Agent35Creator!'.encode()).hexdigest()
            cur.execute("INSERT INTO agent35_users (email,password,is_creator,plan,payment_status) VALUES (%s,%s,TRUE,'lifetime','approved')", ('creator@agent35.com', pw))
            pw2 = hashlib.sha256('Test123!'.encode()).hexdigest()
            cur.execute("INSERT INTO agent35_users (email,password,plan,payment_status) VALUES (%s,%s,'yearly','approved')", ('test@agent35.com', pw2))
            conn.commit()
        cur.close(); conn.close()
        print("✅ Agent 35 DB Ready")
    except Exception as e:
        print(f"❌ DB Init: {e}")

init_db()

# --- TRADING LOGIC CORE ---
def analyze_market(symbol="EURUSD"):
    """
    Agent 35 Logic: Daily -> 4H -> 2H -> 1H -> 30M -> 15M -> 5M entry
    Checks: OB, MB, BB, RB, EQH/EQL, PDH/PDL, FVG, iFVG, BSL/SSL sweeps, BOS/CHOCH, Premium/Discount
    """
    # For V1 we scan structure - real logic uses yfinance + SMC detection
    # This is the framework you expand
    bias = "BULLISH" # from Daily HTF analysis
    confluences = []
    # Example checks (you will replace with real SMC detection)
    # 1. Daily Structure - BOS
    # 2. 4H,2H,1H alignment
    # 3. 5M Order Block + FVG + Liquidity Sweep
    confluences.append("Daily BOS Confirmed")
    confluences.append("4H/2H/1H Aligned")
    confluences.append("5M Bullish OB + FVG + SSL Sweep")
    confluences.append("Entry at Discount Zone")

    if len(confluences) >= 3:
        return {"signal": True, "bias": bias, "confluence": ", ".join(confluences), "entry_zone": "Discount"}
    return {"signal": False}

def send_telegram_signal(user_email, trade):
    if not TELEGRAM_TOKEN: return False
    text = f"""🎯 AGENT 35 SIGNAL
Symbol: {trade['symbol']}
Direction: {trade['direction']} {trade['timeframe_bias']}
Entry: {trade['entry']} | SL: {trade['sl']} | TP: {trade['tp']}
Confluence: {trade['confluence']}
RR: 1:3 | Zone: {trade.get('entry_zone','OB')}
[TOOK TRADE] [SKIPPED]"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT, "text": text})
        return True
    except: return False

# --- ROUTES ---
LOGIN_HTML = """
<body style="background:#0a0e14;color:#fff;font-family:Inter,Arial;display:flex;justify-content:center;align-items:center;height:100vh;margin:0">
<div style="background:#111827;border:1px solid #1f2937;padding:40px;border-radius:16px;width:360px;box-shadow:0 0 30px rgba(16,185,129,0.1)">
<h1 style="color:#10b981;text-align:center">AGENT 35</h1><p style="text-align:center;color:#9ca3af">Trading Bot</p>
<form method="POST" action="/auth"><input name="email" value="{{email}}" placeholder="Email" style="width:100%;padding:12px;margin:8px 0;background:#0a0e14;border:1px solid #374151;color:#fff;border-radius:8px" required>
<input name="password" type="password" placeholder="Password" style="width:100%;padding:12px;margin:8px 0;background:#0a0e14;border:1px solid #374151;color:#fff;border-radius:8px" required>
<button style="width:100%;padding:12px;background:#10b981;color:#000;font-weight:bold;border:none;border-radius:8px;margin-top:10px">LOGIN</button></form>
<p style="font-size:12px;color:#6b7280;text-align:center;margin-top:15px">Creator: creator@agent35.com / Agent35Creator!<br>Test: test@agent35.com / Test123!</p></div></body>
"""

@app.route('/')
def home(): return render_template_string(LOGIN_HTML, email="test@agent35.com")

@app.route('/auth', methods=['POST'])
def auth():
    email = request.form['email'].lower().strip()
    pw = hashlib.sha256(request.form['password'].encode()).hexdigest()
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("SELECT * FROM agent35_users WHERE email=%s AND password=%s", (email, pw))
        u=cur.fetchone()
        cur.close(); conn.close()
        if u:
            session['email']=u['email']; session['is_creator']=u['is_creator']; session['plan']=u['plan']
            if u['is_creator']: return redirect('/master')
            return redirect('/dashboard')
    except Exception as e: return f"DB Error: {e} <a href='/'>back</a>"
    return "Invalid login <a href='/'>back</a>"

@app.route('/dashboard')
def dashboard():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],))
    user=cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC LIMIT 20", (session['email'],))
    trades=cur.fetchall()
    cur.close(); conn.close()
    # PNL Calc
    pnl = sum([t['pnl'] for t in trades]); winrate = len([t for t in trades if t['pnl']>0])/len(trades)*100 if trades else 0

    return render_template_string("""
    <body style="background:#0a0e14;color:#e5e7eb;font-family:Arial;padding:20px">
    <div style="display:flex;justify-content:space-between;background:#111827;padding:15px;border-radius:12px;border:1px solid #1f2937">
    <b style="color:#10b981">AGENT 35 - {{user['email']}} | {{user['plan']}}</b><a href="/logout" style="color:#fff">Logout</a></div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:20px 0">
    <div style="background:#111827;padding:15px;border-radius:10px">PNL: ${{pnl}}<br><small>Winrate: {{winrate}}%</small></div>
    <div style="background:#111827;padding:15px;border-radius:10px">Balance: ${{user['account_size']}}<br><small>Lot: {{user['lot_size']}} Lev: {{user['leverage']}}</small></div>
    <div style="background:#111827;padding:15px;border-radius:10px">Symbols: {{user['symbols']}}<br><small>RR: {{user['risk_reward']}}</small></div>
    <div style="background:#111827;padding:15px;border-radius:10px"><button style="background:#10b981;padding:8px;border:none;border-radius:6px">Scan Market</button><br><small>{{user['sessions']}} sessions</small></div>
    </div>
    <h3 style="color:#10b981">Trading Journal</h3><table style="width:100%;background:#111827;border-radius:10px;padding:10px"><tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>PNL</th><th>Status</th></tr>
    {% for t in trades %}<tr><td>{{t['symbol']}}</td><td>{{t['direction']}}</td><td>{{t['entry']}}</td><td>{{t['pnl']}}</td><td>{{t['status']}}</td></tr>{% endfor %}</table>
    <h3>Payment</h3><p>Capitec: {{capitec}} | <a href="/payment">Pay / Upgrade</a></p>
    </body>
    """, user=user, trades=trades, pnl=round(pnl,2), winrate=round(winrate,1), capitec=CAPITEC_ACC)

@app.route('/master')
def master():
    if not session.get('is_creator'): return redirect('/')
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM agent35_users"); users=cur.fetchall()
    cur.execute("SELECT * FROM agent35_payments ORDER BY created_at DESC"); pays=cur.fetchall()
    cur.close(); conn.close()
    return render_template_string("""
    <body style="background:#0a0e14;color:#fff;font-family:Arial;padding:20px">
    <h1 style="color:#10b981">MASTER DASHBOARD - CREATOR</h1>
    <h3>Users ({{users|length}})</h3>{% for u in users %}<div style="background:#111827;margin:5px;padding:10px;border-radius:8px">{{u['email']}} - {{u['plan']}} - {{u['payment_status']}} - {{u['symbols']}}</div>{% endfor %}
    <h3>Payments to Approve - Capitec {{capitec}}</h3>{% for p in pays %}<div style="background:#111827;margin:5px;padding:10px;border-radius:8px">{{p['user_email']}} - R{{p['amount']}} - Ref: {{p['ref_code']}} - {{p['status']}} <a href="/approve/{{p['id']}}">Approve</a></div>{% endfor %}
    <p><a href="/scan">Run Market Scan Now</a> | <a href="/healthz">Health</a></p></body>
    """, users=users, pays=pays, capitec=CAPITEC_ACC)

@app.route('/scan')
def scan():
    if 'email' not in session: return redirect('/')
    result = analyze_market()
    if result['signal']:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,timeframe_bias,confluence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (session['email'],"EURUSD","BUY",1.0850,1.0830,1.0910,result['bias'],result['confluence']))
        conn.commit(); cur.close(); conn.close()
        send_telegram_signal(session['email'], {"symbol":"EURUSD","direction":"BUY","entry":1.0850,"sl":1.0830,"tp":1.0910,"timeframe_bias":result['bias'],"confluence":result['confluence']})
        return "Signal Sent + Telegram ✅ <a href='/dashboard'>Back</a>"
    return "No A+ setup now - Trend not aligned <a href='/dashboard'>Back</a>"

@app.route('/payment')
def payment_page():
    ref = f"AG35-{datetime.now().strftime('%y%m%d')}-{os.urandom(2).hex().upper()}"
    return render_template_string("""
    <body style="background:#0a0e14;color:#fff;padding:30px;font-family:Arial;text-align:center">
    <div style="background:#111827;padding:30px;border-radius:16px;max-width:400px;margin:auto">
    <h2 style="color:#10b981">Pay for Agent 35</h2><p>Capitec: 2586572676</p>
    <p>Plan 1: R500 / year</p><p>Plan 2: R5000 Lifetime</p>
    <p>Your Ref: <b style="color:#10b981">{{ref}}</b><br>Use this ref when paying</p>
    <p style="font-size:12px;color:#9ca3af">Verification up to 24h</p>
    <a href="/submit-payment?ref={{ref}}&plan=yearly" style="background:#10b981;color:#000;padding:10px 20px;border-radius:8px;text-decoration:none;display:block;margin:10px">I Paid R500 Yearly - {{ref}}</a>
    <a href="/submit-payment?ref={{ref}}&plan=lifetime" style="background:#fff;color:#000;padding:10px 20px;border-radius:8px;text-decoration:none;display:block">I Paid R5000 Lifetime - {{ref}}</a>
    </div></body>
    """, ref=ref)

@app.route('/submit-payment')
def submit_payment():
    ref=request.args.get('ref'); plan=request.args.get('plan')
    conn=get_conn(); cur=conn.cursor()
    amount = 500 if plan=='yearly' else 5000
    cur.execute("INSERT INTO agent35_payments (user_email,plan,ref_code,amount) VALUES (%s,%s,%s,%s)", (session['email'],plan,ref,amount))
    cur.execute("UPDATE agent35_users SET payment_ref=%s, plan=%s, payment_status='pending' WHERE email=%s", (ref,plan,session['email']))
    conn.commit(); cur.close(); conn.close()
    return f"Payment submitted Ref {ref}. Wait 24h for approval. <a href='/dashboard'>Back</a>"

@app.route('/approve/<int:pid>')
def approve(pid):
    if not session.get('is_creator'): return "Not allowed"
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE agent35_payments SET status='approved' WHERE id=%s RETURNING user_email,plan", (pid,))
    row=cur.fetchone()
    if row: cur.execute("UPDATE agent35_users SET payment_status='approved', plan=%s WHERE email=%s", (row['plan'], row['user_email']))
    conn.commit(); cur.close(); conn.close()
    return redirect('/master')

@app.route('/healthz')
def health():
    try:
        conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT 1"); cur.close(); conn.close()
        return jsonify({"status":"ok","bot":"Agent35","time":str(datetime.now())})
    except Exception as e: return jsonify({"status":"error","error":str(e)}),500

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',10000)))
