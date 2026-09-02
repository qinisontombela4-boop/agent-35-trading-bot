import os, hashlib, requests, psycopg, threading, time, csv, io
from psycopg.rows import dict_row
from flask import Flask, request, redirect, session, jsonify, Response
from datetime import datetime
import trading_engine as engine
import yfinance as yf

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'agent35-secret-2025')
DATABASE_URL = os.environ.get('DATABASE_URL','').strip()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
TELEGRAM_BOT_USERNAME = "Sniper035_bot"
CAPITEC_ACC = "2586572676"

# --- CONSTANTS MUST BE AT TOP ---
LOGO_SVG = '<svg width="34" height="34" viewBox="0 0 100 100"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#059669"/></linearGradient></defs><rect width="100" height="100" rx="18" fill="#0b111c" stroke="#10b981" stroke-width="3"/><text x="50%" y="58%" dominant-baseline="middle" text-anchor="middle" font-family="Arial Black" font-weight="900" font-size="48" fill="url(#g)">35</text></svg>'
CUR = {'USD':'$','ZAR':'R','EUR':'\u20ac','GBP':'\u00a3'}
MAP = engine.MAP # use map from engine

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
*{box-sizing:border-box} body{background:#060a14;color:#e5e7eb;font-family:'Inter',sans-serif;margin:0}.header{background:#0b111c;border-bottom:1px solid #1a2535;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}.logo{display:flex;align-items:center;gap:10px;color:#10b981;font-weight:800}.card{background:#0e1625;border:1px solid #1c2a41;border-radius:16px;padding:16px}.btn{background:linear-gradient(135deg,#10b981,#059669);color:#000;font-weight:800;padding:12px 18px;border:none;border-radius:12px;cursor:pointer;text-decoration:none;display:block;text-align:center;width:100%}.btn-outline{background:transparent;border:1px solid #24344e;color:#cbd5e1;padding:12px 18px;border-radius:12px;text-decoration:none;display:block;text-align:center;width:100%;margin-top:8px}.btn-test{background:#3b82f6;color:#fff;font-weight:700;padding:10px;border:none;border-radius:10px;width:100%;margin-top:8px;display:block;text-align:center;text-decoration:none}.grid{display:grid;gap:14px}.grid4{grid-template-columns:repeat(4,1fr)}.badge{padding:5px 10px;border-radius:20px;font-size:11px;font-weight:800}.bull{background:rgba(16,185,129,0.15);color:#10b981}.bear{background:rgba(239,68,68,0.15);color:#ef4444}.win{background:rgba(16,185,129,0.25);color:#10b981}.loss{background:rgba(239,68,68,0.25);color:#ef4444}.chip{display:inline-flex;align-items:center;gap:6px;background:#121d30;border:1px solid #1e2d45;padding:7px 12px;border-radius:24px;margin:4px;font-size:13px;cursor:pointer}.chip-active{background:#10b98122;border-color:#10b981}.x{background:#ef4444;color:#fff;border-radius:50%;width:20px;height:20px;display:inline-flex;justify-content:center;align-items:center;font-size:12px;margin-left:6px}.searchbox{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:12px;width:100%;margin:8px 0}.dropdown{background:#121d30;border:1px solid #1e2d45;border-radius:12px;max-height:200px;overflow:auto;display:none;position:absolute;z-index:50;width:calc(100% - 32px)}.dropdown div{padding:10px 14px;cursor:pointer;border-bottom:1px solid #1a2535} table{width:100%;border-collapse:collapse} th{color:#64748b;text-align:left;padding:12px 8px;font-size:10px;text-transform:uppercase} td{padding:12px 8px;border-top:1px solid #1a2535;font-size:13px}.nav-tabs{display:flex;gap:8px;overflow:auto;margin:12px 0}.nav-tabs a{white-space:nowrap;padding:10px 16px;border-radius:24px;background:#121d30;border:1px solid #1e2d45;color:#94a3b8;text-decoration:none;font-size:13px;font-weight:600}.nav-tabs a.active{background:#10b981;color:#000;border-color:#10b981}.stat-label{font-size:11px;color:#64748b;text-transform:uppercase}.stat-value{font-size:22px;font-weight:800;margin-top:6px} @media(max-width:900px){.grid4{grid-template-columns:1fr 1fr}} @media(max-width:600px){.grid4{grid-template-columns:1fr}table{display:block;overflow-x:auto}} input,select{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:10px;width:100%;margin:6px 0} label{font-size:12px;color:#94a3b8;margin-top:12px;display:block;font-weight:600}.settings-section{background:#0e1625;border:1px solid #1c2a41;border-radius:16px;padding:20px;margin-bottom:16px}.sess-check{display:flex;align-items:center;gap:8px;background:#121d30;padding:12px;border-radius:12px;border:1px solid #1e2d45;cursor:pointer}.sess-check input{width:18px;height:18px}.step{border-left:4px solid #10b981;background:#0e1625;border-radius:12px;padding:18px;margin:14px 0}.step-num{background:#10b981;color:#000;width:32px;height:32px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-weight:800;margin-right:10px}.broker-card{background:#121d30;border:1px solid #1e2d45;border-radius:12px;padding:14px;display:flex;justify-content:space-between;align-items:center;margin:8px 0}.warn{background:#f59e0b22;border:1px solid #f59e0b;color:#f59e0b;padding:12px;border-radius:10px;text-align:center;font-weight:700}
</style>
<script>
const ALL_SYMBOLS=["EURUSD","GBPUSD","USDJPY","EURJPY","GBPJPY","USDZAR","EURZAR","GBPZAR","ZARJPY","XAUUSD","GOLD","XAGUSD","BTCUSD","ETHUSD","SOLUSD","NAS100","US30","SPX500","GER40","UK100","JP225","USOIL","UKOIL","AAPL","TSLA","NVDA","MSFT"];
function addSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!='');if(arr.length>=5){alert('Max 5');return}if(!arr.includes(s)){arr.push(s);i.value=arr.join(',');document.getElementById('symForm').submit();}}
function removeSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!=s.trim()&&x.trim()!='');i.value=arr.join(',');document.getElementById('symForm').submit();}
function filterSyms(){let q=document.getElementById('symSearch').value.toUpperCase();let dd=document.getElementById('symDropdown');if(!q){dd.style.display='none';return}let f=ALL_SYMBOLS.filter(s=>s.includes(q)).slice(0,10);dd.innerHTML=f.map(s=>'<div onclick="addSym(\\''+s+'\\')"><b>'+s+'</b> - Click to Add</div>').join('');dd.style.display=f.length?'block':'none';}
document.addEventListener('click', function(e){let box=document.getElementById('symSearch');let dd=document.getElementById('symDropdown');if(dd && e.target!==box &&!dd.contains(e.target)){dd.style.display='none';}});
</script>
"""

def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode='require', connect_timeout=20)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_users (id SERIAL PRIMARY KEY, email TEXT UNIQUE, password TEXT,is_creator BOOLEAN DEFAULT FALSE, plan TEXT DEFAULT 'none',payment_ref TEXT, payment_status TEXT DEFAULT 'pending',risk_reward TEXT DEFAULT '1:3', symbols TEXT DEFAULT 'EURUSD,XAUUSD,BTCUSD,GBPUSD,NAS100',sessions TEXT DEFAULT 'London,New York', account_size FLOAT DEFAULT 10000,lot_size FLOAT DEFAULT 0.1, leverage TEXT DEFAULT '1:500',telegram_id TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_trades (id SERIAL PRIMARY KEY, user_email TEXT, symbol TEXT,direction TEXT, entry FLOAT, sl FLOAT, tp FLOAT,status TEXT DEFAULT 'sent', pnl FLOAT DEFAULT 0,timeframe_bias TEXT, confluence TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_payments (id SERIAL PRIMARY KEY, user_email TEXT, plan TEXT,ref_code TEXT UNIQUE, amount INT, status TEXT DEFAULT 'pending',created_at TIMESTAMP DEFAULT NOW());""")
    for q in ["ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USD'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS telegram_username TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency_symbol TEXT DEFAULT '$'","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS hit_entry_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS result_price FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS auto_updated BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS sessions TEXT DEFAULT 'London,New York'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_code TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referred_by TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_count INT DEFAULT 0"]:
        try: cur.execute(q)
        except: pass
    conn.commit()
    cur.execute("SELECT * FROM agent35_users WHERE email='creator@agent35.com'")
    if not cur.fetchone():
        pw = hashlib.sha256('Agent35Creator!'.encode()).hexdigest()
        cur.execute("INSERT INTO agent35_users (email,password,is_creator,plan,payment_status,paid_at,sessions,referral_code,referral_count) VALUES (%s,%s,TRUE,'lifetime','approved',NOW(),'24/7',%s,0)", ('creator@agent35.com', pw, f"AG35-CREATOR-{os.urandom(2).hex().upper()}"))
    conn.commit()
    cur.close(); conn.close()

