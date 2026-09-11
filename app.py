from flask import Flask, request, jsonify, session, redirect, Response
import os, json, hashlib, requests, random, string, csv, io
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "agent35-v20-currency-method")
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

CURRENCY_MAP = {"ZAR":{"symbol":"R","name":"Rand"},"USD":{"symbol":"$","name":"Dollar"},"EUR":{"symbol":"€","name":"Euro"},"GBP":{"symbol":"£","name":"Pound"}}

METHODS = {
    "method1_premium_sweep":{"name":"V19.9 Premium + Sweep + Engulfing","desc":"Swing SMC - High Win Rate 65%+, 2-5 signals/day, Best for Gold/Forex H1/M5, RR 1:2.5","rr_default":2.5},
    "method2_ema_rsi":{"name":"EMA 5/20 + RSI Pullback","desc":"Trend continuation - More signals 5-10/day, BUY EMA5>EMA20 + RSI 40-55 pullback, Best for Forex trend","rr_default":2.0},
    "method3_breakout_retest":{"name":"Breakout + Retest","desc":"Indices/Crypto breakout - Breaks high/low + retest + engulf, Best for US30/NAS100/BTC","rr_default":2.0},
    "method4_scalp_m5":{"name":"Scalp M5 Only - Fast","desc":"Fast scalp 10-20/day, M5 EMA9/21 cross + RSI, RR 1:1.5, Best for R142 small accounts","rr_default":1.5},
    "method5_smc_ob_bos":{"name":"SMC Order Block + BOS","desc":"Advanced SMC - BOS + Order Block + FVG, Fewer signals but 70%+ WR","rr_default":3.0}
}

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
    default = {"account_size":142.0,"lot_size":0.01,"leverage":"1:500","sessions":["London","New York"],"symbols":ALL_SYMBOLS[:10],"risk_percent":1.0,"rr_ratio":2.5,"trade_news":True,"spread_forex":0.7,"spread_gold":0.35,"spread_indices":2.0,"spread_crypto":10.0,"currency":"ZAR","trading_method":"method1_premium_sweep"}
    s = settings.get(email, default)
    for k,v in default.items():
        if k not in s: s[k]=v
    return s

def get_currency_symbol(currency_code):
    return CURRENCY_MAP.get(currency_code, CURRENCY_MAP["ZAR"])["symbol"]

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

