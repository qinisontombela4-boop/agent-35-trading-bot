import os, hashlib, requests, psycopg, threading, time, csv, io, random
from psycopg.rows import dict_row
from flask import Flask, request, redirect, session, jsonify, Response
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import trading_engine as engine
import traceback
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'agent35-secret-2025')
DATABASE_URL = os.environ.get('DATABASE_URL','').strip()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN','').strip() or os.environ.get('BOT_TOKEN','').strip()
TELEGRAM_BOT_USERNAME = os.environ.get('BOT_USERNAME','Sniper035_bot')
CAPITEC_ACC = "2586572676"
RISK_PCT = float(os.environ.get('RISK_PCT','1.5'))
LOGO_SVG = '<svg width="34" height="34" viewBox="0 0 100 100"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#059669"/></linearGradient></defs><rect width="100" height="100" rx="18" fill="#0b111c" stroke="#10b981" stroke-width="3"/><text x="50%" y="58%" dominant-baseline="middle" text-anchor="middle" font-family="Arial Black" font-weight="900" font-size="48" fill="url(#g)">35</text></svg>'
CUR = {'USD':'$','ZAR':'R','EUR':'€','GBP':'£'}

FINNHUB_KEY = os.environ.get('FINNHUB_API_KEY','').strip()
TWELVE_KEY = os.environ.get('TWELVEDATA_API_KEY','').strip()
MAP = engine.MAP if hasattr(engine,'MAP') else {"XAUUSD":"XAUUSD","EURUSD":"EUR/USD","GBPUSD":"GBP/USD","USDJPY":"USD/JPY","EURJPY":"EUR/JPY","GBPJPY":"GBP/JPY","USDZAR":"USD/ZAR","BTCUSD":"BTC/USD","NAS100":"QQQ","US30":"DIA"}