init_db()

def send_telegram(chat_id, text, trade_id=None, stage="signal"):
    if not TELEGRAM_TOKEN or not chat_id: return False
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode":"Markdown"}
        if trade_id:
            if stage=="signal":
                payload["reply_markup"] = {"inline_keyboard": [[{"text":"\u2705 TOOK ENTRY","callback_data":f"took:{trade_id}"},{"text":"\u274c SKIP","callback_data":f"skip:{trade_id}"}],[{"text":"\ud83d\udcca View Journal","url":"https://agent-35-trading-bot.onrender.com/journal"}]]}
            elif stage=="active":
                payload["reply_markup"] = {"inline_keyboard": [[{"text":"\u2705 WIN","callback_data":f"win:{trade_id}"},{"text":"\u274c LOSS","callback_data":f"loss:{trade_id}"},{"text":"\u2796 BE","callback_data":f"be:{trade_id}"}]]}
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload, timeout=10)
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

# --- V9 BUILD MSG WITH QUALITY ---
def build_signal_msg(res, user=None):
    try:
        sym = res['symbol']; direction = res['direction']; entry = res['entry']; sl = res['sl']; tp = res['tp']; score = res['score']; bias = res.get('bias',''); confluence = res.get('confluence', []); reason = res.get('reason',''); quality = res.get('quality', 'STANDARD')
        emoji = "🟢" if direction == "BUY" else "🔴"
        rr_val = 0
        if entry!= sl:
            rr_val = (tp - entry) / (entry - sl) if direction == "BUY" and (entry-sl)!=0 else (entry - tp) / (sl - entry) if (sl-entry)!=0 else 0
        bias_parts = bias.split("|"); htf_line = bias_parts[1].strip() if len(bias_parts)>1 else bias; ltf_line = bias_parts[2].strip() if len(bias_parts)>2 else ""
        conf_text = "\n".join([f"• {c}" for c in confluence[:6]])
        if "SNIPER" in quality: header = "🔥🔥 SNIPER - OB + DISCOUNT 🔥🔥\n💎 Highest Win Rate - 2% risk"
        elif "PREMIUM" in quality: header = "🔥 PREMIUM SIGNAL\n⭐ High Quality - 1.5% risk"
        elif quality == "HIGH": header = "✅ HIGH QUALITY\n1% risk"
        else: header = "📊 STANDARD PULLBACK\n0.5% risk"
        msg = f"""{emoji} {sym} {direction} | {quality} {score}/8
{header}
━━━━━━━━━━━━━━
{htf_line}
{ltf_line}

💰 Entry: {entry}
🛑 SL: {sl}
🎯 TP: {tp}
📊 RR: 1:{rr_val:.1f} | Score: {score}/8

🔍 Confluence:
{conf_text}

📝 {reason}
"""
        return msg
    except Exception as e:
        return f"{res.get('symbol')} {res.get('direction')} Entry {res.get('entry')} SL {res.get('sl')} TP {res.get('tp')} Score {res.get('score')} {res.get('quality','')}"

