from flask import Flask, request, jsonify, session, redirect, Response
import os, json, hashlib, requests, random, string, csv, io, threading
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "agent35-v21-pro-ui")
import trading_engine as eng

BASE_DIR = "/data" if os.path.exists("/data") else "."
BACKUP_URL = os.getenv("DATA_BACKUP_URL", "https://api.npoint.io/1e8f3c2a9b4d6e5f7a8c")
MAX_TRACKED = 6

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

ALL_SYMBOLS = ["EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD","EURJPY","GBPJPY","EURGBP","AUDJPY","CADJPY","CHFJPY","EURCHF","GBPCHF","EURAUD","GBPAUD","EURCAD","GBPCAD","EURNZD","GBPNZD","AUDNZD","AUDCAD","NZDCAD","AUDCHF","NZDJPY","XAUUSD","XAGUSD","XTIUSD","XBRUSD","US30","NAS100","SPX500","GER40","UK100","FRA40","ESP35","ITA40","JPN225","AUS200","BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD","ADAUSD","DOGEUSD","DOTUSD","AVAXUSD","LINKUSD","MATICUSD","LTCUSD"]
CURRENCY_MAP = {"ZAR":{"symbol":"R","name":"Rand"},"USD":{"symbol":"$","name":"Dollar"},"EUR":{"symbol":"€","name":"Euro"},"GBP":{"symbol":"£","name":"Pound"}}
METHODS = {
    "method1_premium_sweep":{"name":"Premium + Sweep + Engulfing","desc":"Best for Gold/Forex H1. High win rate 65%+, 2-5 signals/day. RR 1:2.5","rr_default":2.5},
    "method2_ema_rsi":{"name":"EMA + RSI Pullback","desc":"Trend continuation. 5-10 signals/day. BUY when EMA5>EMA20 + RSI 40-55","rr_default":2.0},
    "method3_breakout_retest":{"name":"Breakout + Retest","desc":"Best for US30/NAS100/BTC. Breaks high/low + retest + engulf","rr_default":2.0},
    "method4_scalp_m5":{"name":"Scalp M5 Fast","desc":"10-20 signals/day. M5 EMA9/21 cross + RSI. Best for R142 small accounts","rr_default":1.5},
    "method5_smc_ob_bos":{"name":"SMC Order Block + BOS","desc":"Advanced SMC - BOS + Order Block + FVG. 70%+ WR. Best for BTC","rr_default":3.0}
}

def load_json(p, dt=dict):
    if not os.path.exists(p): return {} if dt==dict else []
    try:
        with open(p,"r") as f: return json.load(f)
    except: return {} if dt==dict else []

def save_json(p, data):
    os.makedirs(os.path.dirname(p) if os.path.dirname(p) else ".", exist_ok=True)
    with open(p,"w") as f: json.dump(data,f,indent=2)
    if BACKUP_URL:
        def do_backup():
            try:
                all_data = {}
                for fname in ["auth_users.json","users_data.json","referrals.json","ref_codes.json","journal.json","tracked_trades.json","system_status.json","user_settings.json","telegram_users.json","temp_chats.json"]:
                    fp = os.path.join(BASE_DIR, fname)
                    if os.path.exists(fp):
                        try:
                            with open(fp,"r") as ff: all_data[fname] = json.load(ff)
                        except: pass
                requests.post(BACKUP_URL, json=all_data, timeout=15)
            except: pass
        threading.Thread(target=do_backup, daemon=True).start()

def remote_restore():
    if not BACKUP_URL: return False
    try:
        if os.path.exists(AUTH_FILE) and os.path.getsize(AUTH_FILE) > 50:
            d = load_json(AUTH_FILE, dict)
            if len(d) > 1: return False
        r = requests.get(BACKUP_URL, timeout=15)
        if r.status_code!=200: return False
        remote = r.json()
        if not remote or not isinstance(remote, dict): return False
        for fname, content in remote.items():
            if not fname.endswith(".json"): continue
            dst = os.path.join(BASE_DIR, fname)
            try:
                with open(dst,"w") as f: json.dump(content, f, indent=2)
            except: pass
        return True
    except: return False

def hash_pwd(p): return hashlib.sha256(p.encode()).hexdigest()
def ensure_files():
    remote_restore()
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

def get_currency_symbol(code): return CURRENCY_MAP.get(code, CURRENCY_MAP["ZAR"])["symbol"]
def save_user_settings(email, new_settings):
    s = load_json(SETTINGS_FILE, dict); s[email] = new_settings; save_json(SETTINGS_FILE, s)

def generate_ref_code(email):
    code_file = load_json(REF_CODE_FILE, dict)
    if email in code_file: return code_file[email]
    base = "".join([c for c in email.upper().split('@')[0] if c.isalnum()])[:5]
    if len(base)<3: base="A35"+base
    code = f"{base}{random.randint(10,99)}"
    while code in code_file: code = f"{base}{random.randint(10,99)}"
    code_file[email]=code; code_file[code]=email; save_json(REF_CODE_FILE, code_file); return code

def get_ref_count_and_auto_upgrade(referrer_email):
    auth = load_json(AUTH_FILE); ref_codes = load_json(REF_CODE_FILE, dict)
    referrer_code = ref_codes.get(referrer_email,"")
    if not referrer_code: return 0
    count=0
    for e,info in auth.items():
        if info.get("referred_by","").upper()==referrer_code.upper() and "ACTIVE" in info.get("plan_status",""): count+=1
    if count>=10 and referrer_email in auth and "CREATOR" not in auth[referrer_email].get("plan_status",""):
        if "lifetime" not in auth[referrer_email].get("plan_status","").lower():
            auth[referrer_email]["plan_status"]="ACTIVE lifetime - FREE 10 Referrals"; auth[referrer_email]["expires"]=(datetime.now()+timedelta(days=36500)).isoformat(); save_json(AUTH_FILE, auth)
    ref_data=load_json(REFERRAL_FILE, dict)
    ref_data[referrer_email]={"code":referrer_code,"count":count,"paid_count":count,"free_eligible":count>=10,"updated":datetime.now().isoformat()}
    save_json(REFERRAL_FILE, ref_data); return count

def calculate_pnl_stats(journal):
    now=datetime.now(); today_str=now.strftime("%Y-%m-%d"); week_start=(now - timedelta(days=now.weekday())).strftime("%Y-%m-%d"); month_str=now.strftime("%Y-%m"); year_str=now.strftime("%Y")
    stats={"total_trades":0,"wins":0,"losses":0,"be":0,"win_rate":0,"daily":0,"weekly":0,"monthly":0,"yearly":0,"total_pnl":0}
    for j in journal:
        result=j.get("result",""); pnl=j.get("pnl",0); date=j.get("date",today_str)
        try:
            if "WIN" in result.upper(): stats["wins"]+=1; stats["total_trades"]+=1
            elif "LOSS" in result.upper(): stats["losses"]+=1; stats["total_trades"]+=1
            elif "BE" in result.upper(): stats["be"]+=1; stats["total_trades"]+=1
        except: pass
        try:
            stats["total_pnl"]+=float(pnl)
            if date==today_str: stats["daily"]+=float(pnl)
            if date>=week_start: stats["weekly"]+=float(pnl)
            if date.startswith(month_str): stats["monthly"]+=float(pnl)
            if date.startswith(year_str): stats["yearly"]+=float(pnl)
        except: pass
    if stats["total_trades"]>0: stats["win_rate"]=round((stats["wins"]/stats["total_trades"])*100,1)
    return stats

