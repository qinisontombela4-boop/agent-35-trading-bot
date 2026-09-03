import os, hashlib, requests, psycopg, threading, time, csv, io
from psycopg.rows import dict_row
from flask import Flask, request, redirect, session, jsonify, Response
from datetime import datetime
from zoneinfo import ZoneInfo
import trading_engine as engine
import yfinance as yf
import traceback
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'agent35-secret-2025')
DATABASE_URL = os.environ.get('DATABASE_URL','').strip()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
TELEGRAM_BOT_USERNAME = "Sniper035_bot"
CAPITEC_ACC = "2586572676"
RISK_PCT = float(os.environ.get('RISK_PCT','1.5'))
LOGO_SVG = '<svg width="34" height="34" viewBox="0 0 100 100"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#059669"/></linearGradient></defs><rect width="100" height="100" rx="18" fill="#0b111c" stroke="#10b981" stroke-width="3"/><text x="50%" y="58%" dominant-baseline="middle" text-anchor="middle" font-family="Arial Black" font-weight="900" font-size="48" fill="url(#g)">35</text></svg>'
CUR = {'USD':'$','ZAR':'R','EUR':'€','GBP':'£'}
MAP = engine.MAP

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
*{box-sizing:border-box} body{background:#060a14;color:#e5e7eb;font-family:'Inter',sans-serif;margin:0}.header{background:#0b111c;border-bottom:1px solid #1a2535;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}.logo{display:flex;align-items:center;gap:10px;color:#10b981;font-weight:800}.card{background:#0e1625;border:1px solid #1c2a41;border-radius:16px;padding:16px;margin-bottom:14px}.btn{background:linear-gradient(135deg,#10b981,#059669);color:#000;font-weight:800;padding:12px 18px;border:none;border-radius:12px;cursor:pointer;text-decoration:none;display:block;text-align:center;width:100%}.btn-outline{background:transparent;border:1px solid #24344e;color:#cbd5e1;padding:12px 18px;border-radius:12px;text-decoration:none;display:block;text-align:center;width:100%;margin-top:8px}.btn-danger{background:#ef4444;color:#fff;padding:8px 14px;border:none;border-radius:10px;cursor:pointer;font-weight:700;font-size:12px;text-decoration:none;display:inline-block}.btn-test{background:#3b82f6;color:#fff;font-weight:700;padding:10px;border:none;border-radius:10px;width:100%;margin-top:8px;display:block;text-align:center;text-decoration:none}.grid{display:grid;gap:14px}.grid4{grid-template-columns:repeat(4,1fr)}.grid2{grid-template-columns:repeat(2,1fr)}.badge{padding:5px 10px;border-radius:20px;font-size:11px;font-weight:800}.bull{background:rgba(16,185,129,0.15);color:#10b981}.bear{background:rgba(239,68,68,0.15);color:#ef4444}.win{background:rgba(16,185,129,0.25);color:#10b981}.loss{background:rgba(239,68,68,0.25);color:#ef4444}.chip{display:inline-flex;align-items:center;gap:6px;background:#121d30;border:1px solid #1e2d45;padding:7px 12px;border-radius:24px;margin:4px;font-size:13px;cursor:pointer}.chip-active{background:#10b98122;border-color:#10b981}.x{background:#ef4444;color:#fff;border-radius:50%;width:20px;height:20px;display:inline-flex;justify-content:center;align-items:center;font-size:12px;margin-left:6px}.searchbox{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:12px;width:100%;margin:8px 0}.dropdown{background:#121d30;border:1px solid #1e2d45;border-radius:12px;max-height:200px;overflow:auto;display:none;position:absolute;z-index:50;width:calc(100% - 32px)}.dropdown div{padding:10px 14px;cursor:pointer;border-bottom:1px solid #1a2535} table{width:100%;border-collapse:collapse} th{color:#64748b;text-align:left;padding:10px 6px;font-size:10px;text-transform:uppercase} td{padding:10px 6px;border-top:1px solid #1a2535;font-size:12px}.nav-tabs{display:flex;gap:8px;overflow:auto;margin:12px 0}.nav-tabs a{white-space:nowrap;padding:10px 16px;border-radius:24px;background:#121d30;border:1px solid #1e2d45;color:#94a3b8;text-decoration:none;font-size:13px;font-weight:600}.nav-tabs a.active{background:#10b981;color:#000;border-color:#10b981}.stat-label{font-size:11px;color:#64748b;text-transform:uppercase}.stat-value{font-size:22px;font-weight:800;margin-top:6px} @media(max-width:900px){.grid4,.grid2{grid-template-columns:1fr 1fr}} @media(max-width:600px){.grid4,.grid2{grid-template-columns:1fr}table{display:block;overflow-x:auto}} input,select,textarea{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:10px;width:100%;margin:6px 0} label{font-size:12px;color:#94a3b8;margin-top:12px;display:block;font-weight:600}.settings-section{background:#0e1625;border:1px solid #1c2a41;border-radius:16px;padding:20px;margin-bottom:16px}.sess-check{display:flex;align-items:center;gap:8px;background:#121d30;padding:12px;border-radius:12px;border:1px solid #1e2d45;cursor:pointer}.sess-check input{width:18px;height:18px}
.clock-bar{display:flex;gap:10px;align-items:center;background:#121d30;border:1px solid #1e2d45;padding:6px 12px;border-radius:20px;font-size:11px;margin-left:12px}
.live-dot{width:8px;height:8px;background:#10b981;border-radius:50%;display:inline-block;animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}
.guide-step{background:#121d30;border-left:4px solid #10b981;padding:14px;margin:10px 0;border-radius:10px}
.plan-card{border:1px solid #1c2a41;background:linear-gradient(180deg,#0e1625,#0b111c);border-radius:18px;padding:22px;text-align:left;position:relative}
.plan-popular{border-color:#10b981;box-shadow:0 0 20px rgba(16,185,129,0.15)}
.plan-badge{position:absolute;top:-10px;right:16px;background:#10b981;color:#000;font-weight:800;font-size:11px;padding:4px 10px;border-radius:20px}
</style>
<script>
const ALL_SYMBOLS=["EURUSD","GBPUSD","USDJPY","EURJPY","GBPJPY","USDZAR","EURZAR","GBPZAR","ZARJPY","USDCHF","XAUUSD","GOLD","XAGUSD","BTCUSD","ETHUSD","SOLUSD","NAS100","US30","SPX500","GER40","UK100","JP225","USOIL","UKOIL","AAPL","TSLA","NVDA","MSFT"];
function addSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!='');if(arr.length>=5){alert('Max 5');return}if(!arr.includes(s)){arr.push(s);i.value=arr.join(',');document.getElementById('symForm').submit();}}
function removeSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!=s.trim()&&x.trim()!='');i.value=arr.join(',');document.getElementById('symForm').submit();}
function filterSyms(){let q=document.getElementById('symSearch').value.toUpperCase();let dd=document.getElementById('symDropdown');if(!q){dd.style.display='none';return}let f=ALL_SYMBOLS.filter(s=>s.includes(q)).slice(0,10);dd.innerHTML=f.map(s=>'<div onclick="addSym(\\''+s+'\\')"><b>'+s+'</b> - Click to Add</div>').join('');dd.style.display=f.length?'block':'none';}
document.addEventListener('click', function(e){let box=document.getElementById('symSearch');let dd=document.getElementById('symDropdown');if(dd && e.target!==box &&!dd.contains(e.target)){dd.style.display='none';}});
</script>
"""

def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode='require', connect_timeout=20)

def init_db():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_users (id SERIAL PRIMARY KEY, email TEXT UNIQUE, password TEXT,is_creator BOOLEAN DEFAULT FALSE, plan TEXT DEFAULT 'none',payment_ref TEXT, payment_status TEXT DEFAULT 'pending',risk_reward TEXT DEFAULT '1:3', symbols TEXT DEFAULT 'EURUSD,XAUUSD,BTCUSD,GBPUSD,NAS100',sessions TEXT DEFAULT 'London,New York', account_size FLOAT DEFAULT 10000,lot_size FLOAT DEFAULT 0.1, leverage TEXT DEFAULT '1:500',telegram_id TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_trades (id SERIAL PRIMARY KEY, user_email TEXT, symbol TEXT,direction TEXT, entry FLOAT, sl FLOAT, tp FLOAT,status TEXT DEFAULT 'sent', pnl FLOAT DEFAULT 0,timeframe_bias TEXT, confluence TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_payments (id SERIAL PRIMARY KEY, user_email TEXT, plan TEXT,ref_code TEXT UNIQUE, amount INT, status TEXT DEFAULT 'pending',created_at TIMESTAMP DEFAULT NOW());""")
    for q in ["ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USD'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS telegram_username TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency_symbol TEXT DEFAULT '$'","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS hit_entry_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS result_price FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS auto_updated BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS sessions TEXT DEFAULT 'London,New York'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_code TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referred_by TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_count INT DEFAULT 0","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'Africa/Johannesburg'","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS be_done BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS lock_done BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS close_r FLOAT DEFAULT 0","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS original_sl FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS original_entry FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT FALSE"]:
        try: cur.execute(q)
        except: pass
    conn.commit()
    cur.execute("SELECT * FROM agent35_users WHERE email='creator@agent35.com'")
    if not cur.fetchone():
        pw = hashlib.sha256('Agent35Creator!'.encode()).hexdigest()
        cur.execute("INSERT INTO agent35_users (email,password,is_creator,plan,payment_status,paid_at,sessions,referral_code,referral_count,timezone) VALUES (%s,%s,TRUE,'lifetime','approved',NOW(),'24/7',%s,0,'Africa/Johannesburg')", ('creator@agent35.com', pw, f"AG35-CREATOR-{os.urandom(2).hex().upper()}"))
    conn.commit(); cur.close(); conn.close()
init_db()

def send_telegram(chat_id, text, trade_id=None, stage="signal"):
    if not TELEGRAM_TOKEN or not chat_id: return False
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode":"Markdown"}
        if trade_id:
            if stage=="signal":
                payload["reply_markup"] = {"inline_keyboard": [[{"text":"✅ TOOK ENTRY","callback_data":f"took:{trade_id}"},{"text":"❌ SKIP","callback_data":f"skip:{trade_id}"}],[{"text":"📊 View Journal","url":"https://agent-35-trading-bot.onrender.com/journal"}]]}
            else:
                payload["reply_markup"] = {"inline_keyboard": [[{"text":"✅ WIN","callback_data":f"win:{trade_id}"},{"text":"❌ LOSS","callback_data":f"loss:{trade_id}"},{"text":"➖ BE","callback_data":f"be:{trade_id}"}],[{"text":"💰 CLOSE EARLY","callback_data":f"closeearly:{trade_id}"}]]}
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload, timeout=15)
        print(f"TG send {chat_id} {r.status_code}")
        return r.status_code==200
    except Exception as e:
        print(f"tg send err {e}")
        return False

SESSIONS_HOURS_UTC = {"Sydney": (22, 6),"Asia": (0, 9),"London": (8, 16),"New York": (13, 21)}
def is_session_active(user_sessions):
    if not user_sessions: return True
    us = user_sessions.strip()
    if "24/7" in us or "All" in us: return True
    now_hour = datetime.utcnow().hour
    for sess in [s.strip() for s in us.split(",")]:
        if sess not in SESSIONS_HOURS_UTC: continue
        start, end = SESSIONS_HOURS_UTC[sess]
        if start < end:
            if start <= now_hour < end: return True
        else:
            if now_hour >= start or now_hour < end: return True
    return False

def build_signal_msg(res, user=None):
    try:
        sym=res['symbol']; direction=res['direction']; entry=res['entry']; sl=res['sl']; tp=res['tp']; score=res['score']; confluence=res.get('confluence',[]); reason=res.get('reason',''); quality=res.get('quality','STANDARD')
        try:
            user_tz = (user.get('timezone') if user and user.get('timezone') else 'Africa/Johannesburg')
            now_local = datetime.now(ZoneInfo(user_tz)).strftime("%H:%M %Z")
            now_sast = datetime.now(ZoneInfo("Africa/Johannesburg")).strftime("%H:%M SAST")
        except:
            now_local=datetime.utcnow().strftime("%H:%M UTC"); now_sast=now_local
        rr_val=(tp-entry)/(entry-sl) if direction=="BUY" and (entry-sl)!=0 else (entry-tp)/(sl-entry) if (sl-entry)!=0 else 0
        acc = user.get('account_size',1000) if user else 1000
        risk_money = acc * (RISK_PCT/100)
        conf_text="\n".join([f"• {c}" for c in confluence[:8]])
        header="🔥🔥 SNIPER 🔥🔥" if "SNIPER" in quality else "🔥 PREMIUM" if "PREMIUM" in quality else "📊"
        emoji="🟢" if direction=="BUY" else "🔴"
        return f"{emoji} {sym} {direction} | {quality} {score}/8\n{header}\n💰 Entry: {entry}\n🛑 SL: {sl}\n🎯 TP: {tp}\n📊 RR: 1:{rr_val:.1f} | Risk: ${risk_money:.2f}\n\n🔍 Confluence:\n{conf_text}\n\n📝 {reason}\n⏰ {now_local} | {now_sast}\n"
    except Exception as e:
        return f"{res.get('symbol')} {res.get('direction')} {res.get('entry')} {e}"

def layout(content, email="", active="dashboard"):
    is_creator="creator" in email.lower()
    ad="active" if active=="dashboard" else ""; aj="active" if active=="journal" else ""; asi="active" if active=="signals" else ""; aset="active" if active=="settings" else ""; am="active" if active=="master" else ""; ag="active" if active=="guide" else ""; ap="active" if active=="payment" else ""
    master_tab=f'<a href="/master" class="{am}">Master</a>' if is_creator else ""
    tabs=f'<div class="nav-tabs"><a href="/dashboard" class="{ad}">Dashboard</a><a href="/journal" class="{aj}">Journal</a><a href="/signals" class="{asi}">All Signals</a><a href="/settings" class="{aset}">Settings</a><a href="/payment" class="{ap}">Plans</a><a href="/guide" class="{ag}">Guide</a>{master_tab}</div>'
    return f'<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Agent 35</title>{STYLE}</head><body><div class="header"><div class="logo">{LOGO_SVG} AGENT 35 <div class="clock-bar"><span class="live-dot"></span><span id="utcClock">UTC --:--:--</span> | <span id="sastClock">SAST --:--:--</span> | <span id="sessClock" style="color:#10b981;font-weight:800">Loading</span></div></div><div><span style="font-size:11px;color:#94a3b8">{email}</span> <a href="/logout" style="color:#94a3b8;text-decoration:none;margin-left:10px">Logout</a></div></div><div style="padding:14px;max-width:1400px;margin:auto">{tabs}{content}</div><script>function updateClock(){{const now=new Date();const utc=now.toISOString().substr(11,8);document.getElementById("utcClock").innerText="UTC "+utc;try{{const sast=new Date(now.toLocaleString("en-US",{{timeZone:"Africa/Johannesburg"}}));document.getElementById("sastClock").innerText="SAST "+sast.toLocaleTimeString("en-GB");}}catch(e){{document.getElementById("sastClock").innerText="SAST "+utc;}} const h=now.getUTCHours();let s=[];if(h>=22||h<6)s.push("Sydney");if(h>=0&&h<9)s.push("Asia");if(h>=8&&h<16)s.push("London");if(h>=13&&h<21)s.push("New York");if(s.length==0)s=["Off Hours"];document.getElementById("sessClock").innerText=s.join(" + ")+" ACTIVE";}} setInterval(updateClock,1000);updateClock();</script></body></html>'

def get_live_price(symbol):
    try:
        yfs = MAP.get(symbol.upper(), symbol.upper()+"=X")
        df = yf.download(yfs, period="1d", interval="5m", progress=False, auto_adjust=True)
        if df.empty: return None
        try: df.columns = df.columns.get_level_values(0)
        except: pass
        return float(df['Close'].iloc[-1]), float(df['High'].iloc[-1]), float(df['Low'].iloc[-1])
    except: return None

def calc_r_now(trade, close_price):
    risk = abs(trade['entry'] - trade['sl'])
    if risk == 0: return 0
    return (close_price - trade['entry']) / risk if trade['direction'] == 'BUY' else (trade['entry'] - close_price) / risk

@app.route('/')
def home():
    return f'<html><head><meta name="viewport" content="width=device-width, initial-scale=1">{STYLE}</head><body style="display:flex;justify-content:center;align-items:center;min-height:100vh;padding:16px"><div class="card" style="max-width:400px;width:100%;text-align:center;padding:28px"><h1 style="color:#10b981;margin:0">AGENT 35</h1><p>Professional Trading Signals</p><form method="POST" action="/auth" style="text-align:left;margin-top:18px"><label>Email</label><input name="email" required><label>Password</label><input name="password" type="password" required><button class="btn" style="margin-top:16px">Login</button></form></div></body></html>'

@app.route('/r/<code>')
def referral_link(code):
    session['ref_code']=code.upper().strip(); return redirect('/')

@app.route('/guide')
def guide_page():
    email=session.get('email','')
    content = """
    <h1 style='color:#10b981'>📘 How to Use Agent 35</h1>
    <div class='guide-step'><b>1️⃣ Getting Started</b><br>Choose your 5 favorite pairs in Dashboard, link Telegram, and start receiving signals.</div>
    <div class='guide-step'><b>2️⃣ Linking Telegram</b><br>- Dashboard -> Link TG -> Opens Telegram bot -> Click START -> Test TG to check</div>
    <div class='guide-step'><b>3️⃣ Understanding Signals</b><br>Each signal shows Symbol, Direction, Quality, Entry, SL, TP. Click ✅ TOOK when you take trade -> Goes to Journal. Click ❌ SKIP if not.</div>
    <div class='guide-step'><b>4️⃣ Dashboard</b><br>Watchlist max 5. SCAN manually checks. WR and profit from TOOK trades only.</div>
    <div class='guide-step'><b>5️⃣ Journal</b><br>Organized by month and day. Shows Took Time, Closed Time, Duration. Clear month if needed - full history stays in All Signals.</div>
    <div class='guide-step'><b>6️⃣ Settings</b><br>Set account size, sessions, timezone.</div>
    <div class='guide-step'><b>7️⃣ Tips</b><br>Focus on SNIPER and PREMIUM signals. Trade London+NY sessions. Always use Stop Loss.</div>
    <div class='card' style='text-align:center'><a class='btn' href='/dashboard'>Back to Dashboard</a></div>
    """
    return layout(content, email, "guide")

@app.route('/auth', methods=['POST'])
def auth():
    email=request.form['email'].lower().strip(); pw=hashlib.sha256(request.form['password'].encode()).hexdigest(); ref_by=session.get('ref_code')
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s AND password=%s", (email, pw)); u=cur.fetchone()
    if not u:
        my_code=f"AG35-{email[:3].upper()}-{os.urandom(2).hex().upper()}"
        cur.execute("INSERT INTO agent35_users (email,password,plan,payment_status,symbols,sessions,referral_code,referred_by,referral_count,timezone) VALUES (%s,%s,'none','pending','EURUSD,XAUUSD','London,New York',%s,%s,0,'Africa/Johannesburg') RETURNING *", (email,pw,my_code,ref_by)); u=cur.fetchone(); conn.commit()
    if not u.get('referral_code'):
        my_code=f"AG35-{u['email'][:3].upper()}-{os.urandom(2).hex().upper()}"
        cur.execute("UPDATE agent35_users SET referral_code=%s WHERE email=%s", (my_code, u['email'])); conn.commit(); u['referral_code']=my_code
    cur.close(); conn.close(); session['email']=u['email']; session['is_creator']=u['is_creator']; session.pop('ref_code', None)
    if u['is_creator']: return redirect('/master')
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND status IN ('took','active','win','loss','be','win_early') ORDER BY created_at DESC LIMIT 8", (session['email'],)); trades=cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as pnl, COUNT(*) FILTER (WHERE status='win' OR status='win_early') as wins, COUNT(*) FILTER (WHERE status='loss') as losses, COUNT(*) FILTER (WHERE status IN ('win','loss','be','win_early')) as closed, COALESCE(SUM(close_r),0) as total_r FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND status IN ('took','active','win','loss','be','win_early')", (session['email'],)); stats=cur.fetchone()
    cur.close(); conn.close()
    pnl=stats['pnl']; wr=(stats['wins']/stats['closed']*100) if stats['closed']>0 else 0; curr_sym=CUR.get(user['currency'],'$'); total_r = stats['total_r'] or 0
    syms=[s for s in (user['symbols'] or '').split(',') if s.strip()]; chips="".join([f"<span class='chip chip-active'><b>{s}</b><span class='x' onclick=\"removeSym('{s}')\">x</span></span>" for s in syms])
    rows="".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td><b>{t['symbol']}</b></td><td><span class='badge { 'win' if 'win' in t['status'] else 'loss' if t['status']=='loss' else 'bull'}'>{t['status'].upper()}</span></td><td>{curr_sym}{round(t['pnl'] or 0,2)} ({t.get('close_r',0)}R)</td></tr>" for t in trades]) or "<tr><td colspan=4>No trades yet</td></tr>"
    pay_ref=user['payment_ref'] or session['email']; sess_display=user['sessions'] or 'London,New York'
    content=f"<div class='card' style='padding:12px;display:flex;justify-content:space-between'><span>Sessions: <b>{sess_display}</b></span><span>WR: {wr:.1f}% | {total_r:.1f}R | {curr_sym}{pnl:.2f}</span></div><div class='grid grid4'><div class='card'><div class='stat-label'>Total Profit</div><div class='stat-value'>{curr_sym}{round(pnl,2)} <span class='badge bull'>{round(wr,1)}% {total_r:.1f}R</span></div></div><div class='card'><div class='stat-label'>Account Size</div><div class='stat-value' style='font-size:18px'>{curr_sym}{user['account_size']}</div><a href='/settings' class='btn-outline'>Edit</a></div><div class='card' style='position:relative'><div class='stat-label'>Watchlist {len(syms)}/5</div><div style='margin:12px 0'>{chips}</div><form id='symForm' method='POST' action='/quick-symbols'><input type='hidden' name='symbols' id='symInput' value=\"{user['symbols']}\"></form><input id='symSearch' class='searchbox' placeholder='Search pairs...' oninput='filterSyms()' autocomplete='off'><div id='symDropdown' class='dropdown'></div></div><div class='card'><a class='btn' href='/scan'>SCAN NOW</a><a href='https://t.me/{TELEGRAM_BOT_USERNAME}?start={pay_ref}' target='_blank' class='btn-outline'>Link Telegram</a><a href='/test-telegram' class='btn-test'>Test Telegram</a></div></div><div class='card' style='margin-top:14px'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th></tr>{rows}</table></div>"
    return layout(content, session['email'], "dashboard")

