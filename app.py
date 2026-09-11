from flask import Flask, request, jsonify, session, redirect
import os, json, hashlib, requests, random, string
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "agent35-v19-8-1-antispam")
import trading_engine as eng

BASE_DIR = "/data" if os.path.exists("/data") else "."
AUTH_FILE = os.path.join(BASE_DIR, "auth_users.json")
USERS_FILE = os.path.join(BASE_DIR, "users_data.json")
REFERRAL_FILE = os.path.join(BASE_DIR, "referrals.json")
REF_CODE_FILE = os.path.join(BASE_DIR, "ref_codes.json")
JOURNAL_FILE = os.path.join(BASE_DIR, "journal.json")
TRACK_FILE = os.path.join(BASE_DIR, "tracked_trades.json")
SYSTEM_FILE = os.path.join(BASE_DIR, "system_status.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "user_settings.json")
TG_FILE = os.path.join(BASE_DIR, "telegram_users.json")
TEMP_CHAT_FILE = os.path.join(BASE_DIR, "temp_chats.json")

PLANS = {"yearly":{"name":"Yearly","price":500,"days":365},"lifetime":{"name":"Lifetime","price":5000,"days":36500}}
ALL_SYMBOLS = ["EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD","EURJPY","GBPJPY","EURGBP","AUDJPY","CADJPY","CHFJPY","EURCHF","GBPCHF","EURAUD","GBPAUD","EURCAD","GBPCAD","XAUUSD","XAGUSD","US30","NAS100","SPX500","GER40","UK100","FRA40","BTCUSD","ETHUSD","SOLUSD","BNBUSD"]

def load_json(p, dt=dict):
    if not os.path.exists(p): return {} if dt==dict else []
    try:
        with open(p,"r") as f: return json.load(f)
    except: return {} if dt==dict else []

def save_json(p, data):
    with open(p,"w") as f: json.dump(data,f,indent=2)

def hash_pwd(p): return hashlib.sha256(p.encode()).hexdigest()

def ensure_files():
    if not os.path.exists(AUTH_FILE):
        save_json(AUTH_FILE, {"admin@agent35.com":{"email":"admin@agent35.com","name":"Master Creator","password":hash_pwd("Agent35!"),"account_size":142.0,"total_profit":-1.42,"plan_status":"ACTIVE lifetime - CREATOR","referred_by":"","expires":(datetime.now()+timedelta(days=36500)).isoformat(),"created":datetime.now().isoformat(),"reset_token":None,"ref_code":"ADMIN35"}})
    for fp in [USERS_FILE, REFERRAL_FILE, REF_CODE_FILE, SETTINGS_FILE, TG_FILE, TEMP_CHAT_FILE]:
        if not os.path.exists(fp): save_json(fp, {})
    if not os.path.exists(JOURNAL_FILE): save_json(JOURNAL_FILE, [])
    if not os.path.exists(TRACK_FILE): save_json(TRACK_FILE, {})
    if not os.path.exists(SYSTEM_FILE): save_json(SYSTEM_FILE, {"last_scan":None,"total_scans":0,"total_signals":0,"system_up_since":datetime.now().isoformat()})
ensure_files()

def get_user_settings(email):
    settings = load_json(SETTINGS_FILE, dict)
    default = {"account_size":142.0,"lot_size":0.01,"leverage":"1:500","sessions":["London","New York"],"symbols":ALL_SYMBOLS[:10],"risk_percent":1.0,"rr_ratio":2.5,"trade_news":True}
    return settings.get(email, default)

def save_user_settings(email, new_settings):
    s = load_json(SETTINGS_FILE, dict)
    s[email] = new_settings
    save_json(SETTINGS_FILE, s)

def generate_ref_code(email):
    code_file = load_json(REF_CODE_FILE, dict)
    if email in code_file: return code_file[email]
    base = "".join([c for c in email.upper().split('@')[0] if c.isalnum()])[:5]
    if len(base)<3: base="A35"+base
    code = f"{base}{random.randint(10,99)}"
    while code in code_file: code = f"{base}{random.randint(10,99)}"
    code_file[email]=code
    code_file[code]=email
    save_json(REF_CODE_FILE, code_file)
    return code

def get_ref_count_and_auto_upgrade(referrer_email):
    auth = load_json(AUTH_FILE)
    ref_codes = load_json(REF_CODE_FILE, dict)
    referrer_code = ref_codes.get(referrer_email,"")
    if not referrer_code: return 0
    count=0
    for e,info in auth.items():
        if info.get("referred_by","").upper()==referrer_code.upper() and "ACTIVE" in info.get("plan_status",""): count+=1
    if count>=10 and referrer_email in auth and "CREATOR" not in auth[referrer_email].get("plan_status",""):
        if "lifetime" not in auth[referrer_email].get("plan_status","").lower():
            auth[referrer_email]["plan_status"]="ACTIVE lifetime - FREE 10 Referrals"
            auth[referrer_email]["expires"]=(datetime.now()+timedelta(days=36500)).isoformat()
            save_json(AUTH_FILE, auth)
    ref_data=load_json(REFERRAL_FILE, dict)
    ref_data[referrer_email]={"code":referrer_code,"count":count,"paid_count":count,"free_eligible":count>=10,"updated":datetime.now().isoformat()}
    save_json(REFERRAL_FILE, ref_data)
    return count

def calculate_dynamic_sl_tp(symbol, entry, bias, account_size, lot_size, leverage, risk_percent, rr_ratio):
    entry=float(entry)
    is_sell="BEARISH" in bias.upper() or "SELL" in bias.upper()
    risk_amount=float(account_size)*(float(risk_percent)/100.0)
    lot_size=float(lot_size) if float(lot_size)>0 else 0.01
    rr_ratio=float(rr_ratio) if float(rr_ratio)>0 else 2.5
    if symbol in ["XAUUSD","XAGUSD","XAUJPY"]:
        sl_dollar=risk_amount/(lot_size*100) if lot_size>0 else 5.0
        sl_dollar=max(2.0,min(sl_dollar,15.0))
        tp_dollar=sl_dollar*rr_ratio
        sl=entry+sl_dollar if is_sell else entry-sl_dollar
        tp=entry-tp_dollar if is_sell else entry+tp_dollar
        return round(sl,2),round(tp,2),round(sl_dollar,2),round(tp_dollar,2),risk_amount
    elif symbol in ["US30","NAS100","SPX500","GER40","UK100","FRA40"]:
        sl_points=(risk_amount/(lot_size*10)) if lot_size>0 else 80
        sl_points=max(30,min(sl_points,250))
        tp_points=sl_points*rr_ratio
        sl=entry+sl_points if is_sell else entry-sl_points
        tp=entry-tp_points if is_sell else entry+tp_points
        return round(sl,2),round(tp,2),round(sl_points,1),round(tp_points,1),risk_amount
    elif "BTC" in symbol:
        sl_d=max(100,min(risk_amount/(lot_size*10) if lot_size>0 else 400,1200))
        tp_d=sl_d*rr_ratio
        sl=entry+sl_d if is_sell else entry-sl_d
        tp=entry-tp_d if is_sell else entry+tp_d
        return round(sl,2),round(tp,2),round(sl_d,1),round(tp_d,1),risk_amount
    elif "ETH" in symbol or "SOL" in symbol or "BNB" in symbol:
        sl_d=max(5,min(risk_amount/(lot_size*10) if lot_size>0 else 40,150))
        tp_d=sl_d*rr_ratio
        sl=entry+sl_d if is_sell else entry-sl_d
        tp=entry-tp_d if is_sell else entry+tp_d
        return round(sl,2),round(tp,2),round(sl_d,1),round(tp_d,1),risk_amount
    else:
        pip_value=lot_size*10
        if pip_value==0: pip_value=0.1
        sl_pips=risk_amount/pip_value
        sl_pips=max(5,min(sl_pips,50))
        if "JPY" in symbol:
            sl_dist=sl_pips*0.01; tp_dist=sl_dist*rr_ratio
        else:
            sl_dist=sl_pips*0.0001; tp_dist=sl_dist*rr_ratio
        sl=entry+sl_dist if is_sell else entry-sl_dist
        tp=entry-tp_dist if is_sell else entry+tp_dist
        if entry<20: return round(sl,5),round(tp,5),round(sl_pips,1),round(sl_pips*rr_ratio,1),risk_amount
        else: return round(sl,2),round(tp,2),round(sl_pips,1),round(sl_pips*rr_ratio,1),risk_amount

def send_telegram_pro(symbol, score, bias, entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot_size, leverage, account_size, confluence_text):
    entry_f=float(entry)
    if entry_f==0: return {"error":"No price"}
    display_score=min(score,8) if score<=10 else 7
    signal_type="BUY" if "BULLISH" in bias.upper() else "SELL"
    if entry_f<20: entry_fmt=f"{entry_f:.5f}"; sl_fmt=f"{float(sl):.5f}"; tp_fmt=f"{float(tp):.5f}"
    else: entry_fmt=f"{entry_f:.2f}"; sl_fmt=f"{float(sl):.2f}"; tp_fmt=f"{float(tp):.2f}"
    bot=os.getenv("TELEGRAM_BOT_TOKEN"); main_chat=os.getenv("TELEGRAM_CHAT_ID")
    tg_users=load_json(TG_FILE, dict); all_chats=[]
    if main_chat: all_chats.append(str(main_chat))
    for data in tg_users.values():
        cid=str(data.get("chat_id",""))
        if cid and cid not in all_chats: all_chats.append(cid)
    if not bot or not all_chats: return {"error":"no bot/chats"}
    sast_now=(datetime.utcnow()+timedelta(hours=2)).strftime("%H:%M SAST")
    text=f"🔴 {symbol} {signal_type} | STANDARD {display_score}/8\n\n📊 Account R{account_size} Lot {lot_size} Lev {leverage}\n💰 Entry: {entry_fmt}\n🛑 SL: {sl_fmt} ({sl_dist})\n🎯 TP: {tp_fmt} ({tp_dist})\n📊 RR 1:{rr} | Risk R{risk_amt:.2f} ({risk_percent}%)\n\n🔍 Confluence:\n{confluence_text}\n\n📝 V19.8.1 ANTI-SPAM | Score {score}/10\n⏰ {sast_now}"
    keyboard={"inline_keyboard": [[{"text":"✅ TOOK ENTRY","callback_data":f"TOOK_{symbol}_{entry_fmt}"},{"text":"❌ SKIP","callback_data":f"SKIP_{symbol}"}],[{"text":"📊 View Journal","url":"https://agent-35-trading-bot.onrender.com/journal"}]]}
    results=[]
    for chat_id in all_chats:
        try:
            r=requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":text,"reply_markup":keyboard}, timeout=10)
            results.append(r.json())
        except Exception as e: results.append({"error":str(e)})
    return results

def pro_layout(content, active="Dashboard", is_admin=False):
    utc=datetime.utcnow().strftime("%H:%M:%S"); sast=(datetime.utcnow()+timedelta(hours=2)).strftime("%H:%M:%S")
    user=session.get("user","Guest")
    tabs=[("Dashboard","📊"),("Journal","📓"),("All Signals","📡"),("Settings","⚙️"),("Referral","👥"),("Plans","💳"),("Guide","📖")]
    if is_admin: tabs.append(("Master","👑"))
    nav_html=""
    for t,icon in tabs:
        url=f"/{t.lower().replace(' ','-')}"
        if active==t: nav_html+=f"<a href='{url}' style='padding:9px 16px;border-radius:10px;text-decoration:none;color:white;font-weight:700;font-size:13px;background:linear-gradient(135deg,#10b981,#059669);margin-right:6px'>{icon} {t}</a>"
        else: nav_html+=f"<a href='{url}' style='padding:9px 16px;border-radius:10px;text-decoration:none;color:#94a3b8;font-weight:600;font-size:13px;background:#1e293b;margin-right:6px'>{icon} {t}</a>"
    html_start=f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>AGENT 35 PRO V19.8.1</title><style>body{{background:#080c14;color:#e2e8f0;font-family:Arial,sans-serif;margin:0}}.topbar{{background:#0f172a;padding:14px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}}.logo{{font-weight:900;font-size:18px;color:#10b981}}.badge{{background:#10b981;padding:4px 10px;border-radius:20px;font-weight:700;font-size:11px;color:white}}.badge-warn{{background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:4px 10px;border-radius:20px;font-size:11px}}.navbar{{background:#0f172a;border-bottom:1px solid #1e293b;padding:12px 20px;display:flex;gap:8px;overflow-x:auto;position:sticky;top:60px;z-index:90}}.main{{padding:20px;display:grid;grid-template-columns:1fr 1fr 1fr 320px;gap:16px;max-width:1600px;margin:0 auto}}.card{{background:#1e293b;border-radius:20px;padding:20px;border:1px solid #2a3a52}}.card-title{{color:#94a3b8;font-size:11px;font-weight:700;text-transform:uppercase}}.card-value{{font-size:26px;font-weight:900}}.btn-primary{{background:#10b981;color:white;padding:14px;border-radius:14px;font-weight:800;border:none;width:100%;cursor:pointer}}.btn-secondary{{background:#1e293b;border:1px solid #334155;color:white;padding:12px;border-radius:12px;text-align:center;display:block;text-decoration:none;margin-top:10px}}.table-card{{grid-column:1 / span 4;background:#1e293b;border-radius:20px;padding:20px;border:1px solid #2a3a52}} table{{width:100%;border-collapse:collapse}} th{{color:#64748b;text-align:left;padding:12px 10px;font-size:10px;text-transform:uppercase;border-bottom:1px solid #334155}} td{{padding:12px 10px;border-bottom:1px solid #1e293b;font-size:12px}}.pill{{padding:5px 12px;border-radius:20px;font-size:11px;font-weight:700}}.pill-took{{background:#10b98122;color:#10b981}}.pill-miss{{background:#ef444422;color:#ef4444}}.search-box{{background:#0f172a;border:1px solid #334155;color:white;padding:12px 16px;border-radius:12px;width:100%}} @media(max-width:1100px){{.main{{grid-template-columns:1fr 1fr}}.table-card{{grid-column:1 / span 2}}}} @media(max-width:640px){{.main{{grid-template-columns:1fr}}.table-card{{grid-column:1}}}} </style></head><body>"
    topbar=f"<div class='topbar'><div class='logo'>AGENT 35 PRO V19.8.1 ANTI-SPAM</div><div style='display:flex;gap:10px;align-items:center;font-size:11px;flex-wrap:wrap'><span class='badge'>ACTIVE</span><span class='badge-warn'>UTC {utc} | SAST {sast}</span><span class='badge-warn' style='color:#10b981'>{user[:20]}</span></div></div>"
    navbar=f"<div class='navbar'>{nav_html}</div>"
    return html_start+topbar+navbar+content+"</body></html>"

@app.route("/")
def home(): return redirect("/dashboard") if session.get("user") else redirect("/login")

@app.route("/dashboard")
def dashboard():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); auth=load_json(AUTH_FILE); info=auth.get(email,{})
    journal=load_json(JOURNAL_FILE, list); user_settings=get_user_settings(email)
    system=load_json(SYSTEM_FILE, dict); tg_users=load_json(TG_FILE, dict)
    is_admin=email=="admin@agent35.com"; ref_count=get_ref_count_and_auto_upgrade(email)
    if not journal: journal=[{"time":"09-03 18:13","symbol":"EURUSD","status":"TOOK","result":"R0","date":datetime.now().strftime("%Y-%m-%d")}]
    rows=""
    for t in reversed(journal[-6:]):
        cls="pill-took" if t.get("status")=="TOOK" else "pill-miss"
        rows+=f"<tr><td style='color:#94a3b8'>{t.get('time')}</td><td style='font-weight:800'>{t.get('symbol')}</td><td><span class='pill {cls}'>{t.get('status')}</span></td><td>{t.get('result')}</td></tr>"
    tg_status="Linked" if email in tg_users else "Not linked"
    sym_spans="".join([f"<span style='background:#1e293b;border:1px solid #334155;padding:5px 9px;border-radius:20px;font-size:10px'>{s}</span>" for s in user_settings.get('symbols',[])[:10]])
    admin_link="<a href='/creator?secret=' class='btn-secondary' style='background:#f59e0b;color:white;font-weight:700'>👑 Creator</a>" if is_admin else ""
    news_status="ON" if user_settings.get('trade_news',True) else "OFF"
    tracked=load_json(TRACK_FILE, dict)
    content=f"<div class='main'><div class='card'><div class='card-title'>Total Profit</div><div class='card-value' style='color:#ef4444'>R{info.get('total_profit',-1.42)}</div><div style='background:#0f172a;border-radius:12px;padding:10px;margin-top:10px;font-size:11px;color:#94a3b8'>TG: {tg_status}<br>Refs: {ref_count}/10<br>News: {news_status}<br>Tracked: {len(tracked)} (anti-spam)<br>RR 1:{user_settings.get('rr_ratio',2.5)}</div></div><div class='card'><div class='card-title'>Account</div><div class='card-value'>R{user_settings.get('account_size',142)}</div><div style='font-size:11px;color:#94a3b8'>Lot {user_settings.get('lot_size',0.01)} Lev {user_settings.get('leverage','1:500')}<br>Risk {user_settings.get('risk_percent',1)}% RR 1:{user_settings.get('rr_ratio',2.5)}<br><a href='/settings' style='color:#10b981;text-decoration:none;font-weight:700'>Edit Settings</a></div></div><div class='card'><div class='card-title'>Watchlist</div><div style='display:flex;flex-wrap:wrap;gap:5px;margin:10px 0'>{sym_spans}</div><div style='font-size:11px;color:#94a3b8'>Last: {str(system.get('last_scan','Never'))[:16]}<br>Cooldown: 4h same bias, 1h any</div></div><div class='card' style='border:1px solid #10b98133'><a href='/dashboard-scan'><button class='btn-primary'>⚡ SCAN NOW</button></a><a href='/test-telegram' class='btn-secondary'>Test Telegram</a><a href='/link-telegram' class='btn-secondary'>Link TG</a>{admin_link}</div></div><div style='max-width:1600px;margin:0 auto;padding:0 20px 20px'><div class='table-card'><h3>Recent Trades</h3><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th></tr>{rows}</table></div></div>"
    return pro_layout(content,"Dashboard", is_admin=is_admin)

@app.route("/all-signals")
@app.route("/dashboard-scan")
def dashboard_scan():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"
    user_settings=get_user_settings(email)
    symbols_to_scan=user_settings.get("symbols", ALL_SYMBOLS[:12])
    q=request.args.get("q","").upper()
    if q: symbols_to_scan=[s for s in ALL_SYMBOLS if q in s]
    rows=""
    for s in symbols_to_scan[:30]:
        try:
            r=eng.full_multi_tf_analysis(s, user_settings)
            score=r.get('score',0); bias=r.get('bias','NEUTRAL'); entry=r.get('entry',0)
            entry_display=f"{float(entry):.5f}" if entry and float(entry)<20 else f"{float(entry):.2f}" if entry else "0"
            premium=r.get('premium_pct',50); details=r.get('details',{})
            candles=",".join(details.get('candles',[])) or "-"; sweep="Y" if details.get('sweep') else "N"
            news_block="NEWS" if details.get('news_blocked') else ""
            color="#10b981" if score>=7 else "#f59e0b" if score>=5 else "#ef4444"
            signal_btn=f"<a href='/send-signal?symbol={s}' style='background:#10b981;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-weight:700;font-size:11px'>Send TG</a>" if r.get('signal') else f"<span style='color:#64748b;font-size:10px'>{r.get('reason','')[:60]}</span>"
            rows+=f"<tr><td style='font-weight:800'>{s}<br><span style='font-size:10px;color:#10b981'>{entry_display} | {premium:.0f}%</span><br><span style='font-size:9px;color:#94a3b8'>{candles} {sweep} {news_block}</span></td><td><span style='background:{color}22;color:{color};padding:4px 10px;border-radius:20px;font-weight:800'>{score}/10</span></td><td>{bias}</td><td>{'STRONG' if r.get('signal') else 'Wait'}</td><td>{signal_btn}</td></tr>"
        except Exception as e:
            rows+=f"<tr><td>{s}</td><td colspan=4 style='color:#ef4444'>{str(e)[:80]}</td></tr>"
    content=f"<div style='max-width:1600px;margin:0 auto;padding:20px'><div class='table-card'><h2>Signals - RR 1:{user_settings.get('rr_ratio',2.5)} | News {'ON' if user_settings.get('trade_news',True) else 'OFF'} | {len(symbols_to_scan)} Pairs</h2><div style='overflow-x:auto'><table><tr><th>Symbol</th><th>Score</th><th>Bias</th><th>Signal</th><th>Action</th></tr>{rows}</table></div></div></div>"
    return pro_layout(content,"All Signals", is_admin=is_admin)

@app.route("/settings", methods=["GET","POST"])
def settings_page():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"
    if request.method=="POST":
        trade_news_val = True if request.form.get("trade_news")=="yes" else False
        new_settings={
            "account_size":float(request.form.get("account_size",142)),
            "lot_size":float(request.form.get("lot_size",0.01)),
            "leverage":request.form.get("leverage","1:500"),
            "risk_percent":float(request.form.get("risk_percent",1)),
            "rr_ratio":float(request.form.get("rr_ratio",2.5)),
            "trade_news":trade_news_val,
            "sessions":request.form.getlist("sessions") or ["London"],
            "symbols":request.form.getlist("symbols") or ALL_SYMBOLS[:10]
        }
        save_user_settings(email,new_settings)
        return redirect("/settings")
    s=get_user_settings(email)
    symbols_html="".join([f"<label style='display:flex;align-items:center;gap:8px;background:#0f172a;border:1px solid #1e293b;padding:10px 12px;border-radius:10px;font-size:11px'><input type='checkbox' name='symbols' value='{sym}' {'checked' if sym in s.get('symbols',[]) else ''}> {sym}</label>" for sym in ALL_SYMBOLS])
    sessions_html="".join([f"<label style='display:flex;align-items:center;gap:8px;background:#0f172a;border:1px solid #1e293b;padding:10px 12px;border-radius:10px'><input type='checkbox' name='sessions' value='{ses}' {'checked' if ses in s.get('sessions',[]) else ''}> {ses}</label>" for ses in ["Asia","London","New York"]])
    rr=s.get('rr_ratio',2.5)
    trade_checked="checked" if s.get('trade_news',True) else ""
    content=f"""
<div style='max-width:1000px;margin:0 auto;padding:20px'>
<h1>Settings</h1>
<form method='post'>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:16px'>
<div class='card'><div class='card-title'>Account Size</div><input name='account_size' type='number' step='0.01' value='{s.get('account_size',142)}' style='width:100%;padding:14px;margin-top:10px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'></div>
<div class='card'><div class='card-title'>Lot Size</div><input name='lot_size' type='number' step='0.01' value='{s.get('lot_size',0.01)}' style='width:100%;padding:14px;margin-top:10px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'></div>
<div class='card'><div class='card-title'>Leverage</div><select name='leverage' style='width:100%;padding:14px;margin-top:10px;border-radius:12px;background:#0f172a;color:white;border:1px solid #334155'><option value='1:100' {'selected' if s.get('leverage')=='1:100' else ''}>1:100</option><option value='1:200' {'selected' if s.get('leverage')=='1:200' else ''}>1:200</option><option value='1:500' {'selected' if s.get('leverage')=='1:500' else ''}>1:500</option><option value='1:1000' {'selected' if s.get('leverage')=='1:1000' else ''}>1:1000</option></select></div>
<div class='card'><div class='card-title'>Risk %</div><input name='risk_percent' type='number' step='0.1' value='{s.get('risk_percent',1)}' style='width:100%;padding:14px;margin-top:10px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'></div>
</div>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px'>
<div class='card'><div class='card-title'>RR Ratio</div><select name='rr_ratio' style='width:100%;padding:14px;margin-top:10px;border-radius:12px;background:#0f172a;color:white;border:1px solid #334155'><option value='1.5' {'selected' if str(rr)=='1.5' else ''}>1:1.5</option><option value='2' {'selected' if str(rr)=='2' else ''}>1:2</option><option value='2.5' {'selected' if str(rr)=='2.5' else ''}>1:2.5</option><option value='3' {'selected' if str(rr)=='3' else ''}>1:3</option><option value='4' {'selected' if str(rr)=='4' else ''}>1:4</option></select></div>
<div class='card'><div class='card-title'>Trade News</div><label style='display:flex;gap:10px;align-items:center;background:#0f172a;padding:14px;border-radius:12px;margin-top:10px'><input type='checkbox' name='trade_news' value='yes' {trade_checked}><span>Trade NFP/CPI/FOMC</span></label><div style='font-size:11px;color:#94a3b8;margin-top:8px'>ON uses $ UP Gold DOWN logic. OFF blocks signals during news.</div></div>
</div>
<div class='card' style='margin-top:16px'><div class='card-title'>Sessions</div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:10px'>{sessions_html}</div></div>
<div class='card' style='margin-top:16px'><div class='card-title'>Symbols</div><div style='display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;max-height:500px;overflow-y:auto'>{symbols_html}</div></div>
<button type='submit' class='btn-primary' style='margin-top:20px'>SAVE</button>
</form>
</div>
"""
    return pro_layout(content,"Settings", is_admin=is_admin)

@app.route("/send-signal")
def send_signal():
    if not session.get("user"): return redirect("/login")
    sym=request.args.get("symbol","EURUSD"); email=session.get("user"); user_set=get_user_settings(email)
    try:
        r=eng.full_multi_tf_analysis(sym, user_set)
        entry=r.get('entry',0)
        if not entry or float(entry)==0:
            return f"<html><body style='background:#080c14;color:white;padding:20px'><h2>No entry</h2><pre>{r}</pre><a href='/all-signals'>Back</a></body></html>"
        rr=user_set.get('rr_ratio',2.5); risk_percent=user_set.get('risk_percent',1); lot=user_set.get('lot_size',0.01); lev=user_set.get('leverage','1:500'); acc=user_set.get('account_size',142)
        sl,tp,sl_dist,tp_dist,risk_amt=calculate_dynamic_sl_tp(sym, entry, r.get('bias',''), acc, lot, lev, risk_percent, rr)
        confluence=r.get('confluence', r.get('reason',''))
        res=send_telegram_pro(sym, r.get('score',0), r.get('bias',''), entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot, lev, acc, confluence)
        msg=f"Sent {sym} {entry} SL {sl} TP {tp} RR 1:{rr}"
    except Exception as e:
        res={"error":str(e)}; msg=f"Error {sym}: {e}"
    return f"<html><body style='background:#080c14;color:white;padding:40px'><div style='max-width:700px;margin:auto;background:#1e293b;padding:24px;border-radius:20px'><h2>{msg}</h2><p style='font-size:11px;background:#0f172a;padding:10px;border-radius:8px'>{str(res)[:3000]}</p><a href='/all-signals' style='background:#10b981;color:white;padding:10px 20px;border-radius:10px;text-decoration:none'>Back</a></div></body></html>"

@app.route("/test-telegram")
def test_telegram():
    email=session.get("user") or "admin@agent35.com"; user_set=get_user_settings(email)
    r=eng.full_multi_tf_analysis("GBPUSD", user_set); entry=r.get('entry',0)
    if not entry or float(entry)==0: entry=1.35057; r={"score":8,"bias":"BEARISH","confluence":"Test","details":{}}
    rr=user_set.get('rr_ratio',2.5); risk_percent=user_set.get('risk_percent',1); lot=user_set.get('lot_size',0.01); lev=user_set.get('leverage','1:500'); acc=user_set.get('account_size',142)
    sl,tp,sl_dist,tp_dist,risk_amt=calculate_dynamic_sl_tp("GBPUSD", entry, r.get('bias','BEARISH'), acc, lot, lev, risk_percent, rr)
    res=send_telegram_pro("GBPUSD", r.get('score',8), r.get('bias','BEARISH'), entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot, lev, acc, r.get('confluence','Test'))
    return f"<html><body style='background:#080c14;color:white;padding:40px'><div style='max-width:700px;margin:auto;background:#1e293b;padding:24px;border-radius:20px'><h2>Test {entry} SL {sl} TP {tp} RR 1:{rr}</h2><p style='font-size:11px;background:#0f172a;padding:10px;border-radius:8px'>{str(res)[:3000]}</p><a href='/dashboard' style='background:#10b981;color:white;padding:10px 20px;border-radius:12px;text-decoration:none'>Back</a></div></body></html>"

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data=request.get_json()
    if not data: return jsonify({"ok":True})
    bot=os.getenv("TELEGRAM_BOT_TOKEN")
    if "message" in data:
        chat_id=data["message"]["chat"]["id"]; from_user=data["message"]["from"]
        temp=load_json(TEMP_CHAT_FILE, dict)
        temp[str(chat_id)]={"first_name":from_user.get("first_name",""),"username":from_user.get("username",""),"time":datetime.now().isoformat(),"text":data["message"].get("text","")[:100]}
        save_json(TEMP_CHAT_FILE, temp)
        if bot and "/start" in data["message"].get("text",""):
            try: requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":f"Chat ID: {chat_id}"}, timeout=5)
            except: pass
    if "callback_query" in data:
        cb=data["callback_query"]; cb_data=cb.get("data",""); cb_id=cb.get("id"); chat_id=cb["message"]["chat"]["id"]; user_name=cb["from"].get("first_name","User")
        journal=load_json(JOURNAL_FILE, list); text="OK"
        if cb_data.startswith("TOOK_"):
            parts=cb_data.split("_"); sym=parts[1]; entry=parts[2] if len(parts)>2 else ""
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"TOOK","result":f"Taken by {user_name} - {entry}","date":datetime.now().strftime("%Y-%m-%d")}); save_json(JOURNAL_FILE, journal[-300:]); text=f"TOOK {sym}"
        elif cb_data.startswith("SKIP_"):
            sym=cb_data.split("_")[1]; journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"MISS","result":f"Skipped by {user_name}","date":datetime.now().strftime("%Y-%m-%d")}); save_json(JOURNAL_FILE, journal[-300:]); text=f"SKIP {sym}"
        elif cb_data.startswith("WIN_"):
            sym=cb_data.split("_")[1]; journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"TOOK","result":f"WIN by {user_name}","date":datetime.now().strftime("%Y-%m-%d")}); save_json(JOURNAL_FILE, journal[-300:]); text=f"WIN {sym}"
        elif cb_data.startswith("LOSS_"):
            sym=cb_data.split("_")[1]; journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"MISS","result":f"LOSS by {user_name}","date":datetime.now().strftime("%Y-%m-%d")}); save_json(JOURNAL_FILE, journal[-300:]); text=f"LOSS {sym}"
        elif cb_data.startswith("BE_"):
            sym=cb_data.split("_")[1]; journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"TOOK","result":f"BE by {user_name}","date":datetime.now().strftime("%Y-%m-%d")}); save_json(JOURNAL_FILE, journal[-300:]); text=f"BE {sym}"
        if bot:
            try:
                requests.post(f"https://api.telegram.org/bot{bot}/answerCallbackQuery", json={"callback_query_id":cb_id,"text":text}, timeout=5)
                requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":text}, timeout=5)
            except: pass
        return jsonify({"ok":True})
    return jsonify({"ok":True})