def calculate_dynamic_sl_tp(symbol, entry, bias, account_size, lot_size, leverage, risk_percent, rr_ratio, spread_forex=0.7, spread_gold=0.35, spread_indices=2.0, spread_crypto=10.0):
    entry=float(entry); is_sell="BEARISH" in bias.upper() or "SELL" in bias.upper()
    risk_amount=float(account_size)*(float(risk_percent)/100.0); lot_size=float(lot_size) if float(lot_size)>0 else 0.01; rr_ratio=float(rr_ratio) if float(rr_ratio)>0 else 2.5
    if symbol in ["XAUUSD","XAGUSD"]:
        spread=float(spread_gold); sl_dollar=risk_amount/(lot_size*100) if lot_size>0 else 5.0; sl_dollar=max(2.0,min(sl_dollar,15.0)); sl_dollar+=spread; tp_dollar=sl_dollar*rr_ratio - spread
        sl=entry+sl_dollar if is_sell else entry-sl_dollar; tp=entry-tp_dollar if is_sell else entry+tp_dollar
        return round(sl,2),round(tp,2),round(sl_dollar,2),round(tp_dollar,2),risk_amount
    elif symbol in ["XTIUSD","XBRUSD"]:
        spread=float(spread_gold); sl_dollar=risk_amount/(lot_size*50) if lot_size>0 else 0.5; sl_dollar=max(0.3,min(sl_dollar,2.0)); sl_dollar+=spread; tp_dollar=sl_dollar*rr_ratio - spread
        sl=entry+sl_dollar if is_sell else entry-sl_dollar; tp=entry-tp_dollar if is_sell else entry+tp_dollar
        return round(sl,2),round(tp,2),round(sl_dollar,2),round(tp_dollar,2),risk_amount
    elif symbol in ["US30","NAS100","SPX500","GER40","UK100","FRA40","ESP35","ITA40","JPN225","AUS200"]:
        spread=float(spread_indices); sl_points=(risk_amount/(lot_size*10)) if lot_size>0 else 80; sl_points=max(30,min(sl_points,250)); sl_points+=spread; tp_points=sl_points*rr_ratio - spread
        sl=entry+sl_points if is_sell else entry-sl_points; tp=entry-tp_points if is_sell else entry+tp_points
        return round(sl,2),round(tp,2),round(sl_points,1),round(tp_points,1),risk_amount
    elif "BTC" in symbol or "ETH" in symbol or "SOL" in symbol or "BNB" in symbol or "XRP" in symbol or "ADA" in symbol or "DOGE" in symbol or "DOT" in symbol or "AVAX" in symbol or "LINK" in symbol or "MATIC" in symbol or "LTC" in symbol:
        spread=float(spread_crypto)
        if "BTC" in symbol: sl_d=max(100,min(risk_amount/(lot_size*10) if lot_size>0 else 400,1200))
        else: sl_d=max(5,min(risk_amount/(lot_size*10) if lot_size>0 else 40,150))
        sl_d+=spread; tp_d=sl_d*rr_ratio - spread; sl=entry+sl_d if is_sell else entry-sl_d; tp=entry-tp_d if is_sell else entry+tp_d
        return round(sl,2),round(tp,2),round(sl_d,1),round(tp_d,1),risk_amount
    else:
        spread=float(spread_forex); pip_value=lot_size*10; sl_pips=risk_amount/pip_value if pip_value!=0 else 10; sl_pips=max(5,min(sl_pips,50)); sl_pips+=spread; tp_pips=sl_pips*rr_ratio - spread
        if "JPY" in symbol: sl_dist=sl_pips*0.01; tp_dist=tp_pips*0.01
        else: sl_dist=sl_pips*0.0001; tp_dist=tp_pips*0.0001
        sl=entry+sl_dist if is_sell else entry-sl_dist; tp=entry-tp_dist if is_sell else entry+tp_dist
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
    text=f"🔴 {symbol} {signal_type} | {display_score}/8 | {method_name[:22]}\n\n📊 {currency_symbol}{account_size} Lot {lot_size} Lev {leverage}\n💰 Entry: {entry_fmt}\n🛑 SL: {sl_fmt} ({sl_dist})\n🎯 TP: {tp_fmt} ({tp_dist})\n📊 RR 1:{rr} | Risk {currency_symbol}{risk_amt:.2f} ({risk_percent}%)\n\n🔍 {confluence_text}\n\n⏰ {sast_now}"
    keyboard={"inline_keyboard": [[{"text":"✅ TOOK ENTRY","callback_data":f"TOOK_{symbol}_{entry_fmt}"},{"text":"❌ SKIP","callback_data":f"SKIP_{symbol}"}],[{"text":"📊 Journal","url":"https://agent-35-trading-bot.onrender.com/journal"}]]}
    results=[]
    for chat_id in all_chats:
        try: r=requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":text,"reply_markup":keyboard}, timeout=10); results.append(r.json())
        except Exception as e: results.append({"error":str(e)})
    return results

def get_active_sessions():
    utc_hour = datetime.utcnow().hour
    sessions = []
    # Asia 00-09 UTC, London 08-17, NY 13-22
    if 0 <= utc_hour < 9 or utc_hour==0: sessions.append("Asia")
    if 8 <= utc_hour < 17: sessions.append("London")
    if 13 <= utc_hour < 22: sessions.append("New York")
    if not sessions: sessions=["Closed"]
    return sessions

def pro_layout(content, active="Dashboard", is_admin=False):
    user=session.get("user","Guest")
    active_sess = get_active_sessions()
    sess_html = ""
    for s in ["Asia","London","New York"]:
        if s in active_sess:
            sess_html+=f"<span style='background:#10b981;padding:3px 8px;border-radius:20px;font-size:9px;font-weight:800;color:white;margin-right:4px;animation:pulse 2s infinite'>● {s}</span>"
        else:
            sess_html+=f"<span style='background:#1e293b;border:1px solid #334155;padding:3px 8px;border-radius:20px;font-size:9px;color:#64748b;margin-right:4px'>{s}</span>"
    tabs=[("Dashboard","📊"),("Journal","📓"),("All Signals","📡"),("Settings","⚙️"),("Referral","👥"),("Plans","💳"),("Guide","📖")]
    if is_admin: tabs.append(("Master","👑"))
    nav_html=""
    for t,icon in tabs:
        url="/creator?secret=ADMIN35" if t=="Master" else f"/{t.lower().replace(' ','-')}"
        if active==t: nav_html+=f"<a href='{url}' class='nav-active'>{icon} {t}</a>"
        else: nav_html+=f"<a href='{url}' class='nav-item'>{icon} {t}</a>"
    html=f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0, maximum-scale=1.0'>