def calculate_pnl_stats(journal):
    now=datetime.now()
    today_str=now.strftime("%Y-%m-%d")
    week_start=(now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    month_str=now.strftime("%Y-%m")
    year_str=now.strftime("%Y")
    stats={"total_trades":0,"wins":0,"losses":0,"be":0,"win_rate":0,"daily":0,"weekly":0,"monthly":0,"yearly":0,"total_pnl":0}
    for j in journal:
        result=j.get("result","")
        pnl=j.get("pnl",0)
        date=j.get("date",today_str)
        try:
            if "WIN" in result.upper():
                stats["wins"]+=1
                stats["total_trades"]+=1
            elif "LOSS" in result.upper():
                stats["losses"]+=1
                stats["total_trades"]+=1
            elif "BE" in result.upper():
                stats["be"]+=1
                stats["total_trades"]+=1
        except: pass
        try:
            stats["total_pnl"]+=float(pnl)
            if date==today_str: stats["daily"]+=float(pnl)
            if date>=week_start: stats["weekly"]+=float(pnl)
            if date.startswith(month_str): stats["monthly"]+=float(pnl)
            if date.startswith(year_str): stats["yearly"]+=float(pnl)
        except: pass
    if stats["total_trades"]>0:
        stats["win_rate"]=round((stats["wins"]/stats["total_trades"])*100,1)
    return stats

def calculate_dynamic_sl_tp(symbol, entry, bias, account_size, lot_size, leverage, risk_percent, rr_ratio, spread_forex=0.7, spread_gold=0.35, spread_indices=2.0, spread_crypto=10.0):
    entry=float(entry)
    is_sell="BEARISH" in bias.upper() or "SELL" in bias.upper()
    risk_amount=float(account_size)*(float(risk_percent)/100.0)
    lot_size=float(lot_size) if float(lot_size)>0 else 0.01
    rr_ratio=float(rr_ratio) if float(rr_ratio)>0 else 2.5
    if symbol in ["XAUUSD","XAGUSD","XAUJPY"]:
        spread=float(spread_gold)
        sl_dollar=risk_amount/(lot_size*100) if lot_size>0 else 5.0
        sl_dollar=max(2.0,min(sl_dollar,15.0))
        sl_dollar+=spread
        tp_dollar=sl_dollar*rr_ratio - spread
        sl=entry+sl_dollar if is_sell else entry-sl_dollar
        tp=entry-tp_dollar if is_sell else entry+tp_dollar
        return round(sl,2),round(tp,2),round(sl_dollar,2),round(tp_dollar,2),risk_amount
    elif symbol in ["US30","NAS100","SPX500","GER40","UK100","FRA40"]:
        spread=float(spread_indices)
        sl_points=(risk_amount/(lot_size*10)) if lot_size>0 else 80
        sl_points=max(30,min(sl_points,250))
        sl_points+=spread
        tp_points=sl_points*rr_ratio - spread
        sl=entry+sl_points if is_sell else entry-sl_points
        tp=entry-tp_points if is_sell else entry+tp_points
        return round(sl,2),round(tp,2),round(sl_points,1),round(tp_points,1),risk_amount
    elif "BTC" in symbol or "ETH" in symbol or "SOL" in symbol or "BNB" in symbol:
        spread=float(spread_crypto)
        if "BTC" in symbol: sl_d=max(100,min(risk_amount/(lot_size*10) if lot_size>0 else 400,1200))
        else: sl_d=max(5,min(risk_amount/(lot_size*10) if lot_size>0 else 40,150))
        sl_d+=spread
        tp_d=sl_d*rr_ratio - spread
        sl=entry+sl_d if is_sell else entry-sl_d
        tp=entry-tp_d if is_sell else entry+tp_d
        return round(sl,2),round(tp,2),round(sl_d,1),round(tp_d,1),risk_amount
    else:
        spread=float(spread_forex)
        pip_value=lot_size*10
        if pip_value==0: pip_value=0.1
        sl_pips=risk_amount/pip_value
        sl_pips=max(5,min(sl_pips,50))
        sl_pips+=spread
        tp_pips=sl_pips*rr_ratio - spread
        if "JPY" in symbol: sl_dist=sl_pips*0.01; tp_dist=tp_pips*0.01
        else: sl_dist=sl_pips*0.0001; tp_dist=tp_pips*0.0001
        sl=entry+sl_dist if is_sell else entry-sl_dist
        tp=entry-tp_dist if is_sell else entry+tp_dist
        if entry<20: return round(sl,5),round(tp,5),round(sl_pips,1),round(tp_pips,1),risk_amount
        else: return round(sl,2),round(tp,2),round(sl_pips,1),round(tp_pips,1),risk_amount

def send_telegram_pro(symbol, score, bias, entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot_size, leverage, account_size, confluence_text, currency_symbol="R", method_name=""):
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
    text=f"🔴 {symbol} {signal_type} | {display_score}/8 | {method_name[:20]}\n\n📊 {currency_symbol}{account_size} Lot {lot_size} Lev {leverage}\n💰 Entry: {entry_fmt}\n🛑 SL: {sl_fmt} ({sl_dist})\n🎯 TP: {tp_fmt} ({tp_dist})\n📊 RR 1:{rr} | Risk {currency_symbol}{risk_amt:.2f} ({risk_percent}%)\n\n🔍 {confluence_text}\n\n⏰ {sast_now}"
    keyboard={"inline_keyboard": [[{"text":"✅ TOOK ENTRY","callback_data":f"TOOK_{symbol}_{entry_fmt}"},{"text":"❌ SKIP","callback_data":f"SKIP_{symbol}"}],[{"text":"📊 Journal","url":"https://agent-35-trading-bot.onrender.com/journal"}]]}
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
        if active==t: nav_html+=f"<a href='{url}' style='padding:8px 12px;border-radius:10px;text-decoration:none;color:white;font-weight:700;font-size:11px;background:#10b981;margin-right:5px'>{icon} {t}</a>"
        else: nav_html+=f"<a href='{url}' style='padding:8px 12px;border-radius:10px;text-decoration:none;color:#94a3b8;font-weight:600;font-size:11px;background:#1e293b;margin-right:5px'>{icon} {t}</a>"
    html_start=f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0, maximum-scale=1.0'><title>AGENT 35 PRO V20</title><style>body{{background:#080c14;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,Arial,sans-serif;margin:0;padding:0}}.topbar{{background:#0f172a;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100;flex-wrap:wrap;gap:8px}}.logo{{font-weight:900;font-size:15px;color:#10b981}}.badge{{background:#10b981;padding:4px 10px;border-radius:20px;font-weight:700;font-size:10px;color:white}}.badge-warn{{background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:4px 10px;border-radius:20px;font-size:10px}}.navbar{{background:#0f172a;border-bottom:1px solid #1e293b;padding:10px 12px;display:flex;gap:5px;overflow-x:auto;position:sticky;top:56px;z-index:90;-webkit-overflow-scrolling:touch}}.main{{padding:10px;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;max-width:1600px;margin:0 auto}}.card{{background:#1e293b;border-radius:14px;padding:14px;border:1px solid #2a3a52;min-width:0}}.card-title{{color:#94a3b8;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px}}.card-value{{font-size:20px;font-weight:900;word-break:break-word}}.btn-primary{{background:#10b981;color:white;padding:12px;border-radius:10px;font-weight:800;border:none;width:100%;cursor:pointer;font-size:13px}}.btn-secondary{{background:#1e293b;border:1px solid #334155;color:white;padding:9px;border-radius:9px;text-align:center;display:block;text-decoration:none;margin-top:6px;font-size:11px}}.table-card{{grid-column:1 / -1;background:#1e293b;border-radius:14px;padding:14px;border:1px solid #2a3a52;overflow-x:auto}} table{{width:100%;border-collapse:collapse;min-width:480px}} th{{color:#64748b;text-align:left;padding:8px 6px;font-size:8px;text-transform:uppercase;border-bottom:1px solid #334155;white-space:nowrap}} td{{padding:8px 6px;border-bottom:1px solid #1e293b;font-size:10px;white-space:nowrap}}.pill{{padding:3px 8px;border-radius:20px;font-size:9px;font-weight:700;display:inline-block}}.pill-took{{background:#10b98122;color:#10b981}}.pill-win{{background:#10b98122;color:#10b981}}.pill-loss{{background:#ef444422;color:#ef4444}}.search-box{{background:#0f172a;border:1px solid #334155;color:white;padding:9px 12px;border-radius:9px;width:100%;font-size:13px}} @media(max-width:768px){{.main{{grid-template-columns:1fr; padding:8px}}.card-value{{font-size:18px}}}} </style></head><body>"
    topbar=f"<div class='topbar'><div class='logo'>AGENT 35 PRO V20 • Currency + Methods</div><div style='display:flex;gap:5px;align-items:center;flex-wrap:wrap'><span class='badge'>LIVE</span><span class='badge-warn'>{sast} SAST</span><span class='badge-warn' style='color:#10b981'>{user[:16]}</span></div></div>"
    navbar=f"<div class='navbar'>{nav_html}</div>"
    return html_start+topbar+navbar+content+"</body></html>"

@app.route("/")
def home(): return redirect("/dashboard") if session.get("user") else redirect("/login")

@app.route("/dashboard")
def dashboard():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); auth=load_json(AUTH_FILE)
    journal=load_json(JOURNAL_FILE, list); user_settings=get_user_settings(email)
    system=load_json(SYSTEM_FILE, dict); tg_users=load_json(TG_FILE, dict)
    is_admin=email=="admin@agent35.com"; ref_count=get_ref_count_and_auto_upgrade(email)
    stats=calculate_pnl_stats(journal)
    curr_sym=get_currency_symbol(user_settings.get("currency","ZAR"))
    method_key=user_settings.get("trading_method","method1_premium_sweep")
    method_name=METHODS.get(method_key, METHODS["method1_premium_sweep"])["name"][:25]
    if not journal: journal=[{"time":"09-03 18:13","symbol":"EURUSD","status":"TOOK","result":"DEMO","pnl":0,"date":datetime.now().strftime("%Y-%m-%d")}]
    rows=""
    for t in reversed(journal[-6:]):
        cls="pill-took" if t.get("status")=="TOOK" else "pill-win" if "WIN" in t.get("result","") else "pill-loss"
        pnl=t.get("pnl",0)
        rows+=f"<tr><td style='color:#94a3b8'>{t.get('time')}</td><td style='font-weight:800'>{t.get('symbol')}</td><td><span class='pill {cls}'>{t.get('status')}</span></td><td>{t.get('result')}</td><td>{curr_sym}{pnl}</td></tr>"
    tg_status="Linked ✅" if email in tg_users else "Not linked ❌"
    sym_spans="".join([f"<span style='background:#0f172a;border:1px solid #334155;padding:3px 7px;border-radius:20px;font-size:8px;margin:2px;display:inline-block'>{s}</span>" for s in user_settings.get('symbols',[])[:10]])
    admin_link="<a href='/creator?secret=' class='btn-secondary' style='background:#f59e0b;color:white;font-weight:700'>👑 Creator</a>" if is_admin else ""
    content=f"""
<div class='main'>
<div class='card'><div class='card-title'>Total PnL ({user_settings.get('currency','ZAR')})</div><div class='card-value' style='color:{"#10b981" if stats['total_pnl']>=0 else "#ef4444"}'>{curr_sym}{stats['total_pnl']:.2f}</div><div style='background:#0f172a;border-radius:8px;padding:6px;margin-top:6px;font-size:9px;color:#94a3b8;display:grid;grid-template-columns:1fr 1fr;gap:5px'><div>Today: {curr_sym}{stats['daily']:.2f}</div><div>Week: {curr_sym}{stats['weekly']:.2f}</div><div>Month: {curr_sym}{stats['monthly']:.2f}</div><div>Year: {curr_sym}{stats['yearly']:.2f}</div></div><div style='font-size:9px;color:#10b981;margin-top:6px'>Method: {method_name}</div></div>
<div class='card'><div class='card-title'>Signals & Win Rate</div><div class='card-value'>{stats['total_trades']} Trades • {stats['win_rate']}% WR</div><div style='font-size:9px;color:#94a3b8;margin-top:4px'>Wins: {stats['wins']} | Losses: {stats['losses']} | BE: {stats['be']}<br>TG: {tg_status} | Refs: {ref_count}/10<br>Spread: {user_settings.get('spread_forex')} pips | {method_name}</div></div>
<div class='card'><div class='card-title'>Account • {user_settings.get('currency','ZAR')} + Spread + RR</div><div class='card-value'>{curr_sym}{user_settings.get('account_size',142)}</div><div style='font-size:9px;color:#94a3b8'>Lot {user_settings.get('lot_size',0.01)} Lev {user_settings.get('leverage','1:500')}<br>Risk {user_settings.get('risk_percent',1)}% RR 1:{user_settings.get('rr_ratio',2.5)}<br>Currency: {user_settings.get('currency','ZAR')} {curr_sym} | Method: {method_key[:12]}<br><a href='/settings' style='color:#10b981;text-decoration:none;font-weight:700'>Change Currency & Method</a></div></div>
<div class='card'><div class='card-title'>Watchlist</div><div style='margin:6px 0'>{sym_spans}</div><div style='font-size:9px;color:#94a3b8'>Last: {str(system.get('last_scan','Never'))[:16]}<br>Cooldown 4h same bias, 1h any</div></div>
<div class='card' style='border:1px solid #10b98133'><a href='/dashboard-scan'><button class='btn-primary'>⚡ SCAN NOW ({method_name})</button></a><a href='/test-telegram' class='btn-secondary'>🧪 Test</a><a href='/link-telegram' class='btn-secondary'>🔗 Link TG</a><a href='/export-journal' class='btn-secondary'>📥 Export CSV</a>{admin_link}</div>
</div>
<div style='max-width:1600px;margin:0 auto;padding:0 10px 10px'><div class='table-card'><div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap'><h3 style='margin:0;font-size:13px'>Recent • {curr_sym}{stats['daily']:.2f} Today • {method_name}</h3><span style='font-size:9px;color:#94a3b8'>{stats['wins']}W / {stats['losses']}L / {stats['win_rate']}%</span></div><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th><th>PnL</th></tr>{rows}</table></div></div>
"""
    return pro_layout(content,"Dashboard", is_admin=is_admin)

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
            "spread_forex":float(request.form.get("spread_forex",0.7)),
            "spread_gold":float(request.form.get("spread_gold",0.35)),
            "spread_indices":float(request.form.get("spread_indices",2.0)),
            "spread_crypto":float(request.form.get("spread_crypto",10.0)),
            "currency":request.form.get("currency","ZAR"),
            "trading_method":request.form.get("trading_method","method1_premium_sweep"),
            "sessions":request.form.getlist("sessions") or ["London"],
            "symbols":request.form.getlist("symbols") or ALL_SYMBOLS[:10]
        }
        rr_def=METHODS.get(new_settings["trading_method"], METHODS["method1_premium_sweep"])["rr_default"]
        if "rr_ratio" not in request.form: new_settings["rr_ratio"]=rr_def
        save_user_settings(email,new_settings)
        return redirect("/settings")
    s=get_user_settings(email)
    symbols_html="".join([f"<label style='display:flex;align-items:center;gap:5px;background:#0f172a;border:1px solid #1e293b;padding:6px 8px;border-radius:6px;font-size:9px'><input type='checkbox' name='symbols' value='{sym}' {'checked' if sym in s.get('symbols',[]) else ''}> {sym}</label>" for sym in ALL_SYMBOLS])
    sessions_html="".join([f"<label style='display:flex;align-items:center;gap:5px;background:#0f172a;border:1px solid #1e293b;padding:6px 8px;border-radius:6px;font-size:9px'><input type='checkbox' name='sessions' value='{ses}' {'checked' if ses in s.get('sessions',[]) else ''}> {ses}</label>" for ses in ["Asia","London","New York"]])
    rr=s.get('rr_ratio',2.5); trade_checked="checked" if s.get('trade_news',True) else ""
    curr=s.get('currency','ZAR'); method=s.get('trading_method','method1_premium_sweep')
    currency_options="".join([f"<option value='{code}' {'selected' if curr==code else ''}>{code} - {info['symbol']} {info['name']}</option>" for code,info in CURRENCY_MAP.items()])
    method_options="".join([f"<option value='{key}' {'selected' if method==key else ''}>{val['name']} - RR 1:{val['rr_default']} - {val['desc'][:60]}</option>" for key,val in METHODS.items()])
    content=f"""
<div style='max-width:1000px;margin:0 auto;padding:10px'>
<h1 style='font-size:16px'>⚙️ Settings • Currency + Trading Method + Spread + RR</h1>
<form method='post'>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px'>
<div class='card' style='border:2px solid #10b981'><div class='card-title'>💰 Currency Selector - FIRST</div><select name='currency' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;background:#0f172a;color:white;border:1px solid #10b981'>{currency_options}</select><div style='font-size:9px;color:#94a3b8;margin-top:4px'>ZAR=R, USD=$, EUR=€, GBP=£ - Affects all PnL display</div></div>
<div class='card' style='border:2px solid #f59e0b'><div class='card-title'>📊 Trading Method Selector</div><select name='trading_method' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;background:#0f172a;color:white;border:1px solid #f59e0b'>{method_options}</select><div style='font-size:9px;color:#94a3b8;margin-top:4px'>Current: {METHODS.get(method, METHODS['method1_premium_sweep'])['desc']}</div></div>
</div>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;margin-top:8px'>
<div class='card'><div class='card-title'>Account Size ({CURRENCY_MAP.get(curr, CURRENCY_MAP['ZAR'])['symbol']})</div><input name='account_size' type='number' step='0.01' value='{s.get('account_size',142)}' style='width:100%;padding:10px;margin-top:6px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'></div>
<div class='card'><div class='card-title'>Lot Size</div><input name='lot_size' type='number' step='0.01' value='{s.get('lot_size',0.01)}' style='width:100%;padding:10px;margin-top:6px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'></div>
<div class='card'><div class='card-title'>Leverage</div><select name='leverage' style='width:100%;padding:10px;margin-top:6px;border-radius:8px;background:#0f172a;color:white;border:1px solid #334155'><option value='1:100' {'selected' if s.get('leverage')=='1:100' else ''}>1:100</option><option value='1:200' {'selected' if s.get('leverage')=='1:200' else ''}>1:200</option><option value='1:500' {'selected' if s.get('leverage')=='1:500' else ''}>1:500</option><option value='1:1000' {'selected' if s.get('leverage')=='1:1000' else ''}>1:1000</option></select></div>
<div class='card'><div class='card-title'>Risk %</div><input name='risk_percent' type='number' step='0.1' value='{s.get('risk_percent',1)}' style='width:100%;padding:10px;margin-top:6px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'></div>
</div>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;margin-top:8px'>
<div class='card'><div class='card-title'>RR Ratio - Changeable</div><select name='rr_ratio' style='width:100%;padding:10px;margin-top:6px;border-radius:8px;background:#0f172a;color:white;border:1px solid #334155'><option value='1.5' {'selected' if str(rr)=='1.5' else ''}>1:1.5 Scalp</option><option value='2' {'selected' if str(rr)=='2' else ''}>1:2</option><option value='2.5' {'selected' if str(rr)=='2.5' else ''}>1:2.5 Recommended</option><option value='3' {'selected' if str(rr)=='3' else ''}>1:3 SMC</option><option value='4' {'selected' if str(rr)=='4' else ''}>1:4 Runner</option></select></div>
<div class='card'><div class='card-title'>Trade News?</div><label style='display:flex;gap:6px;align-items:center;background:#0f172a;padding:10px;border-radius:8px;margin-top:6px'><input type='checkbox' name='trade_news' value='yes' {trade_checked}><span style='font-size:11px'>Trade NFP/CPI/FOMC</span></label></div>
</div>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;margin-top:8px'>
<div class='card' style='border:1px solid #f59e0b44'><div class='card-title'>Spread Forex pips</div><input name='spread_forex' type='number' step='0.1' value='{s.get('spread_forex',0.7)}' style='width:100%;padding:10px;margin-top:6px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'></div>
<div class='card' style='border:1px solid #f59e0b44'><div class='card-title'>Spread Gold $</div><input name='spread_gold' type='number' step='0.01' value='{s.get('spread_gold',0.35)}' style='width:100%;padding:10px;margin-top:6px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'></div>
<div class='card' style='border:1px solid #f59e0b44'><div class='card-title'>Spread Indices pts</div><input name='spread_indices' type='number' step='0.1' value='{s.get('spread_indices',2.0)}' style='width:100%;padding:10px;margin-top:6px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'></div>
<div class='card' style='border:1px solid #f59e0b44'><div class='card-title'>Spread Crypto $</div><input name='spread_crypto' type='number' step='0.1' value='{s.get('spread_crypto',10.0)}' style='width:100%;padding:10px;margin-top:6px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'></div>
</div>
<div class='card' style='margin-top:8px'><div class='card-title'>Sessions</div><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(90px,1fr));gap:6px;margin-top:6px'>{sessions_html}</div></div>
<div class='card' style='margin-top:8px'><div class='card-title'>Symbols 31 Total</div><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(80px,1fr));gap:5px;max-height:350px;overflow-y:auto;margin-top:6px'>{symbols_html}</div></div>
<button type='submit' class='btn-primary' style='margin-top:14px'>💾 SAVE - Currency {curr} + Method + Spread</button>
</form>
</div>
"""
    return pro_layout(content,"Settings", is_admin=is_admin)

