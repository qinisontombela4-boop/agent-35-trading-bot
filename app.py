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

def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode='require', connect_timeout=20)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_users (id SERIAL PRIMARY KEY, email TEXT UNIQUE, password TEXT,is_creator BOOLEAN DEFAULT FALSE, plan TEXT DEFAULT 'none',payment_ref TEXT, payment_status TEXT DEFAULT 'pending',risk_reward TEXT DEFAULT '1:3', symbols TEXT DEFAULT 'EURUSD,XAUUSD,BTCUSD,GBPUSD,NAS100',sessions TEXT DEFAULT 'London,New York', account_size FLOAT DEFAULT 10000,lot_size FLOAT DEFAULT 0.1, leverage TEXT DEFAULT '1:500',telegram_id TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_trades (id SERIAL PRIMARY KEY, user_email TEXT, symbol TEXT,direction TEXT, entry FLOAT, sl FLOAT, tp FLOAT,status TEXT DEFAULT 'sent', pnl FLOAT DEFAULT 0,timeframe_bias TEXT, confluence TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_payments (id SERIAL PRIMARY KEY, user_email TEXT, plan TEXT,ref_code TEXT UNIQUE, amount INT, status TEXT DEFAULT 'pending',created_at TIMESTAMP DEFAULT NOW());""")
    for q in ["ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USD'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS telegram_username TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency_symbol TEXT DEFAULT '$'","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS hit_entry_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS result_price FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS auto_updated BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS sessions TEXT DEFAULT 'London,New York'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_code TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referred_by TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_count INT DEFAULT 0"]:
        try:
            cur.execute(q)
        except:
            pass
    conn.commit()
    cur.execute("SELECT * FROM agent35_users WHERE email='creator@agent35.com'")
    if not cur.fetchone():
        pw = hashlib.sha256('Agent35Creator!'.encode()).hexdigest()
        cur.execute("INSERT INTO agent35_users (email,password,is_creator,plan,payment_status,paid_at,sessions,referral_code,referral_count) VALUES (%s,%s,TRUE,'lifetime','approved',NOW(),'24/7',%s,0)", ('creator@agent35.com', pw, f"AG35-CREATOR-{os.urandom(2).hex().upper()}"))
    conn.commit()
    cur.execute("SELECT * FROM agent35_users WHERE email='test@agent35.com'")
    if not cur.fetchone():
        pw = hashlib.sha256('Test123!'.encode()).hexdigest()
        cur.execute("INSERT INTO agent35_users (email,password,plan,payment_status,symbols,paid_at,sessions,referral_code) VALUES (%s,%s,'yearly','approved','EURUSD,XAUUSD',NOW(),'London,New York',%s)", ('test@agent35.com', pw, f"AG35-TEST-{os.urandom(2).hex().upper()}"))
    conn.commit()
    cur.execute("SELECT email FROM agent35_users WHERE referral_code IS NULL")
    for r in cur.fetchall():
        code = f"AG35-{r['email'][:3].upper()}-{os.urandom(2).hex().upper()}"
        cur.execute("UPDATE agent35_users SET referral_code=%s WHERE email=%s", (code, r['email']))
    conn.commit()
    cur.close()
    conn.close()

init_db()

def send_telegram(chat_id, text, trade_id=None, stage="signal"):
    if not TELEGRAM_TOKEN or not chat_id:
        return False
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode":"Markdown"}
        if trade_id:
            if stage=="signal":
                payload["reply_markup"] = {"inline_keyboard": [[{"text":"\u2705 TOOK ENTRY","callback_data":f"took:{trade_id}"},{"text":"\u274c SKIP","callback_data":f"skip:{trade_id}"}],[{"text":"\ud83d\udcca View Journal","url":"https://agent-35-trading-bot.onrender.com/journal"}]]}
            elif stage=="active":
                payload["reply_markup"] = {"inline_keyboard": [[{"text":"\u2705 WIN","callback_data":f"win:{trade_id}"},{"text":"\u274c LOSS","callback_data":f"loss:{trade_id}"},{"text":"\u2796 BE","callback_data":f"be:{trade_id}"}]]}
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload, timeout=10)
        return r.status_code==200
    except:
        return False

SESSIONS_HOURS_UTC = {"Sydney": (22, 6),"Asia": (0, 9),"London": (8, 16),"New York": (13, 21)}

def is_session_active(user_sessions):
    if not user_sessions:
        return True
    us = user_sessions.strip()
    if "24/7" in us or "All" in us:
        return True
    now_hour = datetime.utcnow().hour
    for sess in [s.strip() for s in us.split(",")]:
        if sess not in SESSIONS_HOURS_UTC:
            continue
        start, end = SESSIONS_HOURS_UTC[sess]
        if start < end:
            if start <= now_hour < end:
                return True
        else:
            if now_hour >= start or now_hour < end:
                return True
    return False

def build_signal_msg(res, user):
    score = res.get('score', 0)
    conv = res.get('confluence', '')
    if isinstance(conv, list):
        conv = "\n".join([f"\u2022 {c}" for c in conv])
    elif isinstance(conv, str) and "," in conv:
        conv = "\n".join([f"\u2022 {c.strip()}" for c in conv.split(",")])
    else:
        conv = f"\u2022 {conv}"
    bias = res.get('bias', '')
    reason = res.get('reason', res.get('timeframe_bias','')) or conv[:250]
    conviction = "HIGH \ud83d\udd25" if score>=7 else "MEDIUM \u26a1" if score>=5 else "LOW \ud83d\udca4"
    sess = user.get('sessions') if isinstance(user, dict) else user['sessions']
    return f"\ud83d\ude80 *{res['symbol']} {res['direction']}* | {conviction} *{score}/8* *Session:* {sess} | UTC {datetime.utcnow().strftime('%H:%M')} *Bias:* {bias} | *RR:* {user['risk_reward']} *Entry:* `{res['entry']}` | *SL:* `{res['sl']}` | *TP:* `{res['tp']}` *Confluence {score}/8:* {conv} *Reason:* _{str(reason)[:220]}_"

LOGO_SVG = '<svg width="34" height="34" viewBox="0 0 100 100"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#059669"/></linearGradient></defs><rect width="100" height="100" rx="18" fill="#0b111c" stroke="#10b981" stroke-width="3"/><text x="50%" y="58%" dominant-baseline="middle" text-anchor="middle" font-family="Arial Black" font-weight="900" font-size="48" fill="url(#g)">35</text></svg>'
CUR = {'USD':'$','ZAR':'R','EUR':'\u20ac','GBP':'\u00a3'}
MAP = {"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"JPY=X","USDZAR":"ZAR=X","EURZAR":"EURZAR=X","XAUUSD":"GC=F","GOLD":"GC=F","BTCUSD":"BTC-USD","ETHUSD":"ETH-USD","NAS100":"^NDX","US30":"^DJI","SPX500":"^GSPC","GER40":"^GDAXI","USOIL":"CL=F"}

def get_live_price(symbol):
    try:
        yfs = MAP.get(symbol.upper(), symbol.upper()+"=X")
        df = yf.download(yfs, period="1d", interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            return None
        try:
            df.columns = df.columns.get_level_values(0)
        except:
            pass
        return float(df['Close'].iloc[-1]), float(df['High'].iloc[-1]), float(df['Low'].iloc[-1])
    except:
        return None   def auto_update_trades_loop():
    while True:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT t.*, u.account_size, u.risk_reward FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.status IN ('sent','took','active') LIMIT 30")
            for tr in cur.fetchall():
                live = get_live_price(tr['symbol'])
                if not live:
                    continue
                close, high, low = live
                rr=3
                try:
                    rr=int(tr['risk_reward'].split(':')[1])
                except:
                    pass
                risk=tr['account_size']*0.01
                new=None
                pnl=0
                if tr['status']=='sent' and low <= tr['entry'] <= high:
                    new='took'
                elif tr['status'] in ('took','active'):
                    if tr['direction']=='BUY':
                        if low <= tr['sl']:
                            new='loss'
                            pnl=-risk
                        elif high >= tr['tp']:
                            new='win'
                            pnl=risk*rr
                    else:
                        if high >= tr['sl']:
                            new='loss'
                            pnl=-risk
                        elif low <= tr['tp']:
                            new='win'
                            pnl=risk*rr
                if new and new!=tr['status']:
                    if new in ('win','loss'):
                        cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s, auto_updated=TRUE WHERE id=%s",(new,pnl,close,tr['id']))
                    else:
                        cur.execute("UPDATE agent35_trades SET status=%s, hit_entry_at=NOW() WHERE id=%s",(new,tr['id']))
            conn.commit()
            cur.close()
            conn.close()
        except:
            pass
        time.sleep(180)

threading.Thread(target=auto_update_trades_loop, daemon=True).start()

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

def layout(content, email="", active="dashboard"):
    is_creator = "creator" in email.lower()
    ad = "active" if active=="dashboard" else ""
    aj = "active" if active=="journal" else ""
    aset = "active" if active=="settings" else ""
    am = "active" if active=="master" else ""
    ag = "active" if active=="guide" else ""
    master_tab = f'<a href="/master" class="{am}">Master</a>' if is_creator else ""
    guide_tab = f'<a href="/guide" class="{ag}">Guide</a>'
    tabs = f'<div class="nav-tabs"><a href="/dashboard" class="{ad}">Dashboard</a><a href="/journal" class="{aj}">Journal</a><a href="/settings" class="{aset}">Settings</a><a href="/payment">Plans</a>{guide_tab}{master_tab}</div>'
    return f'<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Agent35 V6 Guide</title>{STYLE}</head><body><div class="header"><div class="logo">{LOGO_SVG} AGENT 35 V6</div><div><span style="font-size:11px;color:#94a3b8">{email}</span> <a href="/logout" style="color:#94a3b8;text-decoration:none;margin-left:10px">Logout</a></div></div><div style="padding:14px;max-width:1400px;margin:auto">{tabs}{content}</div></body></html>'

@app.route('/')
def home():
    ref_banner = ""
    if session.get('ref_code'):
        ref_banner = f"<div class='card' style='border-color:#10b981;background:#10b98115;text-align:center'><b>Referred by {session.get('ref_code')}</b><br><span style='font-size:12px'>You will count toward their 10 = Lifetime!</span></div>"
    return f'<html><head><meta name="viewport" content="width=device-width, initial-scale=1">{STYLE}</head><body style="display:flex;justify-content:center;align-items:center;min-height:100vh;padding:16px"><div class="card" style="max-width:400px;width:100%;text-align:center;padding:28px"><div style="display:flex;justify-content:center;margin-bottom:16px">{LOGO_SVG.replace("34","72")}</div><h1 style="color:#10b981;margin:0">AGENT 35</h1><p style="color:#64748b;margin-top:8px;font-size:13px">V6 Guide Edition @Sniper035_bot</p>{ref_banner}<div class="warn" style="margin:12px 0;font-size:12px">Recommended: R1000 Total<br>R500 Bot + R500 Trading<br><span style="color:#10b981">OR Refer 10 = Lifetime FREE</span></div><form method="POST" action="/auth" style="text-align:left;margin-top:18px"><label>Email</label><input name="email" placeholder="your@email.com" required><label>Password</label><input name="password" type="password" placeholder="********" required><button class="btn" style="margin-top:16px">Login / Create Profile</button></form><a href="/guide" style="color:#10b981;font-size:13px;display:block;margin-top:12px;text-decoration:none">How it Works - 7 Steps</a></div></body></html>'

@app.route('/r/<code>')
def referral_link(code):
    session['ref_code'] = code.upper().strip()
    return redirect('/')

@app.route('/guide')
def guide_page():
    email = session.get('email','')
    content = """
 <h1 style='color:#10b981;text-align:center'>How To Start With Agent 35</h1>
 <div class='warn'>Recommended Minimum: R1000 Total<br>R500 for Bot + R500 to Fund Trading Account<br><span style='color:#10b981'>OR Refer 10 Friends = Lifetime FREE (R5000 Value)</span></div>
 <p style='text-align:center;color:#94a3b8'>From broker to first signal in 10 minutes - 7 steps</p>
 <div class='step'><div style='display:flex;align-items:center'><div class='step-num'>1</div><h3>Sign Up For A Broker</h3></div><p style='color:#cbd5e1'>We recommend low-spread brokers tested with Agent 35:</p><div class='broker-card'><div><b>Headway</b><br><span style='font-size:11px;color:#10b981'>Best for small accounts</span></div><a class='btn' style='width:auto;padding:8px 14px' href='https://headway.com' target='_blank'>Join</a></div><div class='broker-card'><div><b>RCG Markets</b><br><span style='font-size:11px;color:#10b981'>ZAR local support</span></div><a class='btn' style='width:auto;padding:8px 14px' href='https://rcgmarkets.com' target='_blank'>Join</a></div></div>
 <div class='step'><div style='display:flex;align-items:center'><div class='step-num'>2</div><h3>Fund Your Trading Account</h3></div><p><b>Minimum R500 in broker</b> (so R1000 total with bot). Deposit via EFT or Crypto. Use Standard account, leverage 1:500.</p></div>
 <div class='step'><div style='display:flex;align-items:center'><div class='step-num'>3</div><h3>Create Agent 35 Profile</h3></div><p>Enter email + password on home page -> Ref auto-generated. Share it to earn Lifetime.</p><a class='btn-outline' href='/'>Create Profile Now</a></div>
 <div class='step'><div style='display:flex;align-items:center'><div class='step-num'>4</div><h3>Pay For Preferred Plan</h3></div><p>Go to Plans -> Choose Yearly R500 or Lifetime R5000 -> Pay with your Ref as reference -> Click I Paid. Admin approves in 10 min. OR Refer 10 friends who pay.</p><a class='btn' href='/payment'>View Plans</a></div>
 <div class='step'><div style='display:flex;align-items:center'><div class='step-num'>5</div><h3>Link Telegram - Critical</h3></div><p>1. Install Telegram<br>2. Dashboard -> Link TG -> Opens @Sniper035_bot<br>3. Press START -> Bot says Linked!<br>Test: Click Test with Reason button.</p></div>
 <div class='step'><div style='display:flex;align-items:center'><div class='step-num'>6</div><h3>Set Account Details & Pairs</h3></div><p>Settings page:<br>Size: 1000 | Currency: ZAR | Lot: 0.01 | RR: 1:3<br>Sessions: London + New York</p></div>
 <div class='step' style='border-left-color:#3b82f6'><div style='display:flex;align-items:center'><div class='step-num' style='background:#3b82f6'>7</div><h3>Wait For Signals & Mark Taken</h3></div><p>Bot scans every 15 min (your sessions only, red news blocked).<br><br>Telegram: XAUUSD BUY | HIGH 7/8<br>Entry/SL/TP + Reason + Score<br><br><b>Click:</b> TOOK or SKIP -> Active -> Close as WIN / LOSS / BE<br>Auto-saved to Journal.</p></div>
 <div class='card' style='text-align:center'><h3 style='color:#10b981'>Ready to Start?</h3><a class='btn' href='/dashboard'>Go To Dashboard</a></div>
 """
    return layout(content, email, "guide")

@app.route('/auth', methods=['POST'])
def auth():
    email = request.form['email'].lower().strip()
    pw = hashlib.sha256(request.form['password'].encode()).hexdigest()
    ref_by = session.get('ref_code')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s AND password=%s", (email, pw))
    u = cur.fetchone()
    if not u:
        my_code = f"AG35-{email[:3].upper()}-{os.urandom(2).hex().upper()}"
        cur.execute("INSERT INTO agent35_users (email,password,plan,payment_status,symbols,sessions,referral_code,referred_by,referral_count) VALUES (%s,%s,'none','pending','EURUSD,XAUUSD','London,New York',%s,%s,0) RETURNING *", (email,pw,my_code,ref_by))
        u = cur.fetchone()
        conn.commit()
    if not u.get('referral_code'):
        my_code = f"AG35-{u['email'][:3].upper()}-{os.urandom(2).hex().upper()}"
        cur.execute("UPDATE agent35_users SET referral_code=%s WHERE email=%s", (my_code, u['email']))
        conn.commit()
        u['referral_code'] = my_code
    cur.close()
    conn.close()
    session['email'] = u['email']
    session['is_creator'] = u['is_creator']
    session.pop('ref_code', None)
    if u['is_creator']:
        return redirect('/master')
    return redirect('/dashboard')

@app.route('/approve/<int:pid>')
def approve(pid):
    if 'email' not in session:
        return redirect('/')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],))
    chk = cur.fetchone()
    if not chk or not chk['is_creator']:
        cur.close()
        conn.close()
        return "Not allowed"
    cur.execute("UPDATE agent35_payments SET status='approved' WHERE id=%s RETURNING user_email, plan, ref_code", (pid,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE agent35_users SET payment_status='approved', plan=%s, paid_at=NOW(), payment_ref=%s WHERE email=%s", (row['plan'], row['ref_code'], row['user_email']))
        cur.execute("SELECT referred_by FROM agent35_users WHERE email=%s", (row['user_email'],))
        ref = cur.fetchone()
        if ref and ref['referred_by']:
            cur.execute("UPDATE agent35_users SET referral_count = COALESCE(referral_count,0)+1 WHERE referral_code=%s RETURNING email, referral_count", (ref['referred_by'],))
            referrer = cur.fetchone()
            if referrer and referrer['referral_count'] >= 10:
                cur.execute("UPDATE agent35_users SET plan='lifetime', payment_status='approved', paid_at=NOW() WHERE email=%s", (referrer['email'],))
        conn.commit()
    cur.close()
    conn.close()
    return redirect('/master')

@app.route('/approve-user')
def approve_user():
    if 'email' not in session:
        return redirect('/')
    target = request.args.get('email')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],))
    chk = cur.fetchone()
    if not chk or not chk['is_creator']:
        cur.close()
        conn.close()
        return "Not allowed"
    cur.execute("UPDATE agent35_users SET payment_status='approved', paid_at=NOW() WHERE email=%s RETURNING referred_by", (target,))
    updated = cur.fetchone()
    if updated and updated['referred_by']:
        cur.execute("UPDATE agent35_users SET referral_count = COALESCE(referral_count,0)+1 WHERE referral_code=%s RETURNING email, referral_count", (updated['referred_by'],))
        referrer = cur.fetchone()
        if referrer and referrer['referral_count'] >= 10:
            cur.execute("UPDATE agent35_users SET plan='lifetime', payment_status='approved', paid_at=NOW() WHERE email=%s", (referrer['email'],))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/master')

@app.route('/delete-payment/<int:pid>')
def delete_payment(pid):
    if 'email' not in session:
        return redirect('/')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],))
    chk = cur.fetchone()
    if not chk or not chk['is_creator']:
        cur.close()
        conn.close()
        return "Not allowed"
    cur.execute("DELETE FROM agent35_payments WHERE id=%s", (pid,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/master')

@app.route('/delete-user')
def delete_user():
    if 'email' not in session:
        return redirect('/')
    email_to_delete = request.args.get('email')
    if email_to_delete in ['creator@agent35.com']:
        return "Cannot delete creator"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],))
    chk = cur.fetchone()
    if not chk or not chk['is_creator']:
        cur.close()
        conn.close()
        return "Not allowed"
    cur.execute("DELETE FROM agent35_trades WHERE user_email=%s", (email_to_delete,))
    cur.execute("DELETE FROM agent35_payments WHERE user_email=%s", (email_to_delete,))
    cur.execute("DELETE FROM agent35_users WHERE email=%s", (email_to_delete,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/master') @app.route('/master')
def master():
    if 'email' not in session:
        return redirect('/')
    q = request.args.get('q','').lower().strip()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],))
    r = cur.fetchone()
    if not r or not r['is_creator']:
        cur.close()
        conn.close()
        return redirect('/dashboard')
    cur.execute("SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE payment_status='approved') as active FROM agent35_users")
    stats = cur.fetchone()
    cur.execute("SELECT COALESCE(SUM(amount),0) as rev FROM agent35_payments WHERE status='approved'")
    rev_stats = cur.fetchone()
    if q:
        cur.execute("SELECT * FROM agent35_users WHERE LOWER(email) LIKE %s OR LOWER(payment_ref) LIKE %s ORDER BY created_at DESC LIMIT 100", (f"%{q}%", f"%{q}%"))
        users = cur.fetchall()
        cur.execute("SELECT * FROM agent35_payments WHERE LOWER(user_email) LIKE %s OR LOWER(ref_code) LIKE %s ORDER BY created_at DESC LIMIT 100", (f"%{q}%", f"%{q}%"))
        pays = cur.fetchall()
    else:
        cur.execute("SELECT * FROM agent35_users ORDER BY created_at DESC LIMIT 100")
        users = cur.fetchall()
        cur.execute("SELECT * FROM agent35_payments ORDER BY created_at DESC LIMIT 100")
        pays = cur.fetchall()
    cur.execute("SELECT email, referral_code, referral_count, plan, payment_status FROM agent35_users ORDER BY referral_count DESC LIMIT 20")
    leaders = cur.fetchall()
    cur.close()
    conn.close()
    users_html = "".join([f"<tr><td>{u['email']}<br><span style='font-size:10px;color:#10b981'>{u['payment_ref'] or ''} | {u['referral_code'] or ''} ({u['referral_count'] or 0}/10)</span><br><span style='font-size:10px'>RefBy:{u['referred_by'] or '-'} | {u['sessions']} | TG:{u['telegram_id'] or 'No'}</span></td><td><span class='badge {'win' if u['payment_status']=='approved' else 'loss'}'>{u['payment_status']}</span><br><span style='font-size:10px'>{u['plan']}</span></td><td>{u['created_at'].strftime('%m-%d')}</td><td><a class='btn' style='padding:5px 8px;font-size:10px;width:auto' href='/approve-user?email={u['email']}'>Approve</a><a class='btn-outline' style='padding:5px 8px;font-size:10px;width:auto;border-color:#ef4444;color:#ef4444' href='/delete-user?email={u['email']}' onclick=\"return confirm('Delete?')\">Remove</a></td></tr>" for u in users])
    pays_html = "".join([f"<div class='card' style='margin:6px 0;display:flex;justify-content:space-between'><div><b>{p['user_email']}</b> - {p['ref_code']} - R{p['amount']}</div><div style='display:flex;gap:4px'><a class='btn' style='width:auto;padding:5px 10px;font-size:11px' href='/approve/{p['id']}'>Approve</a><a class='btn-outline' style='width:auto;padding:5px 10px;font-size:11px;border-color:#ef4444;color:#ef4444' href='/delete-payment/{p['id']}'>Remove</a></div></div>" for p in pays])
    leaders_html = "".join([f"<tr><td>{l['email']}</td><td>{l['referral_code']}</td><td><b>{l['referral_count'] or 0}/10</b></td><td>{l['plan']}/{l['payment_status']}</td></tr>" for l in leaders])
    content = f"<h2 style='color:#10b981'>MASTER V6 + Referral</h2><div class='grid grid4'><div class='card'><div class='stat-label'>Users</div><div class='stat-value'>{stats['total']}</div></div><div class='card'><div class='stat-label'>Revenue</div><div class='stat-value'>R{rev_stats['rev']}</div></div><div class='card'><div style='font-size:11px'>UTC {datetime.utcnow().strftime('%H:%M')}</div><a class='btn-outline' href='/setup-webhook'>Webhook</a></div><div class='card'><form method='GET' action='/master'><input name='q' value='{q}' placeholder='Search'><button class='btn' style='margin-top:6px'>Search</button></form></div></div><div class='card' style='margin-top:14px'><h3>Top Referrers - 10 = Lifetime</h3><table><tr><th>User</th><th>Code</th><th>Count</th><th>Plan</th></tr>{leaders_html}</table></div><div class='card' style='margin-top:14px'>{pays_html}</div><div class='card' style='margin-top:14px;overflow:auto'><table><tr><th>User / Session</th><th>Status</th><th>Joined</th><th>Action</th></tr>{users_html}</table></div>"
    return layout(content, session['email'], "master")

@app.route('/payment')
def payment_page():
    ref = f"AG35-{datetime.now().strftime('%m%d')}-{os.urandom(2).hex().upper()}"
    email = session.get('email','')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT referral_code, referral_count FROM agent35_users WHERE email=%s", (email,))
    urow = cur.fetchone()
    cur.close()
    conn.close()
    my_code = urow['referral_code'] if urow and urow['referral_code'] else ref
    my_count = urow['referral_count'] if urow and urow['referral_count'] else 0
    content = f"<div class='card' style='max-width:500px;margin:auto;text-align:center;padding:28px'><h2 style='color:#10b981'>Upgrade</h2><div class='warn' style='margin-bottom:10px'>R1000 Total = R500 Bot + R500 Trading<br><span style='color:#10b981'>OR Refer {my_count}/10 = Lifetime FREE</span></div><div style='background:#070d1a;padding:14px;border-radius:12px;border:1px solid #10b981;margin:12px 0'><div style='font-size:11px;color:#94a3b8'>YOUR REF LINK</div><div style='font-size:12px;font-weight:800;color:#10b981;word-break:break-all'>{request.host_url}r/{my_code}</div><div style='font-size:11px;margin-top:6px'>{my_count}/10 referrals</div></div><p>Capitec: <b>{CAPITEC_ACC}</b></p><div style='background:#070d1a;padding:14px;border-radius:12px;border:1px solid #1e2d45;margin:12px 0'><div style='font-size:22px;font-weight:800;color:#10b981'>{ref}</div></div><a class='btn' href='/submit-payment?ref={ref}&plan=yearly'>I Paid R500 Yearly ({ref})</a><a class='btn-outline' href='/submit-payment?ref={ref}&plan=lifetime'>I Paid R5000 Lifetime ({ref})</a></div>"
    return layout(content, session.get('email',''))

@app.route('/submit-payment')
def submit_payment():
    if 'email' not in session:
        return redirect('/')
    ref = request.args.get('ref')
    plan = request.args.get('plan')
    amount = 500 if plan=='yearly' else 5000
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO agent35_payments (user_email,plan,ref_code,amount,status) VALUES (%s,%s,%s,%s,'pending') ON CONFLICT (ref_code) DO NOTHING", (session['email'],plan,ref,amount))
    except:
        cur.execute("INSERT INTO agent35_payments (user_email,plan,ref_code,amount,status) VALUES (%s,%s,%s,%s,'pending')", (session['email'],plan,ref,amount))
    cur.execute("UPDATE agent35_users SET payment_ref=%s, plan=%s, payment_status='pending' WHERE email=%s", (ref,plan,session['email']))
    conn.commit()
    cur.close()
    conn.close()
    tg_link = f"https://t.me/{TELEGRAM_BOT_USERNAME}?start={ref}"
    return layout(f"<div class='card' style='text-align:center;max-width:500px;margin:auto'><h2 style='color:#10b981'>Submitted {ref}</h2><a href='{tg_link}' target='_blank' class='btn'>Link Telegram</a><a class='btn-outline' href='/dashboard'>Dashboard</a></div><script>setTimeout(()=>window.open('{tg_link}','_blank'),1200)</script>", session['email'])

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect('/')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],))
    user = cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC LIMIT 8", (session['email'],))
    trades = cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as pnl, COUNT(*) FILTER (WHERE status='win') as wins, COUNT(*) FILTER (WHERE status='loss') as losses, COUNT(*) FILTER (WHERE status IN ('win','loss')) as closed FROM agent35_trades WHERE user_email=%s", (session['email'],))
    stats = cur.fetchone()
    cur.close()
    conn.close()
    pnl = stats['pnl']
    wr = (stats['wins']/stats['closed']*100) if stats['closed']>0 else 0
    curr_sym = CUR.get(user['currency'],'$')
    syms = [s for s in (user['symbols'] or '').split(',') if s.strip()]
    chips = "".join([f"<span class='chip chip-active'><b>{s}</b><span class='x' onclick=\"removeSym('{s}')\">x</span></span>" for s in syms])
    rows = "".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td><b>{t['symbol']}</b></td><td><span class='badge { 'win' if t['status']=='win' else 'loss' if t['status']=='loss' else 'bull'}'>{t['status'].upper()}</span></td><td>{curr_sym}{round(t['pnl'],2)}</td></tr>" for t in trades]) or "<tr><td colspan=4>No trades</td></tr>"
    pay_ref = user['payment_ref'] or session['email']
    sess_display = user['sessions'] or 'London,New York'
    ref_link = f"{request.host_url.rstrip('/')}/r/{user['referral_code']}"
    ref_count = user['referral_count'] or 0
    progress = min(int(ref_count/10*100), 100)
    ref_widget = f"<div class='card' style='border:1.5px solid #10b981;background:linear-gradient(135deg,#0e1625,#0b1a13)'><div style='display:flex;justify-content:space-between'><div class='stat-label'>Refer 10 = Lifetime FREE (R5000)</div><div style='background:#10b981;color:#000;font-weight:900;padding:3px 10px;border-radius:20px;font-size:13px'>{ref_count}/10</div></div><div style='background:#070d1a;border-radius:10px;height:14px;margin:12px 0;border:1px solid #1e2d45'><div style='width:{progress}%;height:100%;background:#10b981;border-radius:10px'></div></div><input id='refLink' value='{ref_link}' readonly style='font-size:12px'><div style='display:flex;gap:8px;margin-top:10px'><button class='btn' style='flex:1' onclick=\"navigator.clipboard.writeText('{ref_link}');this.innerText='COPIED!';setTimeout(()=>this.innerText='COPY LINK',2000)\">COPY LINK</button><a class='btn-outline' style='flex:1;background:#25D366;color:#000;font-weight:900;border:none' href=\"https://wa.me/?text=Yo! I use Agent35 to scan EURUSD and Gold with 80% accuracy. Join with my link and we both level up: {ref_link}\" target='_blank'>WHATSAPP</a></div><div style='font-size:11px;margin-top:8px;color:#94a3b8'>Share. When friend pays + you approve, you get +1. At 10 auto Lifetime.</div></div>"
    content = ref_widget + f"<div class='grid grid4'><div class='card'><div class='stat-label'>PNL {sess_display}</div><div class='stat-value'>{curr_sym}{round(pnl,2)} <span class='badge bull'>{round(wr,1)}% WR</span></div><div style='font-size:10px'>Active now: {is_session_active(sess_display)} | UTC {datetime.utcnow().strftime('%H:%M')}</div></div><div class='card'><div class='stat-label'>Account</div><div class='stat-value' style='font-size:18px'>{curr_sym}{user['account_size']}</div><a href='/settings' class='btn-outline'>Edit Sessions</a><a href='/guide' class='btn-outline' style='border-color:#10b981;color:#10b981'>Start Guide</a></div><div class='card' style='position:relative'><div class='stat-label'>Watchlist {len(syms)}/5</div><div style='margin:12px 0'>{chips}</div><form id='symForm' method='POST' action='/quick-symbols'><input type='hidden' name='symbols' id='symInput' value=\"{user['symbols']}\"></form><input id='symSearch' class='searchbox' placeholder='Search...' oninput='filterSyms()' autocomplete='off'><div id='symDropdown' class='dropdown'></div></div><div class='card'><a class='btn' href='/scan'>SCAN NOW</a><a href='https://t.me/{TELEGRAM_BOT_USERNAME}?start={pay_ref}' target='_blank' class='btn-outline'>Link TG: {pay_ref}</a><a href='/test-telegram' class='btn-test'>Test with Reason</a></div></div><div class='card' style='margin-top:14px'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>PNL</th></tr>{rows}</table></div>"
    return layout(content, session['email'], "dashboard")

@app.route('/test-telegram')
def test_telegram():
    if 'email' not in session:
        return redirect('/')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],))
    u = cur.fetchone()
    cur.close()
    conn.close()
    if not u or not u['telegram_id']:
        return layout("<div class='card'>Not Linked - See Guide</div>", session['email'])
    fake_res = {"symbol":"XAUUSD","direction":"BUY","entry":2675.5,"sl":2668.0,"tp":2695.0,"score":7,"bias":"Bullish HTF","confluence":["Daily bullish","4H BOS","1H FVG tap","London sweep","RSI 55","No red news"],"reason":"HTF bullish, swept Asia low, FVG tap + OB"}
    msg = build_signal_msg(fake_res, u)
    ok = send_telegram(u['telegram_id'], msg, trade_id=99999, stage="signal")
    return layout(f"<div class='card'><h3 style='color:#10b981'>Sent!</h3><p style='font-size:12px;white-space:pre-wrap'>{msg}</p><a class='btn' href='/dashboard'>Back</a></div>" if ok else "<div class='card'>Failed</div>", session['email'])

@app.route('/journal')
def journal():
    if 'email' not in session:
        return redirect('/')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],))
    user = cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC", (session['email'],))
    trades = cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as total FROM agent35_trades WHERE user_email=%s", (session['email'],))
    s = cur.fetchone()
    cur.close()
    conn.close()
    curr_sym = CUR.get(user['currency'],'$')
    rows = "".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td><b>{t['symbol']}</b></td><td>{t['direction']}</td><td>{t['status']}</td><td>{curr_sym}{round(t['pnl'],2)}</td></tr>" for t in trades])
    return layout(f"<div class='card'><div class='stat-value'>{curr_sym}{round(s['total'],2)}</div><a href='/export/csv' class='btn'>Export CSV</a></div><div class='card' style='margin-top:14px;overflow:auto'><table><tr><th>Date</th><th>Symbol</th><th>Dir</th><th>Status</th><th>PNL</th></tr>{rows}</table></div>", session['email'], "journal")

@app.route('/export/csv')
def export_csv():
    if 'email' not in session:
        return redirect('/')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],))
    user = cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC", (session['email'],))
    trades = cur.fetchall()
    cur.close()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date','Symbol','Direction','Entry','SL','TP','Status','PNL','Ref'])
    for t in trades:
        writer.writerow([t['created_at'],t['symbol'],t['direction'],t['entry'],t['sl'],t['tp'],t['status'],t['pnl'],user['payment_ref']])
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=agent35_{datetime.now().strftime("%Y-%m-%d")}.csv'})

@app.route('/quick-symbols', methods=['POST'])
def quick_symbols():
    if 'email' not in session:
        return redirect('/')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE agent35_users SET symbols=%s WHERE email=%s",(request.form['symbols'][:100], session['email']))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/dashboard')

@app.route('/scan')
def scan():
    if 'email' not in session:
        return redirect('/')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],))
    user = cur.fetchone()
    if not is_session_active(user['sessions'] or 'London,New York'):
        cur.close()
        conn.close()
        return layout(f"<div class='card' style='text-align:center'><h3 style='color:#f59e0b'>Outside your sessions</h3><p>Your sessions: {user['sessions']}<br>UTC now: {datetime.utcnow().strftime('%H:%M')}</p><a class='btn' href='/settings'>Change Sessions</a><a class='btn' href='/guide'>See Guide</a></div>", session['email'])
    symbols = (user['symbols'] or "EURUSD").split(",")[:5]
    results = []
    for sym in symbols:
        sym = sym.strip().upper()
        if not sym:
            continue
        try:
            res = engine.full_multi_tf_analysis(sym)
        except:
            res = {"signal":False,"symbol":sym}
        res['symbol'] = sym
        results.append(res)
        if res.get('signal'):
            cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,timeframe_bias,confluence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",(session['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['bias'],str(res.get('confluence',''))))
            new_row = cur.fetchone()
            tid = new_row['id'] if new_row else 0
            if user['telegram_id']:
                msg = build_signal_msg(res, user)
                send_telegram(user['telegram_id'], msg, trade_id=tid, stage="signal")
    conn.commit()
    cur.close()
    conn.close()
    html = "".join([f"<div class='card' style='border-left:4px solid #ef4444;margin:10px 0'><b>{r['symbol']} - BLOCKED: {r.get('blocked')}</b></div>" if r.get('blocked') else f"<div class='card' style='border-left:4px solid #10b981;margin:10px 0'><b>{r['symbol']} {r.get('direction','')} {r.get('score',0)}/8</b><br>{r.get('confluence','')}<br><i style='font-size:11px'>{r.get('reason','') or r.get('bias','')}</i><br>Entry {r.get('entry','')} SL {r.get('sl','')} TP {r.get('tp','')}</div>" if r.get('signal') else f"<div class='card' style='opacity:0.6;margin:10px 0'><b>{r['symbol']} - No Setup</b></div>" for r in results])
    return layout(f"<h2>Scan Results - {user['sessions']} | UTC {datetime.utcnow().strftime('%H:%M')}</h2>{html}<br><a class='btn' href='/journal'>Journal</a>", session['email'])

@app.route('/settings', methods=['GET','POST'])
def settings():
    if 'email' not in session:
        return redirect('/')
    if request.method=='POST':
        sess_list = []
        if request.form.get('sess_london'):
            sess_list.append("London")
        if request.form.get('sess_ny'):
            sess_list.append("New York")
        if request.form.get('sess_asia'):
            sess_list.append("Asia")
        if request.form.get('sess_sydney'):
            sess_list.append("Sydney")
        if request.form.get('sess_all'):
            sess_list = ["24/7"]
        sessions_str = ",".join(sess_list) if sess_list else "London,New York"
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE agent35_users SET symbols=%s, risk_reward=%s, account_size=%s, lot_size=%s, currency=%s, currency_symbol=%s, telegram_username=%s, sessions=%s WHERE email=%s",(request.form['symbols'][:100], request.form['rr'], float(request.form['acc']), float(request.form['lot']), request.form['currency'], CUR.get(request.form['currency'],'$'), request.form['tg'], sessions_str, session['email']))
        conn.commit()
        cur.close()
        conn.close()
        return redirect('/dashboard')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],))
    u = cur.fetchone()
    cur.close()
    conn.close()
    sel_usd = "selected" if u['currency']=='USD' else ""
    sel_zar = "selected" if u['currency']=='ZAR' else ""
    sel_eur = "selected" if u['currency']=='EUR' else ""
    sel_12 = "selected" if u['risk_reward']=='1:2' else ""
    sel_13 = "selected" if u['risk_reward']=='1:3' else ""
    sel_14 = "selected" if u['risk_reward']=='1:4' else ""
    sess = (u['sessions'] or 'London,New York')
    c_london = "checked" if "London" in sess else ""
    c_ny = "checked" if "New York" in sess else ""
    c_asia = "checked" if "Asia" in sess else ""
    c_sydney = "checked" if "Sydney" in sess else ""
    c_all = "checked" if "24/7" in sess else ""
    content = f"<div style='max-width:700px;margin:auto'><h2 style='color:#10b981'>Settings</h2><form method='POST'><div class='settings-section'><div style='display:grid;grid-template-columns:1fr 1fr;gap:12px'><div><label>Currency</label><select name='currency'><option value='USD' {sel_usd}>USD</option><option value='ZAR' {sel_zar}>ZAR</option><option value='EUR' {sel_eur}>EUR</option></select></div><div><label>Account</label><input name='acc' type='number' value='{u['account_size']}'></div><div><label>Lot</label><input name='lot' type='number' step='0.01' value='{u['lot_size']}'></div><div><label>RR</label><select name='rr'><option {sel_12}>1:2</option><option {sel_13}>1:3</option><option {sel_14}>1:4</option></select></div></div><label>Symbols</label><input name='symbols' value='{u['symbols']}'><label>Telegram @</label><input name='tg' value='{u['telegram_username'] or ''}'><div style='margin-top:16px'><label>Preferred Sessions</label><div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px'><label class='sess-check'><input type='checkbox' name='sess_london' {c_london}> London 8-16 UTC</label><label class='sess-check'><input type='checkbox' name='sess_ny' {c_ny}> New York 13-21 UTC</label><label class='sess-check'><input type='checkbox' name='sess_asia' {c_asia}> Asia 0-9 UTC</label><label class='sess-check'><input type='checkbox' name='sess_sydney' {c_sydney}> Sydney 22-6 UTC</label></div><label class='sess-check' style='margin-top:8px;background:#10b98122;border-color:#10b981'><input type='checkbox' name='sess_all' {c_all}> 24/7 - All sessions</label></div></div><button class='btn'>Save All</button><a href='/dashboard' class='btn-outline'>Back</a><a href='/guide' class='btn-outline' style='border-color:#10b981;color:#10b981'>See Guide</a></form></div>"
    return layout(content, session['email'], "settings")

@app.route('/telegram/webhook', methods=['POST'])
def tg_webhook():
    data = request.json
    try:
        conn = get_conn()
        cur = conn.cursor()
        if 'callback_query' in data:
            cq = data['callback_query']
            chat_id = cq['message']['chat']['id']
            cdata = cq['data']
            action, tid = cdata.split(':')
            tid = int(tid)
            cur.execute("SELECT * FROM agent35_trades WHERE id=%s", (tid,))
            tr = cur.fetchone()
            if tr:
                if action=='took':
                    cur.execute("UPDATE agent35_trades SET status='took', hit_entry_at=NOW() WHERE id=%s", (tid,))
                    conn.commit()
                    send_telegram(chat_id, f"TOOK {tr['symbol']} active", trade_id=tid, stage="active")
                elif action=='skip':
                    cur.execute("UPDATE agent35_trades SET status='skipped' WHERE id=%s", (tid,))
                    conn.commit()
                    send_telegram(chat_id, f"Skipped {tr['symbol']}")
                elif action in ('win','loss','be'):
                    cur.execute("SELECT account_size, risk_reward, currency_symbol FROM agent35_users WHERE email=%s", (tr['user_email'],))
                    u = cur.fetchone()
                    rr = 3
                    try:
                        rr = int(u['risk_reward'].split(':')[1])
                    except:
                        pass
                    risk = u['account_size']*0.01
                    pnl = risk*rr if action=='win' else -risk if action=='loss' else 0
                    status = 'win' if action=='win' else 'loss' if action=='loss' else 'be'
                    cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s WHERE id=%s", (status,pnl,tr['tp'] if status=='win' else tr['sl'],tid))
                    conn.commit()
                    cs = u['currency_symbol'] or '$'
                    send_telegram(chat_id, f"{'WIN' if status=='win' else 'LOSS' if status=='loss' else 'BE'} {tr['symbol']} PNL {cs}{round(pnl,2)}")
            try:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={"callback_query_id":cq['id'],"text":f"{action.upper()} saved"}, timeout=5)
            except:
                pass
            cur.close()
            conn.close()
            return jsonify({"ok":True})
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            username = data['message']['chat'].get('username','')
            text = data['message'].get('text','').strip()
            ref = text.split('/start')[-1].strip() if '/start' in text else text.strip()
            if not ref:
                cur.close()
                conn.close()
                return jsonify({"ok":True})
            cur.execute("SELECT email, payment_ref FROM agent35_users WHERE payment_ref=%s OR email=%s OR payment_ref ILIKE %s", (ref, ref.lower(), f"%{ref}%"))
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE agent35_users SET telegram_id=%s, telegram_username=%s WHERE email=%s", (str(chat_id), username, row['email']))
                conn.commit()
                send_telegram(chat_id, f"Linked! {row['email']}", trade_id=88888, stage="signal")
            else:
                send_telegram(chat_id, f"Ref {ref} not found - see /guide")
            cur.close()
            conn.close()
    except Exception as e:
        print(f"tg error {e}")
    return jsonify({"ok":True})

@app.route('/setup-webhook')
def setup_webhook():
    if 'email' not in session:
        return redirect('/')
    if not TELEGRAM_TOKEN:
        return "No TELEGRAM_BOT_TOKEN"
    base = request.host_url.rstrip('/')
    wh_url = f"{base}/telegram/webhook"
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={wh_url}")
    return layout(f"<div class='card'><h3>Webhook</h3><p>{wh_url}</p><p>{r.text}</p><a class='btn' href='/master'>Back</a></div>", session['email'])

@app.route('/cron/update-trades')
def cron_update():
    def do_update():
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT t.*, u.account_size, u.risk_reward FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.status IN ('sent','took','active') LIMIT 20")
            for tr in cur.fetchall():
                live = get_live_price(tr['symbol'])
                if not live:
                    continue
                close,high,low = live
                rr = 3
                try:
                    rr = int(tr['risk_reward'].split(':')[1])
                except:
                    pass
                risk = tr['account_size']*0.01
                new = None
                pnl = 0
                if tr['status']=='sent' and low <= tr['entry'] <= high:
                    new = 'took'
                elif tr['status'] in ('took','active'):
                    if tr['direction']=='BUY':
                        if low <= tr['sl']:
                            new='loss'
                            pnl=-risk
                        elif high >= tr['tp']:
                            new='win'
                            pnl=risk*rr
                    else:
                        if high >= tr['sl']:
                            new='loss'
                            pnl=-risk
                        elif low <= tr['tp']:
                            new='win'
                            pnl=risk*rr
                if new and new!=tr['status']:
                    if new in ('win','loss'):
                        cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s, auto_updated=TRUE WHERE id=%s",(new,pnl,close,tr['id']))
                    else:
                        cur.execute("UPDATE agent35_trades SET status=%s, hit_entry_at=NOW() WHERE id=%s",(new,tr['id']))
            conn.commit()
            cur.close()
            conn.close()
        except:
            pass
    threading.Thread(target=do_update, daemon=True).start()
    return jsonify({"ok":True})

@app.route('/cron/scan-all')
def cron_scan_all():
    def do_scan():
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT * FROM agent35_users WHERE payment_status='approved' LIMIT 100")
            users = cur.fetchall()
            for user in users:
                if not is_session_active(user['sessions'] or 'London,New York'):
                    continue
                symbols = (user['symbols'] or "EURUSD").split(",")[:2]
                for sym in symbols:
                    sym = sym.strip().upper()
                    if not sym:
                        continue
                    try:
                        res = engine.full_multi_tf_analysis(sym)
                    except:
                        continue
                    if res.get('blocked') == 'news':
                        continue
                    if res.get('signal'):
                        cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,timeframe_bias,confluence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",(user['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['bias'],str(res.get('confluence',''))))
                        row = cur.fetchone()
                        if row and user['telegram_id']:
                            msg = build_signal_msg(res, user)
                            send_telegram(user['telegram_id'], msg, trade_id=row['id'], stage="signal")
            conn.commit()
            cur.close()
            conn.close()
        except:
            pass
    threading.Thread(target=do_scan, daemon=True).start()
    return jsonify({"ok":True})

@app.route('/healthz')
def health():
    return jsonify({"status":"ok","version":"V6.1-referral","utc":datetime.utcnow().isoformat()})

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))           
