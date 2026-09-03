import os, hashlib, requests, psycopg, threading, time, csv, io
from psycopg.rows import dict_row
from flask import Flask, request, redirect, session, jsonify, Response
from datetime import datetime
from zoneinfo import ZoneInfo
import trading_engine as engine
import yfinance as yf
import traceback

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'agent35-secret-2025')
DATABASE_URL = os.environ.get('DATABASE_URL','').strip()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
TELEGRAM_BOT_USERNAME = "Sniper035_bot"
CAPITEC_ACC = "2586572676"
RISK_PCT = float(os.environ.get('RISK_PCT','1.5'))

LOGO_SVG = '<svg width="34" height="34" viewBox="0 0 100 100"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#059669"/></linearGradient></defs><rect width="100" height="100" rx="18" fill="#0b111c" stroke="#10b981" stroke-width="3"/><text x="50%" y="58%" dominant-baseline="middle" text-anchor="middle" font-family="Arial Black" font-weight="900" font-size="48" fill="url(#g)">35</text></svg>'
CUR = {'USD':'$','ZAR':'R','EUR':'\u20ac','GBP':'\u00a3'}
MAP = engine.MAP

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
*{box-sizing:border-box} body{background:#060a14;color:#e5e7eb;font-family:'Inter',sans-serif;margin:0}.header{background:#0b111c;border-bottom:1px solid #1a2535;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}.logo{display:flex;align-items:center;gap:10px;color:#10b981;font-weight:800}.card{background:#0e1625;border:1px solid #1c2a41;border-radius:16px;padding:16px}.btn{background:linear-gradient(135deg,#10b981,#059669);color:#000;font-weight:800;padding:12px 18px;border:none;border-radius:12px;cursor:pointer;text-decoration:none;display:block;text-align:center;width:100%}.btn-outline{background:transparent;border:1px solid #24344e;color:#cbd5e1;padding:12px 18px;border-radius:12px;text-decoration:none;display:block;text-align:center;width:100%;margin-top:8px}.btn-test{background:#3b82f6;color:#fff;font-weight:700;padding:10px;border:none;border-radius:10px;width:100%;margin-top:8px;display:block;text-align:center;text-decoration:none}.grid{display:grid;gap:14px}.grid4{grid-template-columns:repeat(4,1fr)}.badge{padding:5px 10px;border-radius:20px;font-size:11px;font-weight:800}.bull{background:rgba(16,185,129,0.15);color:#10b981}.bear{background:rgba(239,68,68,0.15);color:#ef4444}.win{background:rgba(16,185,129,0.25);color:#10b981}.loss{background:rgba(239,68,68,0.25);color:#ef4444}.chip{display:inline-flex;align-items:center;gap:6px;background:#121d30;border:1px solid #1e2d45;padding:7px 12px;border-radius:24px;margin:4px;font-size:13px;cursor:pointer}.chip-active{background:#10b98122;border-color:#10b981}.x{background:#ef4444;color:#fff;border-radius:50%;width:20px;height:20px;display:inline-flex;justify-content:center;align-items:center;font-size:12px;margin-left:6px}.searchbox{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:12px;width:100%;margin:8px 0}.dropdown{background:#121d30;border:1px solid #1e2d45;border-radius:12px;max-height:200px;overflow:auto;display:none;position:absolute;z-index:50;width:calc(100% - 32px)}.dropdown div{padding:10px 14px;cursor:pointer;border-bottom:1px solid #1a2535} table{width:100%;border-collapse:collapse} th{color:#64748b;text-align:left;padding:12px 8px;font-size:10px;text-transform:uppercase} td{padding:12px 8px;border-top:1px solid #1a2535;font-size:13px}.nav-tabs{display:flex;gap:8px;overflow:auto;margin:12px 0}.nav-tabs a{white-space:nowrap;padding:10px 16px;border-radius:24px;background:#121d30;border:1px solid #1e2d45;color:#94a3b8;text-decoration:none;font-size:13px;font-weight:600}.nav-tabs a.active{background:#10b981;color:#000;border-color:#10b981}.stat-label{font-size:11px;color:#64748b;text-transform:uppercase}.stat-value{font-size:22px;font-weight:800;margin-top:6px} @media(max-width:900px){.grid4{grid-template-columns:1fr 1fr}} @media(max-width:600px){.grid4{grid-template-columns:1fr}table{display:block;overflow-x:auto}} input,select{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:10px;width:100%;margin:6px 0} label{font-size:12px;color:#94a3b8;margin-top:12px;display:block;font-weight:600}.settings-section{background:#0e1625;border:1px solid #1c2a41;border-radius:16px;padding:20px;margin-bottom:16px}.sess-check{display:flex;align-items:center;gap:8px;background:#121d30;padding:12px;border-radius:12px;border:1px solid #1e2d45;cursor:pointer}.sess-check input{width:18px;height:18px}.warn{background:#f59e0b22;border:1px solid #f59e0b;color:#f59e0b;padding:12px;border-radius:10px;text-align:center;font-weight:700}
.clock-bar{display:flex;gap:10px;align-items:center;background:#121d30;border:1px solid #1e2d45;padding:6px 12px;border-radius:20px;font-size:11px;margin-left:12px}
.live-dot{width:8px;height:8px;background:#10b981;border-radius:50%;display:inline-block;animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}
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
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_users (id SERIAL PRIMARY KEY, email TEXT UNIQUE, password TEXT,is_creator BOOLEAN DEFAULT FALSE, plan TEXT DEFAULT 'none',payment_ref TEXT, payment_status TEXT DEFAULT 'pending',risk_reward TEXT DEFAULT '1:3', symbols TEXT DEFAULT 'EURUSD,XAUUSD,BTCUSD,GBPUSD,NAS100',sessions TEXT DEFAULT 'London,New York', account_size FLOAT DEFAULT 10000,lot_size FLOAT DEFAULT 0.1, leverage TEXT DEFAULT '1:500',telegram_id TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_trades (id SERIAL PRIMARY KEY, user_email TEXT, symbol TEXT,direction TEXT, entry FLOAT, sl FLOAT, tp FLOAT,status TEXT DEFAULT 'sent', pnl FLOAT DEFAULT 0,timeframe_bias TEXT, confluence TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_payments (id SERIAL PRIMARY KEY, user_email TEXT, plan TEXT,ref_code TEXT UNIQUE, amount INT, status TEXT DEFAULT 'pending',created_at TIMESTAMP DEFAULT NOW());""")
    for q in ["ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USD'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS telegram_username TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency_symbol TEXT DEFAULT '$'","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS hit_entry_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS result_price FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS auto_updated BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS sessions TEXT DEFAULT 'London,New York'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_code TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referred_by TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_count INT DEFAULT 0","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'Africa/Johannesburg'","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS be_done BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS lock_done BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS close_r FLOAT DEFAULT 0","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS original_sl FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS original_entry FLOAT"]:
        try: cur.execute(q)
        except: pass
    conn.commit()
    cur.execute("SELECT * FROM agent35_users WHERE email='creator@agent35.com'")
    if not cur.fetchone():
        pw = hashlib.sha256('Agent35Creator!'.encode()).hexdigest()
        cur.execute("INSERT INTO agent35_users (email,password,is_creator,plan,payment_status,paid_at,sessions,referral_code,referral_count,timezone) VALUES (%s,%s,TRUE,'lifetime','approved',NOW(),'24/7',%s,0,'Africa/Johannesburg')", ('creator@agent35.com', pw, f"AG35-CREATOR-{os.urandom(2).hex().upper()}"))
    conn.commit(); cur.close(); conn.close()
init_db()

def send_telegram(chat_id, text, trade_id=None, stage="signal", extra_buttons=None):
    if not TELEGRAM_TOKEN or not chat_id: return False
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode":"Markdown"}
        if trade_id:
            if stage=="signal":
                payload["reply_markup"] = {"inline_keyboard": [[{"text":"\u2705 TOOK ENTRY","callback_data":f"took:{trade_id}"},{"text":"\u274c SKIP","callback_data":f"skip:{trade_id}"}],[{"text":"\ud83d\udcca View Journal","url":"https://agent-35-trading-bot.onrender.com/journal"}]]}
            elif stage=="active":
                kb = [[{"text":"\u2705 WIN","callback_data":f"win:{trade_id}"},{"text":"\u274c LOSS","callback_data":f"loss:{trade_id}"},{"text":"\u2796 BE","callback_data":f"be:{trade_id}"}],[{"text":"\ud83d\udcb0 CLOSE EARLY","callback_data":f"closeearly:{trade_id}"}]]
                if extra_buttons: kb = extra_buttons + kb
                payload["reply_markup"] = {"inline_keyboard": kb}
            elif stage=="profitlock":
                payload["reply_markup"] = {"inline_keyboard": extra_buttons}
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload, timeout=10)
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
        sym=res['symbol']; direction=res['direction']; entry=res['entry']; sl=res['sl']; tp=res['tp']; score=res['score']; bias=res.get('bias',''); confluence=res.get('confluence',[]); reason=res.get('reason',''); quality=res.get('quality','STANDARD')
        try:
            user_tz = (user.get('timezone') if user and user.get('timezone') else 'Africa/Johannesburg')
            now_local = datetime.now(ZoneInfo(user_tz)).strftime("%H:%M %Z")
            now_sast = datetime.now(ZoneInfo("Africa/Johannesburg")).strftime("%H:%M SAST")
        except:
            user_tz='Africa/Johannesburg'; now_local=datetime.utcnow().strftime("%H:%M UTC"); now_sast=now_local
        rr_val=0
        if entry!=sl:
            if direction=="BUY": rr_val=(tp-entry)/(entry-sl) if (entry-sl)!=0 else 0
            else: rr_val=(entry-tp)/(sl-entry) if (sl-entry)!=0 else 0
        acc = user.get('account_size',1000) if user else 1000
        risk_money = acc * (RISK_PCT/100)
        profit_money = risk_money * rr_val
        conf_text="\n".join([f"• {c}" for c in confluence[:8]])
        news_alert=""
        if res.get('news_warning'):
            news_alert=f"\n\n{res.get('news_text','⚠️ HIGH IMPACT NEWS')}"
        if "SNIPER" in quality: header="🔥🔥 SNIPER - Bu-OB/Be-OB+MB 🔥🔥"
        elif "PREMIUM" in quality: header="🔥 PREMIUM"
        else: header="📊"
        emoji="🟢" if direction=="BUY" else "🔴"
        msg=f"""{emoji} {sym} {direction} | {quality} {score}/8
{header}
💰 Entry: {entry}
🛑 SL: {sl}
🎯 TP: {tp}
📊 RR: 1:{rr_val:.1f} | Risk: ${risk_money:.2f} -> +${profit_money:.2f}

🔍 Confluence:
{conf_text}
{news_alert}

📝 {reason}
⏰ {now_local} | {now_sast}
"""
        return msg
    except Exception as e:
        return f"{res.get('symbol')} {res.get('direction')} {res.get('entry')} {e}"

def layout(content, email="", active="dashboard"):
    is_creator="creator" in email.lower()
    ad="active" if active=="dashboard" else ""; aj="active" if active=="journal" else ""; asi="active" if active=="signals" else ""; aset="active" if active=="settings" else ""; am="active" if active=="master" else ""; ag="active" if active=="guide" else ""
    master_tab=f'<a href="/master" class="{am}">Master</a>' if is_creator else ""
    tabs=f'<div class="nav-tabs"><a href="/dashboard" class="{ad}">Dashboard</a><a href="/journal" class="{aj}">Journal (Taken)</a><a href="/signals" class="{asi}">All Signals</a><a href="/settings" class="{aset}">Settings</a><a href="/payment">Plans</a><a href="/guide" class="{ag}">Guide</a>{master_tab}</div>'
    return f'<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Agent35 V8.2</title>{STYLE}</head><body><div class="header"><div class="logo">{LOGO_SVG} AGENT 35 V8.2 NO-SPAM <div class="clock-bar"><span class="live-dot"></span><span id="utcClock">UTC --:--:--</span> | <span id="sastClock">SAST --:--:--</span> | <span id="sessClock" style="color:#10b981;font-weight:800">Loading</span></div></div><div><span style="font-size:11px;color:#94a3b8">{email}</span> <a href="/logout" style="color:#94a3b8;text-decoration:none;margin-left:10px">Logout</a></div></div><div style="padding:14px;max-width:1400px;margin:auto">{tabs}{content}</div><script>function updateClock(){{const now=new Date();const utc=now.toISOString().substr(11,8);document.getElementById("utcClock").innerText="UTC "+utc;try{{const sast=new Date(now.toLocaleString("en-US",{{timeZone:"Africa/Johannesburg"}}));document.getElementById("sastClock").innerText="SAST "+sast.toLocaleTimeString("en-GB");}}catch(e){{document.getElementById("sastClock").innerText="SAST "+utc;}} const h=now.getUTCHours();let s=[];if(h>=22||h<6)s.push("Sydney");if(h>=0&&h<9)s.push("Asia");if(h>=8&&h<16)s.push("London");if(h>=13&&h<21)s.push("New York");if(s.length==0)s=["Off Hours"];document.getElementById("sessClock").innerText=s.join(" + ")+" ACTIVE";}} setInterval(updateClock,1000);updateClock();</script></body></html>'

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
    if trade['direction'] == 'BUY':
        return (close_price - trade['entry']) / risk
    else:
        return (trade['entry'] - close_price) / risk

def auto_update_trades_loop():
    while True:
        try:
            conn=get_conn(); cur=conn.cursor()
            # V8.2 FIX: ONLY TOOK/ACTIVE - NO SPAM FOR SENT
            cur.execute("SELECT t.*, u.account_size, u.risk_reward, u.telegram_id, u.currency_symbol FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.status IN ('took','active') LIMIT 40")
            rows = cur.fetchall()
            for tr in rows:
                live=get_live_price(tr['symbol'])
                if not live: continue
                close,high,low=live
                r_now = calc_r_now(tr, close)
                if r_now >= 1.0 and not tr.get('be_done'):
                    cur.execute("UPDATE agent35_trades SET be_done=TRUE, sl=%s WHERE id=%s", (tr['entry'], tr['id']))
                    conn.commit()
                    if tr['telegram_id']:
                        send_telegram(tr['telegram_id'], f"🔒 {tr['symbol']} +1R -> BE {tr['entry']}\n💰 Floating +{r_now:.1f}R")
                if r_now >= 2.0 and not tr.get('lock_done'):
                    cur.execute("UPDATE agent35_trades SET lock_done=TRUE WHERE id=%s", (tr['id'],))
                    conn.commit()
                    if tr['telegram_id']:
                        risk_money = tr['account_size'] * (RISK_PCT/100)
                        extra = [[{"text":"🔒 LOCK +1R PROFIT","callback_data":f"lock:{tr['id']}"},{"text":"💰 CLOSE EARLY","callback_data":f"closeearly:{tr['id']}"}]]
                        send_telegram(tr['telegram_id'], f"💎 {tr['symbol']} +2R COMFORTABLE! +${risk_money*r_now:.2f}\nLock +1R = +${risk_money:.2f} secured?", trade_id=tr['id'], stage="profitlock", extra_buttons=extra)
                rr=3
                try: rr=int(tr['risk_reward'].split(':')[1])
                except: pass
                risk_money=tr['account_size']*0.01; new=None; pnl=0
                if tr['direction']=='BUY':
                    if low <= tr['sl']: new='be' if tr.get('be_done') else 'loss'; pnl=0 if tr.get('be_done') else -risk_money
                    elif high >= tr['tp']: new='win'; pnl=risk_money*rr
                else:
                    if high >= tr['sl']: new='be' if tr.get('be_done') else 'loss'; pnl=0 if tr.get('be_done') else -risk_money
                    elif low <= tr['tp']: new='win'; pnl=risk_money*rr
                if new:
                    close_r = rr if new=='win' else 0 if new=='be' else -1
                    cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s, auto_updated=TRUE, close_r=%s WHERE id=%s",(new,pnl,close,tr['id'],close_r))
                    conn.commit()
                    if tr['telegram_id']:
                        cs=tr['currency_symbol'] or '$'
                        if new=='win': send_telegram(tr['telegram_id'], f"✅ {tr['symbol']} WIN +{rr}R {cs}{pnl:.2f}\n💼 Balance ~{cs}{tr['account_size']+pnl:.2f}")
                        elif new=='be': send_telegram(tr['telegram_id'], f"➖ {tr['symbol']} BE 0R Protected")
                        else: send_telegram(tr['telegram_id'], f"❌ {tr['symbol']} LOSS -1R {cs}{pnl:.2f}")
            cur.close(); conn.close()
        except Exception as e:
            print(f"loop err {e}")
        time.sleep(90)

threading.Thread(target=auto_update_trades_loop, daemon=True).start()

@app.route('/')
def home():
    return f'<html><head><meta name="viewport" content="width=device-width, initial-scale=1">{STYLE}</head><body style="display:flex;justify-content:center;align-items:center;min-height:100vh;padding:16px"><div class="card" style="max-width:400px;width:100%;text-align:center;padding:28px"><h1 style="color:#10b981;margin:0">AGENT 35 V8.2</h1><p>NO-SPAM + 2 Sheets</p><form method="POST" action="/auth" style="text-align:left;margin-top:18px"><label>Email</label><input name="email" required><label>Password</label><input name="password" type="password" required><button class="btn" style="margin-top:16px">Login</button></form></div></body></html>'

@app.route('/r/<code>')
def referral_link(code):
    session['ref_code']=code.upper().strip(); return redirect('/')

@app.route('/guide')
def guide_page():
    email=session.get('email','')
    content="<h1 style='color:#10b981'>V8.2</h1><div class='card'><b>Journal</b> = Only TOOK trades + Money<br><b>All Signals</b> = All signals for bot winrate<br><b>Telegram</b> = Only alerts for TOOK trades (BE, LOCK, WIN, LOSS)</div><div class='card' style='text-align:center'><a class='btn' href='/dashboard'>Dashboard</a></div>"
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
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND status IN ('took','active','win','loss','be','win_early') ORDER BY created_at DESC LIMIT 8", (session['email'],)); trades=cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as pnl, COUNT(*) FILTER (WHERE status='win' OR status='win_early') as wins, COUNT(*) FILTER (WHERE status='loss') as losses, COUNT(*) FILTER (WHERE status IN ('win','loss','be','win_early')) as closed, COALESCE(SUM(close_r),0) as total_r FROM agent35_trades WHERE user_email=%s AND status IN ('took','active','win','loss','be','win_early')", (session['email'],)); stats=cur.fetchone()
    cur.close(); conn.close()
    pnl=stats['pnl']; wr=(stats['wins']/stats['closed']*100) if stats['closed']>0 else 0; curr_sym=CUR.get(user['currency'],'$')
    total_r = stats['total_r'] or 0
    syms=[s for s in (user['symbols'] or '').split(',') if s.strip()]; chips="".join([f"<span class='chip chip-active'><b>{s}</b><span class='x' onclick=\"removeSym('{s}')\">x</span></span>" for s in syms])
    rows="".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td><b>{t['symbol']}</b></td><td><span class='badge { 'win' if 'win' in t['status'] else 'loss' if t['status']=='loss' else 'bull'}'>{t['status'].upper()}</span></td><td>{curr_sym}{round(t['pnl'] or 0,2)} ({t.get('close_r',0)}R)</td></tr>" for t in trades]) or "<tr><td colspan=4>No taken trades yet</td></tr>"
    pay_ref=user['payment_ref'] or session['email']; sess_display=user['sessions'] or 'London,New York'; ref_link=f"{request.host_url.rstrip('/')}/r/{user['referral_code']}"; ref_count=user['referral_count'] or 0
    user_tz = user.get('timezone') or 'Africa/Johannesburg'
    content=f"<div class='card' style='padding:12px;display:flex;justify-content:space-between'><span>TZ: <b>{user_tz}</b></span><span>WR: {wr:.1f}% | {total_r:.1f}R | {curr_sym}{pnl:.2f}</span></div><div class='grid grid4'><div class='card'><div class='stat-label'>PNL {sess_display} (Taken Only)</div><div class='stat-value'>{curr_sym}{round(pnl,2)} <span class='badge bull'>{round(wr,1)}% {total_r:.1f}R</span></div></div><div class='card'><div class='stat-label'>Account</div><div class='stat-value' style='font-size:18px'>{curr_sym}{user['account_size']}</div><div style='font-size:11px'>Risk {RISK_PCT}% = {curr_sym}{user['account_size']*RISK_PCT/100:.2f}</div><a href='/settings' class='btn-outline'>Edit</a></div><div class='card' style='position:relative'><div class='stat-label'>Watchlist {len(syms)}/5</div><div style='margin:12px 0'>{chips}</div><form id='symForm' method='POST' action='/quick-symbols'><input type='hidden' name='symbols' id='symInput' value=\"{user['symbols']}\"></form><input id='symSearch' class='searchbox' placeholder='Search...' oninput='filterSyms()' autocomplete='off'><div id='symDropdown' class='dropdown'></div></div><div class='card'><a class='btn' href='/scan'>SCAN V8.2</a><a href='https://t.me/{TELEGRAM_BOT_USERNAME}?start={pay_ref}' target='_blank' class='btn-outline'>Link TG</a><a href='/test-telegram' class='btn-test'>Test TG</a></div></div><div class='card' style='margin-top:14px'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>PNL</th></tr>{rows}</table></div>"
    return layout(content, session['email'], "dashboard")

@app.route('/journal')
def journal():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND status IN ('took','active','win','loss','be','win_early') ORDER BY created_at DESC LIMIT 100", (session['email'],)); trades=cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as pnl, COUNT(*) FILTER (WHERE status='win' OR status='win_early') as wins, COUNT(*) FILTER (WHERE status='loss') as losses, COUNT(*) FILTER (WHERE status IN ('win','loss','be','win_early')) as closed, COALESCE(SUM(close_r),0) as total_r FROM agent35_trades WHERE user_email=%s AND status IN ('took','active','win','loss','be','win_early')", (session['email'],)); stats=cur.fetchone()
    cur.close(); conn.close()
    curr_sym=CUR.get(user['currency'],'$') if user else '$'
    total_r = stats['total_r'] or 0; wr = (stats['wins']/stats['closed']*100) if stats['closed']>0 else 0
    def badge_cls(s): return "win" if "win" in s else "loss" if s=="loss" else "bull"
    rows="".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td>{t['symbol']} {t['direction']}</td><td>{t.get('original_entry', t['entry'])} / {t.get('original_sl', t['sl'])} / {t['tp']} | Now SL: {t['sl']}</td><td><span class='badge {badge_cls(t['status'])}'>{t['status'].upper()}</span></td><td>{curr_sym}{round(t['pnl'] or 0,2)} ({t.get('close_r',0)}R)</td><td><a href='/manual-close?id={t['id']}' style='color:#10b981'>Close Early</a></td></tr>" for t in trades]) or "<tr><td colspan=6>No taken trades - click TOOK ENTRY</td></tr>"
    content=f"<div class='card'><h3>Journal - TAKEN ONLY - {wr:.1f}% | {total_r:.1f}R | {curr_sym}{stats['pnl']:.2f} | Bal ~{curr_sym}{user['account_size']+stats['pnl']:.2f}</h3><div style='overflow:auto'><table><tr><th>Date</th><th>Pair</th><th>Entry / Orig SL / TP</th><th>Status</th><th>PNL</th><th>Action</th></tr>{rows}</table></div><br><a class='btn' href='/signals'>View All Signals Sheet</a></div>"
    return layout(content, session['email'], "journal")

@app.route('/signals')
def signals():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC LIMIT 200", (session['email'],)); trades=cur.fetchall()
    cur.execute("SELECT COUNT(*) FILTER (WHERE status='win' OR status='win_early') as wins, COUNT(*) FILTER (WHERE status='loss') as losses FROM agent35_trades WHERE user_email=%s", (session['email'],)); stats=cur.fetchone()
    cur.close(); conn.close()
    curr_sym=CUR.get(user['currency'],'$') if user else '$'
    bot_wr = (stats['wins']/(stats['wins']+stats['losses'])*100) if (stats['wins']+stats['losses'])>0 else 0
    def badge_cls(s): return "win" if "win" in s else "loss" if s=="loss" else "bull"
    rows="".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td>{t['symbol']} {t['direction']}</td><td>{t.get('original_entry', t['entry'])} / {t.get('original_sl', t['sl'])} / {t['tp']}</td><td><span class='badge {badge_cls(t['status'])}'>{t['status'].upper()}</span></td><td>{curr_sym}{round(t['pnl'] or 0,2)} ({t.get('close_r',0)}R)</td><td style='font-size:10px'>{str(t['confluence'])[:80]}</td></tr>" for t in trades]) or "<tr><td colspan=6>No signals</td></tr>"
    content=f"<div class='card'><h3>All Signals Sheet - Bot WR {bot_wr:.1f}% - {len(trades)} signals (Includes skipped for accuracy)</h3><div style='overflow:auto'><table><tr><th>Date</th><th>Pair</th><th>Entry/SL/TP</th><th>Status</th><th>PNL</th><th>Confluence</th></tr>{rows}</table></div><br><a class='btn' href='/journal'>Back to Journal (Taken Only)</a></div>"
    return layout(content, session['email'], "signals")

@app.route('/manual-close')
def manual_close():
    if 'email' not in session: return redirect('/')
    tid = request.args.get('id')
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT t.*, u.account_size FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.id=%s AND t.user_email=%s", (tid, session['email']))
    tr = cur.fetchone()
    if not tr or tr['status'] not in ('took','active'):
        cur.close(); conn.close()
        return layout("<div class='card'>Not open</div>", session['email'])
    live = get_live_price(tr['symbol'])
    close = live[0] if live else tr['entry']
    r_now = calc_r_now(tr, close)
    risk_money = tr['account_size'] * 0.01
    pnl = risk_money * r_now
    cur.execute("UPDATE agent35_trades SET status='win_early', pnl=%s, closed_at=NOW(), result_price=%s, close_r=%s WHERE id=%s", (pnl, close, r_now, tid))
    conn.commit(); cur.close(); conn.close()
    return redirect('/journal')

# --- rest of your routes: payment, settings, master, scan, webhook etc keep same as V8 but with original_entry insert ---

@app.route('/payment')
def payment_page():
    ref=f"AG35-{datetime.now().strftime('%m%d')}-{os.urandom(2).hex().upper()}"
    email=session.get('email',''); conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT referral_code, referral_count FROM agent35_users WHERE email=%s", (email,)); urow=cur.fetchone(); cur.close(); conn.close()
    my_code=urow['referral_code'] if urow and urow['referral_code'] else ref; my_count=urow['referral_count'] if urow and urow['referral_count'] else 0
    content=f"<div class='card' style='max-width:500px;margin:auto;text-align:center;padding:28px'><h2 style='color:#10b981'>Upgrade</h2><div class='warn'>Refer {my_count}/10 = Lifetime</div><div style='background:#070d1a;padding:14px;border-radius:12px;border:1px solid #10b981;margin:12px 0'><div style='font-size:12px;font-weight:800;color:#10b981;word-break:break-all'>{request.host_url}r/{my_code}</div></div><p>Capitec: <b>{CAPITEC_ACC}</b></p><div style='background:#070d1a;padding:14px;border-radius:12px;border:1px solid #1e2d45;margin:12px 0'><div style='font-size:22px;font-weight:800;color:#10b981'>{ref}</div></div><a class='btn' href='/submit-payment?ref={ref}&plan=yearly'>I Paid R500 Yearly</a><a class='btn-outline' href='/submit-payment?ref={ref}&plan=lifetime'>I Paid R5000 Lifetime</a></div>"
    return layout(content, session.get('email',''))

@app.route('/submit-payment')
def submit_payment():
    if 'email' not in session: return redirect('/')
    ref=request.args.get('ref'); plan=request.args.get('plan'); amount=500 if plan=='yearly' else 5000
    conn=get_conn(); cur=conn.cursor()
    try: cur.execute("INSERT INTO agent35_payments (user_email,plan,ref_code,amount,status) VALUES (%s,%s,%s,%s,'pending') ON CONFLICT (ref_code) DO NOTHING", (session['email'],plan,ref,amount))
    except: cur.execute("INSERT INTO agent35_payments (user_email,plan,ref_code,amount,status) VALUES (%s,%s,%s,%s,'pending')", (session['email'],plan,ref,amount))
    cur.execute("UPDATE agent35_users SET payment_ref=%s, plan=%s, payment_status='pending' WHERE email=%s", (ref,plan,session['email'])); conn.commit(); cur.close(); conn.close()
    tg_link=f"https://t.me/{TELEGRAM_BOT_USERNAME}?start={ref}"
    return layout(f"<div class='card' style='text-align:center;max-width:500px;margin:auto'><h2 style='color:#10b981'>Submitted {ref}</h2><a href='{tg_link}' target='_blank' class='btn'>Link Telegram</a><a class='btn-outline' href='/dashboard'>Dashboard</a></div>", session['email'])

@app.route('/test-telegram')
def test_telegram():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); u=cur.fetchone()
    if not u or not u.get('telegram_id'):
        cur.close(); conn.close()
        return layout(f"<div class='card'><h3>No Telegram ID</h3><a class='btn' href='/dashboard'>Dashboard</a></div>", session['email'])
    res = engine.full_multi_tf_analysis("XAUUSD")
    msg = build_signal_msg(res if res.get('signal') else {'symbol': 'XAUUSD','direction': 'BUY','entry': 2685.5,'sl': 2675,'tp': 2705,'score': 7,'quality': 'PREMIUM Be-OB','bias': 'Bu-OB:True','confluence': ['Bu-OB RETEST','MB'],'reason': 'Test V8.2 No-Spam'}, u)
    ok = send_telegram(u['telegram_id'], f"🧪 TEST V8.2 NO-SPAM 🧪\n\n{msg}", trade_id=99999, stage="signal")
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
        except Exception as e: res={"signal":False,"symbol":sym,"reason":f"Error {e}"}
        res['symbol']=sym; results.append(res)
        if res.get('signal') and res.get('score',0) >= 4:
            cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,original_entry,original_sl,timeframe_bias,confluence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",(session['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['entry'],res['sl'],res['bias'],str(res.get('confluence',''))))
            new_row=cur.fetchone(); tid=new_row['id'] if new_row else 0
            if user['telegram_id']:
                msg=build_signal_msg(res, user)
                send_telegram(user['telegram_id'], msg, trade_id=tid, stage="signal")
    conn.commit(); cur.close(); conn.close()
    html="".join([f"<div class='card' style='border-left:4px solid #10b981'><b>{r['symbol']} {r.get('direction','')} {r.get('score',0)}/8 {r.get('quality','')}</b><br>{r.get('confluence','')}<br>Entry {r.get('entry','')} SL {r.get('sl','')} TP {r.get('tp','')}</div>" if r.get('signal') else f"<div class='card' style='opacity:0.6'><b>{r['symbol']} No Setup</b> {r.get('reason','')}</div>" for r in results])
    return layout(f"<h2>Scan V8.2 - No Spam for Real Money</h2>{html}<br><a class='btn' href='/journal'>Journal (Taken)</a> <a class='btn-outline' href='/signals'>All Signals</a>", session['email'])

@app.route('/settings', methods=['GET','POST'])
def settings():
    if 'email' not in session: return redirect('/')
    if request.method=='POST':
        sess_list=[]
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
    content=f"<div style='max-width:700px;margin:auto'><h2 style='color:#10b981'>Settings V8.2</h2><form method='POST'><div class='settings-section'><div style='display:grid;grid-template-columns:1fr 1fr;gap:12px'><div><label>Currency</label><select name='currency'><option value='USD' {sel_usd}>USD</option><option value='ZAR' {sel_zar}>ZAR</option><option value='EUR' {sel_eur}>EUR</option></select></div><div><label>Account REAL SIZE</label><input name='acc' type='number' value='{u['account_size']}'></div><div><label>Lot</label><input name='lot' type='number' step='0.01' value='{u['lot_size']}'></div><div><label>RR</label><select name='rr'><option {sel_12}>1:2</option><option {sel_13}>1:3</option><option {sel_14}>1:4</option></select></div></div><label>Symbols</label><input name='symbols' value='{u['symbols']}'><label>Telegram @</label><input name='tg' value='{u['telegram_username'] or ''}'><label>TZ</label><select name='timezone'><option value='{utz}' selected>{utz}</option><option value='Africa/Johannesburg'>Africa/Johannesburg</option><option value='Europe/London'>Europe/London</option><option value='America/New_York'>America/New_York</option><option value='UTC'>UTC</option></select><div style='margin-top:16px'><label>Sessions</label><div style='display:grid;grid-template-columns:1fr 1fr;gap:8px'><label class='sess-check'><input type='checkbox' name='sess_london' {c_london}> London</label><label class='sess-check'><input type='checkbox' name='sess_ny' {c_ny}> NY</label><label class='sess-check'><input type='checkbox' name='sess_asia' {c_asia}> Asia</label><label class='sess-check'><input type='checkbox' name='sess_sydney' {c_sydney}> Sydney</label></div><label class='sess-check' style='margin-top:8px'><input type='checkbox' name='sess_all' {c_all}> 24/7</label></div></div><button class='btn'>Save</button><a href='/dashboard' class='btn-outline'>Back</a></form></div>"
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
                    cur.execute("UPDATE agent35_trades SET status='took', hit_entry_at=NOW() WHERE id=%s", (tid,)); conn.commit()
                    send_telegram(chat_id, f"📝 {tr['symbol']} TOOK - Now tracking BE, Lock, WIN/LOSS only for this trade", trade_id=tid, stage="active")
                elif action=='skip':
                    cur.execute("UPDATE agent35_trades SET status='skipped' WHERE id=%s", (tid,)); conn.commit()
                    send_telegram(chat_id, f"Skipped {tr['symbol']} - Will still track in All Signals sheet")
                elif action=='lock':
                    risk = abs(tr['entry']-tr['sl'])
                    lock_sl = tr['entry'] + risk*1.0 if tr['direction']=='BUY' else tr['entry'] - risk*1.0
                    cur.execute("UPDATE agent35_trades SET sl=%s, lock_done=TRUE WHERE id=%s", (lock_sl, tid)); conn.commit()
                    risk_money = tr['account_size'] * (RISK_PCT/100)
                    send_telegram(chat_id, f"🔒 {tr['symbol']} LOCKED +1R +${risk_money:.2f} secured! SL now {lock_sl}")
                elif action=='closeearly':
                    live = get_live_price(tr['symbol'])
                    close = live[0] if live else tr['entry']
                    r_now = calc_r_now(tr, close)
                    risk_money = tr['account_size'] * 0.01
                    pnl = risk_money * r_now
                    cur.execute("UPDATE agent35_trades SET status='win_early', pnl=%s, closed_at=NOW(), result_price=%s, close_r=%s WHERE id=%s", (pnl, close, r_now, tid)); conn.commit()
                    send_telegram(chat_id, f"💰 {tr['symbol']} CLOSED EARLY +{r_now:.1f}R +${pnl:.2f}")
                elif action in ('win','loss','be'):
                    risk_money=tr['account_size']*0.01; rr=3
                    try: rr=int(tr['risk_reward'].split(':')[1])
                    except: pass
                    pnl=risk_money*rr if action=='win' else -risk_money if action=='loss' else 0; status='win' if action=='win' else 'loss' if action=='loss' else 'be'
                    close_r = rr if status=='win' else -1 if status=='loss' else 0
                    cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s, close_r=%s WHERE id=%s", (status,pnl,tr['tp'] if status=='win' else tr['sl'],close_r,tid)); conn.commit()
                    cs=tr['currency_symbol'] or '$'; send_telegram(chat_id, f"{'WIN' if status=='win' else 'LOSS' if status=='loss' else 'BE'} {tr['symbol']} {cs}{pnl:.2f} ({close_r}R)")
            try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={"callback_query_id":cq['id'],"text":f"{action.upper()} saved"}, timeout=5)
            except: pass
            cur.close(); conn.close(); return jsonify({"ok":True})
        if 'message' in data:
            chat_id=data['message']['chat']['id']; username=data['message']['chat'].get('username',''); text=data['message'].get('text','').strip()
            ref=text.split('/start')[-1].strip() if '/start' in text else text.strip()
            if not ref: cur.close(); conn.close(); return jsonify({"ok":True})
            cur.execute("SELECT email FROM agent35_users WHERE payment_ref=%s OR email=%s OR payment_ref ILIKE %s", (ref, ref.lower(), f"%{ref}%")); row=cur.fetchone()
            if row:
                cur.execute("UPDATE agent35_users SET telegram_id=%s, telegram_username=%s WHERE email=%s", (str(chat_id), username, row['email'])); conn.commit()
                send_telegram(chat_id, f"Linked! {row['email']} V8.2 No-Spam Active - Only TOOK trades will alert")
            cur.close(); conn.close()
    except Exception as e: print(f"tg error {e} {traceback.format_exc()}")
    return jsonify({"ok":True})

@app.route('/setup-webhook')
def setup_webhook():
    if 'email' not in session: return redirect('/')
    if not TELEGRAM_TOKEN: return "No TOKEN"
    base=request.host_url.rstrip('/'); wh_url=f"{base}/telegram/webhook"
    r=requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={wh_url}")
    return layout(f"<div class='card'><h3>Webhook V8.2</h3><p>{wh_url}</p><p>{r.text}</p><a class='btn' href='/master'>Back</a></div>", session['email'])

@app.route('/cron/update-trades')
def cron_update():
    def do_update():
        try:
            conn=get_conn(); cur=conn.cursor()
            # V8.2: ONLY TOOK/ACTIVE
            cur.execute("SELECT t.*, u.account_size, u.risk_reward, u.telegram_id, u.currency_symbol FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.status IN ('took','active') LIMIT 40")
            for tr in cur.fetchall():
                live=get_live_price(tr['symbol'])
                if not live: continue
                close,high,low=live
                r_now = calc_r_now(tr, close)
                if r_now >= 1.0 and not tr.get('be_done'):
                    cur.execute("UPDATE agent35_trades SET be_done=TRUE, sl=%s WHERE id=%s", (tr['entry'], tr['id'])); conn.commit()
                    if tr['telegram_id']: send_telegram(tr['telegram_id'], f"🔒 {tr['symbol']} +1R -> BE {tr['entry']}")
                if r_now >= 2.0 and not tr.get('lock_done'):
                    cur.execute("UPDATE agent35_trades SET lock_done=TRUE WHERE id=%s", (tr['id'],)); conn.commit()
                    if tr['telegram_id']:
                        extra = [[{"text":"🔒 LOCK +1R","callback_data":f"lock:{tr['id']}"},{"text":"💰 CLOSE EARLY","callback_data":f"closeearly:{tr['id']}"}]]
                        send_telegram(tr['telegram_id'], f"💎 {tr['symbol']} +2R Comfortable! Lock?", trade_id=tr['id'], stage="profitlock", extra_buttons=extra)
                rr=3
                try: rr=int(tr['risk_reward'].split(':')[1])
                except: pass
                risk_money=tr['account_size']*0.01; new=None; pnl=0
                if tr['direction']=='BUY':
                    if low <= tr['sl']: new='be' if tr.get('be_done') else 'loss'; pnl=0 if tr.get('be_done') else -risk_money
                    elif high >= tr['tp']: new='win'; pnl=risk_money*rr
                else:
                    if high >= tr['sl']: new='be' if tr.get('be_done') else 'loss'; pnl=0 if tr.get('be_done') else -risk_money
                    elif low <= tr['tp']: new='win'; pnl=risk_money*rr
                if new:
                    close_r = rr if new=='win' else 0 if new=='be' else -1
                    cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s, auto_updated=TRUE, close_r=%s WHERE id=%s",(new,pnl,close,tr['id'],close_r))
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            print(f"cron err {e}")
    threading.Thread(target=do_update, daemon=True).start()
    return jsonify({"ok":True})

@app.route('/cron/scan-all')
def cron_scan_all():
    def do_scan():
        try:
            conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE payment_status='approved' LIMIT 100"); users=cur.fetchall()
            for user in users:
                if not is_session_active(user['sessions'] or 'London,New York'): continue
                symbols=(user['symbols'] or "EURUSD").split(",")[:5]
                for sym in symbols:
                    sym=sym.strip().upper()
                    if not sym: continue
                    try: res=engine.full_multi_tf_analysis(sym)
                    except: continue
                    if res.get('signal') and res.get('score',0) >= 4:
                        cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,original_entry,original_sl,timeframe_bias,confluence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",(user['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['entry'],res['sl'],res['bias'],str(res.get('confluence',''))))
                        row=cur.fetchone()
                        if row and user['telegram_id']:
                            msg=build_signal_msg(res, user)
                            send_telegram(user['telegram_id'], msg, trade_id=row['id'], stage="signal")
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            print(f"scan err {e} {traceback.format_exc()}")
    threading.Thread(target=do_scan, daemon=True).start()
    return jsonify({"ok":True})

@app.route('/healthz')
def health(): return jsonify({"status":"ok","version":"V8.2-NO-SPAM-2-SHEETS","utc":datetime.utcnow().isoformat()})

@app.route('/master')
def master():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT is_creator FROM agent35_users WHERE email=%s", (session['email'],)); r=cur.fetchone()
    if not r or not r['is_creator']: cur.close(); conn.close(); return redirect('/dashboard')
    cur.execute("SELECT COUNT(*) as total FROM agent35_users"); stats=cur.fetchone(); cur.close(); conn.close()
    return layout(f"<div class='card'><h2>MASTER V8.2 - Users {stats['total']}</h2><a class='btn-outline' href='/setup-webhook'>Setup Webhook</a></div>", session['email'], "master")

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

if __name__ == '__main__': app.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))
