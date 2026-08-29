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
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_users (id SERIAL PRIMARY KEY, email TEXT UNIQUE, password TEXT,is_creator BOOLEAN DEFAULT FALSE, plan TEXT DEFAULT 'none',payment_ref TEXT, payment_status TEXT DEFAULT 'pending',risk_reward TEXT DEFAULT '1:3', symbols TEXT DEFAULT 'EURUSD,XAUUSD,BTCUSD,GBPUSD,NAS100',sessions TEXT DEFAULT 'London,New York', account_size FLOAT DEFAULT 10000,lot_size FLOAT DEFAULT 0.1, leverage TEXT DEFAULT '1:500',telegram_id TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_trades (id SERIAL PRIMARY KEY, user_email TEXT, symbol TEXT,direction TEXT, entry FLOAT, sl FLOAT, tp FLOAT,status TEXT DEFAULT 'sent', pnl FLOAT DEFAULT 0,timeframe_bias TEXT, confluence TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_payments (id SERIAL PRIMARY KEY, user_email TEXT, plan TEXT,ref_code TEXT UNIQUE, amount INT, status TEXT DEFAULT 'pending',created_at TIMESTAMP DEFAULT NOW());""")
    for q in ["ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USD'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS last_scan_at TIMESTAMP","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS last_scan_summary TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS telegram_username TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency_symbol TEXT DEFAULT '$'","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS hit_entry_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS result_price FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS auto_updated BOOLEAN DEFAULT FALSE"]:
        try: cur.execute(q)
        except: pass
    conn.commit(); cur.close(); conn.close()
init_db()

def send_telegram(chat_id, text):
    if not TELEGRAM_TOKEN or not chat_id: return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode":"Markdown"}, timeout=10)
        return r.status_code==200
    except: return False

LOGO_SVG = """<svg width="34" height="34" viewBox="0 0 100 100"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#059669"/></linearGradient></defs><rect width="100" height="100" rx="18" fill="#0b111c" stroke="#10b981" stroke-width="3"/><text x="50%" y="58%" dominant-baseline="middle" text-anchor="middle" font-family="Arial Black" font-weight="900" font-size="48" fill="url(#g)">35</text></svg>"""
CUR = {'USD':'$','ZAR':'R','EUR':'€','GBP':'£'}
MAP = {"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"JPY=X","AUDUSD":"AUDUSD=X","USDCAD":"CAD=X","USDZAR":"ZAR=X","EURZAR":"EURZAR=X","GBPZAR":"GBPZAR=X","XAUUSD":"GC=F","GOLD":"GC=F","XAGUSD":"SI=F","USOIL":"CL=F","UKOIL":"BZ=F","BTCUSD":"BTC-USD","ETHUSD":"ETH-USD","SOLUSD":"SOL-USD","NAS100":"^NDX","US30":"^DJI","SPX500":"^GSPC","GER40":"^GDAXI","UK100":"^FTSE","JP225":"^N225","AAPL":"AAPL","TSLA":"TSLA","NVDA":"NVDA"}

def get_live_price(symbol):
    try:
        yfs = MAP.get(symbol.upper(), f"{symbol.upper()}=X")
        df = yf.download(yfs, period="1d", interval="5m", progress=False, auto_adjust=True)
        if df.empty: return None
        try: df.columns = df.columns.get_level_values(0)
        except: pass
        return float(df['Close'].iloc[-1]), float(df['High'].iloc[-1]), float(df['Low'].iloc[-1])
    except: return None

def auto_update_trades():
    while True:
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute("SELECT t.*, u.account_size, u.risk_reward, u.telegram_id, u.currency, u.currency_symbol FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.status IN ('sent','took','active') LIMIT 50")
            for tr in cur.fetchall():
                live = get_live_price(tr['symbol'])
                if not live: continue
                close, high, low = live; rr_val=3
                try: rr_val=int(tr['risk_reward'].split(':')[1])
                except: pass
                risk_amt = tr['account_size']*0.01; new_status=None; pnl=0
                if tr['status']=='sent' and low <= tr['entry'] <= high:
                    new_status='took'
                    # Telegram entry alert
                    if tr['telegram_id']:
                        send_telegram(tr['telegram_id'], f"🎯 *ENTRY HIT* {tr['symbol']} {tr['direction']}\nEntry: {tr['entry']}\nNow Active - Tracking TP/SL")
                elif tr['status'] in ('took','active'):
                    if tr['direction']=='BUY':
                        if low <= tr['sl']: new_status='loss'; pnl=-risk_amt
                        elif high >= tr['tp']: new_status='win'; pnl=risk_amt*rr_val
                    else:
                        if high >= tr['sl']: new_status='loss'; pnl=-risk_amt
                        elif low <= tr['tp']: new_status='win'; pnl=risk_amt*rr_val
                    # Auto notify on close
                    if new_status in ('win','loss') and tr['telegram_id']:
                        emoji = "✅ WIN" if new_status=='win' else "❌ LOSS"
                        cs = tr['currency_symbol'] or '$'
                        send_telegram(tr['telegram_id'], f"{emoji} *{tr['symbol']} CLOSED* {tr['direction']}\nStatus: {new_status.upper()}\nPNL: {cs}{round(pnl,2)}\nPrice: {close}\n🤖 Auto-Updated by Agent35")
                if new_status and new_status!=tr['status']:
                    if new_status in ('win','loss'): cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s, auto_updated=TRUE WHERE id=%s", (new_status,pnl,close,tr['id']))
                    else: cur.execute("UPDATE agent35_trades SET status=%s, hit_entry_at=NOW() WHERE id=%s", (new_status,tr['id']))
            conn.commit(); cur.close(); conn.close()
        except Exception as e: print(f"auto error {e}")
        time.sleep(180)
threading.Thread(target=auto_update_trades, daemon=True).start()

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
*{box-sizing:border-box}
body{background:#060a14;color:#e5e7eb;font-family:'Inter',sans-serif;margin:0;overflow-x:hidden}
.header{background:rgba(11,17,28,0.95);border-bottom:1px solid #1a2535;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:10px;color:#10b981;font-weight:800;font-size:18px}
.card{background:#0e1625;border:1px solid #1c2a41;border-radius:16px;padding:16px}
.btn{background:linear-gradient(135deg,#10b981,#059669);color:#000;font-weight:800;padding:12px 18px;border:none;border-radius:12px;cursor:pointer;text-decoration:none;display:block;text-align:center;width:100%}
.btn-outline{background:transparent;border:1px solid #24344e;color:#cbd5e1;padding:12px 18px;border-radius:12px;text-decoration:none;display:block;text-align:center;width:100%;margin-top:8px}
.btn-test{background:linear-gradient(135deg,#3b82f6,#2563eb);color:#fff;font-weight:700;padding:10px 14px;border:none;border-radius:10px;cursor:pointer;text-decoration:none;display:block;text-align:center;width:100%;margin-top:8px}
.grid{display:grid;gap:14px}.grid4{grid-template-columns:repeat(4,1fr)}
.badge{padding:5px 10px;border-radius:20px;font-size:11px;font-weight:800;display:inline-block}
.bull{background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.3)}
.bear{background:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.3)}
.win{background:rgba(16,185,129,0.25);color:#10b981}.loss{background:rgba(239,68,68,0.25);color:#ef4444}
.chip{display:inline-flex;align-items:center;gap:6px;background:#121d30;border:1px solid #1e2d45;padding:7px 12px;border-radius:24px;margin:4px;font-size:13px;cursor:pointer}
.x{background:#ef4444;color:#fff;border-radius:50%;width:20px;height:20px;display:inline-flex;justify-content:center;align-items:center;font-size:12px;margin-left:6px}
.searchbox{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px 14px;border-radius:12px;width:100%;margin:8px 0}
.dropdown{background:#121d30;border:1px solid #1e2d45;border-radius:12px;max-height:180px;overflow:auto;margin-top:4px;display:none;position:absolute;z-index:50;width:calc(100% - 32px)}
.dropdown div{padding:10px 14px;cursor:pointer;border-bottom:1px solid #1a2535}
table{width:100%;border-collapse:collapse} th{color:#64748b;text-align:left;padding:12px 8px;font-size:10px;text-transform:uppercase} td{padding:12px 8px;border-top:1px solid #1a2535;font-size:13px}
.nav-tabs{display:flex;gap:8px;overflow:auto;padding-bottom:8px;margin:12px 0}
.nav-tabs a{white-space:nowrap;padding:10px 16px;border-radius:24px;background:#121d30;border:1px solid #1e2d45;color:#94a3b8;text-decoration:none;font-size:13px;font-weight:600}
.nav-tabs a.active{background:#10b981;color:#000;border-color:#10b981}
.stat-label{font-size:11px;color:#64748b;text-transform:uppercase}.stat-value{font-size:22px;font-weight:800;margin-top:6px}
@media(max-width:1200px){.grid4{grid-template-columns:repeat(2,1fr)}}
@media(max-width:768px){.grid4{grid-template-columns:1fr} table{display:block;overflow-x:auto;white-space:nowrap}}
input,select{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:10px;width:100%;margin:6px 0}
label{font-size:12px;color:#94a3b8;margin-top:12px;display:block;font-weight:600}
.settings-section{background:#0e1625;border:1px solid #1c2a41;border-radius:16px;padding:20px;margin-bottom:16px}
</style>
<script>
const ALL_SYMBOLS = ["EURUSD","GBPUSD","USDJPY","USDZAR","XAUUSD","GOLD","BTCUSD","ETHUSD","NAS100","US30","GER40","USOIL","AAPL","TSLA"];
function addSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!='');if(arr.length>=5){alert('Max 5');return}if(!arr.includes(s)){arr.push(s);i.value=arr.join(',');document.getElementById('symForm').submit()}}
function removeSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!=s.trim()&&x.trim()!='');i.value=arr.join(',');document.getElementById('symForm').submit()}
function filterSyms(){let q=document.getElementById('symSearch').value.toUpperCase();let dd=document.getElementById('symDropdown');if(!q){dd.style.display='none';return}let f=ALL_SYMBOLS.filter(s=>s.includes(q)).slice(0,8);dd.innerHTML=f.map(s=>`<div onclick="addSym('${s}')">${s} - Add</div>`).join('');dd.style.display=f.length?'block':'none'}
</script>
"""

def layout(content, email="", active="dashboard"):
    tabs = f"<div class='nav-tabs'><a href='/dashboard' class='{'active' if active=='dashboard' else ''}'>📊 Dashboard</a><a href='/journal' class='{'active' if active=='journal' else ''}'>📔 Journal</a><a href='/settings' class='{'active' if active=='settings' else ''}'>⚙️ Settings</a><a href='/payment'>💳 Plans</a></div>"
    return f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=1'><title>Agent 35</title>{STYLE}</head><body><div class='header'><div class='logo'>{LOGO_SVG} AGENT 35 <span style='font-size:9px;background:#10b981;color:#000;padding:3px 7px;border-radius:20px;margin-left:8px'>V5.2</span></div><div style='display:flex;gap:10px'><span style='font-size:11px;color:#94a3b8'>{email}</span><a href='/logout' style='color:#94a3b8;text-decoration:none;font-size:13px'>Logout</a></div></div><div style='padding:14px;max-width:1400px;margin:auto'>{tabs}{content}</div></body></html>"

@app.route('/')
def home():
    return f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1'>{STYLE}</head><body style='display:flex;justify-content:center;align-items:center;min-height:100vh;padding:16px'><div class='card' style='width:100%;max-width:400px;text-align:center;padding:28px'><div style='display:flex;justify-content:center;margin-bottom:16px'>{LOGO_SVG.replace('34','72')}</div><h1 style='color:#10b981;margin:0'>AGENT 35</h1><p style='color:#64748b'>V5.2 • @{TELEGRAM_BOT_USERNAME}</p><form method='POST' action='/auth' style='margin-top:24px;text-align:left'><label>Email</label><input name='email' required><label>Password</label><input name='password' type='password' required><button class='btn' style='margin-top:16px'>Login</button></form></div></body></html>"

@app.route('/auth', methods=['POST'])
def auth():
    email = request.form['email'].lower().strip(); pw = hashlib.sha256(request.form['password'].encode()).hexdigest()
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s AND password=%s", (email, pw)); u=cur.fetchone()
    if not u:
        cur.execute("INSERT INTO agent35_users (email,password,plan,payment_status,symbols) VALUES (%s,%s,'none','pending','EURUSD,XAUUSD') RETURNING *", (email,pw)); u=cur.fetchone(); conn.commit()
    cur.close(); conn.close(); session['email']=u['email']; session['is_creator']=u['is_creator']; return redirect('/master' if u['is_creator'] else '/dashboard')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC LIMIT 8", (session['email'],)); trades=cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as pnl, COUNT(*) FILTER (WHERE status='win') as wins, COUNT(*) FILTER (WHERE status='loss') as losses, COUNT(*) FILTER (WHERE status IN ('win','loss')) as closed FROM agent35_trades WHERE user_email=%s", (session['email'],)); stats=cur.fetchone()
    cur.close(); conn.close()
    pnl=stats['pnl']; wr=(stats['wins']/stats['closed']*100) if stats['closed']>0 else 0; curr_sym=CUR.get(user['currency'],'$')
    syms=[s for s in (user['symbols'] or '').split(',') if s.strip()]; chips="".join([f"<span class='chip'><b>{s}</b><span class='x' onclick=\"removeSym('{s}')\">×</span></span>" for s in syms])
    popular=["EURUSD","GBPUSD","XAUUSD","BTCUSD","NAS100","USDZAR","US30","GER40"]; pop_btns="".join([f"<span class='chip' onclick=\"addSym('{s}')\">+ {s}</span>" for s in popular if s not in syms])
    tg_linked = bool(user['telegram_id']); tg_msg = f"✅ Linked @{user['telegram_username']}" if tg_linked else "❌ Not linked"
    content=f"""
    <div class='grid grid4'>
      <div class='card'><div class='stat-label'>Total PNL Auto</div><div class='stat-value'>{curr_sym}{round(pnl,2)} <span class='badge {"bull" if pnl>=0 else "bear"}'>{round(wr,1)}% WR</span></div><div style='font-size:11px;color:#10b981;margin-top:6px'>● Auto every 3 min + Telegram alerts</div></div>
      <div class='card'><div class='stat-label'>Account {user['currency']}</div><div class='stat-value' style='font-size:18px'>{curr_sym}{user['account_size']} • {user['lot_size']} lot</div><div style='font-size:12px;color:#64748b'>{user['leverage']} • RR {user['risk_reward']}</div><a href='/settings' class='btn-outline'>Edit Settings</a></div>
      <div class='card' style='position:relative'><div class='stat-label'>Watchlist (5 max)</div><div style='margin:10px 0'>{chips or 'No symbols'}</div><form id='symForm' method='POST' action='/quick-symbols'><input type='hidden' name='symbols' id='symInput' value="{user['symbols']}"></form><input id='symSearch' class='searchbox' placeholder='🔍 Search...' oninput='filterSyms()'><div id='symDropdown' class='dropdown'></div><div style='margin-top:8px'>{pop_btns}</div></div>
      <div class='card'><div class='stat-label'>Telegram • @{TELEGRAM_BOT_USERNAME}</div>
        <a class='btn' href='/scan' style='margin-top:10px'>🔍 SCAN MARKET</a>
        <a href='https://t.me/{TELEGRAM_BOT_USERNAME}?start={session['email']}' target='_blank' class='btn-outline' style='border-color:#10b981;color:#10b981'>📲 {tg_msg} - Tap to Link</a>
        <a href='/test-telegram' class='btn-test'>🧪 Send Test Signal to Telegram</a>
        <div style='font-size:10px;color:#64748b;margin-top:8px;text-align:center'>Test sends a fake BUY signal to verify your Telegram works. Auto-alerts sent when real trades hit TP/SL.</div>
      </div>
    </div>
    <div class='card' style='margin-top:14px'><div style='display:flex;justify-content:space-between'><h3 style='margin:0;color:#10b981'>Recent Trades</h3><a href='/journal' style='font-size:12px'>Full Journal →</a></div><div style='overflow:auto;margin-top:12px'><table><tr><th>Time</th><th>Symbol</th><th>Dir</th><th>Status</th><th>PNL</th></tr>{''.join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td><b>{t['symbol']}</b></td><td><span class='badge { 'bull' if t['direction']=='BUY' else 'bear'}'>{t['direction']}</span></td><td><span class='badge { 'win' if t['status']=='win' else 'loss' if t['status']=='loss' else ''}'>{t['status'].upper()}</span></td><td style='font-weight:800;color:{'#10b981' if t['pnl']>0 else '#ef4444' if t['pnl']<0 else '#94a3b8'}'>{curr_sym}{round(t['pnl'],2)}</td></tr>" for t in trades]) or '<tr><td colspan=5 style=text-align:center;color:#475569>No trades</td></tr>'}</table></div></div>
    """
    return layout(content, session['email'], "dashboard")

@app.route('/test-telegram')
def test_telegram():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT telegram_id, currency, currency_symbol, account_size FROM agent35_users WHERE email=%s", (session['email'],)); u=cur.fetchone(); cur.close(); conn.close()
    if not u or not u['telegram_id']:
        return layout(f"<div class='card' style='text-align:center'><h3 style='color:#ef4444'>❌ Telegram Not Linked</h3><p>Link first via button in dashboard</p><a class='btn' href='https://t.me/{TELEGRAM_BOT_USERNAME}?start={session['email']}' target='_blank'>Link @{TELEGRAM_BOT_USERNAME}</a><br><a class='btn-outline' href='/dashboard' style='margin-top:10px'>Back</a></div>", session['email'])
    msg = f"""🧪 *TEST SIGNAL - Agent 35*

📊 *Symbol:* EURUSD
📈 *Direction:* BUY
💰 *Entry:* 1.08450
🛑 *SL:* 1.08200
🎯 *TP:* 1.09100
📦 *Lot:* 0.10
💵 *Risk:* 1% = ${round(u['account_size']*0.01,2)}

✅ *Your Telegram is working!*
Real signals will look like this + Journal auto-updates when trade closes.

Bot: @{TELEGRAM_BOT_USERNAME}"""
    ok = send_telegram(u['telegram_id'], msg)
    if ok:
        return layout(f"<div class='card' style='text-align:center'><h3 style='color:#10b981'>✅ Test Sent!</h3><p>Check Telegram @{TELEGRAM_BOT_USERNAME}</p><p style='font-size:12px;color:#64748b'>Message sent to ID {u['telegram_id']}</p><a class='btn' href='/dashboard'>Back to Dashboard</a></div>", session['email'])
    else:
        return layout(f"<div class='card' style='text-align:center'><h3 style='color:#ef4444'>❌ Failed to Send</h3><p>Check TELEGRAM_BOT_TOKEN in Render env vars</p><a class='btn-outline' href='/dashboard'>Back</a></div>", session['email'])

@app.route('/journal')
def journal():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC", (session['email'],)); trades=cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as total, COUNT(*) FILTER (WHERE status='win') as wins, COUNT(*) FILTER (WHERE status='loss') as losses, COUNT(*) FILTER (WHERE status IN ('win','loss')) as closed, COUNT(*) as total_trades FROM agent35_trades WHERE user_email=%s", (session['email'],)); s=cur.fetchone()
    cur.close(); conn.close()
    curr_sym=CUR.get(user['currency'],'$'); wr = (s['wins']/s['closed']*100) if s['closed']>0 else 0
    content = f"""
    <div class='grid grid4'>
      <div class='card'><div class='stat-label'>Total PNL</div><div class='stat-value' style='color:{'#10b981' if s['total']>=0 else '#ef4444'}'>{curr_sym}{round(s['total'],2)}</div><div style='font-size:12px;color:#64748b'>{s['wins']}W / {s['losses']}L</div></div>
      <div class='card'><div class='stat-label'>Win Rate</div><div class='stat-value'>{round(wr,1)}%</div></div>
      <div class='card'><div class='stat-label'>Total Trades</div><div class='stat-value'>{s['total_trades']}</div><div style='font-size:12px;color:#10b981'>● Live auto + Telegram</div></div>
      <div class='card'><a href='/export/csv' class='btn'>📥 Export CSV</a><a href='/test-telegram' class='btn-test'>🧪 Test Telegram</a><a href='/cron/update-trades' class='btn-outline'>🔄 Force Update</a></div>
    </div>
    <div class='card' style='margin-top:14px'><h3 style='margin:0;color:#10b981'>📔 Full Journal - Auto Telegram on Close</h3><div style='overflow:auto;margin-top:12px'><table><tr><th>Date</th><th>Symbol</th><th>Dir</th><th>Entry/SL/TP</th><th>Result</th><th>Status</th><th>PNL</th></tr>
    {''.join([f"<tr><td>{t['created_at'].strftime('%Y-%m-%d %H:%M')}</td><td><b>{t['symbol']}</b></td><td><span class='badge { 'bull' if t['direction']=='BUY' else 'bear'}'>{t['direction']}</span></td><td style='font-size:11px'>E {round(t['entry'],4)}<br>SL {round(t['sl'],4)}<br>TP {round(t['tp'],4)}</td><td>{round(t['result_price'],4) if t['result_price'] else '-'}</td><td><span class='badge { 'win' if t['status']=='win' else 'loss' if t['status']=='loss' else 'bull'}'>{t['status'].upper()}</span></td><td style='font-weight:800;color:{'#10b981' if t['pnl']>0 else '#ef4444' if t['pnl']<0 else '#94a3b8'}'>{curr_sym}{round(t['pnl'],2)}</td></tr>" for t in trades]) or '<tr><td colspan=7 style=text-align:center;padding:30px;color:#475569>No trades</td></tr>'}
    </table></div></div>
    """
    return layout(content, session['email'], "journal")

@app.route('/export/csv')
def export_csv():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC", (session['email'],)); trades=cur.fetchall()
    cur.close(); conn.close()
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(['Date','Time','Symbol','Direction','Entry','SL','TP','Result Price','Status','PNL '+user['currency'],'Confluence','Bias','Closed At','Time Held','Auto Updated'])
    for t in trades:
        held = str(t['closed_at']-t['created_at']).split('.')[0] if t['closed_at'] else 'Active'
        writer.writerow([t['created_at'].strftime('%Y-%m-%d'), t['created_at'].strftime('%H:%M:%S'), t['symbol'], t['direction'], t['entry'], t['sl'], t['tp'], t['result_price'] or '', t['status'], t['pnl'], t['confluence'] or '', t['timeframe_bias'] or '', t['closed_at'].strftime('%Y-%m-%d %H:%M') if t['closed_at'] else '', held, 'Yes' if t['auto_updated'] else 'No'])
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=agent35_{session["email"]}_{datetime.now().strftime("%Y-%m-%d")}.csv'})

@app.route('/settings', methods=['GET','POST'])
def settings():
    if 'email' not in session: return redirect('/')
    if request.method=='POST':
        curr = request.form['currency']
        conn=get_conn(); cur=conn.cursor(); cur.execute("UPDATE agent35_users SET symbols=%s, sessions=%s, risk_reward=%s, account_size=%s, lot_size=%s, currency=%s, currency_symbol=%s, telegram_username=%s, leverage=%s WHERE email=%s",(request.form['symbols'][:100], request.form['sessions'], request.form['rr'], float(request.form['acc']), float(request.form['lot']), curr, CUR.get(curr,'$'), request.form['tg'], request.form['lev'], session['email'])); conn.commit(); cur.close(); conn.close(); return redirect('/dashboard')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); u=cur.fetchone(); cur.close(); conn.close()
    opts = "".join([f"<option value='{k}' {'selected' if u['currency']==k else ''}>{k} ({v})</option>" for k,v in CUR.items()])
    return layout(f"<div style='max-width:800px;margin:auto'><h2 style='color:#10b981'>⚙️ Professional Settings</h2><form method='POST'><div class='settings-section'><h4>💱 ACCOUNT</h4><div class='grid' style='grid-template-columns:1fr 1fr;gap:12px'><div><label>Currency</label><select name='currency'>{opts}</select></div><div><label>Size</label><input name='acc' type='number' value=\"{u['account_size']}\"></div><div><label>Lot</label><input name='lot' type='number' step='0.01' value=\"{u['lot_size']}\"></div><div><label>Leverage</label><select name='lev'><option {'selected' if u['leverage']=='1:100' else ''}>1:100</option><option {'selected' if u['leverage']=='1:500' else ''}>1:500</option></select></div></div></div><div class='settings-section'><h4>📊 RISK</h4><div class='grid' style='grid-template-columns:1fr 1fr;gap:12px'><div><label>RR</label><select name='rr'><option {'selected' if u['risk_reward']=='1:2' else ''}>1:2</option><option {'selected' if u['risk_reward']=='1:3' else ''}>1:3</option><option {'selected' if u['risk_reward']=='1:4' else ''}>1:4</option></select></div><div><label>Sessions</label><input name='sessions' value=\"{u['sessions']}\"></div></div><label>Symbols</label><input name='symbols' value=\"{u['symbols']}\"></div><div class='settings-section'><h4>🔗 @{TELEGRAM_BOT_USERNAME}</h4><label>Telegram @</label><input name='tg' value=\"{u['telegram_username'] or ''}\"><div style='margin-top:10px'><a href='https://t.me/{TELEGRAM_BOT_USERNAME}?start={session['email']}' target='_blank' class='btn-outline' style='border-color:#10b981;color:#10b981'>📲 Link Telegram Now</a><a href='/test-telegram' class='btn-test'>🧪 Send Test Signal</a></div></div><button class='btn'>💾 Save</button><a href='/dashboard' class='btn-outline'>Back</a></form></div>", session['email'], "settings")

@app.route('/quick-symbols', methods=['POST'])
def quick_symbols():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("UPDATE agent35_users SET symbols=%s WHERE email=%s",(request.form['symbols'][:100], session['email'])); conn.commit(); cur.close(); conn.close(); return redirect('/dashboard')

@app.route('/scan')
def scan():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); user=cur.fetchone()
    symbols=(user['symbols'] if user else "EURUSD").split(",")[:5]; results=[]
    for sym in symbols:
        sym=sym.strip().upper()
        if not sym: continue
        try: res=engine.full_multi_tf_analysis(sym)
        except: res={"signal":False,"symbol":sym}
        res['symbol']=sym; results.append(res)
        if res.get('signal'):
            cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,timeframe_bias,confluence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(session['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['bias'],res['confluence']))
            # Send real signal to Telegram
            if user['telegram_id']:
                send_telegram(user['telegram_id'], f"🚀 *NEW SIGNAL* {res['symbol']} {res['direction']}\nEntry: {res['entry']}\nSL: {res['sl']}\nTP: {res['tp']}\nScore: {res.get('score','')}/8\n{res.get('confluence','')}\n\nJournal will auto-update when closed.")
    cur.execute("UPDATE agent35_users SET last_scan_at=NOW() WHERE email=%s",(session['email'],))
    conn.commit(); cur.close(); conn.close()
    html="".join([f"<div class='card' style='border-left:4px solid #10b981;margin:10px 0'><b>{r['symbol']} {r.get('direction','')} {r.get('score',0)}/8</b><br>{r.get('entry','')} SL {r.get('sl','')} TP {r.get('tp','')}<br><span style='font-size:12px'>{r.get('confluence','')}</span></div>" if r.get('signal') else f"<div class='card' style='opacity:0.6;margin:10px 0'><b>{r['symbol']} - No Setup</b></div>" for r in results])
    return layout(f"<h2>Scan Results - Sent to @{TELEGRAM_BOT_USERNAME} if linked</h2>{html}<br><a class='btn' href='/journal'>View Journal</a><a class='btn-outline' href='/dashboard'>Dashboard</a>", session['email'])

@app.route('/cron/update-trades')
def cron_update():
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("SELECT t.*, u.account_size, u.risk_reward, u.telegram_id, u.currency_symbol FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.status IN ('sent','took') LIMIT 30")
        for tr in cur.fetchall():
            live=get_live_price(tr['symbol'])
            if not live: continue
            close,high,low=live; rr=3
            try: rr=int(tr['risk_reward'].split(':')[1])
            except: pass
            risk=tr['account_size']*0.01; new=None; pnl=0
            if tr['status']=='sent' and low <= tr['entry'] <= high: new='took'
            elif tr['status'] in ('took','active'):
                if tr['direction']=='BUY':
                    if low <= tr['sl']: new='loss'; pnl=-risk
                    elif high >= tr['tp']: new='win'; pnl=risk*rr
                else:
                    if high >= tr['sl']: new='loss'; pnl=-risk
                    elif low <= tr['tp']: new='win'; pnl=risk*rr
            if new and new!=tr['status']:
                if new in ('win','loss'):
                    cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s, auto_updated=TRUE WHERE id=%s",(new,pnl,close,tr['id']))
                    if tr['telegram_id']:
                        cs=tr['currency_symbol'] or '$'
                        emoji="✅ WIN" if new=='win' else "❌ LOSS"
                        send_telegram(tr['telegram_id'], f"{emoji} *{tr['symbol']} {new.upper()}* {tr['direction']}\nPNL: {cs}{round(pnl,2)}\nClosed: {close}\n🤖 Journal Auto-Updated")
                else: cur.execute("UPDATE agent35_trades SET status=%s, hit_entry_at=NOW() WHERE id=%s",(new,tr['id']))
        conn.commit(); cur.close(); conn.close()
    except Exception as e: return jsonify({"error":str(e)})
    return redirect('/journal')

@app.route('/telegram/webhook', methods=['POST'])
def tg_webhook():
    data=request.json
    try:
        if 'message' in data:
            chat_id=data['message']['chat']['id']; username=data['message']['chat'].get('username',''); text=data['message'].get('text','')
            email=text.split('/start ')[-1].strip() if '/start' in text else None
            if email and '@' in email:
                conn=get_conn(); cur=conn.cursor(); cur.execute("UPDATE agent35_users SET telegram_id=%s, telegram_username=%s WHERE email=%s",(str(chat_id), username, email.lower())); conn.commit(); cur.close(); conn.close()
                if TELEGRAM_TOKEN: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id":chat_id,"text":f"✅ Linked! Agent35 V5.2 @{TELEGRAM_BOT_USERNAME} ready. Use Test button in dashboard."})
    except: pass
    return jsonify({"ok":True})

@app.route('/healthz')
def health(): return jsonify({"status":"ok","bot":"@Sniper035_bot V5.2 Test + Auto"})

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

if __name__ == '__main__': app.run(host='0.0.0.0', port=int(os.environ.get('PORT',10000)))
