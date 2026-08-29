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
    pnl = sum([t['pnl'] for t in trades]); winrate = len([t for t in trades if t['pnl']>0])/len(trades)*100 if trades else 0; took = len([t for t in trades if t['status']=='took'])
    content = f"""<div class='grid4'><div class='card