<title>AGENT 35 PRO</title>
<style>
@keyframes pulse{{0%{{opacity:1}}50%{{opacity:0.6}}100%{{opacity:1}}}}
body{{background:#050a14;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,Inter,Arial,sans-serif;margin:0;padding:0; -webkit-font-smoothing:antialiased}}
.topbar{{background:rgba(15,23,42,0.95);backdrop-filter:blur(12px);padding:12px 16px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100;border-bottom:1px solid #1e293b;flex-wrap:wrap;gap:8px}}
.logo{{font-weight:900;font-size:16px;color:#fff;letter-spacing:-0.5px}}.logo span{{color:#10b981}}
.live-clock{{background:#0f172a;border:1px solid #1e293b;padding:6px 12px;border-radius:10px;font-family:monospace;font-weight:700;font-size:12px;color:#10b981;letter-spacing:0.5px}}
.session-bar{{display:flex;align-items:center;gap:4px;flex-wrap:wrap}}
.badge-live{{background:#10b981;padding:4px 10px;border-radius:20px;font-weight:800;font-size:9px;color:white;letter-spacing:0.5px}}
.navbar{{background:#0b1220;border-bottom:1px solid #1e293b;padding:10px 12px;display:flex;gap:6px;overflow-x:auto;position:sticky;top:60px;z-index:90; -webkit-overflow-scrolling:touch; scrollbar-width:none}}
.navbar::-webkit-scrollbar{{display:none}}
.nav-active{{padding:8px 14px;border-radius:10px;text-decoration:none;color:white;font-weight:700;font-size:11px;background:#10b981;white-space:nowrap;box-shadow:0 2px 8px rgba(16,185,129,0.3)}}
.nav-item{{padding:8px 14px;border-radius:10px;text-decoration:none;color:#94a3b8;font-weight:600;font-size:11px;background:#151e32;border:1px solid #1e293b;white-space:nowrap;transition:all 0.2s}}
.nav-item:hover{{color:white;border-color:#334155}}
.main{{padding:14px;display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;max-width:1600px;margin:0 auto}}
.card{{background:linear-gradient(135deg,#151e32 0%,#111a2e 100%);border-radius:16px;padding:16px;border:1px solid #1e293b;box-shadow:0 4px 12px rgba(0,0,0,0.2);min-width:0;transition:transform 0.2s}}
.card:hover{{transform:translateY(-1px);border-color:#2a3a52}}
.card-title{{color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px}}
.card-value{{font-size:24px;font-weight:900;color:#f8fafc;letter-spacing:-0.5px;word-break:break-word}}
.card-sub{{font-size:11px;color:#94a3b8;margin-top:8px;line-height:1.4}}
.btn-primary{{background:linear-gradient(135deg,#10b981 0%,#059669 100%);color:white;padding:13px;border-radius:12px;font-weight:800;border:none;width:100%;cursor:pointer;font-size:13px;box-shadow:0 4px 12px rgba(16,185,129,0.3);transition:all 0.2s}}
.btn-primary:hover{{transform:translateY(-1px);box-shadow:0 6px 16px rgba(16,185,129,0.4)}}
.btn-secondary{{background:#151e32;border:1px solid #1e293b;color:#e2e8f0;padding:10px;border-radius:10px;text-align:center;display:block;text-decoration:none;margin-top:8px;font-size:11px;font-weight:600;transition:all 0.2s}}
.btn-secondary:hover{{background:#1e293b;border-color:#334155;color:white}}
.table-card{{grid-column:1 / -1;background:#111a2e;border-radius:16px;padding:18px;border:1px solid #1e293b;box-shadow:0 4px 12px rgba(0,0,0,0.2);overflow-x:auto}}
table{{width:100%;border-collapse:collapse;min-width:500px}} th{{color:#64748b;text-align:left;padding:10px 8px;font-size:9px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid #1e293b;white-space:nowrap}} td{{padding:10px 8px;border-bottom:1px solid #0f172a;font-size:11px;white-space:nowrap}}
.pill{{padding:4px 10px;border-radius:20px;font-size:10px;font-weight:700;display:inline-block}}
.pill-took{{background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.2)}}
.pill-win{{background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.2)}}
.pill-loss{{background:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.2)}}
.pro-badge{{background:#0f172a;border:1px solid #1e293b;color:#94a3b8;padding:5px 10px;border-radius:20px;font-size:9px;display:inline-block;margin:2px}}
@media(max-width:768px){{.main{{grid-template-columns:1fr; padding:10px}}.card-value{{font-size:20px}}.topbar{{padding:10px}}}}
</style>
<script>
function updateClock(){{
  const now = new Date();
  const sast = new Date(now.toLocaleString('en-US', {{timeZone: 'Africa/Johannesburg'}}));
  const timeStr = sast.toLocaleTimeString('en-GB', {{hour12:false}}) + ' SAST';
  const dateStr = sast.toLocaleDateString('en-GB', {{day:'2-digit',month:'short'}});
  const el = document.getElementById('live-clock');
  if(el) el.textContent = dateStr + ' ' + timeStr;
}}
setInterval(updateClock,1000);
window.onload=updateClock;
</script>
</head><body>
<div class='topbar'>
  <div style='display:flex;align-items:center;gap:12px;flex-wrap:wrap'>
    <div class='logo'>AGENT <span>35</span> PRO</div>
    <span class='badge-live'>LIVE</span>
    <div class='live-clock' id='live-clock'>--:--:-- SAST</div>
  </div>
  <div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap'>
    <div class='session-bar'>{sess_html}</div>
    <span style='background:#111a2e;border:1px solid #1e293b;color:#94a3b8;padding:5px 10px;border-radius:20px;font-size:10px;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{user[:18]}</span>
  </div>
</div>
<div class='navbar'>{nav_html}</div>
{content}
</body></html>"""
    return html

@app.route("/")
def home(): return redirect("/dashboard") if session.get("user") else redirect("/login")

@app.route("/dashboard")
def dashboard():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); journal=load_json(JOURNAL_FILE, list); user_settings=get_user_settings(email)
    tg_users=load_json(TG_FILE, dict); tracked=load_json(TRACK_FILE, dict)
    is_admin=email=="admin@agent35.com"; ref_count=get_ref_count_and_auto_upgrade(email)
    stats=calculate_pnl_stats(journal); curr_sym=get_currency_symbol(user_settings.get("currency","ZAR"))
    method_key=user_settings.get("trading_method","method1_premium_sweep"); method_name=METHODS.get(method_key, METHODS["method1_premium_sweep"])["name"]
    rows=""
    if not journal: rows="<tr><td colspan=5 style='text-align:center;color:#64748b;padding:24px'>No trades yet. Take your first signal via Telegram.</td></tr>"
    else:
        for t in reversed(journal[-6:]):
            cls="pill-took" if t.get("status")=="TOOK" else "pill-win" if "WIN" in t.get("result","") else "pill-loss"
            pnl=t.get("pnl",0)
            rows+=f"<tr><td style='color:#94a3b8'>{t.get('time')}</td><td style='font-weight:700'>{t.get('symbol')}</td><td><span class='pill {cls}'>{t.get('status')}</span></td><td>{t.get('result')}</td><td style='font-weight:700'>{curr_sym}{pnl}</td></tr>"
    tg_status="✅ Connected" if email in tg_users else "⚠️ Not linked"
    pnl_color="#10b981" if stats['total_pnl']>=0 else "#ef4444"
    admin_link="<a href='/creator?secret=ADMIN35' class='btn-secondary' style='background:#f59e0b;color:white;font-weight:700;border-color:#f59e0b'>👑 Creator Panel</a>" if is_admin else ""
    content=f"""
<div class='main'>
<div class='card'><div class='card-title'>Total Profit & Loss</div><div class='card-value' style='color:{pnl_color}'>{curr_sym}{stats['total_pnl']:.2f}</div><div style='background:#0b1220;border-radius:10px;padding:10px;margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:8px'><div><div style='font-size:9px;color:#64748b'>TODAY</div><div style='font-weight:700;font-size:12px'>{curr_sym}{stats['daily']:.2f}</div></div><div><div style='font-size:9px;color:#64748b'>WEEK</div><div style='font-weight:700;font-size:12px'>{curr_sym}{stats['weekly']:.2f}</div></div><div><div style='font-size:9px;color:#64748b'>MONTH</div><div style='font-weight:700;font-size:12px'>{curr_sym}{stats['monthly']:.2f}</div></div><div><div style='font-size:9px;color:#64748b'>YEAR</div><div style='font-weight:700;font-size:12px'>{curr_sym}{stats['yearly']:.2f}</div></div></div><div class='card-sub'>Strategy: {method_name}</div></div>
<div class='card'><div class='card-title'>Performance</div><div class='card-value'>{stats['total_trades']} Trades • {stats['win_rate']}% WR</div><div class='card-sub'>✅ Wins: {stats['wins']} &nbsp; ❌ Losses: {stats['losses']} &nbsp; ➖ BE: {stats['be']}<br><br>Telegram: {tg_status}<br>Referrals: {ref_count}/10 to free lifetime<br>Tracked: {len(tracked)}/{MAX_TRACKED} active</div></div>
<div class='card'><div class='card-title'>Account Overview</div><div class='card-value'>{curr_sym}{user_settings.get('account_size',142)}</div><div class='card-sub'>Lot Size: {user_settings.get('lot_size',0.01)} • Leverage {user_settings.get('leverage','1:500')}<br>Risk: {user_settings.get('risk_percent',1)}% • RR 1:{user_settings.get('rr_ratio',2.5)}<br>Currency: {user_settings.get('currency','ZAR')} {curr_sym}<br><br><a href='/settings' style='color:#10b981;text-decoration:none;font-weight:700'>Edit Settings →</a></div></div>
<div class='card'><div class='card-title'>Quick Actions</div><div style='display:flex;flex-direction:column;gap:2px;margin-top:8px'><a href='/dashboard-scan'><button class='btn-primary'>🔍 Scan Market Now</button></a><a href='/test-telegram' class='btn-secondary'>📤 Test Telegram</a><a href='/link-telegram' class='btn-secondary'>🔗 Link Telegram</a><a href='/export-journal' class='btn-secondary'>📥 Export Journal CSV</a><a href='/clear-tracked' class='btn-secondary' style='color:#ef4444'>Clear Tracked ({len(tracked)}/{MAX_TRACKED})</a>{admin_link}</div></div>
</div>
<div style='max-width:1600px;margin:0 auto;padding:0 14px 14px'><div class='table-card'><div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:12px'><h3 style='margin:0;font-size:14px;font-weight:800'>Recent Activity</h3><span style='font-size:11px;color:#64748b;background:#0b1220;padding:5px 10px;border-radius:20px'>{stats['wins']}W / {stats['losses']}L • {stats['win_rate']}% WR</span></div><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th><th>PnL</th></tr>{rows}</table></div></div>
"""
    return pro_layout(content,"Dashboard", is_admin=is_admin)

@app.route("/settings", methods=["GET","POST"])
def settings_page():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"
    if request.method=="POST":
        trade_news_val = True if request.form.get("trade_news")=="yes" else False
        new_settings={"account_size":float(request.form.get("account_size",142)),"lot_size":float(request.form.get("lot_size",0.01)),"leverage":request.form.get("leverage","1:500"),"risk_percent":float(request.form.get("risk_percent",1)),"rr_ratio":float(request.form.get("rr_ratio",2.5)),"trade_news":trade_news_val,"spread_forex":float(request.form.get("spread_forex",0.7)),"spread_gold":float(request.form.get("spread_gold",0.35)),"spread_indices":float(request.form.get("spread_indices",2.0)),"spread_crypto":float(request.form.get("spread_crypto",10.0)),"currency":request.form.get("currency","ZAR"),"trading_method":request.form.get("trading_method","method1_premium_sweep"),"sessions":request.form.getlist("sessions") or ["London"],"symbols":request.form.getlist("symbols") or ALL_SYMBOLS[:10]}
        save_user_settings(email,new_settings)
        return redirect("/dashboard")
    s=get_user_settings(email)
    symbols_html="".join([f"<label style='display:flex;align-items:center;gap:6px;background:#0b1220;border:1px solid #1e293b;padding:8px 10px;border-radius:10px;font-size:11px;cursor:pointer'><input type='checkbox' name='symbols' value='{sym}' {'checked' if sym in s.get('symbols',[]) else ''}> {sym}</label>" for sym in ALL_SYMBOLS])
    curr=s.get('currency','ZAR'); method=s.get('trading_method','method1_premium_sweep')
    currency_options="".join([f"<option value='{code}' {'selected' if curr==code else ''}>{code} - {info['symbol']} {info['name']}</option>" for code,info in CURRENCY_MAP.items()])
    method_options="".join([f"<option value='{key}' {'selected' if method==key else ''}>{val['name']}</option>" for key,val in METHODS.items()])
    method_info=METHODS.get(method, METHODS['method1_premium_sweep'])
    content=f"""<div style='max-width:1100px;margin:0 auto;padding:14px'>
<h1 style='font-size:20px;font-weight:900;margin-bottom:4px'>Settings</h1><p style='color:#64748b;font-size:12px;margin-top:0'>Configure your trading preferences. Clean and simple.</p>
<form method='post'>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:16px'>
<div class='card'><div class='card-title'>Currency</div><select name='currency' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;background:#0b1220;color:white;border:1px solid #1e293b'>{currency_options}</select></div>
<div class='card'><div class='card-title'>Trading Strategy</div><select name='trading_method' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;background:#0b1220;color:white;border:1px solid #1e293b'>{method_options}</select><div style='font-size:11px;color:#94a3b8;margin-top:8px;line-height:1.4'>{method_info['desc']}</div></div>
<div class='card'><div class='card-title'>Account Size</div><input name='account_size' type='number' step='0.01' value='{s.get('account_size',142)}' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white'></div>
<div class='card'><div class='card-title'>Lot Size</div><input name='lot_size' type='number' step='0.01' value='{s.get('lot_size',0.01)}' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white'></div>
<div class='card'><div class='card-title'>Risk Per Trade %</div><input name='risk_percent' type='number' step='0.1' value='{s.get('risk_percent',1)}' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white'></div>
<div class='card'><div class='card-title'>Risk Reward</div><select name='rr_ratio' style='width:100%;padding:12px;margin-top:8px;border-radius:10px;background:#0b1220;color:white;border:1px solid #1e293b'><option value='1.5' {'selected' if str(s.get('rr_ratio'))=='1.5' else ''}>1:1.5 Scalp</option><option value='2' {'selected' if str(s.get('rr_ratio'))=='2' else ''}>1:2</option><option value='2.5' {'selected' if str(s.get('rr_ratio'))=='2.5' else ''}>1:2.5 Recommended</option><option value='3' {'selected' if str(s.get('rr_ratio'))=='3' else ''}>1:3 SMC</option></select></div>
</div>
<div class='card' style='margin-top:12px'><div class='card-title'>Watchlist - {len(ALL_SYMBOLS)} Symbols Available (Tracking limited to {MAX_TRACKED})</div><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:6px;max-height:380px;overflow-y:auto;margin-top:10px;padding-right:4px'>{symbols_html}</div></div>
<button type='submit' class='btn-primary' style='margin-top:16px'>Save Settings</button>
</form></div>"""
    return pro_layout(content,"Settings", is_admin=is_admin)

@app.route("/all-signals")
@app.route("/dashboard-scan")
def dashboard_scan():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"; user_settings=get_user_settings(email)
    symbols_to_scan=user_settings.get("symbols", ALL_SYMBOLS[:12]); method_key=user_settings.get("trading_method","method1_premium_sweep"); method_name=METHODS.get(method_key, METHODS["method1_premium_sweep"])["name"]
    tracked=load_json(TRACK_FILE, dict)
    rows=""
    for s in symbols_to_scan[:30]:
        try:
            r=eng.full_multi_tf_analysis(s, user_settings); score=r.get('score',0); bias=r.get('bias','NEUTRAL'); entry=r.get('entry',0)
            entry_display=f"{float(entry):.5f}" if entry and float(entry)<20 else f"{float(entry):.2f}" if entry else "0"
            color="#10b981" if score>=7 else "#f59e0b" if score>=5 else "#ef4444"
            limit_note = f"<div style='font-size:8px;color:#f59e0b'>TRACKED {len(tracked)}/{MAX_TRACKED}</div>" if s in tracked else ""
            if r.get('signal'):
                if len(tracked)>=MAX_TRACKED and s not in tracked:
                    signal_btn=f"<span class='pill' style='background:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.2)'>Limit {MAX_TRACKED} Full</span>"
                else:
                    signal_btn=f"<a href='/send-signal?symbol={s}' style='background:#10b981;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-weight:700;font-size:11px'>Send</a>{limit_note}"
            else: signal_btn=f"<span style='color:#64748b;font-size:10px'>{r.get('reason','')[:42]}</span>{limit_note}"
            rows+=f"<tr><td style='font-weight:700'>{s}<div style='font-size:9px;color:#64748b'>{entry_display}</div></td><td><span class='pill' style='background:{color}22;color:{color};border:1px solid {color}44'>{score}/10</span></td><td>{bias}</td><td>{'✅ STRONG' if r.get('signal') else '⏳ Wait'}</td><td>{signal_btn}</td></tr>"
        except Exception as e: rows+=f"<tr><td>{s}</td><td colspan=4 style='color:#ef4444;font-size:10px'>{str(e)[:50]}</td></tr>"
    content=f"""<div style='max-width:1600px;margin:0 auto;padding:14px'>
<div class='table-card'><div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px'><div><h2 style='font-size:16px;font-weight:800;margin:0'>Market Scan</h2><p style='font-size:11px;color:#64748b;margin:4px 0 0'>Strategy: {method_name} • Tracked {len(tracked)}/{MAX_TRACKED} • {len(symbols_to_scan)} pairs</p></div><a href='/clear-tracked' style='background:#1e293b;border:1px solid #334155;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:11px'>Clear Tracked</a></div>
<table><tr><th>Symbol</th><th>Score</th><th>Bias</th><th>Signal</th><th>Action</th></tr>{rows}</table></div></div>"""
    return pro_layout(content,"All Signals", is_admin=is_admin)

@app.route("/journal")
def journal_page():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"; journal=load_json(JOURNAL_FILE, list)
    user_set=get_user_settings(email); curr_sym=get_currency_symbol(user_set.get("currency","ZAR"))
    stats=calculate_pnl_stats(journal); period=request.args.get("period","all"); now=datetime.now()
    if period=="today": filtered=[j for j in journal if j.get("date")==now.strftime("%Y-%m-%d")]
    elif period=="week":
        week_start=(now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        filtered=[j for j in journal if j.get("date","")>=week_start]
    elif period=="month": filtered=[j for j in journal if j.get("date","").startswith(now.strftime("%Y-%m"))]
    elif period=="year": filtered=[j for j in journal if j.get("date","").startswith(now.strftime("%Y"))]
    else: filtered=journal
    rows="".join([f"<tr><td>{j.get('time')}</td><td style='font-weight:700'>{j.get('symbol')}</td><td><span class='pill {('pill-win' if 'WIN' in j.get('result','') else 'pill-loss' if 'LOSS' in j.get('result','') else 'pill-took')}'>{j.get('status')}</span></td><td>{j.get('result')}</td><td style='font-weight:700'>{curr_sym}{j.get('pnl',0)}</td><td style='color:#64748b'>{j.get('date','')}</td></tr>" for j in reversed(filtered[-200:])])
    def get_style(p): return "background:#10b981;color:white;border:1px solid #10b981" if period==p else "background:#151e32;border:1px solid #1e293b;color:#94a3b8"
    content=f"""<div style='max-width:1400px;margin:0 auto;padding:14px'>
<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px'><h1 style='font-size:20px;font-weight:900;margin:0'>Journal</h1><a href='/export-journal' class='btn-secondary' style='margin:0;display:inline-block'>Export CSV</a></div>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:14px 0'>
<div class='card'><div class='card-title'>Today</div><div class='card-value' style='font-size:18px;color:{"#10b981" if stats['daily']>=0 else "#ef4444"}'>{curr_sym}{stats['daily']:.2f}</div></div>
<div class='card'><div class='card-title'>This Week</div><div class='card-value' style='font-size:18px'>{curr_sym}{stats['weekly']:.2f}</div></div>
<div class='card'><div class='card-title'>This Month</div><div class='card-value' style='font-size:18px'>{curr_sym}{stats['monthly']:.2f}</div></div>
<div class='card'><div class='card-title'>Total PnL</div><div class='card-value' style='font-size:18px;color:{"#10b981" if stats['total_pnl']>=0 else "#ef4444"}'>{curr_sym}{stats['total_pnl']:.2f}</div></div>
</div>
<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px'>
<a href='/journal?period=all' style='padding:7px 14px;border-radius:20px;text-decoration:none;font-size:11px;font-weight:600;{get_style("all")}'>All</a>
<a href='/journal?period=today' style='padding:7px 14px;border-radius:20px;text-decoration:none;font-size:11px;font-weight:600;{get_style("today")}'>Today</a>
<a href='/journal?period=week' style='padding:7px 14px;border-radius:20px;text-decoration:none;font-size:11px;font-weight:600;{get_style("week")}'>Week</a>
<a href='/journal?period=month' style='padding:7px 14px;border-radius:20px;text-decoration:none;font-size:11px;font-weight:600;{get_style("month")}'>Month</a>
<a href='/journal?period=year' style='padding:7px 14px;border-radius:20px;text-decoration:none;font-size:11px;font-weight:600;{get_style("year")}'>Year</a>
</div>
<div class='table-card'><table><tr><th>Time</th><th>Symbol</th><th>Status</th><th>Result</th><th>PnL</th><th>Date</th></tr>{rows if rows else '<tr><td colspan=6 style=text-align:center;color:#64748b;padding:20px>No trades yet</td></tr>'}</table></div>
</div>"""
    return pro_layout(content,"Journal", is_admin=is_admin)

@app.route("/referral")
def referral_page():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"; my_code=generate_ref_code(email)
    ref_count=get_ref_count_and_auto_upgrade(email)
    referral_data=load_json(REFERRAL_FILE, dict); auth=load_json(AUTH_FILE, dict)
    my_refs=[]
    for e,info in auth.items():
        if info.get("referred_by","").upper()==my_code.upper(): my_refs.append({"email":e,"plan":info.get("plan_status","No Plan"),"date":info.get("created","")[:10]})
    ref_rows="".join([f"<tr><td style='font-weight:600'>{r['email'][:24]}</td><td><span class='pill { 'pill-win' if 'ACTIVE' in r['plan'] else 'pill-loss'}'>{r['plan'][:20]}</span></td><td style='color:#64748b'>{r['date']}</td></tr>" for r in my_refs[-20:]]) or "<tr><td colspan=3 style='text-align:center;color:#64748b;padding:16px'>No referrals yet. Share your link.</td></tr>"
    progress_pct = min(ref_count*10,100)
    content=f"""<div style='max-width:900px;margin:0 auto;padding:14px'>
<h1 style='font-size:22px;font-weight:900;margin:0'>Referral Program</h1><p style='color:#64748b;font-size:13px;margin:6px 0 16px'>Invite 10 friends who buy a plan → Get Lifetime FREE</p>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px'>
<div class='card' style='border:1px solid #10b98133'><div class='card-title'>Your Referral Code</div><div class='card-value' style='color:#10b981;letter-spacing:1px'>{my_code}</div><div class='card-sub'>Share this code with friends at registration</div>
<div style='background:#0b1220;border-radius:10px;padding:12px;margin-top:12px'><div style='font-size:11px;color:#94a3b8;margin-bottom:6px'>Your Referral Link:</div><div style='background:#050a14;padding:10px;border-radius:8px;font-size:11px;word-break:break-all;border:1px solid #1e293b'>https://agent-35-trading-bot.onrender.com/register?ref={my_code}</div>
<button onclick="navigator.clipboard.writeText('https://agent-35-trading-bot.onrender.com/register?ref={my_code}');alert('Copied!')" style='background:#10b981;color:white;border:none;padding:8px 14px;border-radius:8px;font-weight:700;margin-top:8px;width:100%;cursor:pointer'>Copy Link</button></div></div>
<div class='card'><div class='card-title'>Progress to Free Lifetime</div><div class='card-value'>{ref_count} / 10 Referrals</div>
<div style='background:#0b1220;border-radius:10px;height:10px;margin-top:12px;overflow:hidden'><div style='background:linear-gradient(90deg,#10b981,#059669);height:100%;width:{progress_pct}%;border-radius:10px;transition:width 0.5s'></div></div>
<div class='card-sub' style='margin-top:8px'>{'🎉 You unlocked FREE Lifetime! Contact admin.' if ref_count>=10 else f'Need {10-ref_count} more paid referrals to unlock Lifetime worth R5000'}</div>
<div style='margin-top:12px;display:flex;gap:6px;flex-wrap:wrap'><span class='pro-badge'>R500 = 1 Year</span><span class='pro-badge'>R5000 = Lifetime</span><span class='pro-badge'>10 Refs = Free Lifetime</span></div></div>
</div>
<div class='table-card' style='margin-top:12px'><h3 style='margin:0 0 12px;font-size:14px;font-weight:800'>Your Referrals ({len(my_refs)})</h3><table><tr><th>Email</th><th>Plan Status</th><th>Joined</th></tr>{ref_rows}</table></div>
</div>"""
    return pro_layout(content,"Referral", is_admin=is_admin)

@app.route("/plans")
def plans_page():
    is_admin=session.get("user")=="admin@agent35.com"
    email=session.get("user","")
    user_set=get_user_settings(email or "admin@agent35.com"); curr_sym=get_currency_symbol(user_set.get("currency","ZAR"))
    content=f"""<div style='max-width:1000px;margin:0 auto;padding:14px'>
<h1 style='font-size:22px;font-weight:900;margin:0'>Choose Your Plan</h1><p style='color:#64748b;font-size:13px;margin:6px 0 18px'>Professional trading signals • 55 symbols • 6 max tracked • Cloud backup</p>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px'>
<div class='card' style='border:1px solid #1e293b'><div style='display:flex;justify-content:space-between;align-items:center'><h3 style='margin:0;font-size:16px'>Yearly</h3><span class='pill pill-took'>Most Popular</span></div><div class='card-value' style='margin:12px 0'>{curr_sym}500 <span style='font-size:13px;color:#64748b;font-weight:500'>/ year</span></div><div style='font-size:12px;color:#94a3b8;line-height:1.6'>
✅ All 55 symbols (Forex, Gold, Oil, Indices, Crypto)<br>
✅ 5 Trading strategies<br>
✅ Telegram signals 24/7<br>
✅ Journal + Export<br>
✅ Up to 6 tracked trades<br>
✅ Cloud backup - never resets<br>
✅ 65%+ win rate<br>
</div><a href='/pay?plan=yearly' style='display:block;background:#10b981;color:white;text-align:center;padding:12px;border-radius:12px;text-decoration:none;font-weight:800;margin-top:16px'>Choose Yearly</a></div>
<div class='card' style='border:1px solid #f59e0b44; background:linear-gradient(135deg,#1a1508 0%,#151e32 100%)'><div style='display:flex;justify-content:space-between;align-items:center'><h3 style='margin:0;font-size:16px'>Lifetime</h3><span style='background:#f59e0b;color:white;padding:4px 10px;border-radius:20px;font-size:10px;font-weight:800'>BEST VALUE</span></div><div class='card-value' style='margin:12px 0;color:#fbbf24'>{curr_sym}5000 <span style='font-size:13px;color:#94a3b8;font-weight:500'>once</span></div><div style='font-size:12px;color:#94a3b8;line-height:1.6'>
🔥 Everything in Yearly PLUS<br>
✅ Lifetime updates<br>
✅ Priority support<br>
✅ All future strategies<br>
✅ Never pay again<br>
✅ Free if you refer 10 friends<br>
✅ Worth {curr_sym}5000 - save forever<br>
</div><a href='/pay?plan=lifetime' style='display:block;background:linear-gradient(135deg,#f59e0b,#d97706);color:white;text-align:center;padding:12px;border-radius:12px;text-decoration:none;font-weight:800;margin-top:16px'>Choose Lifetime</a></div>
</div>
<div class='card' style='margin-top:14px'><h3 style='margin:0 0 8px;font-size:14px'>How to Pay - Capitec</h3><div style='background:#0b1220;padding:14px;border-radius:10px;border:1px solid #1e293b'><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;font-size:12px'><div><div style='color:#64748b;font-size:10px'>BANK</div><div style='font-weight:700'>Capitec Business</div></div><div><div style='color:#64748b;font-size:10px'>ACCOUNT NUMBER</div><div style='font-weight:700;font-family:monospace'>2586572676</div></div><div><div style='color:#64748b;font-size:10px'>REFERENCE</div><div style='font-weight:700'>A35-{'XXXX' if not email else email[:4].upper()}</div></div><div><div style='color:#64748b;font-size:10px'>AMOUNT</div><div style='font-weight:700;color:#10b981'>{curr_sym}500 Yearly or {curr_sym}5000 Lifetime</div></div></div><div style='margin-top:12px;font-size:11px;color:#94a3b8'>After payment, upload proof via Telegram or email. Admin approves within 1 hour. Your referrals: Use code to get free lifetime after 10 paid friends.</div></div></div>
</div>"""
    return pro_layout(content,"Plans", is_admin=is_admin)

@app.route("/guide")
def guide_page():
    is_admin=session.get("user")=="admin@agent35.com"
    content="""<div style='max-width:900px;margin:0 auto;padding:14px'>
<h1 style='font-size:22px;font-weight:900;margin:0'>User Guide</h1><p style='color:#64748b;font-size:13px;margin:6px 0 18px'>Everything you need to master AGENT 35 PRO</p>
<div style='display:grid;gap:12px'>
<div class='card'><h3 style='margin:0 0 8px;font-size:14px'>🚀 Quick Start (2 min)</h3><div style='font-size:12px;color:#cbd5e1;line-height:1.7'>
1. Go to <b>Settings</b> → Set Account Size (R142), Lot Size (0.01), Risk 1%<br>
2. Pick your Currency (ZAR R, USD $, EUR €, GBP £)<br>
3. Choose Strategy: Premium+Sweep for beginners<br>
4. Select 8-12 symbols max (Gold + major forex)<br>
5. <b>Link Telegram</b> → Send /start to bot → Paste Chat ID<br>
6. Click <b>Scan Now</b> → Send signals to Telegram → Take trades
</div></div>
<div class='card'><h3 style='margin:0 0 8px;font-size:14px'>📊 Understanding Scores</h3><div style='font-size:12px;color:#cbd5e1;line-height:1.7'>
<span class='pill' style='background:#10b98122;color:#10b981;border:1px solid #10b98144'>7-10/10 STRONG</span> → Send to Telegram, take trade<br>
<span class='pill' style='background:#f59e0b22;color:#f59e0b;border:1px solid #f59e0b44'>5-6/10</span> → Wait, not strong enough<br>
<span class='pill' style='background:#ef444422;color:#ef4444;border:1px solid #ef444444'>0-4/10</span> → No signal, market choppy<br><br>
<b>Premium/Discount:</b> BULLISH best in Discount (0-35%), BEARISH best in Premium (65-100%)<br>
<b>Sweep:</b> Price sweeps recent low/high then reverses - strong reversal signal<br>
<b>Engulfing/Hammer:</b> Candle patterns confirming reversal<br>
<b>Order Block:</b> Institutional zone where price respects - BTC case fixed
</div></div>
<div class='card'><h3 style='margin:0 0 8px;font-size:14px'>⏰ Trading Sessions (Live Indicator Top Bar)</h3><div style='font-size:12px;color:#cbd5e1;line-height:1.7'>
<span style='background:#10b981;padding:2px 8px;border-radius:20px;font-size:10px;color:white'>● Asia</span> 02:00-11:00 SAST → JPY pairs volatile<br>
<span style='background:#10b981;padding:2px 8px;border-radius:20px;font-size:10px;color:white'>● London</span> 10:00-19:00 SAST → Best for EUR/GBP/XAU<br>
<span style='background:#10b981;padding:2px 8px;border-radius:20px;font-size:10px;color:white'>● New York</span> 15:00-00:00 SAST → Best for US30/NAS100/BTC<br>
Overlap London+NY (15:00-19:00 SAST) = Highest volatility, best signals<br>
Weekend: Forex/Gold/Indices closed Saturday, Crypto (BTC/ETH etc) trades 24/7
</div></div>
<div class='card'><h3 style='margin:0 0 8px;font-size:14px'>🎯 5 Strategies Explained</h3><div style='font-size:12px;color:#cbd5e1;line-height:1.7'>
<b>1. Premium+Sweep (Recommended for beginners):</b> Daily bias + 4H alignment + Discount/Premium + Sweep + Engulfing. 65%+ WR<br>
<b>2. EMA+RSI:</b> EMA5>EMA20 + RSI 40-55 pullback. More signals 5-10/day<br>
<b>3. Breakout+Retest:</b> Breaks high/low + retest + engulf. Best for US30/NAS100/BTC<br>
<b>4. Scalp M5 Fast:</b> M5 EMA9/21 cross + RSI. 10-20/day, RR 1:1.5, best for R142<br>
<b>5. SMC OB+BOS:</b> BOS + Order Block + FVG. Fewer signals but 70%+ WR. Best for BTC OB respect
</div></div>
<div class='card'><h3 style='margin:0 0 8px;font-size:14px'>🔒 6 Max Tracked Rule</h3><div style='font-size:12px;color:#cbd5e1;line-height:1.7'>
System allows max 6 active tracked trades at once. Keeps you focused, stops overtrading.<br>
When limit reached, clear tracked via Dashboard or wait 24h auto-clear.<br>
55 symbols available: 26 Forex, 2 Metals, 2 Oil, 10 Indices, 13 Crypto + 2 new oil pairs
</div></div>
</div>
</div>"""
    return pro_layout(content,"Guide", is_admin=is_admin)

@app.route("/creator")
def creator_dashboard():
    email = session.get("user","")
    secret_param = request.args.get("secret","")
    cron_secret = os.getenv("CRON_SECRET","")
    is_authorized = (email=="admin@agent35.com") or (secret_param and secret_param==cron_secret) or (secret_param=="ADMIN35")
    if not is_authorized:
        return pro_layout("<div style='max-width:600px;margin:80px auto;text-align:center'><div class='card'><h2>🔒 Access Denied</h2><p style='color:#64748b;font-size:13px'>Creator panel requires admin login or secret key<br><br>/creator?secret=ADMIN35</p></div></div>","Master", is_admin=False)
    users=load_json(USERS_FILE); auth=load_json(AUTH_FILE); journal=load_json(JOURNAL_FILE, list); tracked=load_json(TRACK_FILE, dict); system=load_json(SYSTEM_FILE, dict); stats=calculate_pnl_stats(journal)
    pending={k:v for k,v in users.items() if v.get("status")=="pending"}
    pending_rows="".join([f"<tr><td style='font-family:monospace;font-size:10px'>{ref}</td><td>{pay.get('user','')[:24]}</td><td>{pay.get('plan','yearly')}</td><td>R{pay.get('price','')}</td><td><a href='/creator/action?act=approve_payment&ref={ref}&secret={secret_param}' style='background:#10b981;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-weight:700;font-size:11px'>Approve</a> <a href='/creator/action?act=reject&ref={ref}&secret={secret_param}' style='background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:11px'>Reject</a></td></tr>" for ref,pay in pending.items()]) or "<tr><td colspan=5 style='text-align:center;color:#64748b;padding:16px'>No pending payments - all caught up ✅</td></tr>"
    user_rows="".join([f"<tr><td style='font-size:10px'>{e[:24]}</td><td style='font-size:10px'>{info.get('plan_status','')[:18]}</td><td style='font-size:10px'>{info.get('ref_code','')}</td><td style='font-size:10px'>{str(info.get('expires',''))[:10]}</td></tr>" for e,info in list(auth.items())[-15:]])
    content=f"""<div style='max-width:1600px;margin:0 auto;padding:14px'>
<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px'><h1 style='font-size:20px;font-weight:900;margin:0'>👑 Creator Master Panel</h1><div style='display:flex;gap:6px;flex-wrap:wrap'><span class='pro-badge'>Users: {len(auth)}</span><span class='pro-badge'>Pending: {len(pending)}</span><span class='pro-badge'>Trades: {len(journal)}</span><span class='pro-badge'>Tracked: {len(tracked)}/{MAX_TRACKED}</span></div></div>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:14px'>
<div class='card'><div class='card-title'>Pending Payments</div><div class='card-value' style='font-size:20px;color:#f59e0b'>{len(pending)}</div></div>
<div class='card'><div class='card-title'>Total Users</div><div class='card-value' style='font-size:20px'>{len(auth)}</div></div>
<div class='card'><div class='card-title'>Total PnL Tracked</div><div class='card-value' style='font-size:18px;color:{"#10b981" if stats['total_pnl']>=0 else "#ef4444"}'>R{stats['total_pnl']:.2f}</div></div>
<div class='card'><div class='card-title'>System Scans</div><div class='card-value' style='font-size:20px'>{system.get('total_scans',0)}</div><div style='font-size:10px;color:#64748b'>Last: {str(system.get('last_scan','Never'))[:16]}</div></div>
</div>
<div class='table-card'><div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px'><h3 style='margin:0;font-size:14px;font-weight:800'>Pending Payments - Approve / Reject</h3><div style='display:flex;gap:6px'><a href='/backup-now' style='background:#10b981;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:11px'>Force Backup</a><a href='/clear-tracked?secret={secret_param}' style='background:#ef4444;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:11px'>Clear Tracked</a><a href='/health' style='background:#1e293b;border:1px solid #334155;color:white;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:11px'>Health</a></div></div><table><tr><th>Ref ID</th><th>Email</th><th>Plan</th><th>Price</th><th>Action</th></tr>{pending_rows}</table></div>
<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:12px'>
<div class='table-card'><h3 style='margin:0 0 12px;font-size:14px'>Recent Users (15)</h3><table><tr><th>Email</th><th>Plan</th><th>Ref Code</th><th>Expires</th></tr>{user_rows}</table></div>
<div class='card'><h3 style='margin:0 0 10px;font-size:14px'>Tracked Trades {len(tracked)}/{MAX_TRACKED}</h3><div style='font-size:11px;color:#cbd5e1'>{'<br>'.join([f"{k}: {v.get('bias')} {v.get('entry')} Score {v.get('score')}" for k,v in tracked.items()]) if tracked else "No tracked trades - clean"}</div><div style='margin-top:12px'><a href='/dashboard-scan' style='background:#10b981;color:white;padding:8px 14px;border-radius:8px;text-decoration:none;font-size:12px;font-weight:700'>View Signals</a></div></div>
</div>
</div>"""
    return pro_layout(content,"Master", is_admin=True)

@app.route("/creator/action")
def creator_action():
    secret=request.args.get("secret",""); cron_secret=os.getenv("CRON_SECRET",""); email=session.get("user","")
    is_authorized = (email=="admin@agent35.com") or (secret and secret==cron_secret) or secret=="ADMIN35"
    if not is_authorized: return "Unauthorized"
    act=request.args.get("act",""); auth=load_json(AUTH_FILE); users=load_json(USERS_FILE)
    if act=="approve_payment":
        ref=request.args.get("ref","")
        if ref in users:
            users[ref]["status"]="active"; users[ref]["expires"]=(datetime.now()+timedelta(days=365 if users[ref].get('plan')=='yearly' else 36500)).isoformat()
            user_email=users[ref].get("user")
            if user_email in auth:
                plan = users[ref].get('plan','yearly')
                auth[user_email]["plan_status"]=f"ACTIVE {plan}"; auth[user_email]["expires"]=users[ref]["expires"]
            save_json(USERS_FILE, users); save_json(AUTH_FILE, auth)
        return redirect(f"/creator?secret={secret}")
    if act=="reject":
        ref=request.args.get("ref","")
        if ref in users: del users[ref]; save_json(USERS_FILE, users)
        return redirect(f"/creator?secret={secret}")
    return redirect(f"/creator?secret={secret}")

@app.route("/clear-tracked")
def clear_tracked():
    if not session.get("user") and not request.args.get("secret"): return redirect("/login")
    save_json(TRACK_FILE, {})
    secret=request.args.get("secret","")
    if secret: return redirect(f"/creator?secret={secret}")
    return redirect("/dashboard")

@app.route("/send-signal")
def send_signal():
    if not session.get("user"): return redirect("/login")
    sym=request.args.get("symbol","EURUSD"); email=session.get("user"); user_set=get_user_settings(email)
    tracked=load_json(TRACK_FILE, dict)
    if len(tracked)>=MAX_TRACKED and sym not in tracked:
        return pro_layout(f"<div style='max-width:600px;margin:60px auto;text-align:center'><div class='card'><h2>Track Limit Reached ({MAX_TRACKED})</h2><p style='color:#94a3b8;font-size:13px'>Currently tracked: {', '.join(tracked.keys())}<br>Clear one to allow new signals</p><div style='display:flex;gap:8px;justify-content:center;margin-top:16px'><a href='/all-signals' style='background:#10b981;color:white;padding:10px 18px;border-radius:10px;text-decoration:none;font-weight:700'>Back to Signals</a><a href='/clear-tracked' style='background:#ef4444;color:white;padding:10px 18px;border-radius:10px;text-decoration:none;font-weight:700'>Clear All</a></div></div></div>","All Signals", is_admin=email=="admin@agent35.com")
    try:
        r=eng.full_multi_tf_analysis(sym, user_set); entry=r.get('entry',0)
        if not entry or float(entry)==0: return pro_layout(f"<div class='card' style='max-width:600px;margin:40px auto'><h3>No entry price for {sym}</h3><pre style='font-size:10px;background:#0b1220;padding:10px;border-radius:8px'>{r}</pre><a href='/all-signals' class='btn-secondary'>Back</a></div>","All Signals", is_admin=email=="admin@agent35.com")
        rr=user_set.get('rr_ratio',2.5); risk_percent=user_set.get('risk_percent',1); lot=user_set.get('lot_size',0.01); lev=user_set.get('leverage','1:500'); acc=user_set.get('account_size',142)
        curr_sym=get_currency_symbol(user_set.get("currency","ZAR")); method_key=user_set.get("trading_method","method1_premium_sweep"); method_name=METHODS.get(method_key, METHODS["method1_premium_sweep"])["name"]
        sl,tp,sl_dist,tp_dist,risk_amt=calculate_dynamic_sl_tp(sym, entry, r.get('bias',''), acc, lot, lev, risk_percent, rr, user_set.get('spread_forex',0.7), user_set.get('spread_gold',0.35), user_set.get('spread_indices',2.0), user_set.get('spread_crypto',10.0))
        confluence=r.get('confluence', r.get('reason','')); res=send_telegram_pro(sym, r.get('score',0), r.get('bias',''), entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot, lev, acc, confluence, curr_sym, method_name)
        tracked[sym]={"time":datetime.now().isoformat(),"bias":r.get('bias'),"entry":entry,"sl":sl,"tp":tp,"risk_amt":risk_amt,"rr":rr,"score":r.get('score'),"currency":user_set.get("currency","ZAR"),"method":method_key}; save_json(TRACK_FILE, tracked)
        msg=f"Sent {sym} {entry} SL {sl} TP {tp}"
    except Exception as e: res={"error":str(e)}; msg=f"Error {sym}: {e}"
    return pro_layout(f"<div style='max-width:700px;margin:40px auto'><div class='card'><h2 style='font-size:16px'>{msg}</h2><p style='font-size:11px;background:#0b1220;padding:10px;border-radius:8px;word-break:break-all;border:1px solid #1e293b'>{str(res)[:2000]}</p><div style='display:flex;gap:8px;margin-top:12px'><a href='/all-signals' style='background:#10b981;color:white;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:700'>Back to Signals</a><a href='/dashboard' style='background:#1e293b;border:1px solid #334155;color:white;padding:10px 16px;border-radius:10px;text-decoration:none'>Dashboard</a></div></div></div>","All Signals", is_admin=email=="admin@agent35.com")

@app.route("/export-journal")
def export_journal():
    if not session.get("user"): return redirect("/login")
    journal=load_json(JOURNAL_FILE, list); output=io.StringIO(); writer=csv.writer(output); writer.writerow(["Time","Symbol","Status","Result","PnL","Date"])
    for j in journal: writer.writerow([j.get("time",""),j.get("symbol",""),j.get("status",""),j.get("result",""),j.get("pnl",0),j.get("date","")])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=journal.csv"})

@app.route("/test-telegram")
def test_telegram():
    email=session.get("user") or "admin@agent35.com"; user_set=get_user_settings(email)
    r=eng.full_multi_tf_analysis("GBPUSD", user_set); entry=r.get('entry',0)
    if not entry or float(entry)==0: entry=1.35057; r={"score":8,"bias":"BEARISH","confluence":"Test signal - GBPUSD BEARISH engulfing + sweep","details":{}}
    rr=user_set.get('rr_ratio',2.5); risk_percent=user_set.get('risk_percent',1); lot=user_set.get('lot_size',0.01); lev=user_set.get('leverage','1:500'); acc=user_set.get('account_size',142)
    curr_sym=get_currency_symbol(user_set.get("currency","ZAR")); method_key=user_set.get("trading_method","method1_premium_sweep"); method_name=METHODS.get(method_key, METHODS["method1_premium_sweep"])["name"]
    sl,tp,sl_dist,tp_dist,risk_amt=calculate_dynamic_sl_tp("GBPUSD", entry, r.get('bias','BEARISH'), acc, lot, lev, risk_percent, rr, user_set.get('spread_forex',0.7), user_set.get('spread_gold',0.35), user_set.get('spread_indices',2.0), user_set.get('spread_crypto',10.0))
    res=send_telegram_pro("GBPUSD", r.get('score',8), r.get('bias','BEARISH'), entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, risk_percent, lot, lev, acc, r.get('confluence','Test'), curr_sym, method_name)
    return pro_layout(f"<div style='max-width:700px;margin:40px auto'><div class='card'><h2 style='font-size:15px'>Test Telegram Sent - GBPUSD {entry}</h2><p style='font-size:11px;background:#0b1220;padding:12px;border-radius:10px;border:1px solid #1e293b;word-break:break-all'>{str(res)[:2000]}</p><a href='/dashboard' style='background:#10b981;color:white;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:700;display:inline-block;margin-top:10px'>Back</a></div></div>","Dashboard", is_admin=email=="admin@agent35.com")

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
            try: requests.post(f"https://api.telegram.org/bot{bot}/sendMessage", json={"chat_id":chat_id,"text":f"AGENT 35 PRO - Your Chat ID: {chat_id}\n\nCopy this ID and paste in Dashboard > Link Telegram\n\nYou will receive signals here."}, timeout=5)
            except: pass
    if "callback_query" in data:
        cb=data["callback_query"]; cb_data=cb.get("data",""); cb_id=cb.get("id"); chat_id=cb["message"]["chat"]["id"]; user_name=cb["from"].get("first_name","User")
        journal=load_json(JOURNAL_FILE, list); tracked=load_json(TRACK_FILE, dict); text="OK"
        if cb_data.startswith("TOOK_"):
            parts=cb_data.split("_"); sym=parts[1]; entry=parts[2] if len(parts)>2 else ""
            risk_amt=0; rr=2.5; sl=0; tp=0; curr="ZAR"; meth=""
            if sym in tracked: risk_amt=tracked[sym].get("risk_amt",0); rr=tracked[sym].get("rr",2.5); sl=tracked[sym].get("sl",0); tp=tracked[sym].get("tp",0); curr=tracked[sym].get("currency","ZAR"); meth=tracked[sym].get("method","")
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
def login_page(): return f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#050a14;color:white;font-family:Inter,Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:12px'><div style='width:100%;max-width:360px;background:#111a2e;padding:24px;border-radius:20px;border:1px solid #1e293b;box-shadow:0 20px 40px rgba(0,0,0,0.4)'><div style='text-align:center;margin-bottom:20px'><div style='font-weight:900;font-size:22px;letter-spacing:-1px'>AGENT <span style='color:#10b981'>35</span> PRO</div><div style='font-size:11px;color:#64748b;margin-top:4px'>Professional Trading Signals</div><div style='display:flex;gap:6px;justify-content:center;margin-top:10px'><span style='background:#10b98122;color:#10b981;border:1px solid #10b98133;padding:3px 8px;border-radius:20px;font-size:9px'>55 Symbols</span><span style='background:#0b1220;border:1px solid #1e293b;color:#64748b;padding:3px 8px;border-radius:20px;font-size:9px'>Live Clock</span></div></div><form action='/login/check' method='post'><input name='email' type='email' placeholder='Email address' required style='width:100%;padding:12px;margin:6px 0;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white;font-size:14px'><input name='password' type='password' placeholder='Password' required style='width:100%;padding:12px;margin:6px 0;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white;font-size:14px'><button style='background:linear-gradient(135deg,#10b981,#059669);color:white;padding:12px;width:100%;border:none;border-radius:10px;font-weight:800;margin-top:12px;cursor:pointer'>Login</button></form><div style='text-align:center;margin-top:16px;font-size:12px'><a href='/register' style='color:#10b981;text-decoration:none;font-weight:600'>Create account →</a></div></div></body></html>"

@app.route("/register")
def register_page():
    ref=request.args.get("ref","")
    ref_banner=f"<div style='background:#10b98115;border:1px solid #10b98133;padding:8px;border-radius:10px;font-size:11px;color:#10b981;margin-bottom:12px'>🎁 Referred by: <b>{ref}</b> - You'll get support from referrer</div>" if ref else ""
    return f"<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='background:#050a14;color:white;font-family:Inter,Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:12px'><div style='width:100%;max-width:380px;background:#111a2e;padding:24px;border-radius:20px;border:1px solid #1e293b'><h2 style='font-size:18px;font-weight:800;margin:0 0 4px'>Create Account</h2><p style='color:#64748b;font-size:12px;margin:0 0 16px'>Join AGENT 35 PRO - 55 symbols, professional signals</p>{ref_banner}<form action='/register/create' method='post'><input name='email' type='email' placeholder='Email' required style='width:100%;padding:12px;margin:5px 0;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white'><input name='name' placeholder='Full Name' required style='width:100%;padding:12px;margin:5px 0;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white'><input name='password' type='password' placeholder='Password' required style='width:100%;padding:12px;margin:5px 0;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white'><input name='ref' value='{ref}' placeholder='Referral Code (optional)' style='width:100%;padding:12px;margin:5px 0;border-radius:10px;border:1px solid #10b98133;background:#0b1220;color:white'><button style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:10px;font-weight:800;margin-top:12px;cursor:pointer'>Create Account</button></form><div style='text-align:center;margin-top:14px;font-size:12px'><a href='/login' style='color:#64748b;text-decoration:none'>Already have account? Login</a></div></div></body></html>"

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

@app.route("/link-telegram", methods=["GET","POST"])
def link_telegram():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); is_admin=email=="admin@agent35.com"; tg_users=load_json(TG_FILE, dict)
    if request.method=="POST":
        chat_id=request.form.get("chat_id","").strip()
        if chat_id:
            tg_users[email]={"chat_id":chat_id,"linked_at":datetime.now().isoformat(),"manual":True}
            save_json(TG_FILE, tg_users); return redirect("/dashboard")
    current=tg_users.get(email,{}).get("chat_id","Not linked - follow steps below")
    content=f"""<div style='max-width:600px;margin:0 auto;padding:14px'>
<div class='card'><h2 style='font-size:16px;margin:0 0 6px'>Link Telegram</h2><p style='color:#64748b;font-size:12px;margin:0 0 14px'>Get signals directly to your Telegram. 2 steps only.</p>
<div style='background:#0b1220;border:1px solid #1e293b;padding:12px;border-radius:10px;font-size:11px;margin-bottom:14px'><div style='color:#64748b;font-size:9px'>CURRENT STATUS</div><div style='font-weight:700;margin-top:4px'>{current}</div></div>
<div style='background:#111a2e;border:1px solid #1e293b;border-radius:12px;padding:14px;margin-bottom:14px'>
<h4 style='margin:0 0 10px;font-size:13px'>Step 1: Start Bot</h4>
<div style='font-size:12px;color:#94a3b8;line-height:1.6'>1. Open Telegram → Search your bot (from env TELEGRAM_BOT_TOKEN)<br>2. Send <code style='background:#0b1220;padding:2px 6px;border-radius:4px'>/start</code><br>3. Bot will reply with your Chat ID (numbers)<br>4. Copy that Chat ID</div>
</div>
<div style='background:#111a2e;border:1px solid #1e293b;border-radius:12px;padding:14px'>
<h4 style='margin:0 0 10px;font-size:13px'>Step 2: Paste Chat ID</h4>
<form method='post'><input name='chat_id' placeholder='Paste Chat ID here (e.g. 1234567890)' style='width:100%;padding:12px;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white' required><button type='submit' style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:10px;font-weight:800;margin-top:10px;cursor:pointer'>Connect Telegram</button></form>
</div>
</div>
</div>"""
    return pro_layout(content,"Settings", is_admin=is_admin)

@app.route("/pay")
def pay_page():
    plan=request.args.get("plan","yearly"); is_admin=session.get("user")=="admin@agent35.com"; email=session.get("user","")
    curr_sym=get_currency_symbol(get_user_settings(email or "admin@agent35.com").get("currency","ZAR"))
    price = "500" if plan=="yearly" else "5000"
    content=f"""<div style='max-width:600px;margin:0 auto;padding:14px'>
<div class='card'><h2 style='font-size:18px;margin:0'>Pay for {plan.title()} - {curr_sym}{price}</h2>
<div style='background:#0b1220;padding:14px;border-radius:12px;margin:14px 0;border:1px solid #1e293b'>
<div style='display:grid;gap:10px;font-size:13px'>
<div><span style='color:#64748b;font-size:10px'>BANK</span><div style='font-weight:700'>Capitec Business</div></div>
<div><span style='color:#64748b;font-size:10px'>ACCOUNT</span><div style='font-weight:700;font-family:monospace;font-size:14px'>2586572676</div></div>
<div><span style='color:#64748b;font-size:10px'>REFERENCE</span><div style='font-weight:700'>A35-{email[:4].upper() if email else 'XXXX'}</div></div>
<div><span style='color:#64748b;font-size:10px'>AMOUNT</span><div style='font-weight:800;color:#10b981;font-size:16px'>{curr_sym}{price}</div></div>
</div>
</div>
<form action='/pay/submit' method='post' style='margin-top:14px'><input type='hidden' name='plan' value='{plan}'><input type='hidden' name='price' value='{price}'><input name='ref' placeholder='Payment Reference (e.g. A35-JOHN)' required style='width:100%;padding:12px;border-radius:10px;border:1px solid #1e293b;background:#0b1220;color:white;margin-bottom:8px'><button type='submit' style='background:#10b981;color:white;padding:12px;width:100%;border:none;border-radius:10px;font-weight:800'>I Have Paid - Submit Proof</button></form>
<div style='font-size:11px;color:#64748b;margin-top:12px;text-align:center'>Admin approves within 1 hour after verification<br>Need help? Contact via Telegram</div>
</div>
</div>"""
    return pro_layout(content,"Plans", is_admin=is_admin)

@app.route("/pay/submit", methods=["POST"])
def pay_submit():
    if not session.get("user"): return redirect("/login")
    email=session.get("user"); users=load_json(USERS_FILE, dict)
    ref_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    users[ref_id]={"user":email,"plan":request.form.get("plan","yearly"),"price":request.form.get("price","500"),"ref":request.form.get("ref",""),"status":"pending","created":datetime.now().isoformat()}
    save_json(USERS_FILE, users)
    return pro_layout(f"<div style='max-width:600px;margin:60px auto;text-align:center'><div class='card'><h2 style='color:#10b981'>Payment Submitted ✅</h2><p style='color:#94a3b8;font-size:13px'>Ref: {ref_id}<br>Admin will approve within 1 hour.<br>You will receive activation.</p><a href='/dashboard' style='background:#10b981;color:white;padding:10px 18px;border-radius:10px;text-decoration:none;font-weight:700;display:inline-block;margin-top:12px'>Back to Dashboard</a></div></div>","Plans", is_admin=email=="admin@agent35.com")

@app.route("/cron/scan")
def cron_scan():
    if request.args.get("secret")!=os.getenv("CRON_SECRET"): return jsonify({"error":"bad secret"})
    system=load_json(SYSTEM_FILE, dict); system["last_scan"]=datetime.now().isoformat(); system["total_scans"]=system.get("total_scans",0)+1; save_json(SYSTEM_FILE, system)
    settings_all=load_json(SETTINGS_FILE, dict); all_syms=set()
    for s in settings_all.values(): all_syms.update(s.get("symbols",[]))
    if not all_syms: all_syms=set(ALL_SYMBOLS[:12])
    tracked=load_json(TRACK_FILE, dict); now=datetime.now()
    cleaned={};
    for k,v in tracked.items():
        try:
            t=datetime.fromisoformat(v.get("time","2000-01-01T00:00:00"))
            if (now - t).total_seconds() < 86400: cleaned[k]=v
        except: pass
    tracked=cleaned
    if len(tracked)>=MAX_TRACKED: return jsonify({"error":f"Limit {MAX_TRACKED}","tracked":list(tracked.keys())})
    sent=[]; skipped=[]
    for sym in list(all_syms)[:20]:
        if len(tracked)>=MAX_TRACKED and sym not in tracked: skipped.append(f"{sym} LIMIT"); continue
        try:
            sample_settings = next(iter(settings_all.values())) if settings_all else {"trade_news":True,"risk_percent":1,"rr_ratio":2.5,"lot_size":0.01,"leverage":"1:500","account_size":142,"currency":"ZAR","trading_method":"method1_premium_sweep"}
            r=eng.full_multi_tf_analysis(sym, sample_settings)
            if not r.get('signal'): continue
            entry=r.get('entry'); rr=sample_settings.get('rr_ratio',2.5)
            sl,tp,sl_dist,tp_dist,risk_amt=calculate_dynamic_sl_tp(sym, entry, r.get('bias',''), 142, 0.01, "1:500", 1, rr, 0.7, 0.35, 2.0, 10.0)
            curr_sym=get_currency_symbol(sample_settings.get("currency","ZAR"))
            send_telegram_pro(sym, r.get('score',7), r.get('bias',''), entry, sl, tp, sl_dist, tp_dist, rr, risk_amt, 1, 0.01, "1:500", 142, r.get('confluence',''), curr_sym, r.get('method',''))
            tracked[sym]={"time":now.isoformat(),"bias":r.get('bias'),"entry":entry,"sl":sl,"tp":tp,"risk_amt":risk_amt,"rr":rr}
            save_json(TRACK_FILE, tracked); sent.append(sym)
            if len(tracked)>=MAX_TRACKED: break
        except: pass
    return jsonify({"sent":sent,"skipped":skipped,"tracked":len(tracked),"limit":MAX_TRACKED})

@app.route("/health")
def health():
    test=eng.full_multi_tf_analysis("BTCUSD", {"trade_news":True,"currency":"ZAR","trading_method":"method5_smc_ob_bos"})
    tracked=load_json(TRACK_FILE, dict); journal=load_json(JOURNAL_FILE, list)
    return jsonify({"ok":True,"version":"V21 PRO UI","symbols":len(ALL_SYMBOLS),"tracked":f"{len(tracked)}/{MAX_TRACKED}","btc_test":test.get('score'),"journal":len(journal)})

@app.route("/backup-now")
def backup_now():
    if not session.get("user"): return redirect("/login")
    save_json(SYSTEM_FILE, load_json(SYSTEM_FILE, dict))
    return redirect("/dashboard")

@app.route("/master")
def master_redirect(): return redirect("/creator?secret=ADMIN35")

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000)
