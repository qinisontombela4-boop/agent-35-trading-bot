import os, hashlib, requests, psycopg
from psycopg.rows import dict_row
from flask import Flask, request, redirect, session, jsonify
from datetime import datetime
import trading_engine as engine

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
        cur.execute("""CREATE TABLE IF NOT EXISTS agent35_users (id SERIAL PRIMARY KEY, email TEXT UNIQUE, password TEXT,is_creator BOOLEAN DEFAULT FALSE, plan TEXT DEFAULT 'none',payment_ref TEXT, payment_status TEXT DEFAULT 'pending',risk_reward TEXT DEFAULT '1:3', symbols TEXT DEFAULT 'EURUSD,XAUUSD,BTCUSD,GBPUSD,NAS100',sessions TEXT DEFAULT 'London,New York', account_size FLOAT DEFAULT 10000,lot_size FLOAT DEFAULT 0.1, leverage TEXT DEFAULT '1:500',telegram_id TEXT, created_at TIMESTAMP DEFAULT NOW());""")
        cur.execute("""CREATE TABLE IF NOT EXISTS agent35_trades (id SERIAL PRIMARY KEY, user_email TEXT, symbol TEXT,direction TEXT, entry FLOAT, sl FLOAT, tp FLOAT,status TEXT DEFAULT 'sent', pnl FLOAT DEFAULT 0,timeframe_bias TEXT, confluence TEXT, created_at TIMESTAMP DEFAULT NOW());""")
        cur.execute("""CREATE TABLE IF NOT EXISTS agent35_payments (id SERIAL PRIMARY KEY, user_email TEXT, plan TEXT,ref_code TEXT UNIQUE, amount INT, status TEXT DEFAULT 'pending',created_at TIMESTAMP DEFAULT NOW());""")
        conn.commit()
        cur.execute("SELECT * FROM agent35_users WHERE email='creator@agent35.com'")
        if not cur.fetchone():
            pw = hashlib.sha256('Agent35Creator!'.encode()).hexdigest()
            cur.execute("INSERT INTO agent35_users (email,password,is_creator,plan,payment_status) VALUES (%s,%s,TRUE,'lifetime','approved')", ('creator@agent35.com', pw))
            pw2 = hashlib.sha256('Test123!'.encode()).hexdigest()
            cur.execute("INSERT INTO agent35_users (email,password,plan,payment_status,symbols) VALUES (%s,%s,'yearly','approved','EURUSD,XAUUSD')", ('test@agent35.com', pw2))
            conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        print(f"DB Init: {e}")

init_db()