@app.route("/login")
def login_page(): return "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#080c14;color:white;font-family:Arial;padding:20px;min-height:100vh;display:flex;align-items:center;justify-content:center'><div style='width:100%;max-width:420px;background:#1e293b;padding:32px;border-radius:24px'><div style='text-align:center;margin-bottom:24px'><div style='font-weight:900;font-size:26px;color:#10b981'>AGENT 35 PRO V19.8.1</div></div><form action='/login/check' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:14px;margin:8px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><input name='password' type='password' placeholder='Password' required style='width:100%;padding:14px;margin:8px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><button style='background:#10b981;color:white;padding:14px;width:100%;border:none;border-radius:12px;font-weight:800;margin-top:10px'>LOGIN</button></form></div></body></html>"

@app.route("/register")
def register_page():
    ref=request.args.get("ref","")
    ref_banner=f"<div style='background:#10b98122;border:1px solid #10b98144;padding:10px;border-radius:10px;font-size:12px;color:#10b981;margin-bottom:12px'>Referred by: {ref}</div>" if ref else ""
    return f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#080c14;color:white;font-family:Arial;padding:20px;min-height:100vh;display:flex;align-items:center;justify-content:center'><div style='width:100%;max-width:420px;background:#1e293b;padding:32px;border-radius:24px'><h2>Create Account</h2>{ref_banner}<form action='/register/create' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><input name='name' placeholder='Full Name' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><input name='password' type='password' placeholder='Password' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><input name='ref' value='{ref}' placeholder='Referral Code' style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #10b98144;background:#0f172a;color:white'><button style='background:#10b981;color:white;padding:14px;width:100%;border:none;border-radius:12px;font-weight:800;margin-top:10px'>CREATE</button></form></div></body></html>"