@app.route('/journal')
@app.route('/journal/<month_str>')
def journal(month_str=None):
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    cur.execute("SELECT DISTINCT TO_CHAR(created_at, 'YYYY-MM') as month, TO_CHAR(created_at, 'Mon YYYY') as month_label FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND status IN ('took','active','win','loss','be','win_early') ORDER BY month DESC", (session['email'],))
    months = cur.fetchall()
    if not month_str: month_str = months[0]['month'] if months else datetime.now().strftime('%Y-%m')
    cur.execute("SELECT *, EXTRACT(EPOCH FROM (closed_at - COALESCE(hit_entry_at, created_at)))/3600 as duration_hours FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND status IN ('took','active','win','loss','be','win_early') AND TO_CHAR(created_at, 'YYYY-MM') = %s ORDER BY created_at DESC", (session['email'], month_str))
    trades = cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as pnl, COUNT(*) FILTER (WHERE status='win' OR status='win_early') as wins, COUNT(*) FILTER (WHERE status='loss') as losses, COUNT(*) FILTER (WHERE status IN ('win','loss','be','win_early')) as closed, COALESCE(SUM(close_r),0) as total_r FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND TO_CHAR(created_at, 'YYYY-MM')=%s AND status IN ('took','active','win','loss','be','win_early')", (session['email'], month_str))
    stats = cur.fetchone(); cur.close(); conn.close()
    curr_sym=CUR.get(user['currency'],'$') if user else '$'; total_r = stats['total_r'] or 0; wr = (stats['wins']/stats['closed']*100) if stats['closed'] and stats['closed']>0 else 0
    def fmt(v):
        if v is None: return "-"
        try: return f"{float(v):.3f}" if float(v) > 100 else f"{float(v):.5f}".rstrip('0').rstrip('.')
        except: return str(v)
    def fmt_time(dt):
        if not dt: return "-"
        try: return dt.strftime('%H:%M:%S')
        except: return "-"
    def fmt_duration(hours):
        if hours is None: return "Open"
        try:
            h=float(hours)
            if h<0: return "Open"
            if h<1: return f"{int(h*60)}m"
            elif h<24: return f"{int(h)}h {int((h-int(h))*60)}m"
            else: return f"{int(h//24)}d {int(h%24)}h"
        except: return "-"
    def sl_status(t):
        entry = t.get('original_entry') or t.get('entry'); curr_sl = t.get('sl')
        if not entry or not curr_sl: return f"SL {fmt(curr_sl)}"
        try:
            if t.get('be_done') and abs(float(curr_sl)-float(entry))<0.001: return f"✅ BE {fmt(curr_sl)}"
            elif t.get('lock_done'): return f"🔒 +1R {fmt(curr_sl)}"
            else: return f"SL {fmt(curr_sl)}"
        except: return f"SL {fmt(curr_sl)}"
    month_tabs = "".join([f"<a href='/journal/{m['month']}' style='padding:8px 14px;border-radius:20px;text-decoration:none;font-size:12px;font-weight:700;margin:4px;display:inline-block;{'background:#10b981;color:#000' if m['month']==month_str else 'background:#121d30;color:#94a3b8;border:1px solid #1e2d45'}'>{m['month_label']}</a>" for m in months]) or "<span style='color:#64748b'>No months yet</span>"
    by_day = defaultdict(list)
    for t in trades:
        day_key = t['created_at'].strftime('%Y-%m-%d - %A')
        by_day[day_key].append(t)
    rows_html=""
    for day, day_trades in by_day.items():
        rows_html+=f"<tr style='background:#121d30'><td colspan=9 style='font-weight:800;color:#10b981;padding:10px'>📅 {day} - {len(day_trades)} trades</td></tr>"
        for t in day_trades:
            took_time = t.get('hit_entry_at') or t['created_at']; closed_time = t.get('closed_at')
            entry_d = fmt(t.get('original_entry') or t.get('entry')); orig_sl_d = fmt(t.get('original_sl') or t.get('sl')); tp_d = fmt(t.get('tp'))
            if entry_d=="-" and orig_sl_d=="-": continue
            rows_html+=f"<tr><td>{t['created_at'].strftime('%d')}</td><td style='font-size:11px'>{fmt_time(took_time)}</td><td style='font-size:11px'>{fmt_time(closed_time) if closed_time else '<span style=color:#f59e0b>Open</span>'}</td><td style='font-weight:700'>{fmt_duration(t.get('duration_hours'))}</td><td><b>{t['symbol']}</b> {t['direction']}</td><td style='font-size:11px'>{entry_d} / {orig_sl_d} / {tp_d}<br><span style='color:#94a3b8'>{sl_status(t)}</span></td><td><span class='badge win'>{t['status'].upper()}</span></td><td>{curr_sym}{round(t['pnl'] or 0,2)}</td><td><a href='/manual-close?id={t['id']}' style='color:#10b981'>Close</a></td></tr>"
    if not rows_html: rows_html="<tr><td colspan=9>No trades this month</td></tr>"
    content=f"<div class='card'><div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap'><h3>{month_str} - {wr:.1f}% | {total_r:.1f}R | {curr_sym}{stats['pnl']:.2f}</h3><a href='/clear-journal?month={month_str}' onclick=\"return confirm('Clear {month_str}?')\" class='btn-danger'>Clear {month_str}</a></div><div style='margin:12px 0'>{month_tabs}</div><div style='overflow:auto'><table><tr><th>Day</th><th>Took</th><th>Closed</th><th>Duration</th><th>Pair</th><th>Entry/SL/TP</th><th>Status</th><th>PNL</th><th>Action</th></tr>{rows_html}</table></div><br><div style='display:flex;gap:8px'><a class='btn' href='/signals'>All History</a><a class='btn-outline' href='/export-journal?month={month_str}'>Export CSV</a></div></div>"
    return layout(content, session['email'], "journal")

