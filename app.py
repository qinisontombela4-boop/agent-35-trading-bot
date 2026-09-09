import os, hashlib, requests, psycopg, time, csv, io, traceback
from psycopg.rows import dict_row
from flask import Flask, request, redirect, session, jsonify, Response
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import trading_engine as engine
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'agent35-secret-2025')
DATABASE_URL = os.environ.get('DATABASE_URL','').strip()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN','').strip() or os.environ.get('BOT_TOKEN','').strip()
TELEGRAM_BOT_USERNAME = os.environ.get('BOT_USERNAME','Sniper035_bot')
RISK_PCT = float(os.environ.get('RISK_PCT','1.5'))
CUR = {'USD':'$','ZAR':'R','EUR':'€','GBP':'£'}
TWELVE_KEY = os.environ.get('TWELVEDATA_API_KEY','').strip()
FINNHUB_KEY = os.environ.get('FINNHUB_API_KEY','').strip()

def format_price(symbol, price):
    if price is None: return "-"
    s = symbol.upper()
    try:
        p=float(price)
        if "JPY" in s: return f"{p:.3f}"
        if "XAU" in s or "GOLD" in s: return f"{p:.2f}"
        if "BTC" in s: return f"{p:.2f}"
        if "NAS" in s or "US30" in s: return f"{p:.2f}"
        return f"{p:.5f}"
    except: return str(price)