@app.route("/register/create", methods=["POST"])
def register_create():
    email=request.form.get("email","").lower().strip(); auth=load_json(AUTH_FILE)
    if email in auth: return f"Exists <a href='/login'>Login</a>"
    ref_code=request.form.get("ref","").upper().strip(); my_code=generate_ref_code(email)
    auth[email]={"email":email,"name":request.form.get("name"),"password":hash_pwd(request.form.get("password","")),"account_size":142.0,"total_profit":-1.42,"plan_status":"No Plan","referred_by":ref_code,"created":datetime.now().isoformat(),"reset_token":None,"ref_code":my_code}
    save_json(AUTH_FILE, auth); session["user"]=email; return redirect("/dashboard")

@app.route("/login/check", methods=["POST"])
def login_check():
    email=request.form.get("email","").lower().strip(); pwd=request.form.get("password",""); auth=load_json(AUTH_FILE)
    if email in auth and auth[email].get("password")==hash_pwd(pwd):
        session["user"]=email; return redirect("/dashboard")
    return f"Wrong <a href='/login'>Retry</a>"

@app.route("/logout")
def logout(): session.pop("user",None); return redirect("/login")

@app.route("/journal")
def journal_page():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"; journal=load_json(JOURNAL_FILE, list)
    q=request.args.get("q","").upper(); filtered=[j for j in journal if q in j.get("symbol","").upper()] if q else journal
    rows="".join([f"<tr><td>{j.get('time')}</td><td>{j.get('symbol')}</td><td>{j.get('status')}</td><td>{j.get('result')}</td><td>{j.get('date','')}</td></tr>" for j in reversed(filtered[-100:])])
    content=f"<div style='max-width:1400px;margin:0 auto;padding:20px'><h1>Journal ({len(filtered)})</h1><form method='get'><input name='q' value='{q}' placeholder='Search' class='search-box' style='width:200px'><button style='background:#10b981;color:white;padding:10px;border-radius:10px;border:none'>Search</button></form><div class='table-card'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th><th>Date</th></tr>{rows}</table></div></div>"
    return pro_layout(content,"Journal", is_admin=is_admin)