@app.route('/export-journal')
def export_journal():
    if 'email' not in session: return redirect('/')
    month_str = request.args.get('month')
    conn=get_conn(); cur=conn.cursor()
    if month_str: cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND TO_CHAR(created_at,'YYYY-MM')=%s AND archived=FALSE AND status IN ('took','active','win','loss','be','win_early') ORDER BY created_at", (session['email'], month_str))
    else: cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND status IN ('took','active','win','loss','be','win_early') ORDER BY created_at", (session['email'],))
    trades=cur.fetchall(); cur.close(); conn.close()
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(['Date','Day','Took Time','Closed Time','Duration Hours','Symbol','Direction','Entry','Original SL','Current SL','TP','Status','PNL','R'])
    for t in trades:
        took = t.get('hit_entry_at') or t['created_at']; closed = t.get('closed_at'); dur=""
        if took and closed:
            try: dur = round((closed - took).total_seconds()/3600, 2)
            except: pass
        writer.writerow([t['created_at'].strftime('%Y-%m-%d'), t['created_at'].strftime('%A'), took.strftime('%H:%M:%S') if took else "", closed.strftime('%H:%M:%S') if closed else "Open", dur, t['symbol'], t['direction'], t.get('original_entry') or t.get('entry'), t.get('original_sl') or t.get('sl'), t.get('sl'), t.get('tp'), t['status'], t.get('pnl',0), t.get('close_r',0)])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=journal_{month_str or 'all'}.csv"})