#... (keep all other routes same as V19.9 but with currency_symbol)
# For brevity, reusing previous routes with currency added - paste remaining routes from V19.9 here
# Dashboard-scan, send-signal, test-telegram, webhook, login, register, journal, export, link-telegram, plans, guide, creator, pay, referral, cron, health

@app.route("/all-signals")
@app.route("/dashboard-scan")
def dashboard_scan():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"
    user_settings=get_user_settings(email)
    symbols_to_scan=user_settings.get("symbols", ALL_SYMBOLS[:12])
    q=request.args.get("q","").upper()
    if q: symbols_to_scan=[s for s in ALL_SYMBOLS if q in s]
    method_key=user_settings.get("trading_method","method1_premium_sweep")
    method_name=METHODS.get(method_key, METHODS["method1_premium_sweep"])["name"]
    rows=""
    for s in symbols_to_scan[:30]:
        try:
            r=eng.full_multi_tf_analysis(s, user_settings)
            score=r.get('score',0); bias=r.get('bias','NEUTRAL'); entry=r.get('entry',0)
            entry_display=f"{float(entry):.5f}" if entry and float(entry)<20 else f"{float(entry):.2f}" if entry else "0"
            premium=r.get('premium_pct',50)
            color="#10b981" if score>=7 else "#f59e0b" if score>=5 else "#ef4444"
            signal_btn=f"<a href='/send-signal?symbol={s}' style='background:#10b981;color:white;padding:5px 10px;border-radius:6px;text-decoration:none;font-weight:700;font-size:10px'>Send TG</a>" if r.get('signal') else f"<span style='color:#64748b;font-size:9px'>{r.get('reason','')[:45]}</span>"
            rows+=f"<tr><td style='font-weight:800'>{s}<br><span style='font-size:8px;color:#10b981'>{entry_display} | {premium:.0f}%</span></td><td><span style='background:{color}22;color:{color};padding:3px 6px;border-radius:20px;font-weight:800;font-size:9px'>{score}/10</span></td><td style='font-size:9px'>{bias}</td><td style='font-size:9px'>{'STRONG' if r.get('signal') else 'Wait'}</td><td>{signal_btn}</td></tr>"
        except Exception as e:
            rows+=f"<tr><td>{s}</td><td colspan=4 style='color:#ef4444;font-size:9px'>{str(e)[:50]}</td></tr>"
    content=f"<div style='max-width:1600px;margin:0 auto;padding:10px'><div class='table-card'><h2 style='font-size:12px'>Signals • Method: {method_name} • RR 1:{user_settings.get('rr_ratio',2.5)} • {len(symbols_to_scan)} Pairs</h2><div style='overflow-x:auto'><table><tr><th>Symbol</th><th>Score</th><th>Bias</th><th>Signal</th><th>Action</th></tr>{rows}</table></div></div></div>"
    return pro_layout(content,"All Signals", is_admin=is_admin)

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
        curr_sym=get_currency_symbol(user_set.get("currency","ZAR"))
        method_key=user_set.get("trading_method","method1_premium_sweep")
        method_name=METHODS.get(method_key, METHODS["method1_premium_sweep"])["name"]
        sl,tp,sl_dist,tp_dist,risk_amt=calculate_dynamic_sl_tp(sym, entry, r.get('bias',''), acc, lot, lev, risk_percent, rr, user_set.get('spread_forex',0.7), user_set.get('spread_gold',0.35), user_set.get('spread_indices',2.0), user_set.get('spread_crypto',10.0))
        confluence=r.get('confluence', r.get('reason',''))
        res=send_telegram_pro(sym, r.get('score',0), r.get('bias',''), entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot, lev, acc, confluence, curr_sym, method_name)
        msg=f"Sent {sym} {entry} SL {sl} TP {tp} RR 1:{rr} {curr_sym} {method_name}"
        tracked=load_json(TRACK_FILE, dict)
        tracked[sym]={"time":datetime.now().isoformat(),"bias":r.get('bias'),"entry":entry,"sl":sl,"tp":tp,"risk_amt":risk_amt,"rr":rr,"score":r.get('score'),"currency":user_set.get("currency","ZAR"),"method":method_key}
        save_json(TRACK_FILE, tracked)
    except Exception as e:
        res={"error":str(e)}; msg=f"Error {sym}: {e}"
    return f"<html><body style='background:#080c14;color:white;padding:20px'><div style='max-width:700px;margin:auto;background:#1e293b;padding:16px;border-radius:14px'><h2 style='font-size:14px'>{msg}</h2><p style='font-size:10px;background:#0f172a;padding:8px;border-radius:6px;word-break:break-all'>{str(res)[:2000]}</p><a href='/all-signals' style='background:#10b981;color:white;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:11px'>Back</a></div></body></html>"