@app.route("/link-telegram", methods=["GET","POST"])
def link_telegram():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"; tg_users=load_json(TG_FILE, dict)
    if request.method=="POST":
        chat_id=request.form.get("chat_id","").strip()
        if chat_id:
            tg_users[email]={"chat_id":chat_id,"linked_at":datetime.now().isoformat()}
            save_json(TG_FILE, tg_users)
            return redirect("/dashboard")
    current=tg_users.get(email,{}).get("chat_id","Not linked")
    content=f"<div style='max-width:700px;margin:0 auto;padding:20px'><div class='card'><h2>Link Telegram</h2><div>Current: {current}</div><a href='https://t.me/Sniper035_bot' target='_blank' style='background:#0088cc;color:white;padding:14px;border-radius:12px;text-align:center;display:block;text-decoration:none;font-weight:800;margin:12px 0'>Open @Sniper035_bot - /start</a><form method='post'><input name='chat_id' placeholder='Chat ID' style='width:100%;padding:14px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white' required><button type='submit' style='background:#f59e0b;color:white;padding:14px;width:100%;border:none;border-radius:12px;font-weight:800;margin-top:10px'>Save</button></form></div></div>"
    return pro_layout(content,"Settings", is_admin=is_admin)

@app.route("/creator")
def creator_dashboard():
    secret=request.args.get("secret",""); users=load_json(USERS_FILE)
    pending={k:v for k,v in users.items() if v.get("status")=="pending"}
    pending_rows="".join([f"<tr><td>{ref}</td><td>{pay.get('user','')}</td><td>R{pay.get('price','')}</td><td><a href='/creator/action?act=approve_payment&ref={ref}&secret={secret}' style='background:#10b981;color:white;padding:6px 12px;border-radius:8px;text-decoration:none'>APPROVE</a></td></tr>" for ref,pay in pending.items()]) or "<tr><td colspan=4 style='text-align:center;color:#64748b'>No pending</td></tr>"
    content=f"<div style='max-width:1600px;margin:0 auto;padding:20px'><h1>Creator</h1><div class='table-card'><h3>PENDING ({len(pending)})</h3><table><tr><th>Ref</th><th>Email</th><th>Price</th><th>Action</th></tr>{pending_rows}</table></div><div style='margin-top:16px;display:flex;gap:8px'><a href='/creator/webhook?action=set&secret={secret}' style='background:#10b981;color:white;padding:12px;border-radius:10px;text-decoration:none'>SET WEBHOOK</a><a href='/test-telegram' style='background:#1e293b;border:1px solid #334155;color:white;padding:12px;border-radius:10px;text-decoration:none'>Test</a></div></div>"
    return pro_layout(content,"Master", is_admin=True)