@app.route('/clear-journal')
def clear_journal():
    if 'email' not in session: return redirect('/')
    month_str = request.args.get('month')
    conn=get_conn(); cur=conn.cursor()
    if month_str: cur.execute("UPDATE agent35_trades SET archived=TRUE WHERE user_email=%s AND TO_CHAR(created_at,'YYYY-MM')=%s AND status IN ('took','active','win','loss','be','win_early')", (session['email'], month_str))
    else: cur.execute("UPDATE agent35_trades SET archived=TRUE WHERE user_email=%s AND status IN ('took','active','win','loss','be','win_early')", (session['email'],))
    conn.commit(); cur.close(); conn.close()
    return redirect(f'/journal/{month_str}' if month_str else '/journal')

@app.route('/signals')
def signals():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC LIMIT 300", (session['email'],)); trades=cur.fetchall()
    cur.execute("SELECT COUNT(*) FILTER (WHERE status='win' OR status='win_early') as wins, COUNT(*) FILTER (WHERE status='loss') as losses FROM agent35_trades WHERE user_email=%s", (session['email'],)); stats=cur.fetchone(); cur.close(); conn.close()
    def fmt(v):
        if v is None: return "-"
        try: return f"{float(v):.3f}" if float(v) > 100 else f"{float(v):.5f}"
        except: return str(v)
    bot_wr = (stats['wins']/(stats['wins']+stats['losses'])*100) if (stats['wins']+stats['losses'])>0 else 0
    rows="".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td>{t['symbol']} {t['direction']}</td><td>{fmt(t.get('original_entry') or t.get('entry'))} / {fmt(t.get('original_sl') or t.get('sl'))} / {fmt(t.get('tp'))}</td><td>{t['status'].upper()}</td><td>{round(t['pnl'] or 0,2)} ({t.get('close_r',0)}R)</td></tr>" for t in trades]) or "<tr><td colspan=5>No signals yet</td></tr>"
    content=f"<div class='card'><h3>Complete History - {bot_wr:.1f}% - {len(trades)} signals</h3><div style='overflow:auto'><table><tr><th>Date</th><th>Pair</th><th>Entry/SL/TP</th><th>Status</th><th>Result</th></tr>{rows}</table></div><br><a class='btn' href='/journal'>Back to Journal</a></div>"
    return layout(content, session['email'], "signals")