@app.route("/test-telegram")
def test_telegram():
    email=session.get("user") or "admin@agent35.com"; user_set=get_user_settings(email)
    r=eng.full_multi_tf_analysis("GBPUSD", user_set); entry=r.get('entry',0)
    if not entry or float(entry)==0: entry=1.35057; r={"score":8,"bias":"BEARISH","confluence":"Test","details":{}}
    rr=user_set.get('rr_ratio',2.5); risk_percent=user_set.get('risk_percent',1); lot=user_set.get('lot_size',0.01); lev=user_set.get('leverage','1:500'); acc=user_set.get('account_size',142)
    curr_sym=get_currency_symbol(user_set.get("currency","ZAR"))
    method_key=user_set.get("trading_method","method1_premium_sweep")
    method_name=METHODS.get(method_key, METHODS["method1_premium_sweep"])["name"]
    sl,tp,sl_dist,tp_dist,risk_amt=calculate_dynamic_sl_tp("GBPUSD", entry, r.get('bias','BEARISH'), acc, lot, lev, risk_percent, rr, user_set.get('spread_forex',0.7), user_set.get('spread_gold',0.35), user_set.get('spread_indices',2.0), user_set.get('spread_crypto',10.0))
    res=send_telegram_pro("GBPUSD", r.get('score',8), r.get('bias','BEARISH'), entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot, lev, acc, r.get('confluence','Test'), curr_sym, method_name)
    return f"<html><body style='background:#080c14;color:white;padding:20px'><div style='max-width:700px;margin:auto;background:#1e293b;padding:16px;border-radius:14px'><h2 style='font-size:13px'>Test {entry} SL {sl} TP {tp} {curr_sym} RR 1:{rr} {method_name}</h2><p style='font-size:10px;background:#0f172a;padding:8px;border-radius:6px'>{str(res)[:2000]}</p><a href='/dashboard' style='background:#10b981;color:white;padding:8px 16px;border-radius:8px;text-decoration:none'>Back</a></div></body></html>"