@app.route("/creator/webhook")
def creator_webhook():
    secret=request.args.get("secret",""); action=request.args.get("action","info")
    bot_token=os.getenv("TELEGRAM_BOT_TOKEN"); base=f"https://api.telegram.org/bot{bot_token}"
    url="https://agent-35-trading-bot.onrender.com/telegram/webhook"
    try:
        if action=="set":
            r=requests.get(f"{base}/setWebhook", params={"url":url}, timeout=10).json()
            return f"<html><body style='background:#080c14;color:white;padding:20px'><pre>{json.dumps(r, indent=2)}</pre><a href='/creator?secret={secret}'>Back</a></body></html>"
        else:
            r=requests.get(f"{base}/getWebhookInfo", timeout=10).json()
            return f"<pre>{json.dumps(r, indent=2)}</pre>"
    except Exception as e: return str(e)

@app.route("/creator/action")
def creator_action():
    secret=request.args.get("secret",""); act=request.args.get("act",""); auth=load_json(AUTH_FILE); users=load_json(USERS_FILE)
    if act=="approve_payment":
        ref=request.args.get("ref","")
        if ref in users:
            users[ref]["status"]="active"; users[ref]["expires"]=(datetime.now()+timedelta(days=PLANS.get(users[ref].get('plan','yearly'),PLANS['yearly'])['days'])).isoformat()
            email=users[ref].get("user")
            if email in auth:
                auth[email]["plan_status"]=f"ACTIVE {users[ref].get('plan','yearly')} - Approved"; auth[email]["expires"]=users[ref]["expires"]
            save_json(USERS_FILE, users); save_json(AUTH_FILE, auth)
            ref_by=users[ref].get("referred_by","")
            if ref_by:
                codes=load_json(REF_CODE_FILE, dict); referrer_email=codes.get(ref_by,"")
                if referrer_email: get_ref_count_and_auto_upgrade(referrer_email)
        return redirect(f"/creator?secret={secret}")
    return redirect(f"/creator?secret={secret}")