@app.route('/manual-close')
def manual_close():
    if 'email' not in session: return redirect('/')
    tid = request.args.get('id')
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT t.*, u.account_size FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.id=%s AND t.user_email=%s", (tid, session['email'])); tr=cur.fetchone()
    if not tr or tr['status'] not in ('took','active'): cur.close(); conn.close(); return layout("<div class='card'>Not open</div>", session['email'])
    live = get_live_price(tr['symbol']); close = live[0] if live else tr['entry']
    r_now = calc_r_now(tr, close); pnl = tr['account_size'] * 0.01 * r_now
    cur.execute("UPDATE agent35_trades SET status='win_early', pnl=%s, closed_at=NOW(), result_price=%s, close_r=%s, be_done=TRUE, lock_done=TRUE WHERE id=%s", (pnl, close, r_now, tid)); conn.commit(); cur.close(); conn.close()
    return redirect('/journal')

# PROFESSIONAL PAYMENT PAGE V9.4 - VIP REMOVED + 24H
@app.route('/payment')
def payment_page():
    ref=f"AG35-{datetime.now().strftime('%m%d')}-{os.urandom(2).hex().upper()}"
    email=session.get('email','')
    content=f"""
    <div style='max-width:900px;margin:auto'>
        <div style='text-align:center;margin-bottom:24px'>
            <h1 style='color:#10b981;margin:0'>Choose Your Plan</h1>
            <p style='color:#94a3b8'>Join traders using Agent 35 daily</p>
        </div>
        <div class='grid grid2'>
            <div class='plan-card'>
                <h3 style='margin:0;color:#fff'>Yearly Access</h3>
                <div style='font-size:32px;font-weight:800;color:#fff;margin:12px 0'>R500 <span style='font-size:14px;color:#94a3b8;font-weight:400'>/ year</span></div>
                <div style='color:#94a3b8;font-size:13px;line-height:22px'>
                    ✅ 5 Custom Watchlist Pairs<br>
                    ✅ Real-time Telegram Signals<br>
                    ✅ Smart Trade Management<br>
                    ✅ Monthly Journal + Analytics<br>
                    ✅ Priority Support
                </div>
                <a href='/submit-payment?ref={ref}&plan=yearly' class='btn-outline' style='margin-top:18px'>Select Yearly - R500</a>
            </div>
            <div class='plan-card plan-popular'>
                <div class='plan-badge'>MOST POPULAR</div>
                <h3 style='margin:0;color:#fff'>Lifetime Access</h3>
                <div style='font-size:32px;font-weight:800;color:#10b981;margin:12px 0'>R5000 <span style='font-size:14px;color:#94a3b8;font-weight:400'>/ once</span></div>
                <div style='color:#94a3b8;font-size:13px;line-height:22px'>
                    ✅ Everything in Yearly<br>
                    ✅ Lifetime Updates<br>
                    ✅ Never Pay Again<br>
                    ✅ 1-on-1 Setup Call
                </div>
                <a href='/submit-payment?ref={ref}&plan=lifetime' class='btn' style='margin-top:18px'>Select Lifetime - R5000</a>
            </div>
        </div>
        <div class='card' style='margin-top:20px'>
            <h3 style='color:#10b981;margin-top:0'>💳 How to Pay</h3>
            <div class='grid grid2'>
                <div>
                    <label style='color:#fff'>Bank: Capitec</label>
                    <div style='background:#070d1a;border:1px solid #1e2d45;padding:14px;border-radius:12px'>
                        <div>Account Number: <b style='color:#fff;font-size:16px'>{CAPITEC_ACC}</b></div>
                        <div style='margin-top:8px'>Reference: <b style='color:#10b981;font-size:18px'>{ref}</b></div>
                        <div style='font-size:11px;color:#64748b;margin-top:6px'>Use this exact reference for fast approval</div>
                    </div>
                </div>
                <div>
                    <label style='color:#fff'>After Payment</label>
                    <div style='background:#070d1a;border:1px solid #1e2d45;padding:14px;border-radius:12px'>
                        <div style='font-size:13px;color:#cbd5e1;line-height:20px'>
                        1. Pay with reference <b style='color:#10b981'>{ref}</b><br>
                        2. Click "I Have Paid" below<br>
                        3. Link Telegram for activation<br>
                        4. Approval within 24 hours
                        </div>
                    </div>
                </div>
            </div>
            <div style='margin-top:16px;display:flex;gap:10px;flex-wrap:wrap'>
                <a href='/submit-payment?ref={ref}&plan=yearly' class='btn' style='background:#121d30;color:#fff;border:1px solid #1e2d45'>I Paid R500 Yearly - {ref}</a>
                <a href='/submit-payment?ref={ref}&plan=lifetime' class='btn'>I Paid R5000 Lifetime - {ref}</a>
            </div>
            <p style='font-size:11px;color:#64748b;text-align:center;margin-top:12px'>Your reference {ref} is linked to {email} - Approval within 24 hours</p>
        </div>
    </div>
    """
    return layout(content, session.get('email',''), "payment")

