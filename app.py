psql $DATABASE_URL -c "UPDATE agent35_trades SET status='skipped', be_done=TRUE, lock_done=TRUE WHERE status IN ('sent','took','active');"
import os, hashlib, requests, psycopg, threading, time
from psycopg.rows import dict_row
from flask import Flask, request, redirect, session, jsonify
from datetime import datetime
from zoneinfo import ZoneInfo
import trading_engine as engine
import traceback

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'agent35-secret-2025')
DATABASE_URL = os.environ.get('DATABASE_URL','').strip()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
TELEGRAM_BOT_USERNAME = "Sniper035_bot"
RISK_PCT = float(os.environ.get('RISK_PCT','1.5'))
CUR = {'USD':'$','ZAR':'R','EUR':'€','GBP':'£'}
MAP = engine.MAP

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
*{box-sizing:border-box} body{background:#060a14;color:#e5e7eb;font-family:'Inter',sans-serif;margin:0}.header{background:#0b111c;border-bottom:1px solid #1a2535;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}.logo{display:flex;align-items:center;gap:10px;color:#10b981;font-weight:800}.card{background:#0e1625;border:1px solid #1c2a41;border-radius:16px;padding:16px}.btn{background:linear-gradient(135deg,#10b981,#059669);color:#000;font-weight:800;padding:12px 18px;border:none;border-radius:12px;cursor:pointer;text-decoration:none;display:block;text-align:center;width:100%}.btn-outline{background:transparent;border:1px solid #24344e;color:#cbd5e1;padding:12px 18px;border-radius:12px;text-decoration:none;display:block;text-align:center;width:100%;margin-top:8px}.btn-test{background:#3b82f6;color:#fff;font-weight:700;padding:10px;border:none;border-radius:10px;width:100%;margin-top:8px;display:block;text-align:center;text-decoration:none}.grid{display:grid;gap:14px}.grid4{grid-template-columns:repeat(4,1fr)}.badge{padding:5px 10px;border-radius:20px;font-size:11px;font-weight:800}.bull{background:rgba(16,185,129,0.15);color:#10b981}.bear{background:rgba(239,68,68,0.15);color:#ef4444}.win{background:rgba(16,185,129,0.25);color:#10b981}.loss{background:rgba(239,68,68,0.25);color:#ef4444}.chip{display:inline-flex;align-items:center;gap:6px;background:#121d30;border:1px solid #1e2d45;padding:7px 12px;border-radius:24px;margin:4px;font-size:13px}.chip-active{background:#10b98122;border-color:#10b981}.x{background:#ef4444;color:#fff;border-radius:50%;width:20px;height:20px;display:inline-flex;justify-content:center;align-items:center;font-size:12px;margin-left:6px}.searchbox{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:12px;width:100%;margin:8px 0}.dropdown{background:#121d30;border:1px solid #1e2d45;border-radius:12px;max-height:200px;overflow:auto;display:none;position:absolute;z-index:50;width:calc(100% - 32px)}.dropdown div{padding:10px 14px;cursor:pointer;border-bottom:1px solid #1a2535} table{width:100%;border-collapse:collapse} th{color:#64748b;text-align:left;padding:12px 8px;font-size:10px;text-transform:uppercase} td{padding:12px 8px;border-top:1px solid #1a2535;font-size:13px}.nav-tabs{display:flex;gap:8px;overflow:auto;margin:12px 0}.nav-tabs a{white-space:nowrap;padding:10px 16px;border-radius:24px;background:#121d30;border:1px solid #1e2d45;color:#94a3b8;text-decoration:none;font-size:13px;font-weight:600}.nav-tabs a.active{background:#10b981;color:#000;border-color:#10b981}.stat-label{font-size:11px;color:#64748b;text-transform:uppercase}.stat-value{font-size:22px;font-weight:800;margin-top:6px} @media(max-width:900px){.grid4{grid-template-columns:1fr 1fr}} @media(max-width:600px){.grid4{grid-template-columns:1fr}table{display:block;overflow-x:auto}} input,select{background:#070d1a;border:1px solid #1e2d45;color:#fff;padding:12px;border-radius:10px;width:100%;margin:6px 0} label{font-size:12px;color:#94a3b8;margin-top:12px;display:block;font-weight:600}.clock-bar{display:flex;gap:10px;align-items:center;background:#121d30;border:1px solid #1e2d45;padding:6px 12px;border-radius:20px;font-size:11px;margin-left:12px}.live-dot{width:8px;height:8px;background:#10b981;border-radius:50%;display:inline-block;animation:blink 1s infinite}@keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}
</style>
<script>
const ALL_SYMBOLS=["EURUSD","GBPUSD","USDJPY","EURJPY","GBPJPY","USDZAR","EURZAR","GBPZAR","ZARJPY","XAUUSD","GOLD","BTCUSD","ETHUSD","SOLUSD","NAS100","US30","SPX500"];
function addSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!='');if(arr.length>=5){alert('Max 5');return}if(!arr.includes(s)){arr.push(s);i.value=arr.join(',');document.getElementById('symForm').submit();}}
function removeSym(s){let i=document.getElementById('symInput');let arr=i.value.split(',').filter(x=>x.trim()!=s.trim()&&x.trim()!='');i.value=arr.join(',');document.getElementById('symForm').submit();}
function filterSyms(){let q=document.getElementById('symSearch').value.toUpperCase();let dd=document.getElementById('symDropdown');if(!q){dd.style.display='none';return}let f=ALL_SYMBOLS.filter(s=>s.includes(q)).slice(0,10);dd.innerHTML=f.map(s=>'<div onclick="addSym(\\''+s+'\\')"><b>'+s+'</b></div>').join('');dd.style.display=f.length?'block':'none';}
</script>
"""

def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode='require', connect_timeout=20)

def init_db():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_users (id SERIAL PRIMARY KEY, email TEXT UNIQUE, password TEXT,is_creator BOOLEAN DEFAULT FALSE, plan TEXT DEFAULT 'none',payment_ref TEXT, payment_status TEXT DEFAULT 'pending',risk_reward TEXT DEFAULT '1:3', symbols TEXT DEFAULT 'EURUSD,XAUUSD,BTCUSD,GBPUSD,NAS100',sessions TEXT DEFAULT 'London,New York', account_size FLOAT DEFAULT 10000,lot_size FLOAT DEFAULT 0.1, leverage TEXT DEFAULT '1:500',telegram_id TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    cur.execute("""CREATE TABLE IF NOT EXISTS agent35_trades (id SERIAL PRIMARY KEY, user_email TEXT, symbol TEXT,direction TEXT, entry FLOAT, sl FLOAT, tp FLOAT,status TEXT DEFAULT 'sent', pnl FLOAT DEFAULT 0,timeframe_bias TEXT, confluence TEXT, created_at TIMESTAMP DEFAULT NOW());""")
    for q in ["ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USD'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS telegram_username TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS currency_symbol TEXT DEFAULT '$'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS sessions TEXT DEFAULT 'London,New York'","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS referral_code TEXT","ALTER TABLE agent35_users ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'Africa/Johannesburg'","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS be_done BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS lock_done BOOLEAN DEFAULT FALSE","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS close_r FLOAT DEFAULT 0","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS original_sl FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS original_entry FLOAT","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP","ALTER TABLE agent35_trades ADD COLUMN IF NOT EXISTS result_price FLOAT"]:
        try: cur.execute(q)
        except: pass
    conn.commit(); cur.close(); conn.close()
init_db()

def send_telegram(chat_id, text, trade_id=None, stage="signal", extra_buttons=None):
    if not TELEGRAM_TOKEN or not chat_id: return False
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode":"Markdown"}
        if trade_id:
            if stage=="signal":
                payload["reply_markup"] = {"inline_keyboard": [[{"text":"✅ TOOK ENTRY","callback_data":f"took:{trade_id}"},{"text":"❌ SKIP","callback_data":f"skip:{trade_id}"}]]}
            elif stage=="active":
                payload["reply_markup"] = {"inline_keyboard": [[{"text":"✅ WIN","callback_data":f"win:{trade_id}"},{"text":"❌ LOSS","callback_data":f"loss:{trade_id}"},{"text":"➖ BE","callback_data":f"be:{trade_id}"}],[{"text":"💰 CLOSE EARLY","callback_data":f"closeearly:{trade_id}"}]]}
            elif stage=="profitlock":
                payload["reply_markup"] = {"inline_keyboard": extra_buttons}
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload, timeout=10)
        return r.status_code==200
    except: return False

def build_signal_msg(res, user=None):
    sym=res['symbol']; direction=res['direction']; entry=res['entry']; sl=res['sl']; tp=res['tp']; score=res['score']; confluence=res.get('confluence',[]); quality=res.get('quality','')
    rr_val= (tp-entry)/(entry-sl) if direction=="BUY" and (entry-sl)!=0 else (entry-tp)/(sl-entry) if (sl-entry)!=0 else 0
    conf_text="\n".join([f"• {c}" for c in confluence[:6]])
    emoji="🟢" if direction=="BUY" else "🔴"
    return f"""{emoji} {sym} {direction} | {quality} {score}/8