@app.route("/pay")
def pay_page():
    ref=request.args.get("ref","") or session.get("ref",""); email=session.get("user","")
    content=f"<div style='max-width:500px;margin:0 auto;padding:20px'><div class='card'><h2>Buy Plan</h2><form action='/pay/create' method='get'><input type='hidden' name='ref' value='{ref}'><input name='user' value='{email}' placeholder='Email' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><input name='phone' placeholder='WhatsApp' required style='width:100%;padding:14px;margin:6px 0;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><select name='plan' style='width:100%;padding:14px;border-radius:12px;border:1px solid #334155;background:#0f172a;color:white'><option value='yearly'>Yearly R500</option><option value='lifetime'>Lifetime R5000</option></select><button style='background:#10b981;color:white;padding:14px;width:100%;border:none;border-radius:12px;margin-top:10px;font-weight:800'>GET REF</button></form></div></div>"
    return pro_layout(content,"Plans", is_admin=session.get("user")=="admin@agent35.com")

@app.route("/pay/create")
def pay_create():
    user=request.args.get("user","").lower().strip(); phone=request.args.get("phone","").strip()
    plan_key=request.args.get("plan","yearly"); ref=request.args.get("ref","").upper().strip()
    short="".join([c for c in user.upper() if c.isalnum()])[:5] or "USER"; rand="".join(random.choices(string.digits,k=3)); pref=f"A35-{short}-{rand}"
    plan=PLANS.get(plan_key, PLANS["yearly"]); users=load_json(USERS_FILE)
    users[pref]={"user":user,"phone":phone,"plan":plan_key,"price":plan["price"],"payment_ref":pref,"referred_by":ref,"status":"pending","created":datetime.now().isoformat(),"expires":None}
    save_json(USERS_FILE, users)
    return f"<html><body style='background:#080c14;color:white;padding:40px;text-align:center'><div style='max-width:480px;margin:auto;background:#1e293b;padding:28px;border-radius:20px'><h1>Pay R{plan['price']}</h1><h1 style='background:white;color:black;padding:16px;border-radius:12px'>{pref}</h1><a href='/dashboard'>Back</a></div></body></html>"