LOGO_SVG = '<svg width="34" height="34" viewBox="0 0 100 100"><rect width="100" height="100" rx="18" fill="#0b111c" stroke="#10b981" stroke-width="3"/><text x="50%" y="58%" dominant-baseline="middle" text-anchor="middle" font-weight="900" font-size="48" fill="#10b981">35</text></svg>'

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
*{box-sizing:border-box} body{background:#060a14;color:#e5e7eb;font-family:'Inter',sans-serif;margin:0}
.header{background:#0b111c;border-bottom:1px solid #1a2535;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:10px;color:#10b981;font-weight:800}
.card{background:#0e1625;border:1px solid #1c2a41;border-radius:16px;padding:16px;margin-bottom:14px}
.btn{background:linear-gradient(135deg,#10b981,#059669);color:#000;font-weight:800;padding:12px 18px;border:none;border-radius:12px;cursor:pointer;text-decoration:none;display:block;text-align:center;width:100%}
.btn-outline{background:transparent;border:1px solid #24344e;color:#cbd5e1;padding:12px 18px;border-radius:12px;text-decoration:none;display:block;text-align:center;width:100%;margin-top:8px}
.badge{padding:5px 10px;border-radius:20px;font-size:11px;font-weight:800}.bull{background:rgba(16,185,129,0.15);color:#10b981}
.chip{display:inline-flex;align-items:center;gap:6px;background:#121d30;border:1px solid #1e2d45;padding:7px 12px;border-radius:24px;margin:4px;font-size:13px}.chip-active{background:#10b98122;border-color:#10b981}
.x{background:#ef4444;color:#fff;border-radius:50%;width:20px;height:20px;display:inline-flex;justify-content:center;align-items:center;font-size:12px;margin-left:6px;cursor:pointer}
.searchbox{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:12px;width:100%;margin:8px 0}
.dropdown{background:#121d30;border:1px solid #1e2d45;border-radius:12px;max-height:200px;overflow:auto;display:none;position:absolute;z-index:50;width:calc(100% - 32px)}.dropdown div{padding:10px 14px;cursor:pointer;border-bottom:1px solid #1a2535}
table{width:100%;border-collapse:collapse} th{color:#64748b;text-align:left;padding:10px 6px;font-size:10px;text-transform:uppercase} td{padding:10px 6px;border-top:1px solid #1a2535;font-size:12px}
.nav-tabs{display:flex;gap:8px;overflow:auto;margin:12px 0}.nav-tabs a{white-space:nowrap;padding:10px 18px;border-radius:24px;background:#121d30;border:1px solid #1e2d45;color:#94a3b8;text-decoration:none;font-size:13px;font-weight:600}.nav-tabs a.active{background:#10b981;color:#000;border-color:#10b981;font-weight:800}
input,select,textarea{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:10px;width:100%;margin:6px 0}
.paused-banner{background:linear-gradient(135deg,#ef4444 0%,#991b1b 100%);color:#fff;padding:14px;border-radius:12px;text-align:center;font-weight:800;margin-bottom:14px}
</style>
<script>
const ALL_SYMBOLS=["EURUSD","GBPUSD","USDJPY","EURJPY","GBPJPY","USDZAR","EURZAR","GBPZAR","ZARJPY","USDCHF","XAUUSD","GOLD","XAGUSD","BTCUSD","ETHUSD","NAS100","US30","SPX500","GER40","UK100","USOIL"];
function addSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!='');if(arr.length>=5){alert('Max 5');return}if(!arr.includes(s)){arr.push(s);i.value=arr.join(',');document.getElementById('symForm').submit();}}
function removeSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!=s.trim()&&x.trim()!='');i.value=arr.join(',');document.getElementById('symForm').submit();}
function filterSyms(){let q=document.getElementById('symSearch').value.toUpperCase();let dd=document.getElementById('symDropdown');if(!q){dd.style.display='none';return}let f=ALL_SYMBOLS.filter(s=>s.includes(q)).slice(0,10);dd.innerHTML=f.map(s=>'<div onclick="addSym(\\''+s+'\\')"><b>'+s+'</b> - Click</div>').join('');dd.style.display=f.length?'block':'none';}
function copyRef(){let t=document.getElementById('refLink');t.select();document.execCommand('copy');alert('Copied!');}
</script>
"""
def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode='require', connect_timeout=20)

def init_db():
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS agent35_users (id SERIAL PRIMARY KEY, email TEXT UNIQUE, password TEXT, is_creator BOOLEAN DEFAULT FALSE, plan TEXT DEFAULT 'none', payment_ref TEXT, payment_status TEXT DEFAULT 'pending', risk_reward TEXT DEFAULT '1:3', symbols TEXT DEFAULT 'EURUSD,XAUUSD', sessions TEXT DEFAULT 'London,New York', account_size FLOAT DEFAULT 10000, lot_size FLOAT DEFAULT 0.1, leverage TEXT DEFAULT '1:500', telegram_id TEXT, created_at TIMESTAMP DEFAULT NOW());")
        cur.execute("CREATE TABLE IF NOT EXISTS agent35_trades (id SERIAL PRIMARY KEY, user_email TEXT, symbol TEXT, direction TEXT, entry FLOAT, sl FLOAT, tp FLOAT, original_entry FLOAT, original_sl FLOAT, timeframe_bias TEXT, confluence TEXT, status TEXT DEFAULT 'sent', pnl FLOAT DEFAULT 0, close_r FLOAT DEFAULT 0, be_done BOOLEAN DEFAULT FALSE, lock_done BOOLEAN DEFAULT FALSE, archived BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW(), closed_at TIMESTAMP, hit_entry_at TIMESTAMP);")
        for q in ["ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USD'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS telegram_username TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_code TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referred_by TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_count INT DEFAULT 0","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'Africa/Johannesburg'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS news_filter BOOLEAN DEFAULT TRUE","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS is_creator BOOLEAN DEFAULT FALSE"]:
            try: cur.execute(q)
            except: pass
        conn.commit(); cur.close(); conn.close()
        print("DB INIT V12.6.2 OK")
    except Exception as e: print(f"DB init err {e}")

init_db()

def is_subscription_active(user):
    if not user: return False
    if user.get('is_creator'): return True
    if user.get('payment_status')!='approved': return False
    if user.get('plan')=='lifetime': return True
    return True

def send_telegram(chat_id, text, trade_id=None, stage="signal"):
    if not TELEGRAM_TOKEN or not chat_id: return False
    try:
        payload={"chat_id":chat_id,"text":text,"parse_mode":"HTML"}
        if trade_id and stage=="signal":
            payload["reply_markup"]={"inline_keyboard":[[{"text":"✅ TOOK ENTRY","callback_data":f"took:{trade_id}"},{"text":"❌ SKIP","callback_data":f"skip:{trade_id}"}]]}
        r=requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",json=payload,timeout=15)
        return r.status_code==200
    except Exception as e:
        print(f"TG err {e}"); return False

def build_signal_msg(res,user=None):
    sym=res.get('symbol','?'); direction=res.get('direction','?'); score=res.get('score',0)
    dec=3 if "JPY" in sym else 2 if "XAU" in sym or "GOLD" in sym else 5
    rr = res.get('rr','?')
    try:
        return f"<b>🔥 AGENT 35 {res.get('quality','A')} {score}/8</b>\n\n<b>{sym} {'🟢 BUY' if direction=='BUY' else '🔴 SELL'}</b>\nRR: {rr}\n\n<b>Entry:</b> {res.get('entry',0):.{dec}f}\n<b>SL:</b> {res.get('sl',0):.{dec}f}\n<b>TP:</b> {res.get('tp',0):.{dec}f}\n\n<b>Bias:</b> {res.get('bias','')}\n<b>Reason:</b> {res.get('reason','')}\n\n<i>Score {score}/8 | Decimals FIXED V12.6.2</i>"
    except: return str(res)

def get_live_price(symbol):
    try:
        if TWELVE_KEY:
            clean=engine.MAP.get(symbol.upper(),symbol.upper()) if hasattr(engine,'MAP') else symbol.upper()
            url=f"https://api.twelvedata.com/quote?symbol={clean}&apikey={TWELVE_KEY}"
            r=requests.get(url,timeout=8).json()
            if 'close' in r and float(r['close'])>0:
                return float(r['close']), float(r.get('high',r['close'])), float(r.get('low',r['close']))
    except Exception as e: print(f"price err {e}")
    return None

def layout(content,email="",active="dashboard"):
    nav=f'<div class="nav-tabs"><a href="/dashboard" class="{"active" if active=="dashboard" else ""}">Dashboard</a><a href="/journal" class="{"active" if active=="journal" else ""}">Journal</a><a href="/referrals" class="{"active" if active=="referrals" else ""}">Referrals</a><a href="/settings" class="{"active" if active=="settings" else ""}">Settings</a></div>'
    return f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Agent 35 V12.6.2</title>{STYLE}</head><body><div class=header><div class=logo>{LOGO_SVG}<span>AGENT 35</span><small style='margin-left:8px;color:#64748b'>V12.6.2 FIXED</small></div><div>{email} <a href='/logout' style='color:#64748b;text-decoration:none;margin-left:10px'>Logout</a></div></div><div style='padding:12px;max-width:1100px;margin:auto'>{nav}{content}</div></body></html>"

@app.route('/')
def home():
    return f"<html><head>{STYLE}</head><body><div class=card style='max-width:420px;margin:80px auto;text-align:center'><div style='display:flex;justify-content:center'>{LOGO_SVG}</div><h2>AGENT 35 V12.6.2</h2><p style='color:#94a3b8'>Decimals FIXED | JPY=3 | Gold=2 | Forex=5 | DUAL FREE R0</p><form method=POST action=/auth><input name=email placeholder='Email' required><input name=password type=password placeholder='Password' required><button class=btn>Login / Register</button></form></div></body></html>"

@app.route('/auth',methods=['POST'])
def auth():
    email=request.form['email'].lower().strip(); pw=hashlib.sha256(request.form['password'].encode()).hexdigest()
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s", (email,)); u=cur.fetchone()
    if not u:
        my_code=f"AG35-{email[:3].upper()}-{os.urandom(2).hex().upper()}"
        cur.execute("INSERT INTO agent35_users (email,password,plan,payment_status,symbols,sessions,referral_code,timezone,news_filter,currency) VALUES (%s,%s,'none','pending','EURUSD,XAUUSD','London,New York',%s,'Africa/Johannesburg',TRUE,'USD') RETURNING *",(email,pw,my_code)); u=cur.fetchone(); conn.commit()
    else:
        if u['password']!=pw:
            cur.close(); conn.close()
            return "Wrong password <a href='/'>Back</a>"
    cur.close(); conn.close(); session['email']=u['email']
    return redirect('/dashboard')

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

@app.route('/healthz')
def healthz(): return jsonify({"ok":True,"v":"V12.6.2 FIXED","key":bool(TWELVE_KEY),"time":datetime.utcnow().isoformat()})
 @app.route('/dashboard')
def dashboard():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); user=cur.fetchone()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as pnl, COUNT(*) FILTER (WHERE status='win' OR status='win_early') as wins, COUNT(*) FILTER (WHERE status='loss') as losses, COUNT(*) FILTER (WHERE status IN ('win','loss','be','win_early')) as closed, COALESCE(SUM(close_r),0) as total_r FROM agent35_trades WHERE user_email=%s AND archived=FALSE",(session['email'],)); stats=cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND archived=FALSE ORDER BY created_at DESC LIMIT 20",(session['email'],)); trades=cur.fetchall()
    cur.close(); conn.close()
    pnl=stats['pnl'] or 0; total_r=stats['total_r'] or 0
    wr=(stats['wins']/stats['closed']*100) if stats['closed'] and stats['closed']>0 else 0
    curr_sym=CUR.get(user.get('currency','USD'),'$')
    syms=[s for s in (user['symbols'] or '').split(',') if s.strip()]
    chips="".join([f"<span class='chip chip-active'><b>{s}</b><span class='x' onclick=\"removeSym('{s}')\">x</span></span>" for s in syms])
    rows="".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td><b>{t['symbol']}</b> {t['direction']}</td><td><span class='badge bull'>{t['status'].upper()}</span></td><td>{format_price(t['symbol'], t['entry'])} -> {curr_sym}{round(t['pnl'] or 0,2)}</td></tr>" for t in trades]) or "<tr><td colspan=4>No trades yet</td></tr>"
    base_url=request.host_url.rstrip('/'); ref_code=user.get('referral_code') or ""; ref_link=f"{base_url}/r/{ref_code}" if ref_code else ""; ref_count=user.get('referral_count',0) or 0
    active_sub=is_subscription_active(user)
    paused_html="" if active_sub else f"<div class='paused-banner'>SIGNALS PAUSED - Ref: {user.get('payment_ref') or 'Not set'}<br><a href='/payment' style='color:#fff'>Go to Payment</a></div>"
    scan_style="" if active_sub else "opacity:0.4;pointer-events:none"; scan_text="SCAN NOW" if active_sub else "PAUSED"
    symbols_value=user.get('symbols','')
    refer_card=f"<div class='card'><div style='display:flex;justify-content:space-between'><b style='color:#10b981'>Refer & Earn - 10 = Lifetime FREE</b><span class='badge bull'>{ref_count}/10</span></div><div style='margin-top:10px;font-size:12px;color:#94a3b8'>Decimals fixed: JPY 3, Gold 2, Forex 5 | DUAL FREE R0</div><div style='margin-top:10px;display:flex;gap:6px'><input id='refLink' value='{ref_link}' readonly style='flex:1'><button onclick='copyRef()' class='btn' style='width:90px'>Copy</button></div><a href='/referrals' class='btn-outline' style='margin-top:6px'>View Referrals</a></div>"
    content=f"{paused_html}<div class='card' style='padding:12px;display:flex;justify-content:space-between;flex-wrap:wrap'><span>Sessions: <b>{user.get('sessions','')}</b> | News: <b>{'ON' if user.get('news_filter') else 'OFF'}</b> | Plan: <b>{user.get('plan','none').upper()}</b> | V12.6.2 FIXED</span><span>WR: {wr:.1f}% | {total_r:.1f}R | {curr_sym}{pnl:.2f}</span></div><div class='card'><div style='font-size:12px;color:#94a3b8'>Total Profit</div><div style='font-size:24px;font-weight:800'>{curr_sym}{round(pnl,2)}</div><div style='display:flex;gap:8px;margin-top:10px'><a class='btn' href='/scan?symbol=EURUSD' style='{scan_style}'>{scan_text}</a><a href='https://t.me/{TELEGRAM_BOT_USERNAME}?start={user.get('payment_ref') or session['email']}' target='_blank' class='btn-outline'>Link Telegram</a></div></div><div class='card' style='position:relative'><div>Watchlist {len(syms)}/5</div><div style='margin:12px 0'>{chips}</div><form id='symForm' method='POST' action='/quick-symbols'><input type='hidden' name='symbols' id='symInput' value='{symbols_value}'></form><input id='symSearch' class='searchbox' placeholder='Search pairs...' oninput='filterSyms()' autocomplete='off'><div id='symDropdown' class='dropdown'></div></div>{refer_card}<div class='card' style='margin-top:14px;overflow:auto'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th></tr>{rows}</table></div>"
    return layout(content,session['email'],"dashboard")

@app.route('/quick-symbols',methods=['POST'])
def quick_symbols():
    if 'email' not in session: return redirect('/')
    syms=request.form.get('symbols','').upper()
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE agent35_users SET symbols=%s WHERE email=%s",(syms,session['email'])); conn.commit(); cur.close(); conn.close()
    return redirect('/dashboard')

@app.route('/settings')
def settings_page():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); user=cur.fetchone(); cur.close(); conn.close()
    content=f"<div class=card><h3>Settings</h3><form method=POST action=/save-settings><label>Symbols (comma)</label><input name=symbols value='{user.get('symbols','')}'><label>Sessions</label><input name=sessions value='{user.get('sessions','')}'><label>Currency</label><select name=currency><option {'selected' if user.get('currency')=='USD' else ''} value='USD'>USD $</option><option {'selected' if user.get('currency')=='ZAR' else ''} value='ZAR'>ZAR R</option><option {'selected' if user.get('currency')=='EUR' else ''} value='EUR'>EUR €</option></select><label>News Filter</label><select name=news_filter><option value='TRUE' {'selected' if user.get('news_filter') else ''}>ON</option><option value='FALSE' {'selected' if not user.get('news_filter') else ''}>OFF</option></select><button class=btn style='margin-top:12px'>Save</button></form></div>"
    return layout(content,session['email'],"settings")

@app.route('/save-settings',methods=['POST'])
def save_settings():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor()
    cur.execute("UPDATE agent35_users SET symbols=%s, sessions=%s, currency=%s, news_filter=%s WHERE email=%s",(request.form['symbols'].upper(), request.form['sessions'], request.form['currency'], request.form['news_filter']=='TRUE', session['email'])); conn.commit(); cur.close(); conn.close()
    return redirect('/dashboard')
@app.route('/referrals')
def referrals_page():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); user=cur.fetchone()
    cur.execute("SELECT email, plan, payment_status, created_at FROM agent35_users WHERE referred_by=%s ORDER BY created_at DESC",(session['email'],)); referred=cur.fetchall()
    cur.execute("SELECT COUNT(*) as cnt FROM agent35_users WHERE referred_by=%s AND payment_status='approved'",(session['email'],)); approved_cnt=cur.fetchone()['cnt']
    if approved_cnt>=10 and user['plan']!='lifetime':
        cur.execute("UPDATE agent35_users SET plan='lifetime', payment_status='approved', paid_at=NOW() WHERE email=%s",(session['email'],)); conn.commit()
        if user['telegram_id']: send_telegram(user['telegram_id'],"🎉 LIFETIME UNLOCKED! 10 paid referrals!")
        user['plan']='lifetime'
    cur.close(); conn.close()
    base_url=request.host_url.rstrip('/'); ref_link=f"{base_url}/r/{user['referral_code']}" if user.get('referral_code') else ""; ref_count=approved_cnt
    rows="".join([f"<tr><td>{r['email']}</td><td>{r['plan']}</td><td>{r['payment_status'].upper()}</td><td>{'PAID ✅' if r['payment_status']=='approved' else 'Pending'}</td><td>{r['created_at'].strftime('%Y-%m-%d')}</td></tr>" for r in referred]) or "<tr><td colspan=5>No referrals yet</td></tr>"
    progress=min(ref_count*10,100); left=max(0,10-ref_count)
    content=f"<div class='card' style='text-align:center'><h2 style='color:#10b981;margin:0'>Refer & Earn Lifetime FREE</h2><p style='color:#94a3b8'>10 friends buy -> Lifetime auto FREE</p><div style='max-width:500px;margin:16px auto;display:flex;gap:6px'><input id='refLink' value='{ref_link}' readonly><button onclick='copyRef()' class='btn' style='width:90px'>Copy</button></div><div style='display:flex;justify-content:center;gap:12px'><div class=card><div style='font-size:12px'>Paid</div><div style='font-size:22px;font-weight:800;color:#10b981'>{ref_count}/10</div></div><div class=card><div style='font-size:12px'>Progress</div><div style='font-size:22px;font-weight:800'>{progress}%</div></div></div><div style='max-width:400px;margin:12px auto;background:#1a2535;height:14px;border-radius:14px;overflow:hidden'><div style='background:#10b981;height:14px;width:{progress}%'></div></div><div style='color:#94a3b8;font-size:12px'>{left} more needed</div></div><div class=card><h3>My Referred Users</h3><table><tr><th>Email</th><th>Plan</th><th>Status</th><th>Counted</th><th>Date</th></tr>{rows}</table></div><div class=card><a class=btn href='/dashboard'>Back</a></div>"
    return layout(content,session['email'],"referrals")

@app.route('/journal')
@app.route('/journal/<month_str>')
def journal(month_str=None):
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); user=cur.fetchone()
    cur.execute("SELECT DISTINCT TO_CHAR(created_at,'YYYY-MM') as month, TO_CHAR(created_at,'Mon YYYY') as label FROM agent35_trades WHERE user_email=%s AND archived=FALSE ORDER BY month DESC",(session['email'],)); months=cur.fetchall()
    if not month_str: month_str=months[0]['month'] if months else datetime.now().strftime('%Y-%m')
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND TO_CHAR(created_at,'YYYY-MM')=%s ORDER BY created_at DESC",(session['email'],month_str)); trades=cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as pnl, COUNT(*) FILTER (WHERE status='win') as wins, COUNT(*) FILTER (WHERE status IN ('win','loss','be')) as closed, COALESCE(SUM(close_r),0) as total_r FROM agent35_trades WHERE user_email=%s AND archived=FALSE AND TO_CHAR(created_at,'YYYY-MM')=%s",(session['email'],month_str)); stats=cur.fetchone(); cur.close(); conn.close()
    curr_sym=CUR.get(user.get('currency','USD'),'$'); wr=(stats['wins']/stats['closed']*100) if stats['closed'] else 0
    month_tabs="".join([f"<a href='/journal/{m['month']}' style='padding:8px 14px;border-radius:20px;text-decoration:none;font-size:12px;font-weight:700;margin:4px;display:inline-block;{'background:#10b981;color:#000' if m['month']==month_str else 'background:#121d30;color:#94a3b8'}'>{m['label']}</a>" for m in months])
    rows_html=""
    for t in trades:
        rows_html+=f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td><b>{t['symbol']}</b> {t['direction']}</td><td>{format_price(t['symbol'], t['entry'])} / {format_price(t['symbol'], t['sl'])} / {format_price(t['symbol'], t['tp'])}</td><td><span class=badge>{t['status']}</span></td><td>{curr_sym}{round(t['pnl'] or 0,2)}</td><td><a href='/manual-close?id={t['id']}' style='color:#10b981'>Close</a></td></tr>"
    if not rows_html: rows_html="<tr><td colspan=6>No trades</td></tr>"
    content=f"<div class=card><h3>{month_str} - {wr:.1f}% | {stats['total_r'] or 0:.1f}R | {curr_sym}{stats['pnl']:.2f}</h3><div>{month_tabs}</div><div style='overflow:auto'><table><tr><th>Time</th><th>Pair</th><th>Entry/SL/TP</th><th>Status</th><th>PNL</th><th>Action</th></tr>{rows_html}</table></div></div><div class=card><a class=btn-outline href='/export-journal?month={month_str}'>Export CSV</a> <a class=btn href='/dashboard'>Dashboard</a></div>"
    return layout(content,session['email'],"journal")

@app.route('/export-journal')
def export_journal():
    if 'email' not in session: return redirect('/')
    month_str=request.args.get('month')
    conn=get_conn(); cur=conn.cursor()
    if month_str: cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND TO_CHAR(created_at,'YYYY-MM')=%s AND archived=FALSE ORDER BY created_at",(session['email'],month_str))
    else: cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND archived=FALSE ORDER BY created_at",(session['email'],))
    trades=cur.fetchall(); cur.close(); conn.close()
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(['Date','Symbol','Direction','Entry','SL','TP','Status','PNL','R'])
    for t in trades:
        writer.writerow([t['created_at'].strftime('%Y-%m-%d'), t['symbol'], t['direction'], format_price(t['symbol'], t.get('original_entry') or t.get('entry')), format_price(t['symbol'], t.get('original_sl') or t.get('sl')), format_price(t['symbol'], t.get('tp')), t['status'], t.get('pnl',0), t.get('close_r',0)])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=journal_{month_str or 'all'}_v1262.csv"})

@app.route('/clear-journal')
def clear_journal():
    if 'email' not in session: return redirect('/')
    month_str=request.args.get('month')
    conn=get_conn(); cur=conn.cursor()
    if month_str: cur.execute("UPDATE agent35_trades SET archived=TRUE WHERE user_email=%s AND TO_CHAR(created_at,'YYYY-MM')=%s",(session['email'],month_str))
    else: cur.execute("UPDATE agent35_trades SET archived=TRUE WHERE user_email=%s",(session['email'],))
    conn.commit(); cur.close(); conn.close()
    return redirect(f'/journal/{month_str}' if month_str else '/journal')

@app.route('/scan')
def scan():
    sym=request.args.get("symbol","EURUSD").upper()
    try:
        res=engine.full_multi_tf_analysis(sym,use_news_filter=False)
        return jsonify(res)
    except Exception as e:
        return jsonify({"error":str(e),"trace":traceback.format_exc()})
   @app.route("/cron/scan-all")
def cron_scan_all():
    scanned = 0
    checked = 0
    details = []
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT email, telegram_id, symbols, news_filter FROM agent35_users WHERE payment_status='approved' AND telegram_id IS NOT NULL AND telegram_id!=''")
        users = cur.fetchall()
        print(f"CRON V12.6.2 checking {len(users)} users KEY={bool(TWELVE_KEY)}")
        for u in users:
            email = u['email']
            tgid = u['telegram_id']
            syms_str = u.get('symbols') or ''
            use_news = u.get('news_filter', True)
            if not syms_str:
                continue
            syms = [s.strip().upper() for s in syms_str.split(',') if s.strip()]
            checked += 1
            for sym in syms:
                cur.execute("SELECT id FROM agent35_trades WHERE user_email=%s AND symbol=%s AND status IN ('sent','took') AND archived=FALSE AND created_at > NOW() - INTERVAL '4 hours' LIMIT 1", (email, sym))
                if cur.fetchone():
                    print(f"SKIP {sym} {email} dup <4h")
                    continue
                try:
                    res = engine.full_multi_tf_analysis(sym, use_news_filter=use_news)
                except Exception as e:
                    print(f"Scan err {sym} {e} {traceback.format_exc()}")
                    details.append(f"ERR {sym} {e}")
                    continue
                if not res.get('signal'):
                    print(f"SKIP {sym} {email}: {res.get('reason')} Score {res.get('score')}")
                    details.append(f"SKIP {sym}: {res.get('reason')}")
                    continue
                if res.get('score', 0) >= 4:
                    try:
                        cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,original_entry,original_sl,timeframe_bias,confluence,status,be_done,lock_done,archived) VALUES (%s,%s,%s,%s,%s,%s,'sent',FALSE,FALSE,FALSE) RETURNING id", (email, res['symbol'], res['direction'], res['entry'], res['sl'], res['tp'], res['entry'], res['sl'], res['bias'], str(res.get('confluence',''))))
                        row = cur.fetchone()
                        conn.commit()
                        if row and tgid:
                            msg = build_signal_msg(res, u)
                            send_telegram(tgid, msg, trade_id=row['id'], stage="signal")
                            scanned += 1
                            print(f"SENT {sym} {res['direction']} {res['score']}/8 to {email}")
                    except Exception as e:
                        print(f"DB err {e}")
                        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"ok": True, "checked": checked, "sent": scanned, "details": details[:30]})
    except Exception as e:
        print(f"CRON fatal {e} {traceback.format_exc()}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/cron/update-trades")
def cron_update_trades():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, user_email, symbol, direction, entry, sl, original_entry, telegram_id FROM agent35_trades t JOIN agent35_users u ON t.user_email=u.email WHERE t.status='took' AND t.archived=FALSE")
        trades = cur.fetchall()
        updated = 0
        for t in trades:
            live = get_live_price(t['symbol'])
            if not live:
                continue
            close_price = live[0]
            try:
                entry = float(t['entry'])
                sl = float(t['sl'])
                risk = abs(entry - sl)
                if risk == 0:
                    continue
                r_now = (close_price - entry) / risk if t['direction'] == 'BUY' else (entry - close_price) / risk
                if r_now >= 1 and not t.get('be_done'):
                    cur.execute("UPDATE agent35_trades SET sl=%s, be_done=TRUE WHERE id=%s", (t['original_entry'] or entry, t['id']))
                    conn.commit()
                    updated += 1
                    if t.get('telegram_id'):
                        send_telegram(t['telegram_id'], f"🔒 <b>{t['symbol']} BE LOCKED</b> +1R reached", stage="update")
            except Exception as e:
                print(f"update err {t['id']} {e}")
        cur.close()
        conn.close()
        return jsonify({"ok": True, "updated": updated})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route('/manual-close')
def manual_close():
    if 'email' not in session:
        return redirect('/')
    tid = request.args.get('id')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agent35_trades WHERE id=%s AND user_email=%s", (tid, session['email']))
    t = cur.fetchone()
    if t:
        live = get_live_price(t['symbol'])
        close_price = live[0] if live else t['entry']
        cur.execute("UPDATE agent35_trades SET status='be', closed_at=NOW(), pnl=0, close_r=0, archived=FALSE WHERE id=%s", (tid,))
        conn.commit()
    cur.close()
    conn.close()
    return redirect('/journal')
@app.route('/r/<code>')
def referral_redirect(code):
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT email FROM agent35_users WHERE referral_code=%s",(code,)); ref=cur.fetchone()
    if ref:
        session['referred_by']=ref['email']
        return f"<html><head>{STYLE}</head><body><div class=card style='max-width:400px;margin:100px auto;text-align:center'><h2>Referral {code}</h2><p>You were referred by {ref['email']}</p><a class=btn href='/'>Continue to Register</a></div></body></html>"
    cur.close(); conn.close()
    return redirect('/')

@app.route('/payment')
def payment():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); user=cur.fetchone(); cur.close(); conn.close()
    content=f"<div class=card style='text-align:center'><h2>Payment V12.6.2</h2><p>Ref: {user.get('payment_ref') or session['email']}</p><p>Status: {user.get('payment_status','pending').upper()}</p><p>Decimals FIXED - JPY 3, Gold 2, Forex 5</p><a class=btn href='/dashboard'>Back to Dashboard</a></div>"
    return layout(content,session['email'],"payment")

@app.route('/webhook/telegram',methods=['POST'])
def telegram_webhook():
    try:
        data=request.get_json()
        if not data: return jsonify({"ok":True})
        if 'callback_query' in data:
            cq=data['callback_query']; cb_data=cq['data']; chat_id=str(cq['message']['chat']['id'])
            if ':' in cb_data:
                action,tid=cb_data.split(':')
                conn=get_conn(); cur=conn.cursor()
                cur.execute("SELECT * FROM agent35_trades WHERE id=%s",(tid,)); tr=cur.fetchone()
                if tr:
                    if action=='took':
                        cur.execute("UPDATE agent35_trades SET status='took', hit_entry_at=NOW() WHERE id=%s",(tid,)); conn.commit()
                        send_telegram(chat_id,f"✅ <b>TOOK {tr['symbol']} {tr['direction']}</b> Entry {format_price(tr['symbol'], tr['entry'])}",stage="update")
                    else:
                        cur.execute("UPDATE agent35_trades SET status='skip', archived=TRUE WHERE id=%s",(tid,)); conn.commit()
                        send_telegram(chat_id,f"❌ Skipped {tr['symbol']}",stage="update")
                cur.close(); conn.close()
        elif 'message' in data:
            msg=data['message']; chat_id=str(msg['chat']['id']); text=msg.get('text','')
            if text.startswith('/start'):
                parts=text.split(); ref=parts[1] if len(parts)>1 else ''
                if ref:
                    conn=get_conn(); cur=conn.cursor()
                    cur.execute("SELECT email FROM agent35_users WHERE payment_ref=%s OR email=%s",(ref,ref)); u=cur.fetchone()
                    if u:
                        cur.execute("UPDATE agent35_users SET telegram_id=%s, telegram_username=%s WHERE email=%s",(chat_id, msg['chat'].get('username',''), u['email'])); conn.commit()
                        send_telegram(chat_id,f"✅ <b>Linked to {u['email']}</b>\nV12.6.2 FIXED Decimals\nJPY 3, Gold 2, Forex 5\n\nYou will now receive signals!",stage="update")
                    cur.close(); conn.close()
                else:
                    send_telegram(chat_id,"Send your payment ref: /start YOUR_REF",stage="update")
        return jsonify({"ok":True})
    except Exception as e:
        print(f"webhook err {e} {traceback.format_exc()}")
        return jsonify({"ok":False,"error":str(e)})

@app.route('/test-telegram')
def test_telegram():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT telegram_id FROM agent35_users WHERE email=%s",(session['email'],)); u=cur.fetchone(); cur.close(); conn.close()
    if u and u['telegram_id']:
        send_telegram(u['telegram_id'],"<b>✅ Test OK V12.6.2 FIXED</b>\nDecimals: JPY 3, Gold 2, Forex 5\nDual FREE R0\nBot is working!",stage="update")
        return "Sent! Check Telegram"
    return "No telegram linked - go to dashboard and link"

if __name__=="__main__":
    port=int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port)