@app.route('/submit-payment')
def submit_payment():
    if 'email' not in session: return redirect('/')
    ref=request.args.get('ref'); plan=request.args.get('plan'); amount=500 if plan=='yearly' else 5000
    conn=get_conn(); cur=conn.cursor()
    try: cur.execute("INSERT INTO agent35_payments (user_email,plan,ref_code,amount,status) VALUES (%s,%s,%s,%s,'pending') ON CONFLICT (ref_code) DO NOTHING", (session['email'],plan,ref,amount))
    except: cur.execute("INSERT INTO agent35_payments (user_email,plan,ref_code,amount,status) VALUES (%s,%s,%s,%s,'pending')", (session['email'],plan,ref,amount))
    cur.execute("UPDATE agent35_users SET payment_ref=%s, plan=%s, payment_status='pending' WHERE email=%s", (ref,plan,session['email'])); conn.commit(); cur.close(); conn.close()
    tg_link=f"https://t.me/{TELEGRAM_BOT_USERNAME}?start={ref}"
    return layout(f"<div class='card' style='text-align:center;max-width:500px;margin:auto'><h2 style='color:#10b981'>Payment Submitted: {ref}</h2><p style='color:#94a3b8'>We will verify and approve within 24 hours. Link Telegram now.</p><a href='{tg_link}' target='_blank' class='btn'>Link Telegram Now</a><a class='btn-outline' href='/dashboard'>Back</a></div>", session['email'])

@app.route('/test-telegram')
def test_telegram():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); u=cur.fetchone()
    if not u or not u.get('telegram_id'): cur.close(); conn.close(); return layout(f"<div class='card'><h3>Link Telegram first</h3></div>", session['email'])
    res = engine.full_multi_tf_analysis("USDCHF")
    msg = build_signal_msg(res if res.get('signal') else {'symbol': 'USDCHF','direction': 'BUY','entry': 0.79635,'sl': 0.79450,'tp': 0.80005,'score': 7,'quality': 'PREMIUM','bias': 'Bullish','confluence': ['Strong Trend','Key Level Retest','Momentum'],'reason': 'Test signal - Working!'}, u)
    ok = send_telegram(u['telegram_id'], f"🧪 Test Successful 🧪\n\n{msg}", trade_id=99999, stage="signal")
    cur.close(); conn.close()
    content = f"<div class='card' style='text-align:center'><h3 style='color:#10b981'>✅ Sent!</h3><div style='background:#070d1a;padding:12px;border-radius:10px;text-align:left;font-size:12px;white-space:pre-wrap'>{msg}</div><br><a class='btn' href='/dashboard'>Back</a></div>" if ok else "<div class='card'><h3>Failed</h3></div>"
    return layout(content, session['email'])

@app.route('/quick-symbols', methods=['POST'])
def quick_symbols():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("UPDATE agent35_users SET symbols=%s WHERE email=%s",(request.form['symbols'][:100], session['email'])); conn.commit(); cur.close(); conn.close(); return redirect('/dashboard')

@app.route('/scan')
def scan():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); user=cur.fetchone()
    symbols=(user['symbols'] or "EURUSD").split(",")[:5]; results=[]
    for sym in symbols:
        sym=sym.strip().upper()
        if not sym: continue
        try: res=engine.full_multi_tf_analysis(sym)
        except Exception as e: res={"signal":False,"symbol":sym,"reason":f"No setup"}
        res['symbol']=sym; results.append(res)
        if res.get('signal') and res.get('score',0) >= 4:
            cur.execute("SELECT id FROM agent35_trades WHERE user_email=%s AND symbol=%s AND status IN ('sent','took') AND archived=FALSE AND created_at > NOW() - INTERVAL '24 hours' LIMIT 1", (session['email'], sym))
            if cur.fetchone(): continue
            cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,original_entry,original_sl,timeframe_bias,confluence,status,be_done,lock_done,archived) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'sent',FALSE,FALSE,FALSE) RETURNING id",(session['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['entry'],res['sl'],res['bias'],str(res.get('confluence',''))))
            new_row=cur.fetchone(); tid=new_row['id'] if new_row else 0
            if user['telegram_id']:
                msg=build_signal_msg(res, user)
                send_telegram(user['telegram_id'], msg, trade_id=tid, stage="signal")
    conn.commit(); cur.close(); conn.close()
    html="".join([f"<div class='card' style='border-left:4px solid #10b981'><b>{r['symbol']} {r.get('direction','')} {r.get('score',0)}/8 {r.get('quality','')}</b><br>Entry {r.get('entry','')} SL {r.get('sl','')} TP {r.get('tp','')}</div>" if r.get('signal') else f"<div class='card' style='opacity:0.6'><b>{r['symbol']} - No setup</b></div>" for r in results])
    return layout(f"<h2>Scan Results</h2>{html}<br><a class='btn' href='/journal'>Journal</a>", session['email'])

@app.route('/settings', methods=['GET','POST'])
def settings():
    if 'email' not in session: return redirect('/')
    if request.method=='POST':
        sess_list=[];
        if request.form.get('sess_london'): sess_list.append("London")
        if request.form.get('sess_ny'): sess_list.append("New York")
        if request.form.get('sess_asia'): sess_list.append("Asia")
        if request.form.get('sess_sydney'): sess_list.append("Sydney")
        if request.form.get('sess_all'): sess_list=["24/7"]
        sessions_str=",".join(sess_list) if sess_list else "London,New York"
        tz = request.form.get('timezone','Africa/Johannesburg')
        try: ZoneInfo(tz)
        except: tz='Africa/Johannesburg'
        conn=get_conn(); cur=conn.cursor()
        cur.execute("UPDATE agent35_users SET symbols=%s, risk_reward=%s, account_size=%s, lot_size=%s, currency=%s, currency_symbol=%s, telegram_username=%s, sessions=%s, timezone=%s WHERE email=%s",(request.form['symbols'][:100], request.form['rr'], float(request.form['acc']), float(request.form['lot']), request.form['currency'], CUR.get(request.form['currency'],'$'), request.form['tg'], sessions_str, tz, session['email']))
        conn.commit(); cur.close(); conn.close(); return redirect('/dashboard')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); u=cur.fetchone(); cur.close(); conn.close()
    sel_usd="selected" if u['currency']=='USD' else ""; sel_zar="selected" if u['currency']=='ZAR' else ""; sel_eur="selected" if u['currency']=='EUR' else ""; sel_12="selected" if u['risk_reward']=='1:2' else ""; sel_13="selected" if u['risk_reward']=='1:3' else ""; sel_14="selected" if u['risk_reward']=='1:4' else ""
    sess=(u['sessions'] or 'London,New York'); c_london="checked" if "London" in sess else ""; c_ny="checked" if "New York" in sess else ""; c_asia="checked" if "Asia" in sess else ""; c_sydney="checked" if "Sydney" in sess else ""; c_all="checked" if "24/7" in sess else ""
    utz = u.get('timezone') or 'Africa/Johannesburg'
    content=f"<div style='max-width:700px;margin:auto'><h2 style='color:#10b981'>Settings</h2><form method='POST'><div class='settings-section'><div style='display:grid;grid-template-columns:1fr 1fr;gap:12px'><div><label>Currency</label><select name='currency'><option value='USD' {sel_usd}>USD</option><option value='ZAR' {sel_zar}>ZAR</option><option value='EUR' {sel_eur}>EUR</option></select></div><div><label>Account Size</label><input name='acc' type='number' value='{u['account_size']}'></div><div><label>Lot Size</label><input name='lot' type='number' step='0.01' value='{u['lot_size']}'></div><div><label>RR</label><select name='rr'><option {sel_12}>1:2</option><option {sel_13}>1:3</option><option {sel_14}>1:4</option></select></div></div><label>Symbols</label><input name='symbols' value='{u['symbols']}'><label>Telegram @</label><input name='tg' value='{u['telegram_username'] or ''}'><label>TZ</label><select name='timezone'><option value='{utz}' selected>{utz}</option><option value='Africa/Johannesburg'>Africa/Johannesburg</option><option value='Europe/London'>Europe/London</option><option value='America/New_York'>America/New_York</option><option value='UTC'>UTC</option></select><div style='margin-top:16px'><label>Sessions</label><div style='display:grid;grid-template-columns:1fr 1fr;gap:8px'><label class='sess-check'><input type='checkbox' name='sess_london' {c_london}> London</label><label class='sess-check'><input type='checkbox' name='sess_ny' {c_ny}> NY</label><label class='sess-check'><input type='checkbox' name='sess_asia' {c_asia}> Asia</label><label class='sess-check'><input type='checkbox' name='sess_sydney' {c_sydney}> Sydney</label></div><label class='sess-check' style='margin-top:8px'><input type='checkbox' name='sess_all' {c_all}> 24/7</label></div></div><button class='btn'>Save</button><a href='/dashboard' class='btn-outline'>Back</a></form></div>"
    return layout(content, session['email'], "settings")