@app.route("/guide")
def guide_page():
    is_admin=session.get("user")=="admin@agent35.com"
    content="<div style='max-width:900px;margin:0 auto;padding:20px'><h1>Guide V19.8.1</h1><div class='card'><p>Anti-spam: 4h same bias, 1h any. Change cron to */30 * * * *</p></div></div>"
    return pro_layout(content,"Guide", is_admin=is_admin)

@app.route("/plans")
def plans_page(): return pro_layout("<div style='max-width:600px;margin:0 auto;padding:20px'><div class='card'><h2>Plans</h2><a href='/pay'>Buy</a></div></div>","Plans", is_admin=session.get("user")=="admin@agent35.com")

@app.route("/referral")
def referral_page():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"
    auth=load_json(AUTH_FILE); my_code=generate_ref_code(email); get_ref_count_and_auto_upgrade(email)
    my_refs=[]
    for e,info in auth.items():
        if info.get("referred_by","").upper()==my_code.upper():
            status="PAID" if "ACTIVE" in info.get("plan_status","") else "Pending"
            my_refs.append({"email":e,"status":status,"plan":info.get("plan_status","")})
    paid_count=len([r for r in my_refs if "PAID" in r["status"]]); progress=int((paid_count/10)*100) if paid_count<=10 else 100
    refs_html="".join([f"<tr><td>{r['email'][:28]}</td><td><span style='color:{'#10b981' if 'PAID' in r['status'] else '#f59e0b'}'>{r['status']}</span></td><td>{r['plan'][:24]}</td></tr>" for r in my_refs]) or "<tr><td colspan=3 style='text-align:center;color:#64748b'>No referrals</td></tr>"
    link=f"https://agent-35-trading-bot.onrender.com/register?ref={my_code}"
    free_banner="<div style='background:#10b981;color:white;padding:12px;border-radius:12px;text-align:center;font-weight:900;margin-top:12px'>FREE LIFETIME UNLOCKED!</div>" if paid_count>=10 else ""
    content=f"<div style='max-width:1000px;margin:0 auto;padding:20px'><h1>Referral</h1><div style='display:grid;grid-template-columns:1fr 1fr;gap:16px'><div class='card'><div class='card-title'>Your Code</div><div style='background:white;color:black;padding:16px;border-radius:12px;font-weight:900;font-size:24px;text-align:center;margin:12px 0'>{my_code}</div><div style='background:#0f172a;padding:10px;border-radius:10px;font-size:11px;word-break:break-all'>{link}</div></div><div class='card'><div class='card-title'>Progress {paid_count}/10</div><div style='background:#0f172a;border-radius:20px;height:14px;overflow:hidden;margin:12px 0'><div style='background:#10b981;width:{progress}%;height:100%'></div></div>{free_banner}</div></div><div class='table-card' style='margin-top:20px'><h3>Referrals ({len(my_refs)})</h3><table><tr><th>Email</th><th>Status</th><th>Plan</th></tr>{refs_html}</table></div></div>"
    return pro_layout(content,"Referral", is_admin=is_admin)