def layout(content, email="", active="dashboard"):
    is_creator = "creator" in email.lower()
    ad = "active" if active=="dashboard" else ""; aj = "active" if active=="journal" else ""; aset = "active" if active=="settings" else ""; am = "active" if active=="master" else ""; ag = "active" if active=="guide" else ""
    master_tab = f'<a href="/master" class="{am}">Master</a>' if is_creator else ""
    guide_tab = f'<a href="/guide" class="{ag}">Guide</a>'
    tabs = f'<div class="nav-tabs"><a href="/dashboard" class="{ad}">Dashboard</a><a href="/journal" class="{aj}">Journal</a><a href="/settings" class="{aset}">Settings</a><a href="/payment">Plans</a>{guide_tab}{master_tab}</div>'
    return f'<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Agent35 V6 Guide</title>{STYLE}</head><body><div class="header"><div class="logo">{LOGO_SVG} AGENT 35 V6</div><div><span style="font-size:11px;color:#94a3b8">{email}</span> <a href="/logout" style="color:#94a3b8;text-decoration:none;margin-left:10px">Logout</a></div></div><div style="padding:14px;max-width:1400px;margin:auto">{tabs}{content}</div></body></html>'

def get_live_price(symbol):
    try:
        yfs = MAP.get(symbol.upper(), symbol.upper()+"=X")
        df = yf.download(yfs, period="1d", interval="5m", progress=False, auto_adjust=True)
        if df.empty: return None
        try: df.columns = df.columns.get_level_values(0)
        except: pass
        return float(df['Close'].iloc[-1]), float(df['High'].iloc[-1]), float(df['Low'].iloc[-1])
    except: return None

def auto_update_trades_loop():
    while True:
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute("SELECT t.*, u.account_size, u.risk_reward FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.status IN ('sent','took','active') LIMIT 30")
            rows = cur.fetchall()
            for tr in rows:
                live = get_live_price(tr['symbol'])
                if not live: continue
                close, high, low = live
                rr = 3
                try: rr = int(tr['risk_reward'].split(':')[1])
                except: rr = 3
                risk = tr['account_size']*0.01; new=None; pnl=0
                if tr['status']=='sent' and low <= tr['entry'] <= high: new='took'
                elif tr['status'] in ('took','active'):
                    if tr['direction']=='BUY':
                        if low <= tr['sl']: new='loss'; pnl=-risk
                        elif high >= tr['tp']: new='win'; pnl=risk*rr
                    else:
                        if high >= tr['sl']: new='loss'; pnl=-risk
                        elif low <= tr['tp']: new='win'; pnl=risk*rr
                if new and new!=tr['status']:
                    if new in ('win','loss'): cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s, auto_updated=TRUE WHERE id=%s",(new,pnl,close,tr['id']))
                    else: cur.execute("UPDATE agent35_trades SET status=%s, hit_entry_at=NOW() WHERE id=%s",(new,tr['id']))
            conn.commit(); cur.close(); conn.close()
        except: pass
        time.sleep(180)

threading.Thread(target=auto_update_trades_loop, daemon=True).start()