@app.route('/telegram/webhook', methods=['POST'])
def tg_webhook():
    data=request.json
    try:
        conn=get_conn(); cur=conn.cursor()
        if 'callback_query' in data:
            cq=data['callback_query']; chat_id=cq['message']['chat']['id']; cdata=cq['data']
            parts=cdata.split(':'); action=parts[0]; tid=int(parts[1]) if len(parts)>1 else 0
            cur.execute("SELECT t.*, u.account_size, u.risk_reward, u.currency_symbol FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.id=%s", (tid,)); tr=cur.fetchone()
            if tr:
                if action=='took':
                    cur.execute("UPDATE agent35_trades SET status='took', hit_entry_at=NOW(), archived=FALSE WHERE id=%s", (tid,)); conn.commit()
                    send_telegram(chat_id, f"📝 {tr['symbol']} Tracking started", trade_id=tid, stage="active")
                elif action=='skip':
                    cur.execute("UPDATE agent35_trades SET status='skipped', be_done=TRUE, lock_done=TRUE WHERE id=%s", (tid,)); conn.commit()
                elif action=='closeearly':
                    live = get_live_price(tr['symbol']); close = live[0] if live else tr['entry']; r_now = calc_r_now(tr, close); risk_money = tr['account_size'] * 0.01; pnl = risk_money * r_now
                    cur.execute("UPDATE agent35_trades SET status='win_early', pnl=%s, closed_at=NOW(), result_price=%s, close_r=%s, be_done=TRUE, lock_done=TRUE WHERE id=%s", (pnl, close, r_now, tid)); conn.commit()
                elif action in ('win','loss','be'):
                    risk_money=tr['account_size']*0.01; rr=3
                    try: rr=int(tr['risk_reward'].split(':')[1])
                    except: pass
                    pnl=risk_money*rr if action=='win' else -risk_money if action=='loss' else 0; status='win' if action=='win' else 'loss' if action=='loss' else 'be'
                    close_r = rr if status=='win' else -1 if status=='loss' else 0
                    cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s, close_r=%s, be_done=TRUE, lock_done=TRUE WHERE id=%s", (status,pnl,tr['tp'] if status=='win' else tr['sl'],close_r,tid)); conn.commit()
            try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={"callback_query_id":cq['id'],"text":f"{action.upper()}"}, timeout=5)
            except: pass
            cur.close(); conn.close(); return jsonify({"ok":True})
        if 'message' in data:
            chat_id=data['message']['chat']['id']; username=data['message']['chat'].get('username',''); text=data['message'].get('text','').strip()
            ref=text.split('/start')[-1].strip() if '/start' in text else text.strip()
            if not ref: cur.close(); conn.close(); return jsonify({"ok":True})
            cur.execute("SELECT email FROM agent35_users WHERE payment_ref=%s OR email=%s OR payment_ref ILIKE %s", (ref, ref.lower(), f"%{ref}%")); row=cur.fetchone()
            if row:
                cur.execute("UPDATE agent35_users SET telegram_id=%s, telegram_username=%s WHERE email=%s", (str(chat_id), username, row['email'])); conn.commit()
                send_telegram(chat_id, f"✅ Linked! {row['email']}")
            cur.close(); conn.close()
    except Exception as e: print(f"tg error {e} {traceback.format_exc()}")
    return jsonify({"ok":True})

@app.route('/setup-webhook')
def setup_webhook():
    if 'email' not in session: return redirect('/')
    if not TELEGRAM_TOKEN: return "No TOKEN"
    base=request.host_url.rstrip('/'); wh_url=f"{base}/telegram/webhook"
    r=requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={wh_url}")
    return layout(f"<div class='card'><h3>Webhook</h3><p>{wh_url}</p><p>{r.text}</p><a class='btn' href='/master'>Back</a></div>", session['email'])

@app.route('/cron/update-trades')
def cron_update():
    def do_update():
        try:
            conn=get_conn(); cur=conn.cursor()
            cur.execute("SELECT t.*, u.account_size, u.risk_reward, u.telegram_id FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.status='took' AND t.archived=FALSE AND t.created_at > NOW() - INTERVAL '12 hours' LIMIT 20")
            rows=cur.fetchall()
            print(f"CRON update-trades checking {len(rows)} active")
            for tr in rows:
                live=get_live_price(tr['symbol'])
                if not live: continue
                close,high,low=live; r_now = calc_r_now(tr, close)
                if r_now >= 1.0 and not tr.get('be_done'):
                    cur.execute("UPDATE agent35_trades SET be_done=TRUE, sl=%s WHERE id=%s AND be_done=FALSE", (tr['entry'], tr['id']))
                    if cur.rowcount>0:
                        conn.commit()
                        if tr['telegram_id']: send_telegram(tr['telegram_id'], f"🔒 {tr['symbol']} +1R -> BE secured")
                    else: conn.rollback()
                rr=3
                try: rr=int(tr['risk_reward'].split(':')[1])
                except: pass
                risk_money=tr['account_size']*0.01; new=None; pnl=0; close_r=0
                if tr['direction']=='BUY':
                    if low <= tr['sl']: new='be' if tr.get('be_done') else 'loss'; pnl=0 if tr.get('be_done') else -risk_money; close_r=0 if tr.get('be_done') else -1
                    elif high >= tr['tp']: new='win'; pnl=risk_money*rr; close_r=rr
                else:
                    if high >= tr['sl']: new='be' if tr.get('be_done') else 'loss'; pnl=0 if tr.get('be_done') else -risk_money; close_r=0 if tr.get('be_done') else -1
                    elif low <= tr['tp']: new='win'; pnl=risk_money*rr; close_r=rr
                if new:
                    cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s, auto_updated=TRUE, close_r=%s, be_done=TRUE, lock_done=TRUE WHERE id=%s AND status='took'",(new,pnl,close,close_r,tr['id']))
                    if cur.rowcount>0:
                        conn.commit()
                        if tr['telegram_id']:
                            if new=='win': send_telegram(tr['telegram_id'], f"✅ {tr['symbol']} WIN +{rr}R")
                            elif new=='be': send_telegram(tr['telegram_id'], f"➖ {tr['symbol']} BE")
                            else: send_telegram(tr['telegram_id'], f"❌ {tr['symbol']} LOSS")
                    else: conn.rollback()
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            print(f"cron update err {e} {traceback.format_exc()}")
    threading.Thread(target=do_update, daemon=True).start()
    return jsonify({"ok":True, "version":"V9.4 AUTO-SCANNER FIXED"})