# ===== DECIMAL FIX - PER SYMBOL =====
def format_price(symbol, price):
    if price is None: return "-"
    s = symbol.upper() if symbol else ""
    try:
        p = float(price)
        if "JPY" in s: return f"{p:.3f}"
        if "XAU" in s or "GOLD" in s: return f"{p:.2f}"
        if "XAG" in s: return f"{p:.3f}"
        if "BTC" in s: return f"{p:.2f}"
        if "ETH" in s: return f"{p:.2f}"
        if "NAS" in s or "US30" in s or "SPX" in s or "GER" in s or "UK100" in s or "USOIL" in s or "UKOIL" in s: return f"{p:.2f}"
        # Forex majors: EURUSD, GBPUSD etc = 5 decimals
        return f"{p:.5f}"
    except:
        return str(price)

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');
*{box-sizing:border-box} body{background:#060a14;color:#e5e7eb;font-family:'Inter',sans-serif;margin:0}
.header{background:#0b111c;border-bottom:1px solid #1a2535;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100;flex-wrap:wrap;gap:8px}
.logo{display:flex;align-items:center;gap:10px;color:#10b981;font-weight:800;font-family:'JetBrains Mono',monospace}
.card{background:#0e1625;border:1px solid #1c2a41;border-radius:16px;padding:16px;margin-bottom:14px}
.btn{background:linear-gradient(135deg,#10b981,#059669);color:#000;font-weight:800;padding:12px 18px;border:none;border-radius:12px;cursor:pointer;text-decoration:none;display:block;text-align:center;width:100%}
.btn-outline{background:transparent;border:1px solid #24344e;color:#cbd5e1;padding:12px 18px;border-radius:12px;text-decoration:none;display:block;text-align:center;width:100%;margin-top:8px}
.btn-danger{background:#ef4444;color:#fff;padding:8px 14px;border:none;border-radius:10px;cursor:pointer;font-weight:700;font-size:12px;text-decoration:none;display:inline-block}
.btn-test{background:#3b82f6;color:#fff;font-weight:700;padding:10px;border:none;border-radius:10px;width:100%;margin-top:8px;display:block;text-align:center;text-decoration:none}
.grid{display:grid;gap:14px}.grid4{grid-template-columns:repeat(4,1fr)}.grid2{grid-template-columns:repeat(2,1fr)}
.badge{padding:5px 10px;border-radius:20px;font-size:11px;font-weight:800}.bull{background:rgba(16,185,129,0.15);color:#10b981}.bear{background:rgba(239,68,68,0.15);color:#ef4444}.win{background:rgba(16,185,129,0.25);color:#10b981}.loss{background:rgba(239,68,68,0.25);color:#ef4444}
.chip{display:inline-flex;align-items:center;gap:6px;background:#121d30;border:1px solid #1e2d45;padding:7px 12px;border-radius:24px;margin:4px;font-size:13px;cursor:pointer}.chip-active{background:#10b98122;border-color:#10b981}.x{background:#ef4444;color:#fff;border-radius:50%;width:20px;height:20px;display:inline-flex;justify-content:center;align-items:center;font-size:12px;margin-left:6px}
.searchbox{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:12px;width:100%;margin:8px 0}
.dropdown{background:#121d30;border:1px solid #1e2d45;border-radius:12px;max-height:200px;overflow:auto;display:none;position:absolute;z-index:50;width:calc(100% - 32px)}.dropdown div{padding:10px 14px;cursor:pointer;border-bottom:1px solid #1a2535}
table{width:100%;border-collapse:collapse} th{color:#64748b;text-align:left;padding:10px 6px;font-size:10px;text-transform:uppercase} td{padding:10px 6px;border-top:1px solid #1a2535;font-size:12px}
.nav-tabs{display:flex;gap:8px;overflow:auto;margin:12px 0;padding-bottom:4px}.nav-tabs a{white-space:nowrap;padding:10px 18px;border-radius:24px;background:#121d30;border:1px solid #1e2d45;color:#94a3b8;text-decoration:none;font-size:13px;font-weight:600;transition:0.2s}.nav-tabs a.active{background:#10b981;color:#000;border-color:#10b981;box-shadow:0 0 15px rgba(16,185,129,0.3);font-weight:800}.nav-tabs a:hover{background:#1a2a40;color:#fff}
.stat-label{font-size:11px;color:#64748b;text-transform:uppercase}.stat-value{font-size:22px;font-weight:800;margin-top:6px}
input,select,textarea{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:10px;width:100%;margin:6px 0} label{font-size:12px;color:#94a3b8;margin-top:12px;display:block;font-weight:600}
.settings-section{background:#0e1625;border:1px solid #1c2a41;border-radius:16px;padding:20px;margin-bottom:16px}
.sess-check{display:flex;align-items:center;gap:8px;background:#121d30;padding:12px;border-radius:12px;border:1px solid #1e2d45;cursor:pointer}.sess-check input{width:18px;height:18px}
.clock-bar{display:flex;gap:10px;align-items:center;background:#121d30;border:1px solid #1e2d45;padding:6px 12px;border-radius:20px;font-size:11px}
.live-dot{width:8px;height:8px;background:#10b981;border-radius:50%;display:inline-block;animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}
.guide-step{background:#121d30;border-left:4px solid #10b981;padding:14px;margin:10px 0;border-radius:10px}
.plan-card{border:1px solid #1c2a41;background:linear-gradient(180deg,#0e1625,#0b111c);border-radius:18px;padding:22px;text-align:left;position:relative}
.plan-popular{border-color:#10b981;box-shadow:0 0 20px rgba(16,185,129,0.15)}
.plan-badge{position:absolute;top:-10px;right:16px;background:#10b981;color:#000;font-weight:800;font-size:11px;padding:4px 10px;border-radius:20px}
.news-check{border-color:#f59e0b!important;background:rgba(245,158,11,0.08)!important}
.refer-card{background:linear-gradient(135deg,#0e1625 0%,#112233 100%);border:1px solid #10b98155}
.paused-banner{background:linear-gradient(135deg,#ef4444 0%,#991b1b 100%);color:#fff;padding:14px;border-radius:12px;text-align:center;font-weight:800;margin-bottom:14px}
@media(max-width:900px){.grid4,.grid2{grid-template-columns:1fr 1fr}} @media(max-width:600px){.grid4,.grid2{grid-template-columns:1fr}table{display:block;overflow-x:auto}}
</style>
<script>
const ALL_SYMBOLS=["EURUSD","GBPUSD","USDJPY","EURJPY","GBPJPY","USDZAR","EURZAR","GBPZAR","ZARJPY","USDCHF","XAUUSD","GOLD","XAGUSD","BTCUSD","ETHUSD","SOLUSD","NAS100","US30","SPX500","GER40","UK100","JP225","USOIL","UKOIL","AAPL","TSLA","NVDA","MSFT"];
function addSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!='');if(arr.length>=5){alert('Max 5');return}if(!arr.includes(s)){arr.push(s);i.value=arr.join(',');document.getElementById('symForm').submit();}}
function removeSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!=s.trim()&&x.trim()!='');i.value=arr.join(',');document.getElementById('symForm').submit();}
function filterSyms(){let q=document.getElementById('symSearch').value.toUpperCase();let dd=document.getElementById('symDropdown');if(!q){dd.style.display='none';return}let f=ALL_SYMBOLS.filter(s=>s.includes(q)).slice(0,10);dd.innerHTML=f.map(s=>'<div onclick="addSym(\\''+s+'\\')"><b>'+s+'</b> - Click to Add</div>').join('');dd.style.display=f.length?'block':'none';}
document.addEventListener('click', function(e){let box=document.getElementById('symSearch');let dd=document.getElementById('symDropdown');if(dd && e.target!==box &&!dd.contains(e.target)){dd.style.display='none';}});
function copyRef(){let t=document.getElementById('refLink');t.select();t.setSelectionRange(0,99999);document.execCommand('copy');alert('Referral link copied!');}
</script>
"""

def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode='require', connect_timeout=20)

def init_db():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_users (id SERIAL PRIMARY KEY, email TEXT UNIQUE, password TEXT,is_creator BOOLEAN DEFAULT FALSE, plan TEXT DEFAULT 'none',payment_ref TEXT, payment_status TEXT DEFAULT 'pending',risk_reward TEXT DEFAULT '1:3', symbols TEXT DEFAULT 'EURUSD,XAUUSD,BTCUSD,GBPUSD,NAS100',sessions TEXT DEFAULT 'London,New York', account_size FLOAT DEFAULT 10000,lot_size FLOAT DEFAULT 0.1, leverage TEXT DEFAULT '1:500',telegram_id TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_trades (id SERIAL PRIMARY KEY, user_email TEXT, symbol TEXT,direction TEXT, entry FLOAT, sl FLOAT, tp FLOAT,status TEXT DEFAULT 'sent', pnl FLOAT DEFAULT 0,timeframe_bias TEXT, confluence TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_payments (id SERIAL PRIMARY KEY, user_email TEXT, plan TEXT,ref_code TEXT UNIQUE, amount INT, status TEXT DEFAULT 'pending',created_at TIMESTAMP DEFAULT NOW());""")
    for q in ["ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USD'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS telegram_username TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency_symbol TEXT DEFAULT '$'","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS hit_entry_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS result_price FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS auto_updated BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS sessions TEXT DEFAULT 'London,New York'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_code TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referred_by TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_count INT DEFAULT 0","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'Africa/Johannesburg'","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS be_done BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS lock_done BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS close_r FLOAT DEFAULT 0","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS original_sl FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS original_entry FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS news_filter BOOLEAN DEFAULT TRUE"]:
        try: cur.execute(q)
        except: pass
    conn.commit()
    cur.execute("SELECT * FROM agent35_users WHERE email='creator@agent35.com'")
    if not cur.fetchone():
        pw = hashlib.sha256('Agent35Creator!'.encode()).hexdigest()
        cur.execute("INSERT INTO agent35_users (email,password,is_creator,plan,payment_status,paid_at,sessions,referral_code,referral_count,timezone,news_filter) VALUES (%s,%s,TRUE,'lifetime','approved',NOW(),'24/7',%s,0,'Africa/Johannesburg',TRUE)", ('creator@agent35.com', pw, f"AG35-CREATOR-{os.urandom(2).hex().upper()}"))
    conn.commit(); cur.close(); conn.close()
init_db()

def is_subscription_active(user):
    if not user: return False
    if user.get('is_creator'): return True
    if user.get('payment_status')!= 'approved': return False
    if user.get('plan') == 'lifetime': return True
    if user.get('plan') == 'yearly':
        paid_at = user.get('paid_at')
        if not paid_at: return False
        try:
            now = datetime.now(ZoneInfo("UTC")); pa = paid_at
            if pa.tzinfo is None: pa = pa.replace(tzinfo=ZoneInfo("UTC"))
            if now - pa < timedelta(days=365): return True
        except:
            try:
                if datetime.utcnow() - paid_at.replace(tzinfo=None) < timedelta(days=365): return True
            except: pass
        return False
    return False

def send_telegram(chat_id, text, trade_id=None, stage="signal"):
    if not TELEGRAM_TOKEN or not chat_id: return False
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode":"Markdown"}
        if trade_id:
            if stage=="signal":
                payload["reply_markup"] = {"inline_keyboard": [[{"text":"✅ TOOK ENTRY","callback_data":f"took:{trade_id}"},{"text":"❌ SKIP","callback_data":f"skip:{trade_id}"}],[{"text":"📊 View Journal","url":f"{os.environ.get('RENDER_EXTERNAL_URL','https://agent-35-trading-bot.onrender.com')}/journal"}]]}
            else:
                payload["reply_markup"] = {"inline_keyboard": [[{"text":"✅ WIN","callback_data":f"win:{trade_id}"},{"text":"❌ LOSS","callback_data":f"loss:{trade_id}"},{"text":"➖ BE","callback_data":f"be:{trade_id}"}],[{"text":"💰 CLOSE EARLY","callback_data":f"closeearly:{trade_id}"}]]}
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload, timeout=15)
        return r.status_code==200
    except: return False

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
        news_warn = res.get('news_warning','')
        if news_warn: conf_text += f"\n\n⚠️ {news_warn}"
        header="🔥🔥 SNIPER 🔥🔥" if "SNIPER" in quality else "🔥 PREMIUM" if "PREMIUM" in quality else "📊"
        emoji="🟢" if direction=="BUY" else "🔴"
        entry_f = format_price(sym, entry)
        sl_f = format_price(sym, sl)
        tp_f = format_price(sym, tp)
        return f"{emoji} {sym} {direction} | {quality} {score}/8\n{header}\n💰 Entry: {entry_f}\n🛑 SL: {sl_f}\n🎯 TP: {tp_f}\n📊 RR: 1:{rr_val:.1f} | Risk: ${risk_money:.2f}\n\n🔍 Confluence:\n{conf_text}\n\n📝 {reason}\n⏰ {now_local} | {now_sast}\n"
    except Exception as e:
        return f"{res.get('symbol')} {res.get('direction')} {res.get('entry')} {e}"

def layout(content, email="", active="dashboard"):
    is_creator="creator" in email.lower()
    def a(tab): return "active" if active==tab else ""
    master_tab=f'<a href="/master" class="{a("master")}">Master</a>' if is_creator else ""
    tabs=f'<div class="nav-tabs"><a href="/dashboard" class="{a("dashboard")}">Dashboard</a><a href="/journal" class="{a("journal")}">Journal</a><a href="/signals" class="{a("signals")}">All Signals</a><a href="/settings" class="{a("settings")}">Settings</a><a href="/payment" class="{a("payment")}">Plans</a><a href="/referrals" class="{a("referrals")}">Refer & Earn</a><a href="/guide" class="{a("guide")}">Guide</a>{master_tab}</div>'
    return f'<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Agent 35 V12.6.1</title>{STYLE}</head><body><div class="header"><div class="logo">{LOGO_SVG} AGENT 35 <div class="clock-bar"><span class="live-dot"></span><span id="utcClock">UTC --:--:--</span> | <span id="sastClock">SAST --:--:--</span> | <span id="sessClock" style="color:#10b981;font-weight:800">Loading</span></div></div><div><span style="font-size:11px;color:#94a3b8">{email}</span> <a href="/logout" style="color:#94a3b8;text-decoration:none;margin-left:10px">Logout</a></div></div><div style="padding:14px;max-width:1400px;margin:auto">{tabs}{content}</div><script>function updateClock(){{const now=new Date();const utc=now.toISOString().substr(11,8);document.getElementById("utcClock").innerText="UTC "+utc;try{{const sast=new Date(now.toLocaleString("en-US",{{timeZone:"Africa/Johannesburg"}}));document.getElementById("sastClock").innerText="SAST "+sast.toLocaleTimeString("en-GB");}}catch(e){{document.getElementById("sastClock").innerText="SAST "+utc;}} const h=now.getUTCHours();let s=[];if(h>=22||h<6)s.push("Sydney");if(h>=0&&h<9)s.push("Asia");if(h>=8&&h<16)s.push("London");if(h>=13&&h<21)s.push("New York");if(s.length==0)s=["Off Hours"];document.getElementById("sessClock").innerText=s.join(" + ")+" ACTIVE";}} setInterval(updateClock,1000);updateClock();</script></body></html>'

def get_live_price(symbol):
    sym_clean = symbol.replace("GOLD","XAUUSD").replace(".X","").replace("=X","")
    try:
        if TWELVE_KEY:
            url=f"https://api.twelvedata.com/quote?symbol={sym_clean}&apikey={TWELVE_KEY}"
            r=requests.get(url,timeout=8).json()
            if 'close' in r and float(r['close'])>0:
                return float(r['close']), float(r.get('high',r['close'])), float(r.get('low',r['close']))
    except: pass
    try:
        if FINNHUB_KEY:
            fh_sym = f"OANDA:{sym_clean[:3]}_{sym_clean[3:]}" if len(sym_clean)==6 else sym_clean
            url=f"https://finnhub.io/api/v1/quote?symbol={fh_sym}&token={FINNHUB_KEY}"
            r=requests.get(url,timeout=8).json()
            if 'c' in r and r['c']>0:
                return float(r['c']), float(r.get('h',r['c'])), float(r.get('l',r['c']))
    except: pass
    return None

def calc_r_now(trade, close_price):
    risk = abs(trade['entry'] - trade['sl'])
    if risk == 0: return 0
    return (close_price - trade['entry']) / risk if trade['direction'] == 'BUY' else (trade['entry'] - close_price) / risk

@app.route('/')
def home():
    return f'<html><head><meta name="viewport" content="width=device-width, initial-scale=1">{STYLE}</head><body style="display:flex;justify-content:center;align-items:center;min-height:100vh;padding:16px"><div class="card" style="max-width:400px;width:100%;text-align:center;padding:28px"><h1 style="color:#10b981;margin:0">AGENT 35</h1><p>V12.6.1 DECIMAL FIX - Professional Tabs</p><form method="POST" action="/auth" style="text-align:left;margin-top:18px"><label>Email</label><input name="email" required><label>Password</label><input name="password" type="password" required><button class="btn" style="margin-top:16px">Login</button></form><p style="font-size:11px;color:#64748b;margin-top:12px">Referral? Use /r/CODE - 10 refs = Lifetime FREE</p></div></body></html>'

@app.route('/r/<code>')
def referral_link(code):
    session['ref_code']=code.upper().strip()
    return redirect('/')

@app.route('/guide')
def guide_page():
    email=session.get('email','')
    content = """
    <h1 style='color:#10b981'>📘 How to Use Agent 35 V12.6.1 DECIMAL FIX</h1>
    <div class='guide-step'><b>Auto Signals: Every 5 minutes</b><br><span style='color:#cbd5e1'>Same pair max 1 per 30 min. 10 pairs = R0 DUAL FREE. Decimals fixed: JPY=3, Gold=2, Forex=5.</span></div>
    <div class='guide-step'><b>Manual Scan: Every 5 minutes</b><br><span style='color:#cbd5e1'>SCAN NOW = 5M FVG + OB/MB + BOS/CHoCH.</span></div>
    <div class='guide-step'><b>Referral - 10 = Lifetime FREE</b><br><span style='color:#cbd5e1'>Share /r/YOURCODE.</span></div>
    <div class='card' style='text-align:center; margin-top:20px'><a class='btn' href='/dashboard'>Back to Dashboard</a></div>
    """
    return layout(content, email, "guide")

@app.route('/auth', methods=['POST'])
def auth():
    email=request.form['email'].lower().strip(); pw=hashlib.sha256(request.form['password'].encode()).hexdigest()
    ref_code_session=session.get('ref_code')
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s AND password=%s", (email, pw)); u=cur.fetchone()
    if not u:
        referred_by_email = None
        if ref_code_session:
            cur.execute("SELECT email FROM agent35_users WHERE referral_code=%s", (ref_code_session,))
            ref_row = cur.fetchone()
            if ref_row: referred_by_email = ref_row['email']
        my_code=f"AG35-{email[:3].upper()}-{os.urandom(2).hex().upper()}"
        cur.execute("INSERT INTO agent35_users (email,password,plan,payment_status,symbols,sessions,referral_code,referred_by,referral_count,timezone,news_filter) VALUES (%s,%s,'none','pending','EURUSD,XAUUSD','London,New York',%s,%s,0,'Africa/Johannesburg',TRUE) RETURNING *", (email,pw,my_code,referred_by_email)); u=cur.fetchone(); conn.commit()
    if not u.get('referral_code'):
        my_code=f"AG35-{u['email'][:3].upper()}-{os.urandom(2).hex().upper()}"
        cur.execute("UPDATE agent35_users SET referral_code=%s WHERE email=%s", (my_code, u['email'])); conn.commit(); u['referral_code']=my_code
    cur.close(); conn.close(); session['email']=u['email']; session['is_creator']=u['is_creator']
    if u['payment_status']=='pending' and not u['is_creator']:
        session.pop('ref_code', None)
        return redirect('/payment')
    session.pop('ref_code', None)
    if u['is_creator']: return redirect('/master')
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    if not user: cur.close(); conn.close(); return redirect('/logout')
    active_sub = is_subscription_active(user)
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND status IN ('took','active','win','loss','be','win_early') ORDER BY created_at DESC LIMIT 8", (session['email'],)); trades=cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as pnl, COUNT(*) FILTER (WHERE status='win' OR status='win_early') as wins, COUNT(*) FILTER (WHERE status='loss') as losses, COUNT(*) FILTER (WHERE status IN ('win','loss','be','win_early')) as closed, COALESCE(SUM(close_r),0) as total_r FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND status IN ('took','active','win','loss','be','win_early')", (session['email'],)); stats=cur.fetchone()
    cur.close(); conn.close()
    pnl=stats['pnl']; wr=(stats['wins']/stats['closed']*100) if stats['closed']>0 else 0; curr_sym=CUR.get(user['currency'],'$'); total_r = stats['total_r'] or 0
    syms=[s for s in (user['symbols'] or '').split(',') if s.strip()]
    chips="".join([f"<span class='chip chip-active'><b>{s}</b><span class='x' onclick=\"removeSym('{s}')\">x</span></span>" for s in syms])
    rows="".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td><b>{t['symbol']}</b></td><td><span class='badge win'>{t['status'].upper()}</span></td><td>{curr_sym}{round(t['pnl'] or 0,2)}</td></tr>" for t in trades]) or "<tr><td colspan=4>No trades yet</td></tr>"
    pay_ref=user['payment_ref'] or session['email']
    sess_display=user['sessions'] or 'London,New York'
    news_stat = "ON" if user.get('news_filter') else "OFF"
    base_url = request.host_url.rstrip('/')
    ref_code = user.get('referral_code') or ""; ref_link = f"{base_url}/r/{ref_code}" if ref_code else ""; ref_count = user.get('referral_count',0) or 0
    paused_html = "" if active_sub else f"<div class='paused-banner'>SIGNALS PAUSED - Ref: {user.get('payment_ref') or 'Not set'}<br><a href='/payment' style='color:#fff'>Go to Payment</a></div>"
    scan_style = "" if active_sub else "opacity:0.4;pointer-events:none"; scan_text = "SCAN NOW" if active_sub else "PAUSED"
    symbols_value = user.get('symbols','')
    refer_card = f"<div class='card refer-card'><div style='display:flex;justify-content:space-between'><b style='color:#10b981'>Refer & Earn - 10 = Lifetime FREE</b><span class='badge bull'>{ref_count}/10</span></div><div style='margin-top:10px;font-size:12px;color:#94a3b8'>Decimals fixed: JPY 3, Gold 2, Forex 5 | DUAL FREE R0</div><div style='margin-top:10px;display:flex;gap:6px'><input id='refLink' value='{ref_link}' readonly style='flex:1'><button onclick='copyRef()' class='btn' style='width:90px'>Copy</button></div><a href='/referrals' class='btn-outline' style='margin-top:6px'>View My Referrals</a></div>"
    content = f"{paused_html}<div class='card' style='padding:12px;display:flex;justify-content:space-between;flex-wrap:wrap'><span>Sessions: <b>{sess_display}</b> | News: <b>{news_stat}</b> | Plan: <b>{user.get('plan','none').upper()}</b> | V12.6.1 FIXED</span><span>WR: {wr:.1f}% | {total_r:.1f}R | {curr_sym}{pnl:.2f}</span></div><div class='grid grid4'><div class='card'><div class='stat-label'>Total Profit</div><div class='stat-value'>{curr_sym}{round(pnl,2)}</div></div><div class='card'><div class='stat-label'>Account</div><div class='stat-value' style='font-size:18px'>{curr_sym}{user['account_size']}</div><a href='/settings' class='btn-outline'>Edit</a></div><div class='card' style='position:relative'><div class='stat-label'>Watchlist {len(syms)}/5</div><div style='margin:12px 0'>{chips}</div><form id='symForm' method='POST' action='/quick-symbols'><input type='hidden' name='symbols' id='symInput' value='{symbols_value}'></form><input id='symSearch' class='searchbox' placeholder='Search pairs...' oninput='filterSyms()' autocomplete='off'><div id='symDropdown' class='dropdown'></div></div><div class='card'><a class='btn' href='/scan' style='{scan_style}'>{scan_text}</a><a href='https://t.me/{TELEGRAM_BOT_USERNAME}?start={pay_ref}' target='_blank' class='btn-outline'>Link Telegram</a><a href='/test-telegram' class='btn-test'>Test Telegram</a></div></div>{refer_card}<div class='card' style='margin-top:14px'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th></tr>{rows}</table></div>"
    return layout(content, session['email'], "dashboard")

@app.route('/referrals')
def referrals_page():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    cur.execute("SELECT email, plan, payment_status, paid_at, created_at FROM agent35_users WHERE referred_by=%s ORDER BY created_at DESC", (session['email'],)); referred=cur.fetchall()
    cur.execute("SELECT COUNT(*) as cnt FROM agent35_users WHERE referred_by=%s AND payment_status='approved'", (session['email'],)); approved_cnt=cur.fetchone()['cnt']
    if approved_cnt >= 10 and user['plan']!= 'lifetime':
        cur.execute("UPDATE agent35_users SET plan='lifetime', payment_status='approved', paid_at=NOW() WHERE email=%s", (session['email'],)); conn.commit()
        if user['telegram_id']: send_telegram(user['telegram_id'], "🎉 LIFETIME UNLOCKED! 10 paid referrals!")
        user['plan']='lifetime'
    cur.close(); conn.close()
    base_url = request.host_url.rstrip('/'); ref_link = f"{base_url}/r/{user['referral_code']}" if user.get('referral_code') else ""; ref_count = approved_cnt
    rows="".join([f"<tr><td>{r['email']}</td><td>{r['plan']}</td><td>{r['payment_status'].upper()}</td><td>{'PAID ✅' if r['payment_status']=='approved' else 'Pending'}</td><td>{r['created_at'].strftime('%Y-%m-%d')}</td></tr>" for r in referred]) or "<tr><td colspan=5>No referrals yet</td></tr>"
    progress = min(ref_count*10,100); left = max(0, 10-ref_count)
    content=f"<div class='card refer-card' style='text-align:center'><h2 style='color:#10b981;margin:0'>Refer & Earn Lifetime FREE</h2><p style='color:#94a3b8'>10 friends buy -> Lifetime auto FREE</p><div style='max-width:500px;margin:16px auto;display:flex;gap:6px'><input id='refLink' value='{ref_link}' readonly><button onclick='copyRef()' class='btn' style='width:90px'>Copy</button></div><div style='display:flex;justify-content:center;gap:12px;flex-wrap:wrap'><div class='card'><div class='stat-label'>Paid Referrals</div><div class='stat-value' style='color:#10b981'>{ref_count} / 10</div></div><div class='card'><div class='stat-label'>Progress</div><div class='stat-value'>{progress}%</div></div></div><div style='max-width:400px;margin:12px auto;background:#1a2535;height:14px;border-radius:14px;overflow:hidden'><div style='background:#10b981;height:14px;width:{progress}%'></div></div><div style='color:#94a3b8;font-size:12px'>{left} more needed</div></div><div class='card'><h3>My Referred Users</h3><table><tr><th>Email</th><th>Plan</th><th>Status</th><th>Counted</th><th>Date</th></tr>{rows}</table></div><div class='card'><a class='btn' href='/dashboard'>Back</a></div>"
    return layout(content, session['email'], "referrals")

@app.route('/journal')
@app.route('/journal/<month_str>')
def journal(month_str=None):
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    if not is_subscription_active(user) and not user.get('is_creator'):
        cur.close(); conn.close()
        return layout(f"<div class='paused-banner'>Journal Paused - <a href='/payment' style='color:#fff'>Pay Now</a></div>", session['email'], "journal")
    cur.execute("SELECT DISTINCT TO_CHAR(created_at, 'YYYY-MM') as month, TO_CHAR(created_at, 'Mon YYYY') as month_label FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND status IN ('took','active','win','loss','be','win_early') ORDER BY month DESC", (session['email'],))
    months = cur.fetchall()
    if not month_str: month_str = months[0]['month'] if months else datetime.now().strftime('%Y-%m')
    cur.execute("SELECT *, EXTRACT(EPOCH FROM (closed_at - COALESCE(hit_entry_at, created_at)))/3600 as duration_hours FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND status IN ('took','active','win','loss','be','win_early') AND TO_CHAR(created_at, 'YYYY-MM') = %s ORDER BY created_at DESC", (session['email'], month_str))
    trades = cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as pnl, COUNT(*) FILTER (WHERE status='win' OR status='win_early') as wins, COUNT(*) FILTER (WHERE status='loss') as losses, COUNT(*) FILTER (WHERE status IN ('win','loss','be','win_early')) as closed, COALESCE(SUM(close_r),0) as total_r FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND TO_CHAR(created_at, 'YYYY-MM')=%s AND status IN ('took','active','win','loss','be','win_early')", (session['email'], month_str))
    stats = cur.fetchone(); cur.close(); conn.close()
    curr_sym=CUR.get(user['currency'],'$') if user else '$'; total_r = stats['total_r'] or 0; wr = (stats['wins']/stats['closed']*100) if stats['closed'] and stats['closed']>0 else 0
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
        if not entry or not curr_sl: return f"SL {format_price(t['symbol'], curr_sl)}"
        try:
            if t.get('be_done') and abs(float(curr_sl)-float(entry))<0.001: return f"BE {format_price(t['symbol'], curr_sl)}"
            elif t.get('lock_done'): return f"+1R {format_price(t['symbol'], curr_sl)}"
            else: return f"SL {format_price(t['symbol'], curr_sl)}"
        except: return f"SL {format_price(t['symbol'], curr_sl)}"
    month_tabs = "".join([f"<a href='/journal/{m['month']}' style='padding:8px 14px;border-radius:20px;text-decoration:none;font-size:12px;font-weight:700;margin:4px;display:inline-block;{'background:#10b981;color:#000' if m['month']==month_str else 'background:#121d30;color:#94a3b8;border:1px solid #1e2d45'}'>{m['month_label']}</a>" for m in months]) or "<span style='color:#64748b'>No months</span>"
    by_day = defaultdict(list)
    for t in trades:
        day_key = t['created_at'].strftime('%Y-%m-%d - %A')
        by_day[day_key].append(t)
    rows_html=""
    for day, day_trades in by_day.items():
        rows_html+=f"<tr style='background:#121d30'><td colspan=9 style='font-weight:800;color:#10b981;padding:10px'>{day} - {len(day_trades)} trades</td></tr>"
        for t in day_trades:
            took_time = t.get('hit_entry_at') or t['created_at']; closed_time = t.get('closed_at')
            entry_d = format_price(t['symbol'], t.get('original_entry') or t.get('entry')); orig_sl_d = format_price(t['symbol'], t.get('original_sl') or t.get('sl')); tp_d = format_price(t['symbol'], t.get('tp'))
            if entry_d=="-" and orig_sl_d=="-": continue
            rows_html+=f"<tr><td>{t['created_at'].strftime('%d')}</td><td style='font-size:11px'>{fmt_time(took_time)}</td><td style='font-size:11px'>{fmt_time(closed_time) if closed_time else '<span style=color:#f59e0b>Open</span>'}</td><td style='font-weight:700'>{fmt_duration(t.get('duration_hours'))}</td><td><b>{t['symbol']}</b> {t['direction']}</td><td style='font-size:11px'>{entry_d} / {orig_sl_d} / {tp_d}<br><span style='color:#94a3b8'>{sl_status(t)}</span></td><td><span class='badge win'>{t['status'].upper()}</span></td><td>{curr_sym}{round(t['pnl'] or 0,2)}</td><td><a href='/manual-close?id={t['id']}' style='color:#10b981'>Close</a></td></tr>"
    if not rows_html: rows_html="<tr><td colspan=9>No trades this month</td></tr>"
    content=f"<div class='card'><div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap'><h3>{month_str} - {wr:.1f}% | {total_r:.1f}R | {curr_sym}{stats['pnl']:.2f} | FIXED DECIMALS</h3><a href='/clear-journal?month={month_str}' onclick=\"return confirm('Clear {month_str}?')\" class='btn-danger'>Clear {month_str}</a></div><div style='margin:12px 0'>{month_tabs}</div><div style='overflow:auto'><table><tr><th>Day</th><th>Took</th><th>Closed</th><th>Duration</th><th>Pair</th><th>Entry/SL/TP</th><th>Status</th><th>PNL</th><th>Action</th></tr>{rows_html}</table></div></div><div class='card'><a class='btn-outline' href='/export-journal?month={month_str}'>Export CSV</a> <a class='btn' href='/dashboard'>Dashboard</a></div>"
    return layout(content, session['email'], "journal")

@app.route('/export-journal')
def export_journal():
    if 'email' not in session: return redirect('/')
    month_str = request.args.get('month')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    if not is_subscription_active(user): cur.close(); conn.close(); return redirect('/payment')
    if month_str: cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND TO_CHAR(created_at,'YYYY-MM')=%s AND archived=FALSE AND status IN ('took','active','win','loss','be','win_early') ORDER BY created_at", (session['email'], month_str))
    else: cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND status IN ('took','active','win','loss','be','win_early') ORDER BY created_at", (session['email'],))
    trades=cur.fetchall(); cur.close(); conn.close()
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(['Date','Symbol','Direction','Entry','SL','TP','Status','PNL','R'])
    for t in trades:
        writer.writerow([t['created_at'].strftime('%Y-%m-%d'), t['symbol'], t['direction'], format_price(t['symbol'], t.get('original_entry') or t.get('entry')), format_price(t['symbol'], t.get('original_sl') or t.get('sl')), format_price(t['symbol'], t.get('tp')), t['status'], t.get('pnl',0), t.get('close_r',0)])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=journal_{month_str or 'all'}_v1261.csv"})

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
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    if not is_subscription_active(user) and not user.get('is_creator'):
        cur.close(); conn.close(); return layout(f"<div class='paused-banner'>Signals Paused - <a href='/payment' style='color:#fff'>Pay Now</a></div>", session['email'], "signals")
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC LIMIT 300", (session['email'],)); trades=cur.fetchall()
    cur.execute("SELECT COUNT(*) FILTER (WHERE status='win' OR status='win_early') as wins, COUNT(*) FILTER (WHERE status='loss') as losses FROM agent35_trades WHERE user_email=%s", (session['email'],)); stats=cur.fetchone(); cur.close(); conn.close()
    bot_wr = (stats['wins']/(stats['wins']+stats['losses'])*100) if (stats['wins']+stats['losses'])>0 else 0
    rows="".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td>{t['symbol']} {t['direction']}</td><td>{format_price(t['symbol'], t.get('original_entry') or t.get('entry'))} / {format_price(t['symbol'], t.get('original_sl') or t.get('sl'))} / {format_price(t['symbol'], t.get('tp'))}</td><td>{t['status'].upper()}</td><td>{round(t['pnl'] or 0,2)}</td></tr>" for t in trades]) or "<tr><td colspan=5>No signals - FIXED DECIMALS V12.6.1</td></tr>"
    content=f"<div class='card'><h3>Complete History - {bot_wr:.1f}% - {len(trades)} signals - FIXED DECIMALS</h3><div style='overflow:auto'><table><tr><th>Date</th><th>Pair</th><th>Entry/SL/TP</th><th>Status</th><th>Result</th></tr>{rows}</table></div><br><a class='btn' href='/journal'>Back to Journal</a></div>"
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

@app.route('/payment')
def payment_page():
    ref=f"AG35-{datetime.now().strftime('%m%d')}-{os.urandom(2).hex().upper()}"
    email = session.get('email',''); conn=get_conn(); cur=conn.cursor()
    u=None
    if email: cur.execute("SELECT * FROM agent35_users WHERE email=%s", (email,)); u=cur.fetchone()
    cur.close(); conn.close()
    paid_banner = f"<div class='card' style='background:#10b98122;border-color:#10b981;text-align:center'><b style='color:#10b981'>Your {u.get('plan')} plan is active - FIXED DECIMALS V12.6.1</b><br><a href='/referrals' class='btn' style='margin-top:10px'>Refer 10 = Lifetime FREE</a></div>" if u and is_subscription_active(u) else ""
    content=f"{paid_banner}<div style='max-width:900px;margin:auto'><div style='text-align:center;margin-bottom:24px'><h1 style='color:#10b981;margin:0'>Choose Your Plan - V12.6.1 FIXED</h1><p style='color:#94a3b8'>Decimals fixed: JPY 3, Gold 2, Forex 5 | R0 forever</p></div><div class='grid grid2'><div class='plan-card'><h3>Yearly Access</h3><div style='font-size:32px;font-weight:800'>R500 <span style='font-size:14px;color:#94a3b8'>/ year</span></div><p style='color:#94a3b8;font-size:12px'>✅ 5 pairs ✅ Telegram ✅ Journal</p><a href='/submit-payment?ref={ref}&plan=yearly' class='btn-outline' style='margin-top:18px'>Select Yearly - R500</a></div><div class='plan-card plan-popular'><div class='plan-badge'>MOST POPULAR</div><h3>Lifetime Access</h3><div style='font-size:32px;font-weight:800;color:#10b981'>R5000 <span style='font-size:14px;color:#94a3b8'>/ once</span></div><p style='color:#94a3b8;font-size:12px'>Everything + VIP</p><a href='/submit-payment?ref={ref}&plan=lifetime' class='btn' style='margin-top:18px'>Select Lifetime - R5000</a></div></div><div class='card' style='margin-top:20px'><h3 style='color:#10b981;margin-top:0'>💳 How to Pay - Capitec</h3><div>Account: <b>{CAPITEC_ACC}</b> | Reference: <b style='color:#10b981'>{ref}</b></div><p style='color:#94a3b8;font-size:11px'>Use reference {ref} exactly.</p><div style='margin-top:16px;display:flex;gap:10px;flex-wrap:wrap'><a href='/submit-payment?ref={ref}&plan=yearly' class='btn' style='background:#121d30;color:#fff;border:1px solid #1e2d45'>I Paid R500 - {ref}</a><a href='/submit-payment?ref={ref}&plan=lifetime' class='btn'>I Paid R5000 - {ref}</a></div></div></div>"
    return layout(content, email, "payment")

@app.route('/submit-payment')
def submit_payment():
    if 'email' not in session: return redirect('/')
    ref=request.args.get('ref'); plan=request.args.get('plan'); amount=500 if plan=='yearly' else 5000
    conn=get_conn(); cur=conn.cursor()
    try: cur.execute("INSERT INTO agent35_payments (user_email,plan,ref_code,amount,status) VALUES (%s,%s,%s,%s,'pending') ON CONFLICT (ref_code) DO NOTHING", (session['email'],plan,ref,amount))
    except: cur.execute("INSERT INTO agent35_payments (user_email,plan,ref_code,amount,status) VALUES (%s,%s,%s,%s,'pending')", (session['email'],plan,ref,amount))
    cur.execute("UPDATE agent35_users SET payment_ref=%s, plan=%s, payment_status='pending' WHERE email=%s", (ref,plan,session['email'])); conn.commit(); cur.close(); conn.close()
    tg_link=f"https://t.me/{TELEGRAM_BOT_USERNAME}?start={ref}"
    return layout(f"<div class='card' style='text-align:center;max-width:500px;margin:auto'><h2 style='color:#f59e0b'>Payment Submitted: {ref}</h2><p>Signals PAUSED until verified</p><a href='{tg_link}' target='_blank' class='btn'>Link Telegram</a><a class='btn-outline' href='/dashboard'>Back</a></div>", session['email'])

@app.route('/test-telegram')
def test_telegram():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); u=cur.fetchone()
    if not u or not u.get('telegram_id'): cur.close(); conn.close(); return layout(f"<div class='card'><h3>Link Telegram first</h3></div>", session['email'])
    use_news = u.get('news_filter', True)
    res = engine.full_multi_tf_analysis("USDCHF", use_news_filter=use_news)
    if not res.get('signal'):
        res = {'symbol': 'USDJPY','direction': 'BUY','entry': 156.258,'sl': 156.139,'tp': 156.554,'score': 8,'quality': 'PREMIUM SHIFT','confluence': ['HTF: Daily DISCOUNT 11% | 4H DISCOUNT 19%','🔥 5M SHIFT: BULLCHOCH in DISCOUNT','✅ 15M BULLFVG','✅ Daily DISCOUNT 11%'],'reason': 'HTF DISCOUNT + 5M BULLCHOCH + BULLFVG | Score 8/12 | FIXED DECIMALS','news_warning': ''}
    msg = build_signal_msg(res, u)
    ok = send_telegram(u['telegram_id'], f"✅ Test FIXED DECIMALS V12.6.1\n\n{msg}", trade_id=99999, stage="signal")
    cur.close(); conn.close()
    content = f"<div class='card' style='text-align:center'><h3 style='color:#10b981'>Sent! FIXED DECIMALS - JPY=3 Gold=2 Forex=5</h3><div style='background:#070d1a;padding:12px;border-radius:10px;text-align:left;font-size:12px;white-space:pre-wrap'>{msg}</div><br><a class='btn' href='/dashboard'>Back</a></div>" if ok else "<div class='card'><h3>Failed - Check BOT_TOKEN</h3></div>"
    return layout(content, session['email'])

@app.route('/quick-symbols', methods=['POST'])
def quick_symbols():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); u=cur.fetchone()
    if not is_subscription_active(u) and not u.get('is_creator'):
        cur.close(); conn.close()
        return layout(f"<div class='paused-banner'>Signals Paused</div>", session['email'])
    cur.execute("UPDATE agent35_users SET symbols=%s WHERE email=%s",(request.form['symbols'][:100], session['email'])); conn.commit(); cur.close(); conn.close(); return redirect('/dashboard')

@app.route('/scan')
def scan():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); user=cur.fetchone()
    if not is_subscription_active(user):
        cur.close(); conn.close()
        return layout(f"<div class='paused-banner'>SIGNALS PAUSED - Ref: {user.get('payment_ref','Not set')}<br><a href='/payment' style='color:#fff'>Pay Now</a></div>", session['email'])
    symbols=(user['symbols'] or "EURUSD").split(",")[:5]; results=[]; use_news = user.get('news_filter', True)
    for sym in symbols:
        sym=sym.strip().upper()
        if not sym: continue
        try: res=engine.full_multi_tf_analysis(sym, use_news_filter=use_news)
        except Exception as e: res={"signal":False,"symbol":sym,"reason":f"Error {e}"}
        res['symbol']=sym; results.append(res)
        if res.get('signal') and res.get('score',0) >= 4 and not res.get('news_block'):
            cur.execute("SELECT id FROM agent35_trades WHERE user_email=%s AND symbol=%s AND status IN ('sent','took') AND archived=FALSE AND created_at > NOW() - INTERVAL '5 minutes' LIMIT 1", (session['email'], sym))
            if cur.fetchone(): continue
            cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,original_entry,original_sl,timeframe_bias,confluence,status,be_done,lock_done,archived) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'sent',FALSE,FALSE,FALSE) RETURNING id",(session['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['entry'],res['sl'],res['bias'],str(res.get('confluence',''))))
            new_row=cur.fetchone(); tid=new_row['id'] if new_row else 0; conn.commit()
            if user['telegram_id']:
                msg=build_signal_msg(res, user); send_telegram(user['telegram_id'], msg, trade_id=tid, stage="signal")
    conn.commit(); cur.close(); conn.close()
    html="".join([f"<div class='card' style='border-left:4px solid #10b981'><b>{r['symbol']} {r.get('direction','')} {r.get('score',0)}/8</b><br>Entry {format_price(r['symbol'], r.get('entry',''))} SL {format_price(r['symbol'], r.get('sl',''))} TP {format_price(r['symbol'], r.get('tp',''))}</div>" if r.get('signal') else f"<div class='card' style='opacity:0.6'><b>{r['symbol']} - No setup</b></div>" for r in results])
    return layout(f"<h2>Scan Results V12.6.1 FIXED DECIMALS</h2>{html}<br><a class='btn' href='/journal'>Journal</a>", session['email'])

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
        news_filter = True if request.form.get('news_filter') else False
        conn=get_conn(); cur=conn.cursor()
        cur.execute("UPDATE agent35_users SET symbols=%s, risk_reward=%s, account_size=%s, lot_size=%s, currency=%s, currency_symbol=%s, telegram_username=%s, sessions=%s, timezone=%s, news_filter=%s WHERE email=%s",(request.form['symbols'][:100], request.form['rr'], float(request.form['acc']), float(request.form['lot']), request.form['currency'], CUR.get(request.form['currency'],'$'), request.form['tg'], sessions_str, tz, news_filter, session['email']))
        conn.commit(); cur.close(); conn.close(); return redirect('/dashboard')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); u=cur.fetchone(); cur.close(); conn.close()
    sel_usd="selected" if u['currency']=='USD' else ""; sel_zar="selected" if u['currency']=='ZAR' else ""; sel_eur="selected" if u['currency']=='EUR' else ""; sel_12="selected" if u['risk_reward']=='1:2' else ""; sel_13="selected" if u['risk_reward']=='1:3' else ""; sel_14="selected" if u['risk_reward']=='1:4' else ""
    sess=(u['sessions'] or 'London,New York'); c_london="checked" if "London" in sess else ""; c_ny="checked" if "New York" in sess else ""; c_asia="checked" if "Asia" in sess else ""; c_sydney="checked" if "Sydney" in sess else ""; c_all="checked" if "24/7" in sess else ""
    utz = u.get('timezone') or 'Africa/Johannesburg'; news_checked = "checked" if u.get('news_filter', True) else ""
    content=f"<div style='max-width:700px;margin:auto'><h2 style='color:#10b981'>Settings - V12.6.1 FIXED DECIMALS</h2><div class='card' style='background:#10b98122;border-color:#10b981'><b>DECIMALS FIXED:</b> JPY=3 | XAU=2 | Forex=5 | Twelve: {'YES' if TWELVE_KEY else 'NO'} Finnhub: {'YES' if FINNHUB_KEY else 'NO'}</div><form method='POST'><div class='settings-section'><div style='display:grid;grid-template-columns:1fr 1fr;gap:12px'><div><label>Currency</label><select name='currency'><option value='USD' {sel_usd}>USD</option><option value='ZAR' {sel_zar}>ZAR</option><option value='EUR' {sel_eur}>EUR</option></select></div><div><label>Account Size</label><input name='acc' type='number' value='{u['account_size']}'></div><div><label>Lot Size</label><input name='lot' type='number' step='0.01' value='{u['lot_size']}'></div><div><label>RR</label><select name='rr'><option {sel_12}>1:2</option><option {sel_13}>1:3</option><option {sel_14}>1:4</option></select></div></div><label>Symbols (5 max)</label><input name='symbols' value='{u['symbols']}'><label>Telegram @</label><input name='tg' value='{u['telegram_username'] or ''}'><label>TZ</label><select name='timezone'><option value='{utz}' selected>{utz}</option><option value='Africa/Johannesburg'>Africa/Johannesburg</option><option value='Europe/London'>Europe/London</option><option value='America/New_York'>America/New_York</option><option value='UTC'>UTC</option></select><div style='margin-top:16px'><label>Sessions</label><div style='display:grid;grid-template-columns:1fr 1fr;gap:8px'><label class='sess-check'><input type='checkbox' name='sess_london' {c_london}> London</label><label class='sess-check'><input type='checkbox' name='sess_ny' {c_ny}> NY</label><label class='sess-check'><input type='checkbox' name='sess_asia' {c_asia}> Asia</label><label class='sess-check'><input type='checkbox' name='sess_sydney' {c_sydney}> Sydney</label></div><label class='sess-check' style='margin-top:8px'><input type='checkbox' name='sess_all' {c_all}> 24/7</label></div><div style='margin-top:18px'><label>News Filter</label><label class='sess-check news-check'><input type='checkbox' name='news_filter' {news_checked}> Avoid News</label></div></div><button class='btn'>Save</button><a href='/dashboard' class='btn-outline'>Back</a></form></div>"
    return layout(content, session['email'], "settings")

@app.route('/telegram/webhook', methods=['POST'])
def tg_webhook():
    data=request.json
    try:
        conn=get_conn(); cur=conn.cursor()
        if 'callback_query' in data:
            cq=data['callback_query']; chat_id=cq['message']['chat']['id']; cdata=cq['data']
            parts=cdata.split(':'); action=parts[0]; tid=int(parts[1]) if len(parts)>1 else 0
            cur.execute("SELECT t.*, u.account_size, u.risk_reward, u.currency_symbol, u.payment_status, u.plan, u.is_creator, u.paid_at FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.id=%s", (tid,)); tr=cur.fetchone()
            if tr:
                if action=='took':
                    if not is_subscription_active(tr):
                        send_telegram(chat_id, "Signals paused - renew")
                    else:
                        cur.execute("UPDATE agent35_trades SET status='took', hit_entry_at=NOW(), archived=FALSE WHERE id=%s", (tid,)); conn.commit()
                        send_telegram(chat_id, f"{tr['symbol']} Tracking - {format_price(tr['symbol'], tr['entry'])}", trade_id=tid, stage="active")
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
            cur.execute("SELECT email FROM agent35_users WHERE payment_ref=%s OR email=%s OR payment_ref ILIKE %s OR referral_code=%s", (ref, ref.lower(), f"%{ref}%", ref)); row=cur.fetchone()
            if row:
                cur.execute("UPDATE agent35_users SET telegram_id=%s, telegram_username=%s WHERE email=%s", (str(chat_id), username, row['email'])); conn.commit()
                send_telegram(chat_id, f"Linked! {row['email']} - V12.6.1 FIXED DECIMALS Ready!")
            cur.close(); conn.close()
    except Exception as e: print(f"tg error {e} {traceback.format_exc()}")
    return jsonify({"ok":True})

@app.route('/setup-webhook')
def setup_webhook():
    if 'email' not in session: return redirect('/')
    if not TELEGRAM_TOKEN: return "No TOKEN"
    base=request.host_url.rstrip('/'); wh_url=f"{base}/telegram/webhook"
    r=requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={wh_url}")
    return layout(f"<div class='card'><h3>Webhook V12.6.1 FIXED</h3><p>{wh_url}</p><p>{r.text}</p><a class='btn' href='/master'>Back</a></div>", session['email'])

@app.route('/cron/update-trades')
def cron_update():
    def do_update():
        try:
            conn=get_conn(); cur=conn.cursor()
            cur.execute("SELECT t.*, u.account_size, u.risk_reward, u.telegram_id, u.payment_status, u.plan, u.is_creator, u.paid_at FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.status='took' AND t.archived=FALSE AND t.created_at > NOW() - INTERVAL '12 hours' LIMIT 20")
            rows=cur.fetchall()
            for tr in rows:
                if not is_subscription_active(tr): continue
                live=get_live_price(tr['symbol'])
                if not live: continue
                close,high,low=live; r_now = calc_r_now(tr, close)
                if r_now >= 1.0 and not tr.get('be_done'):
                    cur.execute("UPDATE agent35_trades SET be_done=TRUE, sl=%s WHERE id=%s AND be_done=FALSE", (tr['entry'], tr['id']))
                    if cur.rowcount>0:
                        conn.commit()
                        if tr['telegram_id']: send_telegram(tr['telegram_id'], f"{tr['symbol']} +1R -> BE {format_price(tr['symbol'], tr['entry'])}")
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
                    if cur.rowcount>0: conn.commit()
                    else: conn.rollback()
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            print(f"cron update err {e} {traceback.format_exc()}")
    threading.Thread(target=do_update, daemon=True).start()
    return jsonify({"ok":True})

@app.route('/cron/scan-all')
def cron_scan_all():
    def do_scan():
        try:
            conn=get_conn(); cur=conn.cursor()
            cur.execute("SELECT * FROM agent35_users WHERE payment_status='approved' AND symbols IS NOT NULL AND telegram_id IS NOT NULL")
            users=cur.fetchall()
            for user in users:
                if not is_subscription_active(user): continue
                if not is_session_active(user['sessions'] or 'London,New York'): continue
                symbols=(user['symbols'] or "EURUSD").split(",")[:5]
                use_news = user.get('news_filter', True)
                for sym in symbols:
                    sym=sym.strip().upper()
                    if not sym: continue
                    cur.execute("SELECT direction FROM agent35_trades WHERE user_email=%s AND symbol=%s AND status IN ('sent','took') AND archived=FALSE AND created_at > NOW() - INTERVAL '30 minutes' ORDER BY created_at DESC LIMIT 1", (user['email'], sym))
                    last = cur.fetchone()
                    try: res=engine.full_multi_tf_analysis(sym, use_news_filter=use_news)
                    except: continue
                    if res.get('news_block'): continue
                    if last:
                        if last['direction'] == res.get('direction'): continue
                        else:
                            cur.execute("SELECT id FROM agent35_trades WHERE user_email=%s AND symbol=%s AND created_at > NOW() - INTERVAL '15 minutes' LIMIT 1", (user['email'], sym))
                            if cur.fetchone(): continue
                    if not res.get('signal') or res.get('score',0) < 4: continue
                    cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,original_entry,original_sl,timeframe_bias,confluence,status,be_done,lock_done,archived) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'sent',FALSE,FALSE,FALSE) RETURNING id",(user['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['entry'],res['sl'],res['bias'],str(res.get('confluence',''))))
                    row=cur.fetchone(); conn.commit()
                    if row and user['telegram_id']:
                        msg=build_signal_msg(res, user)
                        send_telegram(user['telegram_id'], msg, trade_id=row['id'], stage="signal")
                    time.sleep(4)
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            print(f"scan-all err {e} {traceback.format_exc()}")
    threading.Thread(target=do_scan, daemon=True).start()
    return jsonify({"ok":True})

@app.route('/healthz')
def health(): return jsonify({"status":"ok","version":"V12.6.1-FIXED-DECIMALS","utc":datetime.utcnow().isoformat(),"finnhub": "YES" if FINNHUB_KEY else "NO","twelve": "YES" if TWELVE_KEY else "NO"})

@app.route('/master')
def master():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],)); r=cur.fetchone()
    if not r or not r['is_creator']: cur.close(); conn.close(); return redirect('/dashboard')
    cur.execute("SELECT COUNT(*) as total FROM agent35_users"); total_users=cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) as c FROM agent35_users WHERE payment_status='approved'"); approved=cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM agent35_users WHERE payment_status='pending'"); pending=cur.fetchone()['c']
    cur.execute("SELECT * FROM agent35_payments WHERE status='pending' ORDER BY created_at DESC LIMIT 30"); payments=cur.fetchall()
    cur.execute("SELECT email, plan, payment_status, telegram_id, referral_code, referred_by, referral_count, paid_at, payment_ref FROM agent35_users ORDER BY created_at DESC LIMIT 50"); users=cur.fetchall()
    cur.execute("SELECT referred_by, COUNT(*) as cnt FROM agent35_users WHERE payment_status='approved' AND referred_by IS NOT NULL GROUP BY referred_by ORDER BY cnt DESC"); ref_stats=cur.fetchall()
    cur.close(); conn.close()
    pay_rows="".join([f"<tr><td>{p['ref_code']}</td><td>{p['user_email']}</td><td>{p['plan']}</td><td>R{p['amount']}</td><td><a href='/master/approve?ref={p['ref_code']}' class='btn' style='padding:6px;display:inline-block;width:auto'>Approve</a> <a href='/master/reject?ref={p['ref_code']}' class='btn-danger'>Reject</a></td></tr>" for p in payments]) or "<tr><td colspan=5>No pending</td></tr>"
    user_rows="".join([f"<tr><td>{u['email'][:22]}</td><td>{u['plan']}/{u['payment_status']}</td><td>{'Y' if u['telegram_id'] else 'N'}</td><td>{u['referral_code']}</td><td>{(u['referred_by'] or '-')[:20]}</td><td>{u['referral_count']}</td><td>{u['payment_ref'] or '-'}</td></tr>" for u in users])
    ref_rows_list=[]
    for s in ref_stats:
        ref_by = s['referred_by'][:25]
        cnt = s['cnt']
        left = 10 - cnt
        status_txt = "READY FOR LIFETIME" if cnt>=10 else f"{left} left"
        ref_rows_list.append(f"<tr><td>{ref_by}</td><td>{cnt}/10</td><td>{status_txt}</td><td><a href='/master/upgrade-lifetime?email={s['referred_by']}' class='btn' style='padding:4px;width:auto;display:inline-block'>Make Lifetime</a></td></tr>")
    ref_rows="".join(ref_rows_list) or "<tr><td colspan=4>No refs yet</td></tr>"
    content=f"<h1 style='color:#10b981'>Master V12.6.1 FIXED DECIMALS</h1><div class='grid grid4'><div class='card'><div class='stat-label'>Total</div><div class='stat-value'>{total_users}</div></div><div class='card'><div class='stat-label'>Approved</div><div class='stat-value' style='color:#10b981'>{approved}</div></div><div class='card'><div class='stat-label'>Pending</div><div class='stat-value' style='color:#f59e0b'>{pending}</div></div><div class='card'><a href='/cron/scan-all' class='btn'>TEST SCAN</a><a href='/setup-webhook' class='btn-outline'>Setup Webhook</a><a href='/cron/update-trades' class='btn-outline'>Test Update</a><div style='font-size:11px;margin-top:8px'>Twelve: {'YES' if TWELVE_KEY else 'NO'} Finnhub: {'YES' if FINNHUB_KEY else 'NO'} | Decimals: FIXED</div></div></div><div class='card'><h3>Pending Payments</h3><table><tr><th>Ref</th><th>Email</th><th>Plan</th><th>Amt</th><th>Action</th></tr>{pay_rows}</table></div><div class='card'><h3>🏆 Referral Leaderboard</h3><table><tr><th>Referrer Email</th><th>Paid Refs</th><th>Status</th><th>Action</th></tr>{ref_rows}</table></div><div class='card'><h3>All Users</h3><table><tr><th>Email</th><th>Plan/Status</th><th>TG</th><th>Code</th><th>Referred By</th><th>Count</th><th>Ref</th></tr>{user_rows}</table></div>"
    return layout(content, session['email'], "master")

@app.route('/master/approve')
def master_approve():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],)); r=cur.fetchone()
    if not r or not r['is_creator']: cur.close(); conn.close(); return redirect('/dashboard')
    ref=request.args.get('ref')
    cur.execute("SELECT * FROM agent35_payments WHERE ref_code=%s", (ref,)); pay=cur.fetchone()
    if not pay: cur.close(); conn.close(); return layout("<div class='card'>Payment not found</div>", session['email'], "master")
    cur.execute("UPDATE agent35_payments SET status='approved' WHERE ref_code=%s", (ref,))
    cur.execute("UPDATE agent35_users SET payment_status='approved', paid_at=NOW() WHERE email=%s", (pay['user_email'],))
    cur.execute("SELECT referred_by FROM agent35_users WHERE email=%s", (pay['user_email'],)); referred_row = cur.fetchone()
    if referred_row and referred_row['referred_by']:
        referrer_email = referred_row['referred_by']
        cur.execute("SELECT COUNT(*) as cnt FROM agent35_users WHERE referred_by=%s AND payment_status='approved'", (referrer_email,)); cnt = cur.fetchone()['cnt']
        cur.execute("UPDATE agent35_users SET referral_count=%s WHERE email=%s", (cnt, referrer_email))
        if cnt >= 10:
            cur.execute("UPDATE agent35_users SET plan='lifetime', payment_status='approved', paid_at=NOW() WHERE email=%s AND plan!='lifetime'", (referrer_email,))
            cur.execute("SELECT telegram_id FROM agent35_users WHERE email=%s", (referrer_email,)); ref_user = cur.fetchone()
            if ref_user and ref_user['telegram_id']:
                send_telegram(ref_user['telegram_id'], f"🎉 LIFETIME UNLOCKED! {cnt} paid referrals!")
    conn.commit()
    cur.execute("SELECT telegram_id FROM agent35_users WHERE email=%s", (pay['user_email'],)); u = cur.fetchone()
    if u and u['telegram_id']:
        send_telegram(u['telegram_id'], f"✅ Payment {ref} APPROVED! {pay['plan']} active. FIXED DECIMALS V12.6.1!")
    cur.close(); conn.close()
    return redirect('/master')

@app.route('/master/reject')
def master_reject():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],)); r=cur.fetchone()
    if not r or not r['is_creator']: cur.close(); conn.close(); return redirect('/dashboard')
    ref=request.args.get('ref')
    cur.execute("UPDATE agent35_payments SET status='rejected' WHERE ref_code=%s", (ref,))
    cur.execute("UPDATE agent35_users SET payment_status='pending' WHERE payment_ref=%s", (ref,))
    conn.commit(); cur.close(); conn.close()
    return redirect('/master')

@app.route('/master/upgrade-lifetime')
def master_upgrade_lifetime():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],)); r=cur.fetchone()
    if not r or not r['is_creator']: cur.close(); conn.close(); return redirect('/dashboard')
    email_param=request.args.get('email')
    cur.execute("UPDATE agent35_users SET plan='lifetime', payment_status='approved', paid_at=NOW() WHERE email=%s", (email_param,)); conn.commit(); cur.close(); conn.close()
    return redirect('/master')

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

if __name__=='__main__':
    print(f"🚀 Agent 35 V12.6.1 FIXED DECIMALS")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',10000)))