# Include remaining routes: webhook, login, register, journal, export, link-telegram, plans, guide, creator, pay, referral, cron, health as in V19.9 but with currency

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
            try: requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":f"AGENT 35 V20\nChat ID: {chat_id}\nPaste in Dashboard > Link TG Manual\nCurrency + Methods ready"}, timeout=5)
            except: pass
    if "callback_query" in data:
        cb=data["callback_query"]; cb_data=cb.get("data",""); cb_id=cb.get("id"); chat_id=cb["message"]["chat"]["id"]; user_name=cb["from"].get("first_name","User")
        journal=load_json(JOURNAL_FILE, list); tracked=load_json(TRACK_FILE, dict); text="OK"
        if cb_data.startswith("TOOK_"):
            parts=cb_data.split("_"); sym=parts[1]; entry=parts[2] if len(parts)>2 else ""
            risk_amt=0; rr=2.5; sl=0; tp=0; curr="ZAR"; meth=""
            if sym in tracked:
                risk_amt=tracked[sym].get("risk_amt",0); rr=tracked[sym].get("rr",2.5); sl=tracked[sym].get("sl",0); tp=tracked[sym].get("tp",0); curr=tracked[sym].get("currency","ZAR"); meth=tracked[sym].get("method","")
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"TOOK","result":f"Taken by {user_name} {meth[:8]}","pnl":0,"entry":entry,"sl":sl,"tp":tp,"risk_amt":risk_amt,"rr":rr,"date":datetime.now().strftime("%Y-%m-%d"),"currency":curr})
            save_json(JOURNAL_FILE, journal[-500:]); text=f"TOOK {sym} {entry}"
        elif cb_data.startswith("SKIP_"):
            sym=cb_data.split("_")[1]
            journal.append({"time":datetime.now().strftime("%m-%d %H:%M"),"symbol":sym,"status":"MISS","result":f"Skipped by {user_name}","pnl":0,"date":datetime.now().strftime("%Y-%m-%d")})
            save_json(JOURNAL_FILE, journal[-500:]); text=f"SKIP {sym}"
        if bot:
            try:
                requests.post(f"https://api.telegram.org/bot{bot}/answerCallbackQuery", json={"callback_query_id":cb_id,"text":text}, timeout=5)
                requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":text}, timeout=5)
            except: pass
        return jsonify({"ok":True})
    return jsonify({"ok":True})

@app.route("/login")
def login_page(): return "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#080c14;color:white;font-family:Arial;padding:12px;min-height:100vh;display:flex;align-items:center;justify-content:center'><div style='width:100%;max-width:360px;background:#1e293b;padding:20px;border-radius:16px'><div style='text-align:center;margin-bottom:16px'><div style='font-weight:900;font-size:18px;color:#10b981'>AGENT 35 PRO V20</div><div style='font-size:9px;color:#94a3b8'>Currency + Methods</div></div><form action='/login/check' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:10px;margin:5px 0;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'><input name='password' type='password' placeholder='Password' required style='width:100%;padding:10px;margin:5px 0;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'><button style='background:#10b981;color:white;padding:10px;width:100%;border:none;border-radius:8px;font-weight:800;margin-top:8px'>LOGIN</button></form></div></body></html>"