@app.route('/cron/scan-all')
def cron_scan_all():
    def do_scan():
        try:
            conn=get_conn(); cur=conn.cursor()
            # AUTO SCANNER FIX: scan approved + creator, not pending
            cur.execute("SELECT * FROM agent35_users WHERE (payment_status='approved' OR is_creator=TRUE) AND symbols IS NOT NULL AND telegram_id IS NOT NULL")
            users=cur.fetchall()
            print(f"CRON scan-all checking {len(users)} users")
            scanned=0
            for user in users:
                if not is_session_active(user['sessions'] or 'London,New York'):
                    print(f"Skip {user['email']} sessions inactive {user['sessions']}")
                    continue
                symbols=(user['symbols'] or "EURUSD").split(",")[:5]
                for sym in symbols:
                    sym=sym.strip().upper()
                    if not sym: continue
                    cur.execute("SELECT id FROM agent35_trades WHERE user_email=%s AND symbol=%s AND status IN ('sent','took') AND archived=FALSE AND created_at > NOW() - INTERVAL '12 hours' LIMIT 1", (user['email'], sym))
                    if cur.fetchone():
                        print(f"Dedup {user['email']} {sym}")
                        continue
                    try:
                        res=engine.full_multi_tf_analysis(sym)
                        print(f"Scan {sym} for {user['email']} -> {res.get('signal')} {res.get('score')}")
                    except Exception as e:
                        print(f"Scan err {sym} {e}")
                        continue
                    if res.get('signal') and res.get('score',0) >= 4:
                        cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,original_entry,original_sl,timeframe_bias,confluence,status,be_done,lock_done,archived) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'sent',FALSE,FALSE,FALSE) RETURNING id",(user['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['entry'],res['sl'],res['bias'],str(res.get('confluence',''))))
                        row=cur.fetchone()
                        conn.commit()
                        if row and user['telegram_id']:
                            msg=build_signal_msg(res, user)
                            send_telegram(user['telegram_id'], msg, trade_id=row['id'], stage="signal")
                            scanned+=1
            conn.commit(); cur.close(); conn.close()
            print(f"CRON scan-all done scanned={scanned}")
        except Exception as e:
            print(f"scan-all err {e} {traceback.format_exc()}")
    threading.Thread(target=do_scan, daemon=True).start()
    return jsonify({"ok":True, "msg":"Auto scanner started"})

@app.route('/healthz')
def health(): return jsonify({"status":"ok","version":"V9.4-FIXED-AUTO-SCANNER","utc":datetime.utcnow().isoformat()})

@app.route('/master')
def master():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],)); r=cur.fetchone()
    if not r or not r['is_creator']: cur.close(); conn.close(); return redirect('/dashboard')
    cur.execute("SELECT COUNT(*) as total FROM agent35_users"); total_users=cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) as c FROM agent35_users WHERE payment_status='approved'"); approved=cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM agent35_users WHERE payment_status='pending'"); pending=cur.fetchone()['c']
    cur.execute("SELECT * FROM agent35_payments WHERE status='pending' ORDER BY created_at DESC LIMIT 20"); payments=cur.fetchall()
    cur.execute("SELECT email, plan, payment_status, telegram_id, symbols, sessions FROM agent35_users ORDER BY created_at DESC LIMIT 30"); users=cur.fetchall()
    cur.close(); conn.close()
    pay_rows="".join([f"<tr><td>{p['ref_code']}</td><td>{p['user_email']}</td><td>{p['plan']} R{p['amount']}</td><td><a href='/master/approve?ref={p['ref_code']}' class='btn' style='padding:6px'>Approve</a></td></tr>" for p in payments]) or "<tr><td colspan=4>No pending</td></tr>"
    user_rows="".join([f"<tr><td>{u['email']}</td><td>{u['plan']}/{u['payment_status']}</td><td>{'✅' if u['telegram_id'] else '❌'}</td><td>{u['symbols']}</td><td>{u['sessions']}</td></tr>" for u in users])
    content=f"""
    <h1 style='color:#10b981'>👑 Master V9.4 Auto Scanner Fixed</h1>
    <div class='grid grid4'><div class='card'>Total {total_users}</div><div class='card'>Approved {approved}</div><div class='card'>Pending {pending}</div><div class='card'><a href='/cron/scan-all' target='_blank' class='btn'>TEST AUTO SCANNER NOW</a><p style='font-size:11px'>Check Render logs after clicking</p></div></div>
    <div class='card'><h3>Pending Payments</h3><table><tr><th>Ref</th><th>Email</th><th>Plan</th><th>Action</th></tr>{pay_rows}</table></div>
    <div class='card'><h3>Users</h3><table><tr><th>Email</th><th>Plan</th><th>TG</th><th>Symbols</th><th>Sessions</th></tr>{user_rows}</table></div>
    <div class='card'><a href='/setup-webhook' class='btn-outline'>Setup Webhook</a> <a href='/cron/update-trades' class='btn-outline'>Test Update Trades</a> <a href='/healthz' class='btn-outline'>Health</a></div>
    """
    return layout(content, session['email'], "master")

@app.route('/master/approve')
def master_approve():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],)); r=cur.fetchone()
    if not r or not r['is_creator']: cur.close(); conn.close(); return redirect('/dashboard')
    ref=request.args.get('ref')
    cur.execute("UPDATE agent35_payments SET status='approved' WHERE ref_code=%s", (ref,))
    cur.execute("UPDATE agent35_users SET payment_status='approved', paid_at=NOW() WHERE payment_ref=%s", (ref,))
    cur.execute("SELECT user_email FROM agent35_payments WHERE ref_code=%s", (ref,)); row=cur.fetchone(); conn.commit()
    if row:
        cur.execute("SELECT telegram_id FROM agent35_users WHERE email=%s", (row['user_email'],)); u=cur.fetchone()
        if u and u['telegram_id']: send_telegram(u['telegram_id'], f"✅ Payment {ref} Approved! Bot active within 24h - Start trading!")
    cur.close(); conn.close()
    return redirect('/master')

@app.route('/master/reject')
def master_reject():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],)); r=cur.fetchone()
    if not r or not r['is_creator']: cur.close(); conn.close(); return redirect('/dashboard')
    ref=request.args.get('ref')
    cur.execute("UPDATE agent35_payments SET status='rejected' WHERE ref_code=%s", (ref,)); conn.commit(); cur.close(); conn.close()
    return redirect('/master')

@app.route('/master/broadcast', methods=['POST'])
def master_broadcast():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],)); r=cur.fetchone()
    if not r or not r['is_creator']: cur.close(); conn.close(); return redirect('/dashboard')
    msg=request.form.get('message','')
    if msg:
        cur.execute("SELECT telegram_id FROM agent35_users WHERE telegram_id IS NOT NULL")
        for u in cur.fetchall(): send_telegram(u['telegram_id'], f"📢 {msg}")
    cur.close(); conn.close()
    return redirect('/master')

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

if __name__ == '__main__': app.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))