LOGO_SVG = """<svg width="38" height="38" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#059669"/></linearGradient></defs><rect width="100" height="100" rx="18" fill="#0b111c" stroke="#10b981" stroke-width="3"/><text x="50%" y="58%" dominant-baseline="middle" text-anchor="middle" font-family="Arial Black" font-weight="900" font-size="48" fill="url(#g)">35</text><circle cx="78" cy="22" r="4" fill="#10b981"/></svg>"""

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
body{background:#05080f;color:#e5e7eb;font-family:'Inter',sans-serif;margin:0}
.header{background:#0b111c;border-bottom:1px solid #1a2535;padding:14px 24px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0}
.logo{display:flex;align-items:center;gap:10px;color:#10b981;font-weight:800;font-size:20px;letter-spacing:1px}
.card{background:#0b111c;border:1px solid #1a2535;border-radius:14px;padding:18px}
.btn{background:#10b981;color:#000;font-weight:800;padding:11px 18px;border:none;border-radius:10px;cursor:pointer;text-decoration:none;display:inline-block}
.btn-outline{background:transparent;border:1px solid #1a2535;color:#fff;padding:11px 18px;border-radius:10px;text-decoration:none}
.grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:20px 0}
.badge{padding:4px 10px;border-radius:20px;font-size:11px;font-weight:800}
.bull{background:rgba(16,185,129,0.12);color:#10b981;border:1px solid rgba(16,185,129,0.3)}
.bear{background:rgba(239,68,68,0.12);color:#ef4444;border:1px solid rgba(239,68,68,0.3)}
input,select{background:#05080f;border:1px solid #1a2535;color:#fff;padding:12px;border-radius:10px;width:100%;margin:6px 0}
table{width:100%;border-collapse:collapse} th{color:#6b7280;text-align:left;padding:12px;font-size:12px;text-transform:uppercase} td{padding:12px;border-top:1px solid #1a2535;font-size:14px}
a{color:#10b981}
</style>
"""

def layout(content, email=""):
    return f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1'>{STYLE}</head><body><div class='header'><div class='logo'>{LOGO_SVG} AGENT 35</div><div style='display:flex;gap:12px;align-items:center'><span style='font-size:12px;color:#9ca3af'>{email}</span><a href='/logout' class='btn-outline'>Logout</a></div></div><div style='padding:24px;max-width:1200px;margin:auto'>{content}</div></body></html>"

@app.route('/')
def home():
    return f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1'>{STYLE}</head><body style='display:flex;justify-content:center;align-items:center;height:100vh'><div class='card' style='width:380px;text-align:center;padding:32px'><div style='display:flex;justify-content:center;margin-bottom:12px'>{LOGO_SVG.replace('38','80').replace('38','80')}</div><h1 style='color:#10b981;margin:0'>AGENT 35</h1><p style='color:#9ca3af;margin-top:4px'>Professional Trading Intelligence</p><form method='POST' action='/auth' style='margin-top:20px;text-align:left'><input name='email' placeholder='Email' value='test@agent35.com' required><input name='password' type='password' placeholder='Password' value='Test123!' required><button class='btn' style='width:100%;margin-top:12px'>LOGIN TO DASHBOARD</button></form><p style='font-size:11px;color:#6b7280;margin-top:14px'>Creator: creator@agent35.com / Agent35Creator!<br>Test: test@agent35.com / Test123!</p></div></body></html>"

@app.route('/auth', methods=['POST'])
def auth():
    email = request.form['email'].lower().strip(); pw = hashlib.sha256(request.form['password'].encode()).hexdigest()
    try:
        conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s AND password=%s", (email, pw)); u=cur.fetchone(); cur.close(); conn.close()
        if u: session['email']=u['email']; session['is_creator']=u['is_creator']; return redirect('/master' if u['is_creator'] else '/dashboard')
    except Exception as e: return f"DB Error: {e} <a href='/'>back</a>"
    return "Invalid <a href='/'>back</a>"

@app.route('/dashboard')
def dashboard():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC LIMIT 25", (session['email'],)); trades=cur.fetchall(); cur.close(); conn.close()
    pnl = sum([t['pnl'] for t in trades]); winrate = len([t for t in trades if t['pnl']>0])/len(trades)*100 if trades else 0; took = len([t for t in
         trades if t['status']=='took'])
    content = f"""<div class='grid4'><div class='card'><div style='color:#9ca3af;font-size:12px'>TOTAL PNL</div><div style='font-size:22px;font-weight:800;margin-top:6px'>${round(pnl,2)} <span class='badge bull'>{round(winrate,1)}% WR</span></div><div style='font-size:12px;color:#6b7280;margin-top:6px'>{took} trades taken</div></div><div class='card'><div style='color:#9ca3af;font-size:12px'>ACCOUNT</div><div style='font-size:16px;font-weight:700;margin-top:6px'>${user['account_size']} | Lot {user['lot_size']}</div><div style='font-size:12px;color:#6b7280'>{user['leverage']} | RR {user['risk_reward']}</div></div><div class='card'><div style='color:#9ca3af;font-size:12px'>WATCHLIST (5 MAX)</div><div style='margin-top:8px'>{user['symbols']}</div><a href='/settings' style='font-size:12px'>Edit Symbols / Sessions</a></div><div class='card'><div style='color:#9ca3af;font-size:12px'>ACTIONS</div><div style='margin-top:10px;display:flex;gap:8px'><a class='btn' href='/scan'>🔍 SCAN MARKET</a><a class='btn-outline' href='/payment'>💳 Pay</a></div><div style='font-size:11px;color:#6b7280;margin-top:8px'>Sessions: {user['sessions']}</div></div></div><div class='card'><h3 style='margin:0 0 12px 0;color:#10b981'>Trading Journal - Auto Tracked from Telegram</h3><table><tr><th>Time</th><th>Symbol</th><th>Dir</th><th>Entry/SL/TP</th><th>Confluence</th><th>Status</th><th>PNL</th></tr>{''.join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td><b>{t['symbol']}</b></td><td><span class='badge { 'bull' if t['direction']=='BUY' else 'bear'}'>{t['direction']}</span></td><td>{t['entry']} / {t['sl']} / {t['tp']}</td><td style='font-size:11px'>{t['confluence'][:80]}</td><td>{t['status']}</td><td>{t['pnl']}</td></tr>" for t in trades])}</table></div>"""
    return layout(content, session['email'])

@app.route('/scan')
def scan():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT symbols FROM agent35_users WHERE email=%s",(session['email'],)); row=cur.fetchone()
    symbols = (row['symbols'] if row else "EURUSD").split(",")[:5]; results=[]
    for sym in symbols:
        sym=sym.strip().upper()
        if not sym: continue
        try: res = engine.full_multi_tf_analysis(sym)
        except Exception as e: res={"signal":False,"symbol":sym,"reason":str(e)}
        res['symbol']=sym; results.append(res)
        if res.get('signal'):
            cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,timeframe_bias,confluence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(session['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['bias'],res['confluence']))
            if TELEGRAM_TOKEN and TELEGRAM_CHAT:
                text = f"🎯 AGENT 35 {res['score']}/8\n{res['symbol']} {res['direction']}\nEntry {res['entry']} SL {res['sl']} TP {res['tp']}\n{res['confluence']}"
                try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id":TELEGRAM_CHAT,"text":text}, timeout=5)
                except: pass
    conn.commit(); cur.close(); conn.close()
    html_results=""
    for r in results:
        if r.get('signal'): html_results+= f"<div class='card' style='margin:12px 0;border-left:4px solid #10b981'><div style='display:flex;justify-content:space-between'><b>{r['symbol']} {r['direction']} - Score {r['score']}/8</b><span class='badge bull'>{r['zone']}</span></div><div style='margin:8px 0'>Entry {r['entry']} | SL {r['sl']} | TP {r['tp']}</div><div style='font-size:12px;color:#9ca3af'>{r['confluence']}</div></div>"
        else: html_results+= f"<div class='card' style='margin:12px 0;opacity:0.6'><b>{r['symbol']} - NO A+ SETUP</b> Score {r.get('score',0)}/8<br><span style='font-size:12px'>{r.get('reasons',r.get('reason','Waiting alignment'))}</span></div>"
    return layout(f"<h2 style='color:#10b981'>Scan Results - Multi TF SMC</h2><p style='color:#9ca3af'>Daily → 4H → 1H → 15M → 5M | OB, FVG, Liquidity Sweeps</p>{html_results}<br><a class='btn' href='/dashboard'>Back</a>", session['email'])

@app.route('/settings', methods=['GET','POST'])
def settings():
    if 'email' not in session: return redirect('/')
    if request.method=='POST':
        conn=get_conn(); cur=conn.cursor(); cur.execute("UPDATE agent35_users SET symbols=%s, sessions=%s, risk_reward=%s, account_size=%s, lot_size=%s WHERE email=%s",(request.form['symbols'][:100], request.form['sessions'], request.form['rr'], float(request.form['acc']), float(request.form['lot']), session['email'])); conn.commit(); cur.close(); conn.close(); return redirect('/dashboard')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); u=cur.fetchone(); cur.close(); conn.close()
    return layout(f"<div class='card' style='max-width:600px'><h3>Settings - Max 5 Symbols</h3><form method='POST'><label>Symbols</label><input name='symbols' value=\"{u['symbols']}\"><label>Sessions</label><input name='sessions' value=\"{u['sessions']}\"><label>RR</label><select name='rr'><option>1:2</option><option selected>1:3</option><option>1:4</option></select><label>Account Size</label><input name='acc' type='number' value=\"{u['account_size']}\"><label>Lot Size</label><input name='lot' type='number' step='0.01' value=\"{u['lot_size']}\"><button class='btn' style='margin-top:10px;width:100%'>Save</button></form></div>", session['email'])

@app.route('/master')
def master():
    if not session.get('is_creator'): return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users ORDER BY created_at DESC"); users=cur.fetchall(); cur.execute("SELECT * FROM agent35_payments ORDER BY created_at DESC"); pays=cur.fetchall(); cur.close(); conn.close()
    users_html="".join([f"<tr><td>{u['email']}</td><td>{u['plan']}</td><td>{u['payment_status']}</td><td>{u['symbols']}</td><td>{u['created_at'].strftime('%Y-%m-%d')}</td></tr>" for u in users])
    pays_html="".join([f"<div class='card' style='margin:8px 0;display:flex;justify-content:space-between'><span>{p['user_email']} - R{p['amount']} - {p['plan']} - Ref: {p['ref_code']} - {p['status']}</span><a class='btn' href='/approve/{p['id']}'>Approve</a></div>" for p in pays])
    return layout(f"<h1 style='color:#10b981'>MASTER DASHBOARD</h1><div class='grid4'><div class='card'>Users: {len(users)}</div><div class='card'>Pending: {len([p for p in pays if p['status']=='pending'])}</div><div class='card'>Capitec: {CAPITEC_ACC}</div><div class='card'><a class='btn' href='/scan'>Run Global Scan</a></div></div><div class='card'><h3>Payments</h3>{pays_html if pays_html else 'No payments'}</div><div class='card' style='margin-top:14px'><h3>All Users</h3><table><tr><th>Email</th><th>Plan</th><th>Status</th><th>Symbols</th><th>Joined</th></tr>{users_html}</table></div>", session['email'])

@app.route('/payment')
def payment_page():
    ref = f"AG35-{datetime.now().strftime('%m%d')}-{os.urandom(2).hex().upper()}"
    return layout(f"<div class='card' style='max-width:480px;margin:auto;text-align:center;padding:32px'><h2 style='color:#10b981'>Upgrade Agent 35</h2><p>Capitec: <b style='font-size:18px'>{CAPITEC_ACC}</b></p><div class='grid4' style='grid-template-columns:1fr 1fr'><div class='card' style='border:2px solid #10b981'><h3>R500</h3><p>Year</p></div><div class='card'><h3>R5000</h3><p>Lifetime</p></div></div><p>Ref: <b style='color:#10b981;font-size:18px'>{ref}</b><br><span style='font-size:11px;color:#9ca3af'>Use ref when paying. 24h verification</span></p><a class='btn' style='width:100%;margin:8px 0' href='/submit-payment?ref={ref}&plan=yearly'>I Paid R500 - {ref}</a><a class='btn' style='width:100%;background:#fff;color:#000' href='/submit-payment?ref={ref}&plan=lifetime'>I Paid R5000 - {ref}</a></div>", session.get('email',''))

@app.route('/submit-payment')
def submit_payment():
    if 'email' not in session: return redirect('/')
    ref=request.args.get('ref'); plan=request.args.get('plan'); amount = 500 if plan=='yearly' else 5000
    conn=get_conn(); cur=conn.cursor(); cur.execute("INSERT INTO agent35_payments (user_email,plan,ref_code,amount) VALUES (%s,%s,%s,%s)", (session['email'],plan,ref,amount)); cur.execute("UPDATE agent35_users SET payment_ref=%s, plan=%s, payment_status='pending' WHERE email=%s", (ref,plan,session['email'])); conn.commit(); cur.close(); conn.close()
    return layout(f"<div class='card' style='text-align:center'><h2>Payment Submitted ✅</h2><p>Ref {ref} - R{amount}</p><p>Verification up to 24h</p><a class='btn' href='/dashboard'>Back</a></div>", session['email'])

@app.route('/approve/<int:pid>')
def approve(pid):
    if not session.get('is_creator'): return "Not allowed"
    conn=get_conn(); cur=conn.cursor(); cur.execute("UPDATE agent35_payments SET status='approved' WHERE id=%s RETURNING user_email,plan", (pid,)); row=cur.fetchone()
    if row: cur.execute("UPDATE agent35_users SET payment_status='approved', plan=%s WHERE email=%s", (row['plan'], row['user_email']))
    conn.commit(); cur.close(); conn.close(); return redirect('/master')

@app.route('/healthz')
def health():
    try: conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT 1"); cur.close(); conn.close(); return jsonify({"status":"ok","bot":"Agent35"})
    except Exception as e: return jsonify({"status":"error","error":str(e)}),500

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

if __name__ == '__main__': app.run(host='0.0.0.0', port=int(os.environ.get('PORT',10000)))                                                                                                                                  