💰 Entry: {entry}
🛑 SL: {sl}
🎯 TP: {tp}
📊 RR 1:{rr_val:.1f}

{conf_text}
"""

def layout(content, email="", active="dashboard"):
    is_creator="creator" in email.lower()
    ad="active" if active=="dashboard" else ""; aj="active" if active=="journal" else ""; asi="active" if active=="signals" else ""
    tabs=f'<div class="nav-tabs"><a href="/dashboard" class="{ad}">Dashboard</a><a href="/journal" class="{aj}">Journal (Taken Only)</a><a href="/signals" class="{asi}">All Signals</a><a href="/settings">Settings</a></div>'
    return f'<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>V8.5</title>{STYLE}</head><body><div class="header"><div class="logo">AGENT 35 V8.5 <div class="clock-bar"><span class="live-dot"></span>TOOK ONLY</div></div><div>{email} <a href="/logout" style="color:#94a3b8;margin-left:10px">Logout</a></div></div><div style="padding:14px;max-width:1400px;margin:auto">{tabs}{content}</div></body></html>'

def get_live_price(symbol):
    try:
        import yfinance as yf
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

# NO BACKGROUND THREAD IN V8.5 - ONLY CRON RUNS

@app.route('/')
def home():
    return f'<html><head><meta name="viewport" content="width=device-width, initial-scale=1">{STYLE}</head><body style="display:flex;justify-content:center;align-items:center;min-height:100vh"><div class="card" style="max-width:380px;width:100%;text-align:center"><h1 style="color:#10b981">V8.5 NO-SPAM</h1><form method="POST" action="/auth"><input name="email" placeholder="email" required><input name="password" type="password" required><button class="btn" style="margin-top:12px">Login</button></form></div></body></html>'

@app.route('/auth', methods=['POST'])
def auth():
    email=request.form['email'].lower().strip(); pw=hashlib.sha256(request.form['password'].encode()).hexdigest()
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT * FROM agent35_users WHERE email=%s AND password=%s", (email, pw)); u=cur.fetchone()
    if not u:
        my_code=f"AG35-{email[:3].upper()}-{os.urandom(2).hex().upper()}"
        cur.execute("INSERT INTO agent35_users (email,password,symbols,referral_code) VALUES (%s,%s,'EURUSD,XAUUSD',%s) RETURNING *", (email,pw,my_code)); u=cur.fetchone(); conn.commit()
    cur.close(); conn.close(); session['email']=u['email']; session['is_creator']=u['is_creator']
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s", (session['email'],)); user=cur.fetchone()
    cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND status IN ('took','win','loss','be','win_early') ORDER BY created_at DESC LIMIT 8", (session['email'],)); trades=cur.fetchall()
    cur.execute("SELECT COALESCE(SUM(pnl),0) as pnl, COUNT(*) FILTER (WHERE status='win') as wins, COUNT(*) FILTER (WHERE status='loss') as losses FROM agent35_trades WHERE user_email=%s AND status IN ('took','win','loss','be','win_early')", (session['email'],)); stats=cur.fetchone()
    cur.close(); conn.close()
    syms=[s for s in (user['symbols'] or '').split(',') if s.strip()]; chips="".join([f"<span class='chip chip-active'><b>{s}</b><span class='x' onclick=\"removeSym('{s}')\">x</span></span>" for s in syms])
    rows="".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td>{t['symbol']}</td><td>{t['status'].upper()}</td><td>{round(t['pnl'] or 0,2)}</td></tr>" for t in trades]) or "<tr><td>No taken trades</td></tr>"
    pay_ref=user['payment_ref'] or session['email']
    content=f"<div class='card'><b>PNL Taken Only:</b> {round(stats['pnl'],2)} | V8.5 No-Spam Mode</div><div class='grid grid4' style='margin-top:12px'><div class='card'><div>Watchlist {len(syms)}/5</div>{chips}<form id='symForm' method='POST' action='/quick-symbols'><input type='hidden' name='symbols' id='symInput' value=\"{user['symbols']}\"></form><input id='symSearch' class='searchbox' placeholder='Search EURUSD...' oninput='filterSyms()'><div id='symDropdown' class='dropdown'></div></div><div class='card'><a class='btn' href='/scan'>SCAN</a><a href='https://t.me/{TELEGRAM_BOT_USERNAME}?start={pay_ref}' target='_blank' class='btn-outline'>Link TG</a></div></div><div class='card' style='margin-top:12px'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>PNL</th></tr>{rows}</table></div>"
    return layout(content, session['email'], "dashboard")

@app.route('/journal')
def journal():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s AND status IN ('took','win','loss','be','win_early') ORDER BY created_at DESC LIMIT 100", (session['email'],)); trades=cur.fetchall()
    cur.close(); conn.close()
    rows="".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td>{t['symbol']} {t['direction']}</td><td>{t.get('original_entry', t['entry'])} / {t.get('original_sl', t['sl'])} / {t['tp']}</td><td>{t['status'].upper()}</td><td>{round(t['pnl'] or 0,2)} ({t.get('close_r',0)}R)</td><td><a href='/manual-close?id={t['id']}' style='color:#10b981'>Close</a></td></tr>" for t in trades]) or "<tr><td>No taken</td></tr>"
    return layout(f"<div class='card'><h3>Journal - TAKEN ONLY (No Spam)</h3><table><tr><th>Date</th><th>Pair</th><th>Entry/SL/TP</th><th>Status</th><th>PNL</th><th>Action</th></tr>{rows}</table><br><a class='btn' href='/signals'>All Signals Sheet</a></div>", session['email'], "journal")

@app.route('/signals')
def signals():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_trades WHERE user_email=%s ORDER BY created_at DESC LIMIT 200", (session['email'],)); trades=cur.fetchall()
    cur.close(); conn.close()
    rows="".join([f"<tr><td>{t['created_at'].strftime('%m-%d %H:%M')}</td><td>{t['symbol']}</td><td>{t.get('original_entry', t['entry'])} / {t.get('original_sl', t['sl'])} / {t['tp']}</td><td>{t['status'].upper()}</td><td>{round(t['pnl'] or 0,2)}</td></tr>" for t in trades]) or "<tr><td>No signals</td></tr>"
    return layout(f"<div class='card'><h3>All Signals - No Telegram for these unless TOOK</h3><table><tr><th>Date</th><th>Pair</th><th>Entry/SL/TP</th><th>Status</th><th>PNL</th></tr>{rows}</table></div>", session['email'], "signals")

@app.route('/quick-symbols', methods=['POST'])
def quick_symbols():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("UPDATE agent35_users SET symbols=%s WHERE email=%s",(request.form['symbols'][:100], session['email'])); conn.commit(); cur.close(); conn.close(); return redirect('/dashboard')

@app.route('/scan')
def scan():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); user=cur.fetchone()
    symbols=(user['symbols'] or "EURUSD").split(",")[:5]
    for sym in symbols:
        sym=sym.strip().upper()
        if not sym: continue
        try: res=engine.full_multi_tf_analysis(sym)
        except: continue
        if res.get('signal') and res.get('score',0) >= 4:
            cur.execute("SELECT id FROM agent35_trades WHERE user_email=%s AND symbol=%s AND status IN ('sent','took') AND created_at > NOW() - INTERVAL '24 hours' LIMIT 1", (session['email'], sym))
            if cur.fetchone(): continue
            cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,original_entry,original_sl,status,be_done,lock_done) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'sent',FALSE,FALSE) RETURNING id",(session['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['entry'],res['sl']))
            row=cur.fetchone()
            if row and user['telegram_id']:
                msg=build_signal_msg(res, user)
                send_telegram(user['telegram_id'], msg, trade_id=row['id'], stage="signal")
    conn.commit(); cur.close(); conn.close()
    return redirect('/journal')

@app.route('/manual-close')
def manual_close():
    if 'email' not in session: return redirect('/')
    tid = request.args.get('id')
    conn=get_conn(); cur=conn.cursor()
    cur.execute("SELECT t.*, u.account_size FROM agent35_trades t JOIN agent35_users u ON u.email=t.user_email WHERE t.id=%s AND t.user_email=%s", (tid, session['email'])); tr=cur.fetchone()
    if tr:
        live = get_live_price(tr['symbol']); close = live[0] if live else tr['entry']
        r_now = calc_r_now(tr, close); pnl = tr['account_size'] * 0.01 * r_now
        cur.execute("UPDATE agent35_trades SET status='win_early', pnl=%s, closed_at=NOW(), be_done=TRUE, lock_done=TRUE, close_r=%s WHERE id=%s", (pnl, r_now, tid)); conn.commit()
    cur.close(); conn.close()
    return redirect('/journal')

@app.route('/telegram/webhook', methods=['POST'])
def tg_webhook():
    data=request.json
    try:
        conn=get_conn(); cur=conn.cursor()
        if 'callback_query' in data:
            cq=data['callback_query']; chat_id=cq['message']['chat']['id']; cdata=cq['data']
            action, tid_str = cdata.split(':'); tid=int(tid_str)
            cur.execute("SELECT * FROM agent35_trades WHERE id=%s", (tid,)); tr=cur.fetchone()
            if tr:
                if action=='took':
                    cur.execute("UPDATE agent35_trades SET status='took' WHERE id=%s", (tid,)); conn.commit()
                    send_telegram(chat_id, f"📝 {tr['symbol']} TOOK - Will alert BE/WIN/LOSS only once", trade_id=tid, stage="active")
                elif action=='skip':
                    cur.execute("UPDATE agent35_trades SET status='skipped', be_done=TRUE, lock_done=TRUE WHERE id=%s", (tid,)); conn.commit()
                    send_telegram(chat_id, f"Skipped {tr['symbol']} - No more alerts")
                elif action in ('win','loss','be'):
                    cur.execute("UPDATE agent35_trades SET status=%s, be_done=TRUE, lock_done=TRUE, closed_at=NOW() WHERE id=%s", (action, tid)); conn.commit()
                    send_telegram(chat_id, f"{action.upper()} {tr['symbol']} saved")
                elif action=='closeearly':
                    cur.execute("UPDATE agent35_trades SET status='win_early', be_done=TRUE, lock_done=TRUE, closed_at=NOW() WHERE id=%s", (tid,)); conn.commit()
                    send_telegram(chat_id, f"Closed early {tr['symbol']}")
            try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={"callback_query_id":cq['id'],"text":"Saved"}, timeout=5)
            except: pass
            cur.close(); conn.close(); return jsonify({"ok":True})
        if 'message' in data:
            chat_id=data['message']['chat']['id']; username=data['message']['chat'].get('username',''); text=data['message'].get('text','').strip()
            ref=text.split('/start')[-1].strip() if '/start' in text else ""
            if ref:
                cur.execute("SELECT email FROM agent35_users WHERE payment_ref=%s OR email=%s", (ref, ref.lower())); row=cur.fetchone()
                if row:
                    cur.execute("UPDATE agent35_users SET telegram_id=%s, telegram_username=%s WHERE email=%s", (str(chat_id), username, row['email'])); conn.commit()
                    send_telegram(chat_id, "Linked V8.5 - TOOK ONLY mode active")
            cur.close(); conn.close()
    except Exception as e: print(f"tg err {e}")
    return jsonify({"ok":True})

@app.route('/cron/update-trades')
def cron_update():
    def do_update():
        try:
            conn=get_conn(); cur=conn.cursor()
            cur.execute("""
                SELECT t.*, u.account_size, u.risk_reward, u.telegram_id, u.currency_symbol
                FROM agent35_trades t
                JOIN agent35_users u ON u.email=t.user_email
                WHERE t.status = 'took'
                AND t.created_at > NOW() - INTERVAL '12 hours'
                LIMIT 10
            """)
            for tr in cur.fetchall():
                live=get_live_price(tr['symbol'])
                if not live: continue
                close,high,low=live
                r_now = calc_r_now(tr, close)
                if r_now >= 1.0 and not tr.get('be_done'):
                    cur.execute("UPDATE agent35_trades SET be_done=TRUE, sl=%s WHERE id=%s", (tr['entry'], tr['id'])); conn.commit()
                    if tr['telegram_id']:
                        send_telegram(tr['telegram_id'], f"🔒 {tr['symbol']} +1R -> BE")
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
                    cur.execute("UPDATE agent35_trades SET status=%s, pnl=%s, closed_at=NOW(), be_done=TRUE, lock_done=TRUE, close_r=%s WHERE id=%s",(new,pnl,close_r,tr['id'])); conn.commit()
                    if tr['telegram_id']:
                        if new=='win': send_telegram(tr['telegram_id'], f"✅ {tr['symbol']} WIN +{rr}R")
                        elif new=='be': send_telegram(tr['telegram_id'], f"➖ {tr['symbol']} BE")
                        else: send_telegram(tr['telegram_id'], f"❌ {tr['symbol']} LOSS -1R")
            cur.close(); conn.close()
        except Exception as e:
            print(f"V8.5 update err {e} {traceback.format_exc()}")
    threading.Thread(target=do_update, daemon=True).start()
    return jsonify({"ok":True, "mode":"V8.5 TOOK ONLY"})

@app.route('/cron/scan-all')
def cron_scan_all():
    def do_scan():
        try:
            conn=get_conn(); cur=conn.cursor()
            cur.execute("SELECT * FROM agent35_users WHERE payment_status='approved' AND symbols IS NOT NULL LIMIT 30")
            for user in cur.fetchall():
                symbols=(user['symbols'] or "").split(",")[:5]
                for sym in symbols:
                    sym=sym.strip().upper()
                    if not sym: continue
                    cur.execute("SELECT id FROM agent35_trades WHERE user_email=%s AND symbol=%s AND status IN ('sent','took') AND created_at > NOW() - INTERVAL '24 hours' LIMIT 1", (user['email'], sym))
                    if cur.fetchone(): continue
                    try: res=engine.full_multi_tf_analysis(sym)
                    except: continue
                    if res.get('signal') and res.get('score',0) >= 4:
                        cur.execute("INSERT INTO agent35_trades (user_email,symbol,direction,entry,sl,tp,original_entry,original_sl,status,be_done,lock_done) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'sent',FALSE,FALSE) RETURNING id",(user['email'],res['symbol'],res['direction'],res['entry'],res['sl'],res['tp'],res['entry'],res['sl']))
                        row=cur.fetchone()
                        if row and user['telegram_id']:
                            msg=build_signal_msg(res, user)
                            send_telegram(user['telegram_id'], msg, trade_id=row['id'], stage="signal")
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            print(f"scan err {e}")
    threading.Thread(target=do_scan, daemon=True).start()
    return jsonify({"ok":True})

@app.route('/setup-webhook')
def setup_webhook():
    base=request.host_url.rstrip('/'); wh_url=f"{base}/telegram/webhook"
    r=requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={wh_url}")
    return f"Webhook {wh_url} {r.text}"

@app.route('/settings')
def settings_page():
    if 'email' not in session: return redirect('/')
    conn=get_conn(); cur=conn.cursor(); cur.execute("SELECT * FROM agent35_users WHERE email=%s",(session['email'],)); u=cur.fetchone(); cur.close(); conn.close()
    content=f"<div class='card' style='max-width:500px'><h3>Settings V8.5</h3>Symbols: {u['symbols']}<br>Account: {u['account_size']}<form method='POST' action='/quick-symbols'><input name='symbols' value='{u['symbols']}'><button class='btn' style='margin-top:8px'>Save Symbols</button></form></div>"
    return layout(content, session['email'])

@app.route('/healthz')
def health(): return jsonify({"status":"ok","version":"V8.5-TOOK-ONLY-FIXED"})

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

if __name__ == '__main__': app.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))