@app.route("/register")
def register_page():
    ref=request.args.get("ref","")
    ref_banner=f"<div style='background:#10b98122;border:1px solid #10b98144;padding:6px;border-radius:6px;font-size:10px;color:#10b981;margin-bottom:8px'>Referred by: {ref}</div>" if ref else ""
    return f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#080c14;color:white;font-family:Arial;padding:12px;min-height:100vh;display:flex;align-items:center;justify-content:center'><div style='width:100%;max-width:360px;background:#1e293b;padding:20px;border-radius:16px'><h2 style='font-size:16px'>Create Account</h2>{ref_banner}<form action='/register/create' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:10px;margin:4px 0;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'><input name='name' placeholder='Full Name' required style='width:100%;padding:10px;margin:4px 0;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'><input name='password' type='password' placeholder='Password' required style='width:100%;padding:10px;margin:4px 0;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'><input name='ref' value='{ref}' placeholder='Referral Code' style='width:100%;padding:10px;margin:4px 0;border-radius:8px;border:1px solid #10b98144;background:#0f172a;color:white'><button style='background:#10b981;color:white;padding:10px;width:100%;border:none;border-radius:8px;font-weight:800;margin-top:8px'>CREATE</button></form></div></body></html>"

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
    user_set=get_user_settings(email); curr_sym=get_currency_symbol(user_set.get("currency","ZAR"))
    stats=calculate_pnl_stats(journal)
    q=request.args.get("q","").upper(); filtered=[j for j in journal if q in j.get("symbol","").upper()] if q else journal
    period=request.args.get("period","all")
    now=datetime.now()
    if period=="today": filtered=[j for j in filtered if j.get("date")==now.strftime("%Y-%m-%d")]
    elif period=="week":
        week_start=(now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        filtered=[j for j in filtered if j.get("date","")>=week_start]
    elif period=="month": filtered=[j for j in filtered if j.get("date","").startswith(now.strftime("%Y-%m"))]
    elif period=="year": filtered=[j for j in filtered if j.get("date","").startswith(now.strftime("%Y"))]
    rows="".join([f"<tr><td>{j.get('time')}</td><td>{j.get('symbol')}</td><td>{j.get('status')}</td><td>{j.get('result')}</td><td>{curr_sym}{j.get('pnl',0)}</td><td>{j.get('date','')}</td></tr>" for j in reversed(filtered[-200:])])
    content=f"<div style='max-width:1400px;margin:0 auto;padding:10px'><h1 style='font-size:16px'>Journal • {len(filtered)} Trades • {curr_sym}{calculate_pnl_stats(filtered)['total_pnl']:.2f} • {calculate_pnl_stats(filtered)['win_rate']}% WR • {user_set.get('currency','ZAR')}</h1><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:6px;margin:10px 0'><div class='card'><div class='card-title'>Daily</div><div class='card-value' style='font-size:14px;color:{\"#10b981\" if stats['daily']>=0 else \"#ef4444\"}'>{curr_sym}{stats['daily']:.2f}</div></div><div class='card'><div class='card-title'>Weekly</div><div class='card-value' style='font-size:14px'>{curr_sym}{stats['weekly']:.2f}</div></div><div class='card'><div class='card-title'>Monthly</div><div class='card-value' style='font-size:14px'>{curr_sym}{stats['monthly']:.2f}</div></div><div class='card'><div class='card-title'>Yearly</div><div class='card-value' style='font-size:14px'>{curr_sym}{stats['yearly']:.2f}</div></div></div><div style='display:flex;gap:5px;flex-wrap:wrap;margin:10px 0'><a href='/journal?period=all' style='padding:6px 12px;border-radius:20px;text-decoration:none;font-size:10px;background:{\"#10b981\" if period==\"all\" else \"#1e293b\"};color:white'>All</a><a href='/journal?period=today' style='padding:6px 12px;border-radius:20px;text-decoration:none;font-size:10px;background:{\"#10b981\" if period==\"today\" else \"#1e293b\"};color:white'>Today</a><a href='/journal?period=week' style='padding:6px 12px;border-radius:20px;text-decoration:none;font-size:10px;background:{\"#10b981\" if period==\"week\" else \"#1e293b\"};color:white'>Week</a><a href='/journal?period=month' style='padding:6px 12px;border-radius:20px;text-decoration:none;font-size:10px;background:{\"#10b981\" if period==\"month\" else \"#1e293b\"};color:white'>Month</a><a href='/journal?period=year' style='padding:6px 12px;border-radius:20px;text-decoration:none;font-size:10px;background:{\"#10b981\" if period==\"year\" else \"#1e293b\"};color:white'>Year</a><a href='/export-journal' style='padding:6px 12px;border-radius:20px;text-decoration:none;font-size:10px;background:#f59e0b;color:white'>Export</a></div><div class='table-card'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th><th>PnL {curr_sym}</th><th>Date</th></tr>{rows}</table></div></div>"
    return pro_layout(content,"Journal", is_admin=is_admin)

@app.route("/export-journal")
def export_journal():
    if not session.get("user"): return redirect("/login")
    journal=load_json(JOURNAL_FILE, list)
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(["Time","Symbol","Status","Result","PnL","Date","Entry","SL","TP","RR","Risk","Currency","Method"])
    for j in journal: writer.writerow([j.get("time",""),j.get("symbol",""),j.get("status",""),j.get("result",""),j.get("pnl",0),j.get("date",""),j.get("entry",""),j.get("sl",""),j.get("tp",""),j.get("rr",""),j.get("risk_amt",""),j.get("currency","ZAR"),j.get("method","")])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=journal.csv"})

@app.route("/link-telegram", methods=["GET","POST"])
def link_telegram():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"; tg_users=load_json(TG_FILE, dict)
    if request.method=="POST":
        chat_id=request.form.get("chat_id","").strip()
        if chat_id:
            tg_users[email]={"chat_id":chat_id,"linked_at":datetime.now().isoformat(),"manual":True}
            save_json(TG_FILE, tg_users); return redirect("/dashboard")
    current=tg_users.get(email,{}).get("chat_id","Not linked")
    content=f"<div style='max-width:600px;margin:0 auto;padding:10px'><div class='card'><h2 style='font-size:14px'>🔗 Link Telegram Manual</h2><div style='background:#0f172a;padding:8px;border-radius:8px;font-size:10px;margin:8px 0'>Current: {current}</div><a href='https://t.me/Sniper035_bot' target='_blank' style='background:#0088cc;color:white;padding:10px;border-radius:8px;text-align:center;display:block;text-decoration:none;font-weight:800;margin:8px 0'>Open @Sniper035_bot /start</a><form method='post'><input name='chat_id' placeholder='Paste Chat ID' style='width:100%;padding:10px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white' required><button type='submit' style='background:#10b981;color:white;padding:10px;width:100%;border:none;border-radius:8px;font-weight:800;margin-top:6px'>Save</button></form></div></div>"
    return pro_layout(content,"Settings", is_admin=is_admin)

@app.route("/plans")
def plans_page():
    is_admin=session.get("user")=="admin@agent35.com"
    user_set=get_user_settings(session.get("user","admin@agent35.com")); curr_sym=get_currency_symbol(user_set.get("currency","ZAR"))
    content=f"""
<div style='max-width:900px;margin:0 auto;padding:10px'>
<h1 style='font-size:18px'>💳 Plans • {curr_sym} Currency Supported • Capitec 2586572676</h1>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-top:10px'>
<div class='card'><h3>📅 Yearly {curr_sym}500</h3><div style='font-size:24px;font-weight:900;color:#10b981'>{curr_sym}500/year</div><ul style='font-size:11px;color:#94a3b8;line-height:1.7;padding-left:14px;margin:10px 0'><li>31 Symbols + 5 Methods selectable</li><li>Currency ZAR/USD/EUR/GBP</li><li>Spread included SL/TP</li><li>Daily/Weekly/Monthly PnL {curr_sym}</li><li>Auto Track WIN/LOSS</li><li>Mobile Adaptive</li></ul><a href='/pay?plan=yearly' style='background:#10b981;color:white;padding:10px;border-radius:8px;text-align:center;display:block;text-decoration:none;font-weight:800'>Get Yearly</a></div>
<div class='card' style='border:2px solid #f59e0b'><div style='background:#f59e0b;color:white;padding:3px 8px;border-radius:20px;font-size:9px;font-weight:800;display:inline-block'>POPULAR</div><h3>♾️ Lifetime {curr_sym}5000</h3><div style='font-size:24px;font-weight:900;color:#f59e0b'>{curr_sym}5000</div><ul style='font-size:11px;color:#94a3b8;line-height:1.7;padding-left:14px;margin:10px 0'><li>All Yearly + Lifetime updates</li><li>All 5 Methods + Future Methods Free</li><li>All Currencies Free</li><li>No Renewal Ever</li></ul><a href='/pay?plan=lifetime' style='background:#f59e0b;color:white;padding:10px;border-radius:8px;text-align:center;display:block;text-decoration:none;font-weight:800'>Get Lifetime</a></div>
</div>
<div class='card' style='margin-top:10px'><h3>🏦 Capitec 2586572676</h3><div style='background:#0f172a;padding:10px;border-radius:8px;font-size:11px'>Bank: Capitec | Acc: 2586572676 | Ref: A35-XXXX | Currency: You can pay in {curr_sym} equivalent</div></div>
</div>
"""
    return pro_layout(content,"Plans", is_admin=is_admin)

@app.route("/guide")
def guide_page():
    is_admin=session.get("user")=="admin@agent35.com"
    content="""
<div style='max-width:800px;margin:0 auto;padding:10px'>
<h1 style='font-size:16px'>📖 Guide V20 - Currency + Methods</h1>
<div style='display:grid;gap:8px;margin-top:10px'>
<div class='card' style='border-left:3px solid #10b981'><h3 style='font-size:12px'>1. Currency FIRST</h3><p style='font-size:10px;color:#94a3b8'>Settings → Currency Selector → ZAR=R, USD=$, EUR=€, GBP=£. All PnL, Dashboard, Telegram will show in that currency. If you have R142 account choose ZAR, $100 choose USD.</p></div>
<div class='card' style='border-left:3px solid #f59e0b'><h3 style='font-size:12px'>2. Trading Method</h3><p style='font-size:10px;color:#94a3b8'>Settings → Trading Method: Method1 Premium/Sweep (safe, 65% WR), Method2 EMA+RSI (more signals), Method3 Breakout (US30), Method4 Scalp M5 (R142 small account, 1:1.5 RR, 10-20/day), Method5 SMC OB+BOS (advanced 70% WR). Each method has different RR default.</p></div>
<div class='card' style='border-left:3px solid #10b981'><h3 style='font-size:12px'>3. Spread + RR + Risk</h3><p style='font-size:10px;color:#94a3b8'>Enter broker spread: Forex 0.7 pips, Gold 0.35$. Bot adds spread to SL, subtracts from TP. RR changeable 1:1.5 to 1:4. Risk % 1% recommended.</p></div>
<div class='card' style='border-left:3px solid #3b82f6'><h3 style='font-size:12px'>4. First Signal</h3><p style='font-size:10px;color:#94a3b8'>Scan Now → All Signals shows entry + method. Telegram sends with currency symbol + method name. TOOK ENTRY → Journal logs with currency. Auto track hits SL/TP → WIN/LOSS auto + PnL in your currency.</p></div>
</div>
</div>
"""
    return pro_layout(content,"Guide", is_admin=is_admin)

@app.route("/creator")
def creator_dashboard():
    secret=request.args.get("secret",""); users=load_json(USERS_FILE)
    pending={k:v for k,v in users.items() if v.get("status")=="pending"}
    pending_rows="".join([f"<tr><td style='font-size:9px'>{ref}</td><td style='font-size:9px'>{pay.get('user','')[:20]}</td><td>R{pay.get('price','')}</td><td><a href='/creator/action?act=approve_payment&ref={ref}&secret={secret}' style='background:#10b981;color:white;padding:5px 8px;border-radius:5px;text-decoration:none;font-size:9px'>APPROVE</a></td></tr>" for ref,pay in pending.items()]) or "<tr><td colspan=4 style='text-align:center;color:#64748b'>No pending</td></tr>"
    content=f"<div style='max-width:1600px;margin:0 auto;padding:10px'><h1 style='font-size:16px'>Creator V20 Currency+Methods</h1><div class='table-card'><h3 style='font-size:12px'>PENDING ({len(pending)})</h3><table><tr><th>Ref</th><th>Email</th><th>Price</th><th>Action</th></tr>{pending_rows}</table></div></div>"
    return pro_layout(content,"Master", is_admin=True)

@app.route("/creator/action")
def creator_action():
    secret=request.args.get("secret",""); act=request.args.get("act",""); auth=load_json(AUTH_FILE); users=load_json(USERS_FILE)
    if act=="approve_payment":
        ref=request.args.get("ref","")
        if ref in users:
            users[ref]["status"]="active"; users[ref]["expires"]=(datetime.now()+timedelta(days=PLANS.get(users[ref].get('plan','yearly'),PLANS['yearly'])['days'])).isoformat()
            email=users[ref].get("user")
            if email in auth:
                auth[email]["plan_status"]=f"ACTIVE {users[ref].get('plan','yearly')}"; auth[email]["expires"]=users[ref]["expires"]
            save_json(USERS_FILE, users); save_json(AUTH_FILE, auth)
        return redirect(f"/creator?secret={secret}")
    return redirect(f"/creator?secret={secret}")

@app.route("/pay")
def pay_page():
    plan=request.args.get("plan","yearly")
    ref=request.args.get("ref",""); email=session.get("user","")
    price=PLANS.get(plan,PLANS["yearly"])["price"]
    content=f"<div style='max-width:500px;margin:0 auto;padding:10px'><div class='card'><h2 style='font-size:14px'>Buy {plan.upper()} R{price}</h2><form action='/pay/create' method='get'><input type='hidden' name='ref' value='{ref}'><input name='user' value='{email}' placeholder='Email' required style='width:100%;padding:10px;margin:4px 0;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'><input name='phone' placeholder='WhatsApp' required style='width:100%;padding:10px;margin:4px 0;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'><select name='plan' style='width:100%;padding:10px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:white'><option value='yearly' {'selected' if plan=='yearly' else ''}>Yearly R500</option><option value='lifetime' {'selected' if plan=='lifetime' else ''}>Lifetime R5000</option></select><button style='background:#10b981;color:white;padding:10px;width:100%;border:none;border-radius:8px;margin-top:8px;font-weight:800'>GET REF - Capitec 2586572676</button></form></div></div>"
    return pro_layout(content,"Plans", is_admin=session.get("user")=="admin@agent35.com")

@app.route("/pay/create")
def pay_create():
    user=request.args.get("user","").lower().strip(); phone=request.args.get("phone","").strip()
    plan_key=request.args.get("plan","yearly"); ref=request.args.get("ref","").upper().strip()
    short="".join([c for c in user.upper() if c.isalnum()])[:5] or "USER"; rand="".join(random.choices(string.digits,k=3)); pref=f"A35-{short}-{rand}"
    plan=PLANS.get(plan_key, PLANS["yearly"]); users=load_json(USERS_FILE)
    users[pref]={"user":user,"phone":phone,"plan":plan_key,"price":plan["price"],"payment_ref":pref,"referred_by":ref,"status":"pending","created":datetime.now().isoformat(),"expires":None}
    save_json(USERS_FILE, users)
    return f"<html><body style='background:#080c14;color:white;padding:20px;text-align:center'><div style='max-width:460px;margin:auto;background:#1e293b;padding:20px;border-radius:14px'><h1 style='font-size:16px'>Pay R{plan['price']} Capitec 2586572676</h1><h1 style='background:white;color:black;padding:12px;border-radius:8px;font-size:18px'>{pref}</h1><a href='/dashboard' style='background:#10b981;color:white;padding:8px 16px;border-radius:8px;text-decoration:none;display:inline-block;margin-top:10px'>Back</a></div></body></html>"

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
    refs_html="".join([f"<tr><td style='font-size:9px'>{r['email'][:22]}</td><td style='font-size:9px'>{r['status']}</td><td style='font-size:9px'>{r['plan'][:18]}</td></tr>" for r in my_refs]) or "<tr><td colspan=3 style='text-align:center;color:#64748b;font-size:10px'>No refs</td></tr>"
    link=f"https://agent-35-trading-bot.onrender.com/register?ref={my_code}"
    free_banner="<div style='background:#10b981;color:white;padding:8px;border-radius:8px;text-align:center;font-weight:800;margin-top:8px;font-size:11px'>FREE LIFETIME UNLOCKED!</div>" if paid_count>=10 else ""
    content=f"<div style='max-width:900px;margin:0 auto;padding:10px'><h1 style='font-size:16px'>Referral 10=Free</h1><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px'><div class='card'><div class='card-title'>Code</div><div style='background:white;color:black;padding:10px;border-radius:8px;font-weight:900;font-size:18px;text-align:center;margin:8px 0'>{my_code}</div><div style='background:#0f172a;padding:6px;border-radius:6px;font-size:8px;word-break:break-all'>{link}</div></div><div class='card'><div class='card-title'>Progress {paid_count}/10</div><div style='background:#0f172a;border-radius:20px;height:10px;overflow:hidden;margin:8px 0'><div style='background:#10b981;width:{progress}%;height:100%'></div></div>{free_banner}</div></div><div class='table-card' style='margin-top:10px'><h3 style='font-size:12px'>Refs ({len(my_refs)})</h3><table><tr><th>Email</th><th>Status</th><th>Plan</th></tr>{refs_html}</table></div></div>"
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
    journal=load_json(JOURNAL_FILE, list)
    all_syms=set()
    for s in settings_all.values(): all_syms.update(s.get("symbols",[]))
    if not all_syms: all_syms=set(ALL_SYMBOLS[:12])
    sent=[]; skipped=[]; auto_closed=[]; now=datetime.now()
    cleaned={}
    for k,v in tracked.items():
        try:
            t=datetime.fromisoformat(v.get("time","2000-01-01T00:00:00"))
            if (now - t).total_seconds() < 86400: cleaned[k]=v
        except: pass
    if len(cleaned)!=len(tracked):
        tracked=cleaned; save_json(TRACK_FILE, tracked)
    for sym, info in list(tracked.items())[:10]:
        try:
            if "sl" not in info or "tp" not in info: continue
            sl=float(info.get("sl",0)); tp=float(info.get("tp",0)); entry=float(info.get("entry",0)); bias=info.get("bias","")
            if sl==0 or tp==0 or entry==0: continue
            current_data=eng.td_request(sym,"5min")
            if "values" not in current_data: continue
            current_price=float(current_data["values"][0]["close"])
            is_buy="BULLISH" in bias.upper() or "BUY" in bias.upper()
            hit=None
            if is_buy:
                if current_price>=tp: hit="WIN"
                elif current_price<=sl: hit="LOSS"
            else:
                if current_price<=tp: hit="WIN"
                elif current_price>=sl: hit="LOSS"
            if hit:
                risk_amt=info.get("risk_amt",10); rr=info.get("rr",2.5)
                pnl=risk_amt*rr if hit=="WIN" else -risk_amt
                journal.append({"time":now.strftime("%m-%d %H:%M"),"symbol":sym,"status":"TOOK","result":f"{hit} AUTO {info.get('method','')[:8]}","pnl":round(pnl,2),"entry":entry,"sl":sl,"tp":tp,"risk_amt":risk_amt,"rr":rr,"date":now.strftime("%Y-%m-%d"),"currency":info.get("currency","ZAR")})
                auto_closed.append(f"{sym} {hit} {pnl:.2f}"); del tracked[sym]
        except: pass
    if auto_closed:
        save_json(JOURNAL_FILE, journal[-500:]); save_json(TRACK_FILE, tracked)
    for sym in list(all_syms)[:20]:
        try:
            sample_settings = next(iter(settings_all.values())) if settings_all else {"trade_news":True,"risk_percent":1,"rr_ratio":2.5,"lot_size":0.01,"leverage":"1:500","account_size":142,"spread_forex":0.7,"spread_gold":0.35,"spread_indices":2.0,"spread_crypto":10.0,"currency":"ZAR","trading_method":"method1_premium_sweep"}
            r=eng.full_multi_tf_analysis(sym, sample_settings)
            if not r.get('signal') or not r.get('entry') or float(r.get('entry'))==0: continue
            last_info=tracked.get(sym)
            if last_info:
                try:
                    last_time=datetime.fromisoformat(last_info.get("time","2000-01-01T00:00:00"))
                    last_bias=last_info.get("bias",""); hours_since=(now-last_time).total_seconds()/3600
                    if last_bias==r.get('bias') and hours_since<4: skipped.append(f"{sym} {last_bias} {hours_since:.1f}h"); continue
                    if hours_since<1: skipped.append(f"{sym} 1h"); continue
                except: pass
            entry=r.get('entry'); rr=sample_settings.get('rr_ratio',2.5); risk_percent=sample_settings.get('risk_percent',1); lot=sample_settings.get('lot_size',0.01); lev=sample_settings.get('leverage','1:500'); acc=sample_settings.get('account_size',142)
            sl,tp,sl_dist,tp_dist,risk_amt=calculate_dynamic_sl_tp(sym, entry, r.get('bias',''), acc, lot, lev, risk_percent, rr, sample_settings.get('spread_forex',0.7), sample_settings.get('spread_gold',0.35), sample_settings.get('spread_indices',2.0), sample_settings.get('spread_crypto',10.0))
            curr_sym=get_currency_symbol(sample_settings.get("currency","ZAR"))
            method_key=sample_settings.get("trading_method","method1_premium_sweep")
            method_name=METHODS.get(method_key, METHODS["method1_premium_sweep"])["name"]
            confluence=r.get('confluence', r.get('reason',''))
            send_telegram_pro(sym, r.get('score',7), r.get('bias',''), entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot, lev, acc, confluence, curr_sym, method_name)
            tracked[sym]={"time":now.isoformat(),"bias":r.get('bias'),"entry":entry,"sl":sl,"tp":tp,"risk_amt":risk_amt,"rr":rr,"score":r.get('score'),"currency":sample_settings.get("currency","ZAR"),"method":method_key}
            save_json(TRACK_FILE, tracked); sent.append(f"{sym} {method_key[:8]}")
        except Exception as e: print(f"Scan error {sym}: {e}")
    return jsonify({"sent":sent,"skipped":skipped,"auto_closed":auto_closed,"scanned":len(all_syms),"tracked_count":len(tracked)})

@app.route("/health")
def health():
    test=eng.full_multi_tf_analysis("GBPUSD", {"trade_news":True,"spread_forex":0.7,"spread_gold":0.35,"currency":"ZAR","trading_method":"method1_premium_sweep"})
    tracked=load_json(TRACK_FILE, dict); journal=load_json(JOURNAL_FILE, list); stats=calculate_pnl_stats(journal)
    return jsonify({"ok":True,"version":"V20 Currency+5 Methods","entry":test.get('entry'),"score":test.get('score'),"bias":test.get('bias'),"method":test.get('method'),"tracked":len(tracked),"stats":stats})

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000)
