import os, hashlib, requests, psycopg, threading, time
from psycopg.rows import dict_row
from flask import Flask, request, redirect, session, jsonify
from datetime import datetime
import trading_engine as engine
import yfinance as yf

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'agent35-secret-2025')
DATABASE_URL = os.environ.get('DATABASE_URL','').strip()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN','')
TELEGRAM_CHAT = os.environ.get('TELEGRAM_CHAT_ID','')
TELEGRAM_BOT_USERNAME = os.environ.get('TELEGRAM_BOT_USERNAME','Agent35_bot')
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
    conn.commit()
    cur.execute("SELECT * FROM agent35_users WHERE email='creator@agent35.com'")
    if not cur.fetchone():
        pw = hashlib.sha256('Agent35Creator!'.encode()).hexdigest()
        cur.execute("INSERT INTO agent35_users (email,password,is_creator,plan,payment_status,paid_at) VALUES (%s,%s,TRUE,'lifetime','approved',NOW())", ('creator@agent35.com', pw))
        pw2 = hashlib.sha256('Test123!'.encode()).hexdigest()
        cur.execute("INSERT INTO agent35_users (email,password,plan,payment_status,symbols,paid_at) VALUES (%s,%s,'yearly','approved','EURUSD,XAUUSD',NOW())", ('test@agent35.com', pw2))
        conn.commit()
    cur.close(); conn.close()

init_db()

LOGO_SVG = """<svg width="38" height="38" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#059669"/></linearGradient></defs><rect width="100" height="100" rx="18" fill="#0b111c" stroke="#10b981" stroke-width="3"/><text x="50%" y="58%" dominant-baseline="middle" text-anchor="middle" font-family="Arial Black" font-weight="900" font-size="48" fill="url(#g)">35</text><circle cx="78" cy="22" r="4" fill="#10b981"/></svg>"""
CUR = {'USD':'$','ZAR':'R','EUR':'€','GBP':'£'}

# FULL 60 SYMBOL MAP
MAP = {
    "EURUSD":"EURUSD=X", "GBPUSD":"GBPUSD=X", "USDJPY":"JPY=X", "AUDUSD":"AUDUSD=X", "USDCAD":"CAD=X", "USDCHF":"CHF=X", "NZDUSD":"NZDUSD=X",
    "EURGBP":"EURGBP=X", "EURJPY":"EURJPY=X", "GBPJPY":"GBPJPY=X", "AUDJPY":"AUDJPY=X", "EURAUD":"EURAUD=X", "GBPAUD":"GBPAUD=X", "EURCAD":"EURCAD=X", "GBPCAD":"GBPCAD=X", "CADJPY":"CADJPY=X", "CHFJPY":"CHFJPY=X", "AUDCAD":"AUDCAD=X",
    "USDZAR":"ZAR=X", "EURZAR":"EURZAR=X", "GBPZAR":"GBPZAR=X", "USDTRY":"TRY=X", "USDMXN":"MXN=X",
    "XAUUSD":"GC=F", "GOLD":"GC=F", "XAGUSD":"SI=F", "SILVER":"SI=F", "USOIL":"CL=F", "WTI":"CL=F", "UKOIL":"BZ=F", "BRENT":"BZ=F", "NATGAS":"NG=F", "COPPER":"HG=F",
    "BTCUSD":"BTC-USD", "ETHUSD":"ETH-USD", "SOLUSD":"SOL-USD", "XRPUSD":"XRP-USD", "BNBUSD":"BNB-USD", "DOGEUSD":"DOGE-USD", "ADAUSD":"ADA-USD",
    "NAS100":"^NDX", "NASDAQ":"^NDX", "US30":"^DJI", "DOW":"^DJI", "SPX500":"^GSPC", "SP500":"^GSPC", "US2000":"^RUT", "VIX":"^VIX",
    "GER40":"^GDAXI", "DAX":"^GDAXI", "UK100":"^FTSE", "FTSE":"^FTSE", "FRA40":"^FCHI", "EU50":"^STOXX50E", "JP225":"^N225", "NIKKEI":"^N225", "HK50":"^HSI", "AUS200":"^AXJO",
    "AAPL":"AAPL", "TSLA":"TSLA", "NVDA":"NVDA", "MSFT":"MSFT", "META":"META", "GOOGL":"GOOGL", "AMZN":"AMZN"
}

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
    print("🔄 Auto-Update Worker Started")
    while True:
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute("SELECT t.*, u.account_size, u.lot_size, u.currency, u.risk_reward, u.telegram_id FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.status IN ('sent','took','active') ORDER BY t.created_at DESC LIMIT 50")
            trades = cur.fetchall()
            for tr in trades:
                live = get_live_price(tr['symbol'])
                if not live: continue
                close, high, low = live
                entry, sl, tp, direction = tr['entry'], tr['sl'], tr['tp'], tr['direction']
                status = tr['status']; new_status = status; pnl = tr['pnl']; closed=False
                if status == 'sent':
                    if low <= entry <= high:
                        new_status='took'; cur.execute("UPDATE agent35_trades SET status=%s, hit_entry_at=NOW() WHERE id=%s", (new_status, tr['id'])); conn.commit(); continue
                if new_status in ('took','active'):
                    rr_val=3
                    try: rr_val=int(tr['risk_reward'].split(':')[1])
                    except: pass
                    risk_amt = tr['account_size']*0.01
                    if direction=='BUY':
                        if low <= sl: new_status='loss'; pnl=-risk_amt; closed=True
                        elif high >= tp: new_status='win'; pnl=risk_amt*rr_val; closed=True
                    else:
                        if high >= sl: new_status='loss'; pnl=-risk_amt; closed=True
                        elif low <= tp: new_status='win'; pnl=risk_amt*rr_val; closed=True
                    if closed:
                        cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s, auto_updated=TRUE WHERE id=%s", (new_status,pnl,close,tr['id'])); conn.commit()
            cur.close(); conn.close()
        except Exception as e: print(f"Auto-update error: {e}")
        time.sleep(300)