@app.route("/cron/scan")
def cron_scan():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    system=load_json(SYSTEM_FILE, dict)
    system["last_scan"]=datetime.now().isoformat()
    system["total_scans"]=system.get("total_scans",0)+1
    save_json(SYSTEM_FILE, system)

    settings_all=load_json(SETTINGS_FILE, dict)
    tracked=load_json(TRACK_FILE, dict)
    all_syms=set()
    for s in settings_all.values(): all_syms.update(s.get("symbols",[]))
    if not all_syms: all_syms=set(ALL_SYMBOLS[:12])

    sent=[]
    skipped=[]
    now=datetime.now()

    # Clean old tracked >24h
    cleaned={}
    for k,v in tracked.items():
        try:
            t=datetime.fromisoformat(v.get("time","2000-01-01T00:00:00"))
            if (now - t).total_seconds() < 86400: cleaned[k]=v
        except: pass
    if len(cleaned)!=len(tracked):
        tracked=cleaned
        save_json(TRACK_FILE, tracked)

    for sym in list(all_syms)[:20]:
        try:
            sample_settings = next(iter(settings_all.values())) if settings_all else {"trade_news":True,"risk_percent":1,"rr_ratio":2.5,"lot_size":0.01,"leverage":"1:500","account_size":142}
            r=eng.full_multi_tf_analysis(sym, sample_settings)

            if not r.get('signal') or not r.get('entry') or float(r.get('entry'))==0:
                continue

            last_info=tracked.get(sym)
            if last_info:
                try:
                    last_time=datetime.fromisoformat(last_info.get("time","2000-01-01T00:00:00"))
                    last_bias=last_info.get("bias","")
                    hours_since=(now-last_time).total_seconds()/3600
                    if last_bias==r.get('bias') and hours_since<4:
                        skipped.append(f"{sym} {last_bias} {hours_since:.1f}h cooldown")
                        continue
                    if hours_since<1:
                        skipped.append(f"{sym} 1h cooldown")
                        continue
                except: pass

            entry=r.get('entry')
            rr=sample_settings.get('rr_ratio',2.5)
            risk_percent=sample_settings.get('risk_percent',1)
            lot=sample_settings.get('lot_size',0.01)
            lev=sample_settings.get('leverage','1:500')
            acc=sample_settings.get('account_size',142)
            sl,tp,sl_dist,tp_dist,risk_amt=calculate_dynamic_sl_tp(sym, entry, r.get('bias',''), acc, lot, lev, risk_percent, rr)
            confluence=r.get('confluence', r.get('reason',''))
            send_telegram_pro(sym, r.get('score',7), r.get('bias',''), entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot, lev, acc, confluence)

            tracked[sym]={"time":now.isoformat(),"bias":r.get('bias'),"entry":entry,"score":r.get('score')}
            save_json(TRACK_FILE, tracked)
            sent.append(sym)

        except Exception as e:
            print(f"Scan error {sym}: {e}")

    return jsonify({"sent":sent,"skipped":skipped,"scanned":len(all_syms),"cooldown":"4h same bias, 1h any","tracked_count":len(tracked)})

@app.route("/health")
def health():
    test=eng.full_multi_tf_analysis("GBPUSD", {"trade_news":True})
    tracked=load_json(TRACK_FILE, dict)
    return jsonify({"ok":True,"version":"V19.8.1 ANTI-SPAM 4h/1h","entry":test.get('entry'),"score":test.get('score'),"bias":test.get('bias'),"premium":test.get('premium_pct'),"details":test.get('details'),"keys":len([k for k in [os.getenv("TWELVE_DATA_API_KEY"),os.getenv("TWELVE_DATA_API_KEY_2"),os.getenv("TWELVE_DATA_API_KEY_3"),os.getenv("TWELVE_DATA_API_KEY_4")] if k]),"tracked":len(tracked)})

@app.route("/forgot-password")
def forgot_page(): return "<html><body style='background:#080c14;color:white;padding:30px'><div style='max-width:400px;margin:auto;background:#1e293b;padding:20px;border-radius:12px'><h2>Forgot</h2><form action='/forgot-password/send' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:12px;border-radius:8px;background:#0f172a;border:1px solid #334155;color:white'><button style='background:#f59e0b;color:white;padding:12px;width:100%;border:none;border-radius:12px;margin-top:10px'>SEND</button></form></div></body></html>"

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000)