threading.Thread(target=auto_update_trades, daemon=True).start()

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
body{background:#05080f;color:#e5e7eb;font-family:'Inter',sans-serif;margin:0}
.header{background:#0b111c;border-bottom:1px solid #1a2535;padding:14px 24px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:10}
.logo{display:flex;align-items:center;gap:10px;color:#10b981;font-weight:800;font-size:20px}
.card{background:#0b111c;border:1px solid #1a2535;border-radius:14px;padding:18px}
.btn{background:#10b981;color:#000;font-weight:800;padding:11px 18px;border:none;border-radius:10px;cursor:pointer;text-decoration:none;display:inline-block;text-align:center}
.btn-outline{background:transparent;border:1px solid #1a2535;color:#fff;padding:11px 18px;border-radius:10px;text-decoration:none}
.grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px;margin:20px 0}
.badge{padding:4px 10px;border-radius:20px;font-size:11px;font-weight:800}
.bull{background:rgba(16,185,129,0.12);color:#10b981;border:1px solid rgba(16,185,129,0.3)}
.bear{background:rgba(239,68,68,0.12);color:#ef4444;border:1px solid rgba(239,68,68,0.3)}
.win{background:rgba(16,185,129,0.2);color:#10b981}.loss{background:rgba(239,68,68,0.2);color:#ef4444}
.chip{display:inline-flex;align-items:center;gap:6px;background:#111a2a;border:1px solid #1e2d45;padding:6px 10px;border-radius:20px;margin:4px;font-size:13px;cursor:pointer}
.chip b{color:#10b981}.x{background:#ef4444;color:#fff;border-radius:50%;width:18px;height:18px;display:inline-flex;justify-content:center;align-items:center;font-size:11px}
table{width:100%;border-collapse:collapse} th{color:#6b7280;text-align:left;padding:12px;font-size:11px;text-transform:uppercase} td{padding:10px;border-top:1px solid #1a2535;font-size:13px}
.searchbox{background:#05080f;border:1px solid #10b981;color:#fff;padding:12px;border-radius:10px;width:100%;margin:6px 0}
.dropdown{background:#111a2a;border:1px solid #1e2d45;border-radius:10px;max-height:160px;overflow:auto;margin-top:4px;display:none}
.dropdown div{padding:8px 12px;cursor:pointer;border-bottom:1px solid #1a2535;font-size:13px}
.dropdown div:hover{background:#1a2535;color:#10b981}
a{color:#10b981}
</style>
<script>
const ALL_SYMBOLS = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD","EURGBP","EURJPY","GBPJPY","AUDJPY","EURAUD","GBPAUD","EURCAD","GBPCAD","CADJPY","CHFJPY","USDZAR","EURZAR","GBPZAR","XAUUSD","GOLD","XAGUSD","SILVER","USOIL","WTI","UKOIL","BRENT","NATGAS","COPPER","BTCUSD","ETHUSD","SOLUSD","XRPUSD","BNBUSD","DOGEUSD","NAS100","US30","SPX500","SP500","US2000","GER40","DAX","UK100","FTSE","FRA40","JP225","NIKKEI","HK50","AAPL","TSLA","NVDA","MSFT","META","GOOGL","AMZN"];
function addSym(s){let i=document.getElementById('symInput');let v=i.value;let arr=v?v.split(',').filter(x=>x.trim()!=''):[];if(arr.length>=5){alert('Max 5 symbols - upgrade for more');return}if(!arr.includes(s)){arr.push(s);i.value=arr.join(',');document.getElementById('symForm').submit()}}
function removeSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!=s.trim() && x.trim()!='');i.value=arr.join(',');document.getElementById('symForm').submit()}
function filterSyms(){let q=document.getElementById('symSearch').value.toUpperCase();let dd=document.getElementById('symDropdown');if(!q){dd.style.display='none';return}let filtered=ALL_SYMBOLS.filter(s=>s.includes(q)).slice(0,10);if(filtered.length==0){dd.style.display='none';return}dd.innerHTML=filtered.map(s=>`<div onclick="addSym('${s}')">${s} - Click to add</div>`).join('');dd.style.display='block'}
function hideDD(){setTimeout(()=>{document.getElementById('symDropdown').style.display='none'},200)}
</script>
"""

def layout(content, email=""):
    return f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1'>{STYLE}</head><body><div class='header'><div class='logo'>{LOGO_SVG} AGENT 35 <span style='font-size:10px;background:#10b981;color:#000;padding:2px 6px;border-radius:10px;margin-left:8px'>60 SYMBOLS</span></div><div style='display:flex;gap:12px;align-items:center'><span style='font-size:11px;color:#9ca3af'>{email}</span><a href='/logout' class='btn-outline'>Logout</a></div></div><div style='padding:20px;max-width:1250px;margin:auto'>{content}</div></body></html>"

@app.route('/')
def home():
    return f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1'>{STYLE}</head><body style='display:flex;justify-content:center;align-items:center;height:100vh'><div class='card' style='width:380px;text-align:center;padding:32px'><div style='display:flex;justify-content:center;margin-bottom:12px'>{LOGO_SVG.replace('38','80')}</div><h1 style='color:#10b981;margin:0'>AGENT 35</h1><p style='color:#9ca3af;margin-top:4px'>V4.2 - 60 Symbols Auto</p><form method='POST' action='/auth' style='margin-top:20px;text-align:left'><input name='email' placeholder='Email' value='test@agent35.com' required><input name='password' type='password' placeholder='Password' value='Test123!' required><button class='btn' style='width:100%;margin-top:12px'>LOGIN</button></form></div></body></html>"

@app.route('/auth', methods=['POST'])
def auth():
    email = request.form['email'].lower().strip(); pw = hashlib.sha256(request.form['password'].encode()).hexdigest()
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s AND password=%s", (email, pw)); u=cur.fetchone(); cur.close(); conn.close()
    if u: session['email']=u['email']; session['is_creator']=u['is_creator']; return redirect('/master' if u['is_creator'] else '/dashboard')
    return "Invalid <a href='/'>back</a>"

@app.route('/dashboard')
def dashboard():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC LIMIT 30", (session['email'],)); trades=cur.fetchall(); cur.close(); conn.close()
    pnl = sum([t['pnl'] for t in trades]); winrate = len([t for t in trades if t['pnl']>0])/len([t for t in trades if t['status'] in ('win','loss')])*100 if [t for t in trades if t['status'] in ('win','loss')] else 0
    took = len([t for t in trades if t['status']!='sent']); curr_sym = CUR.get(user['currency'],'$'); last_scan = user['last_scan_at'].strftime('%Y-%m-%d %H:%M') if user['last_scan_at'] else 'Never'; tg_status = f"✅ @{user['telegram_username']}" if user['telegram_username'] else "❌ Not linked"
    syms = [s for s in (user['symbols'] or '').split(',') if s.strip()]; chips = "".join([f"<span class='chip'><b>{s}</b> <span class='x' style='margin-left:6px;background:#ef4444;color:#fff;border-radius:50%;width:18px;height:18px;display:inline-flex;justify-content:center;align-items:center;font-size:11px;cursor:pointer' onclick=\"removeSym('{s}')\">x</span></span>" for s in syms])
    popular = ["EURUSD","GBPUSD","XAUUSD","BTCUSD","NAS100","USDJPY","GBPJPY","US30","USDZAR","GER40","ETHUSD","USOIL","AUDUSD","SPX500","AAPL","TSLA"]
    popular_btns = "".join([f"<span class='chip' onclick=\"addSym('{s}')\">+ {s}</span>" for s in popular if s not in syms])
    content = f"""
    <div class='grid4'>
      <div class='card'><div style='color:#9ca3af;font-size:11px'>TOTAL PNL ({user['currency']}) AUTO</div><div style='font-size:24px;font-weight:800;margin-top:6px'>{curr_sym}{round(pnl,2)} <span class='badge {"bull" if pnl>=0 else "bear"}'>{round(winrate,1)}% WR</span></div><div style='font-size:12px;color:#6b7280;margin-top:6px'>{took} taken • Last: {last_scan}</div><div style='font-size:11px;color:#10b981;margin-top:8px'>🤖 Auto every 5 min</div><div style='font-size:11px;color:#9ca3af'>{user['last_scan_summary'] or ''}</div></div>
      <div class='card'><div style='color:#9ca3af;font-size:11px'>ACCOUNT ({user['currency']})</div><div style='font-size:18px;font-weight:700;margin-top:6px'>{curr_sym}{user['account_size']} | Lot {user['lot_size']}</div><div style='font-size:12px;color:#6b7280'>{user['leverage']} | RR {user['risk_reward']}</div><div style='font-size:11px;color:#9ca3af;margin-top:6px'>1% Risk = {curr_sym}{round(user['account_size']*0.01,2)}</div><a href='/settings' class='btn-outline' style='display:block;margin-top:10px;font-size:12px;text-align:center'>Edit</a></div>
      <div class='card' style='position:relative'><div style='color:#9ca3af;font-size:11px'>WATCHLIST (5 MAX) - SEARCH & ADD</div><div style='margin-top:10px'>{chips or 'No symbols'}</div><form id='symForm' method='POST' action='/quick-symbols'><input type='hidden' name='symbols' id='symInput' value="{user['symbols']}"></form><input id='symSearch' class='searchbox' placeholder='🔍 Search 60 symbols e.g. ZAR, OIL, BTC...' oninput='filterSyms()' onblur='hideDD()' onfocus='filterSyms()' autocomplete='off'><div id='symDropdown' class='dropdown'></div><div style='margin-top:10px'><div style='font-size:11px;color:#6b7280'>Quick Add:</div>{popular_btns}</div></div>
      <div class='card'><div style='color:#9ca3af;font-size:11px'>ACTIONS & TELEGRAM</div><div style='margin-top:10px;display:grid;gap:8px'><a class='btn' href='/scan'>🔍 SCAN MARKET</a><a class='btn-outline' href='/cron/update-trades'>🔄 Force Update</a><a class='btn-outline' href='https://t.me/{TELEGRAM_BOT_USERNAME}?start={session['email']}' target='_blank' style='border-color:#10b981;color:#10b981'>📲 {tg_status}</a></div></div>
    </div>
    <div class='card'><h3 style='margin:0 0 12px 0;color:#10b981'>Journal - Auto Tracked</h3><table><tr><th>Time</th><th>Symbol</th><th>Dir</th><th>Entry/SL/TP</th><th>Status</th><th>PNL</th></tr>{''.join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}<br><span style='font-size:10px;color:#6b7280'>{(t['closed_at'].strftime('%H:%M')+' closed') if t['closed_at'] else (t['hit_entry_at'].strftime('%H:%M')+' active') if t['hit_entry_at'] else 'waiting'}</span></td><td><b>{t['symbol']}</b></td><td><span class='badge { 'bull' if t['direction']=='BUY' else 'bear'}'>{t['direction']}</span></td><td style='font-size:11px'>{round(t['entry'],4)}<br>SL {round(t['sl'],4)}<br>TP {round(t['tp'],4)}</td><td><span class='badge { 'win' if t['status']=='win' else 'loss' if t['status']=='loss' else 'bull' if t['status']=='took' else ''}'>{t['status'].upper()}</span>{'<br><span style=font-size:10px>🤖</span>' if t['auto_updated'] else ''}</td><td style='font-weight:800;color:{'#10b981' if t['pnl']>0 else '#ef4444' if t['pnl']<0 else '#9ca3af'}'>{curr_sym}{round(t['pnl'],2)}</td></tr>" for t in trades]) or '<tr><td colspan=6 style=text-align:center;color:#6b7280>No trades</td></tr>'}</table></div>
    """
    return layout(content, session['email'])

@app.route('/quick-symbols', methods=['POST'])
def quick_symbols():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("UPDATE agent35_users SET symbols=%s WHERE email=%s",(request.form['symbols'][:100], session['email'])); conn.commit(); cur.close(); conn.close(); return redirect('/dashboard')

@app.route('/scan')
def scan():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT symbols FROM agent35_users WHERE email=%s",(session['email'],)); row=cur.fetchone()
    symbols = (row['symbols'] if row else "EURUSD").split(",")[:5]; results=[]; summary=[]
    for sym in symbols:
        sym=sym.strip().upper()
        if not sym: continue
        try: res = engine.full_multi_tf_analysis(sym)
        except Exception as e: res={"signal":False,"symbol":sym,"reason":str(e)}
        res['symbol']=sym; results.append(res)
        if res.get('signal'):
            cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,timeframe_bias,confluence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(session['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['bias'],res['confluence']))
            summary.append(f"{sym}:{res['direction']}")
        else: summary.append(f"{sym}:No")
    cur.execute("UPDATE agent35_users SET last_scan_at=NOW(), last_scan_summary=%s WHERE email=%s",(", ".join(summary)[:200], session['email'])); conn.commit(); cur.close(); conn.close()
    html=""
    for r in results:
        if r.get('signal'): html+= f"<div class='card' style='border-left:4px solid #10b981;margin:10px 0'><b>{r['symbol']} {r['direction']} Score {r['score']}/8</b><br>Entry {r['entry']} SL {r['sl']} TP {r['tp']}<br><span style='font-size:12px'>{r['confluence']}</span></div>"
        else: html+= f"<div class='card' style='opacity:0.6;margin:10px 0'><b>{r['symbol']} - No Setup</b></div>"
    return layout(f"<h2>Scan {datetime.now().strftime('%H:%M:%S')}</h2>{html}<br><a class='btn' href='/dashboard'>Back</a>", session['email'])

@app.route('/cron/update-trades')
def cron_update():
    try:
        conn=get_conn(); cur=conn.cursor()
        cur.execute("SELECT t.*, u.account_size, u.risk_reward FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.status IN ('sent','took') LIMIT 20")
        for tr in cur.fetchall():
            live = get_live_price(tr['symbol'])
            if not live: continue
            close, high, low = live; entry, sl, tp = tr['entry'], tr['sl'], tr['tp']
            rr_val=3
            try: rr_val=int(tr['risk_reward'].split(':')[1])
            except: pass
            risk_amt = tr['account_size']*0.01; new_status=None; pnl=0
            if tr['status']=='sent' and low <= entry <= high: new_status='took'
            elif tr['status'] in ('took','active'):
                if tr['direction']=='BUY':
                    if low <= sl: new_status='loss'; pnl=-risk_amt
                    elif high >= tp: new_status='win'; pnl=risk_amt*rr_val
                else:
                    if high >= sl: new_status='loss'; pnl=-risk_amt
                    elif low <= tp: new_status='win'; pnl=risk_amt*rr_val
            if new_status and new_status!=tr['status']:
                if new_status in ('win','loss'): cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), result_price=%s, auto_updated=TRUE WHERE id=%s", (new_status,pnl,close,tr['id']))
                else: cur.execute("UPDATE agent35_trades SET status=%s, hit_entry_at=NOW() WHERE id=%s", (new_status,tr['id']))
        conn.commit(); cur.close(); conn.close()
    except Exception as e: return jsonify({"error":str(e)})
    return redirect('/dashboard')

@app.route('/settings', methods=['GET','POST'])
def settings():
    if 'email' not in session: return redirect('/')
    if request.method=='POST':
        curr = request.form['currency']
        conn=get_conn(); cur=conn.cursor(); cur.execute("UPDATE agent35_users SET symbols=%s, sessions=%s, risk_reward=%s, account_size=%s, lot_size=%s, currency=%s, currency_symbol=%s, telegram_username=%s WHERE email=%s",(request.form['symbols'][:100], request.form['sessions'], request.form['rr'], float(request.form['acc']), float(request.form['lot']), curr, CUR.get(curr,'$'), request.form['tg'], session['email'])); conn.commit(); cur.close(); conn.close(); return redirect('/dashboard')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); u=cur.fetchone(); cur.close(); conn.close()
    opts = "".join([f"<option value='{k}' {'selected' if u['currency']==k else ''}>{k} ({v})</option>" for k,v in CUR.items()])
    all_opts = "".join([f"<option value='{s}'>" for s in sorted(MAP.keys())])
    return layout(f"<div class='card' style='max-width:650px'><h3>Settings - 60 Symbols Available</h3><form method='POST'><label>Currency</label><select name='currency'>{opts}</select><label>Symbols (searchable)</label><input list='allSymbols' name='symbols' value=\"{u['symbols']}\" placeholder='Type to search 60 symbols'><datalist id='allSymbols'>{all_opts}</datalist><div style='font-size:11px;color:#6b7280;margin-bottom:8px'>Available: {', '.join(sorted(MAP.keys())[:20])} + {len(MAP)-20} more</div><label>Sessions</label><input name='sessions' value=\"{u['sessions']}\"><label>RR</label><select name='rr'><option {'selected' if u['risk_reward']=='1:2' else ''}>1:2</option><option {'selected' if u['risk_reward']=='1:3' else ''}>1:3</option><option {'selected' if u['risk_reward']=='1:4' else ''}>1:4</option></select><label>Account Size</label><input name='acc' type='number' value=\"{u['account_size']}\"><label>Lot Size</label><input name='lot' type='number' step='0.01' value=\"{u['lot_size']}\"><label>Telegram @</label><input name='tg' value=\"{u['telegram_username'] or ''}\"><button class='btn' style='width:100%;margin-top:12px'>Save</button></form></div>", session['email'])

@app.route('/master')
def master():
    if not session.get('is_creator'): return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users ORDER BY created_at DESC"); users=cur.fetchall(); cur.execute("SELECT * FROM agent35_payments ORDER BY created_at DESC"); pays=cur.fetchall()
    pnl_map={}
    for u in users:
        cur.execute("SELECT COALESCE(SUM(pnl),0) as s, COUNT(*) as c FROM agent35_trades WHERE user_email=%s", (u['email'],)); r=cur.fetchone(); pnl_map[u['email']] = (r['s'], r['c'])
    cur.close(); conn.close()
    users_html="".join([f"<tr><td>{u['email']}<br><span style='font-size:10px;color:#6b7280'>@{u['telegram_username'] or 'no TG'}</span></td><td>{u['plan']}<br>{u['payment_status']}</td><td style='font-weight:800;color:{'#10b981' if pnl_map.get(u['email'],(0,0))[0]>=0 else '#ef4444'}'>{CUR.get(u['currency'],'$')}{round(pnl_map.get(u['email'],(0,0))[0],2)}<br><span style='font-size:10px'>{pnl_map.get(u['email'],(0,0))[1]} trades</span></td><td>{u['created_at'].strftime('%Y-%m-%d')}<br><span style='font-size:10px'>Joined</span></td><td>{u['paid_at'].strftime('%Y-%m-%d %H:%M') if u['paid_at'] else 'Not paid'}<br><span style='font-size:10px'>{u['payment_ref'] or ''}</span></td><td>{u['last_scan_at'].strftime('%m-%d %H:%M') if u['last_scan_at'] else 'Never'}</td></tr>" for u in users])
    pays_html="".join([f"<div class='card' style='margin:8px 0;display:flex;justify-content:space-between'><span>{p['user_email']} - R{p['amount']} - {p['plan']} - {p['ref_code']}</span><a class='btn' href='/approve/{p['id']}'>Approve</a></div>" for p in pays])
    return layout(f"<h1 style='color:#10b981'>MASTER - 60 SYMBOLS + PNL</h1><div class='grid4'><div class='card'>Users: {len(users)}</div><div class='card'>Total PNL: ${round(sum([v[0] for v in pnl_map.values()]),2)}</div><div class='card'>Symbols: {len(MAP)} available</div><div class='card'><a class='btn' href='/cron/update-trades'>Update All</a></div></div><div class='card'><h3>Payments</h3>{pays_html or 'None'}</div><div class='card' style='margin-top:14px;overflow:auto'><table><tr><th>User</th><th>Plan</th><th>PNL</th><th>Joined</th><th>Paid</th><th>Scan</th></tr>{users_html}</table></div>", session['email'])

@app.route('/payment')
def payment_page():
    ref = f"AG35-{datetime.now().strftime('%m%d')}-{os.urandom(2).hex().upper()}"
    return layout(f"<div class='card' style='max-width:480px;margin:auto;text-align:center;padding:32px'><h2 style='color:#10b981'>Upgrade</h2><p>Capitec: <b>{CAPITEC_ACC}</b></p><p>Ref: <b style='color:#10b981'>{ref}</b></p><a class='btn' style='width:100%;margin:8px 0' href='/submit-payment?ref={ref}&plan=yearly'>I Paid R500 - {ref}</a><a class='btn' style='width:100%;background:#fff;color:#000' href='/submit-payment?ref={ref}&plan=lifetime'>I Paid R5000 - {ref}</a></div>", session.get('email',''))

@app.route('/submit-payment')
def submit_payment():
    if 'email' not in session: return redirect('/')
    ref=request.args.get('ref'); plan=request.args.get('plan'); amount = 500 if plan=='yearly' else 5000
    conn=get_conn(); cur=conn.cursor(); cur.execute("INSERT INTO agent35_payments (user_email,plan,ref_code,amount) VALUES (%s,%s,%s,%s)", (session['email'],plan,ref,amount)); cur.execute("UPDATE agent35_users SET payment_ref=%s, plan=%s, payment_status='pending' WHERE email=%s", (ref,plan,session['email'])); conn.commit(); cur.close(); conn.close()
    return layout(f"<div class='card' style='text-align:center'><h2>Submitted {ref}</h2><a class='btn' href='/dashboard'>Back</a></div>", session['email'])

@app.route('/approve/<int:pid>')
def approve(pid):
    if not session.get('is_creator'): return "Not allowed"
    conn=get_conn(); cur=conn.cursor(); cur.execute("UPDATE agent35_payments SET status='approved' WHERE id=%s RETURNING user_email,plan", (pid,)); row=cur.fetchone()
    if row: cur.execute("UPDATE agent35_users SET payment_status='approved', plan=%s, paid_at=NOW() WHERE email=%s", (row['plan'], row['user_email']))
    conn.commit(); cur.close(); conn.close(); return redirect('/master')

@app.route('/telegram/webhook', methods=['POST'])
def tg_webhook():
    data = request.json
    try:
        if 'message' in data:
            chat_id = data['message']['chat']['id']; username = data['message']['chat'].get('username',''); text = data['message'].get('text','')
            email = text.split('/start ')[-1].strip() if '/start' in text else None
            if email and '@' in email:
                conn=get_conn(); cur=conn.cursor(); cur.execute("UPDATE agent35_users SET telegram_id=%s, telegram_username=%s WHERE email=%s", (str(chat_id), username, email.lower())); conn.commit(); cur.close(); conn.close()
                if TELEGRAM_TOKEN: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id":chat_id,"text":f"✅ Agent 35 V4.2 linked! 60 symbols ready."})
    except Exception as e: print(e)
    return jsonify({"ok":True})

@app.route('/healthz')
def health(): return jsonify({"status":"ok","bot":"Agent35 V4.2 60 Symbols"})

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

if __name__ == '__main__': app.run(host='0.0.0.0', port=int(os.environ.get('PORT',10000)))
