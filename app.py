"""
AGENT 35 - V12.6 ULTIMATE FINAL
- DUAL FREE: Finnhub + TwelveData = R0 (No Yahoo block)
- SCREENSHOT LOOK: /pay page exactly like your image
- FULL REFERRAL: 10 refs = Lifetime auto, /r/CODE, leaderboard, tracking
- All features: /pay, /dashboard, /scan, /status, /pairs, /journal, /leaderboard, TradingView webhook
"""
import os, json, random, string, threading, time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
import requests
from trading_engine import full_multi_tf_analysis

app = Flask(__name__)
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///agent35.db')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'agent35-final-v12-secret-2024')
db = SQLAlchemy(app)

BOT_TOKEN = os.environ.get('BOT_TOKEN','') or os.environ.get('TELEGRAM_BOT_TOKEN','')
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL','https://agent-35-trading-bot.onrender.com').rstrip('/')
BOT_USERNAME = os.environ.get('BOT_USERNAME','Agent35_Signals_Bot')
ADMIN_ID = os.environ.get('ADMIN_ID','')
ADMIN_SECRET = os.environ.get('ADMIN_SECRET','admin123')
# 10 PAIRS FOR FREE LIMIT
SCAN_PAIRS = ["XAUUSD","EURUSD","GBPUSD","USDJPY","GBPJPY","EURJPY","USDZAR","BTCUSD","NAS100","US30"]

# ========== DB MODELS ==========
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(100)); first_name = db.Column(db.String(100))
    referral_code = db.Column(db.String(20), unique=True); referred_by = db.Column(db.String(20), nullable=True)
    subscription_type = db.Column(db.String(20), default="trial") # trial, yearly, lifetime
    subscription_end = db.Column(db.DateTime, default=lambda: datetime.utcnow()+timedelta(days=3))
    is_active = db.Column(db.Boolean, default=True)
    selected_pairs = db.Column(db.Text, default=json.dumps(["XAUUSD","EURUSD","GBPUSD","GBPJPY","EURJPY"]))
    referrals_count = db.Column(db.Integer, default=0); total_earned = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow); last_seen = db.Column(db.DateTime, default=datetime.utcnow)

class Signal(db.Model):
    id = db.Column(db.Integer, primary_key=True); symbol=db.Column(db.String(20)); direction=db.Column(db.String(10))
    entry=db.Column(db.Float); sl=db.Column(db.Float); tp=db.Column(db.Float); score=db.Column(db.Integer)
    quality=db.Column(db.String(50)); bias=db.Column(db.String(300)); confluence=db.Column(db.Text)
    created_at=db.Column(db.DateTime, default=datetime.utcnow); result=db.Column(db.String(20), default="pending")

class ReferralPayment(db.Model):
    id=db.Column(db.Integer, primary_key=True); referrer_code=db.Column(db.String(20))
    referred_telegram_id=db.Column(db.String(100)); amount=db.Column(db.Float, default=500)
    status=db.Column(db.String(20), default="pending"); created_at=db.Column(db.DateTime, default=datetime.utcnow)

class ScanLog(db.Model):
    id=db.Column(db.Integer, primary_key=True); message=db.Column(db.Text); created_at=db.Column(db.DateTime, default=datetime.utcnow)

class Journal(db.Model):
    id=db.Column(db.Integer, primary_key=True); telegram_id=db.Column(db.String(100)); symbol=db.Column(db.String(20))
    direction=db.Column(db.String(10)); entry=db.Column(db.Float); sl=db.Column(db.Float); tp=db.Column(db.Float)
    result=db.Column(db.String(20)); profit=db.Column(db.Float, default=0); created_at=db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context(): db.create_all()

# ========== HELPERS ==========
def generate_ref_code(u="USER"):
    base=''.join([c for c in (u[:3].upper() if len(u)>=3 else "AG35") if c.isalnum()])
    return f"AG35-{base}-{''.join(random.choices(string.ascii_uppercase+string.digits,k=4))}"

def send_telegram(chat_id,text,parse_mode="Markdown",reply_markup=None):
    if not BOT_TOKEN: print(f"[MOCK {chat_id}]: {text[:200]}"); return True
    try:
        payload={"chat_id":chat_id,"text":text,"parse_mode":parse_mode}
        if reply_markup: payload["reply_markup"]=reply_markup
        r=requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=15)
        if r.status_code!=200: print(f"TG Error {r.text[:200]}")
        return r.status_code==200
    except Exception as e: print(f"TG send err {e}"); return False

def get_user_pairs(u):
    try: return json.loads(u.selected_pairs)
    except: return ["XAUUSD","EURUSD","GBPUSD","GBPJPY","EURJPY"]

def check_subscription(u):
    if not u: return False
    if u.subscription_type=="lifetime": return True
    return u.subscription_end and u.subscription_end>datetime.utcnow()

def format_signal_msg(a,source="SCANNER"):
    emoji="🟢 BUY" if a['direction']=="BUY" else "🔴 SELL"
    return f"""{emoji} **{a['symbol']} | {a.get('quality','')}**
{'🤖 AUTO SCAN V12.6 DUAL FREE' if source=='SCANNER' else '⚡ TRADINGVIEW SMC'}

**ENTRY:** `{a['entry']:.5f}`
**SL:** `{a['sl']:.5f}`
**TP:** `{a['tp']:.5f}`
**Score:** {a.get('score',0)}/12
**BIAS:** {a.get('bias','')}

**CONFLUENCE:**
"""+"\n".join([f"• {c}" for c in a.get('confluence',[])[:7]])+f"\n\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"

# ========== SCANNER ==========
last_signals={}
def scan_and_send():
    print(f"[{datetime.utcnow()}] V12.6 DUAL FREE scan {len(SCAN_PAIRS)} pairs")
    with app.app_context():
        try:
            for symbol in SCAN_PAIRS:
                if symbol in last_signals and datetime.utcnow()-last_signals[symbol]<timedelta(minutes=30): continue
                analysis=full_multi_tf_analysis(symbol, rr_target=2.5)
                if analysis.get('signal') and analysis.get('score',0)>=5:
                    print(f"✅ SIGNAL {symbol} {analysis['direction']} Score {analysis['score']}")
                    last_signals[symbol]=datetime.utcnow()
                    sig=Signal(symbol=symbol,direction=analysis['direction'],entry=analysis['entry'],sl=analysis['sl'],tp=analysis['tp'],score=analysis['score'],quality=analysis['quality'],bias=analysis['bias'],confluence=json.dumps(analysis['confluence']))
                    db.session.add(sig); db.session.commit()
                    msg=format_signal_msg(analysis)
                    sent=0
                    for u in User.query.filter_by(is_active=True).all():
                        if not check_subscription(u): continue
                        if symbol not in get_user_pairs(u): continue
                        if send_telegram(u.telegram_id,msg): sent+=1; time.sleep(0.06)
                    if ADMIN_ID: send_telegram(ADMIN_ID, f"📡 V12.6 {symbol} sent to {sent} users")
                    db.session.add(ScanLog(message=f"SIGNAL {symbol} {analysis['direction']} Score {analysis['score']} -> {sent} users"))
                    db.session.commit()
                else:
                    print(f"⏭️ {symbol}: {analysis.get('reason','No signal')} Score:{analysis.get('score',0)}")
                time.sleep(4)
        except Exception as e:
            print(f"CRITICAL Scan error {e}"); import traceback; traceback.print_exc()

def background_scanner():
    while True:
        try: scan_and_send()
        except Exception as e: print(f"Scanner loop err {e}")
        time.sleep(300)

if not hasattr(app,'scanner_started'):
    threading.Thread(target=background_scanner,daemon=True).start()
    app.scanner_started=True
    print(f"✅ Background 5m scanner started for {len(SCAN_PAIRS)} pairs - V12.6 DUAL FREE")

# ========== PAYMENT PAGE - YOUR SCREENSHOT LOOK ==========
PAYMENT_TEMPLATE = """
<!DOCTYPE html><html><head><title>Agent 35 - Payment</title><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
*{font-family:'Inter',Arial,sans-serif;box-sizing:border-box}
body{margin:0;background:#0d1b2a;color:#e0e0e0;min-height:100vh}
.topbar{display:flex;justify-content:space-between;align-items:center;padding:10px 18px;background:rgba(255,255,255,0.05);border-bottom:1px solid rgba(0,255,170,0.18);font-size:12px;color:#00ffaa;flex-wrap:wrap;gap:6px}
.container{max-width:1050px;margin:0 auto;padding:16px}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px}
@media(max-width:720px){.cards{grid-template-columns:1fr}}
.card{background:linear-gradient(135deg,rgba(255,255,255,0.07),rgba(255,255,255,0.03));backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.1);border-radius:18px;padding:22px;position:relative}
.card.lifetime{border:1.5px solid #00ffaa;box-shadow:0 0 22px rgba(0,255,170,0.15);background:linear-gradient(135deg,rgba(0,255,170,0.08),rgba(255,255,255,0.03))}
.card h2{margin:0 0 12px 0;font-size:18px;font-weight:800;line-height:1.2}
.card h2 span.price{font-size:30px;font-weight:900}
.yearly h2 span.price{color:#fff}.lifetime h2 span.price{color:#00ffaa}
.sub{color:#8a9bb0;font-size:13px;font-weight:400}
.feat{margin:16px 0}
.feat div{margin:8px 0;display:flex;align-items:center;font-size:13.5px}
.feat div::before{content:'✓';margin-right:8px;background:#00ffaa;color:#000;border-radius:3px;width:18px;height:18px;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:12px;flex-shrink:0}
.btn{display:block;width:100%;padding:13px;text-align:center;border-radius:12px;font-weight:800;text-decoration:none;margin-top:14px;border:1px solid rgba(255,255,255,0.15);cursor:pointer;transition:0.2s}
.btn-yearly{background:rgba(255,255,255,0.06);color:#fff}
.btn-yearly:hover{background:rgba(255,255,255,0.12)}
.btn-lifetime{background:#00ffaa;color:#000;box-shadow:0 4px 15px rgba(0,255,170,0.3)}
.btn-lifetime:hover{background:#00e699}
.pay-box{background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);border-radius:18px;padding:20px;margin-top:8px}
.pay-box h3{color:#00ffaa;margin:0 0 14px 0;display:flex;align-items:center;font-size:15px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:720px){.grid2{grid-template-columns:1fr}}
.info-card{background:rgba(0,0,0,0.32);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:14px;font-size:13px;line-height:1.7}
.ref{color:#00ffaa;font-weight:900;letter-spacing:0.6px}
.btn-paid{display:block;width:100%;padding:12px;border-radius:10px;text-align:center;font-weight:800;text-decoration:none;margin-top:12px;font-size:13px;transition:0.2s}
.btn-paid-yearly{background:rgba(255,255,255,0.08);color:#fff;border:1px solid rgba(255,255,255,0.15)}
.btn-paid-lifetime{background:rgba(0,255,170,0.15);color:#00ffaa;border:1px solid #00ffaa}
.small{font-size:11px;color:#7a8a9a;margin-top:6px}
.badge-ref{display:inline-block;background:rgba(0,255,170,0.12);border:1px solid rgba(0,255,170,0.25);color:#00ffaa;padding:4px 10px;border-radius:20px;font-size:11px;font-weight:700;margin-top:8px}
</style></head><body>
<div class="topbar">
  <div><b id="live-time">--:--:--</b> &nbsp;|&nbsp; SAST <span id="sast">--:--</span> &nbsp;|&nbsp; <span style="color:#00ffaa;font-weight:700">London + New York ACTIVE</span> &nbsp;|&nbsp; Ref: <span class="ref">{{code}}</span></div>
  <div>creator@agent35.co.za | {{referrer_name}} invited you | {{refs}} referrals</div>
</div>
<div class="container">
<div class="cards">
  <div class="card yearly">
    <h2>Yearly Access<br><span class="price">R500</span> <span class="sub">/ year</span></h2>
    <div class="feat">
      <div>5 Custom Watchlist Pairs</div>
      <div>Real-time Telegram Signals</div>
      <div>Smart Trade Management</div>
      <div>Monthly Journal + Analytics</div>
      <div>Priority Support</div>
    </div>
    <a class="btn btn-yearly" href="https://t.me/{{bot}}?start={{code}}">Select Yearly - R500</a>
    <div class="badge-ref">Your link: /r/{{code}} | {{refs}}/10 for Lifetime</div>
  </div>
  <div class="card lifetime">
    <h2>Lifetime Access<br><span class="price">R5000</span> <span class="sub">/ once</span></h2>
    <div class="feat">
      <div>Everything in Yearly</div>
      <div>Lifetime Updates</div>
      <div>Never Pay Again</div>
      <div>VIP Telegram Group</div>
      <div>1-on-1 Setup Call</div>
    </div>
    <a class="btn btn-lifetime" href="https://t.me/{{bot}}?start={{code}}">Select Lifetime - R5000</a>
    <div class="badge-ref">🔥 Refer 10 = Lifetime FREE auto!</div>
  </div>
</div>

<div class="pay-box">
  <h3>💳 How to Pay</h3>
  <div class="grid2">
    <div>
      <div style="font-size:12px;color:#8aa;margin-bottom:8px">Bank: Capitec</div>
      <div class="info-card">
        <b>Account Number:</b> 2586572676<br>
        <b>Reference:</b> <span class="ref">{{code}}</span><br>
        <div class="small">Use this exact reference so we can approve you instantly. Take screenshot after payment.</div>
      </div>
      <a class="btn-paid btn-paid-yearly" href="https://t.me/{{admin}}?text=I%20Paid%20R500%20Yearly%20-%20{{code}}%20-%20My%20Telegram%20ID%20is%20{{tg_id}}">I Paid R500 Yearly - {{code}}</a>
    </div>
    <div>
      <div style="font-size:12px;color:#8aa;margin-bottom:8px">After Payment</div>
      <div class="info-card">
        1. Make payment with reference <span class="ref">{{code}}</span><br>
        2. Click "I Have Paid" below<br>
        3. Link Telegram for instant activation<br>
        4. Approval within 1-2 hours<br>
        <div class="small">Refer 10 paid users and you get Lifetime FREE automatically!</div>
      </div>
      <a class="btn-paid btn-paid-lifetime" href="https://t.me/{{admin}}?text=I%20Paid%20R5000%20Lifetime%20-%20{{code}}%20-%20My%20Telegram%20ID%20is%20{{tg_id}}">I Paid R5000 Lifetime - {{code}}</a>
    </div>
  </div>
  <div style="text-align:center;margin-top:18px;font-size:12px;color:#7a8a9a">
    <a href="/dashboard" style="color:#7a8a9a;text-decoration:none">← Back to Dashboard</a> |
    Your referral link: <span style="color:#00ffaa">{{render_url}}/r/{{code}}</span> |
    10 refs = Lifetime FREE |
    <a href="/leaderboard" style="color:#00ffaa">Leaderboard</a>
  </div>
</div>
</div>
<script>
function tick(){
  const now=new Date();
  const sast=new Date(now.toLocaleString('en-US',{timeZone:'Africa/Johannesburg'}));
  document.getElementById('live-time').innerText=now.toLocaleTimeString();
  document.getElementById('sast').innerText=sast.toLocaleTimeString();
}
setInterval(tick,1000);tick();
</script></body></html>
"""

# ========== ROUTES ==========
@app.route('/')
def home():
    with app.app_context():
        total=User.query.count()
        active=User.query.filter(User.subscription_end>datetime.utcnow()).count()+User.query.filter_by(subscription_type="lifetime").count()
        sig_count=Signal.query.count()
    return render_template_string("""
    <html><head><title>Agent 35 V12.6</title><meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{background:#0d1b2a;color:#fff;font-family:Inter,Arial;text-align:center;padding:20px}
  .card{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:20px;max-width:520px;margin:15px auto}
  .btn{background:#00ffaa;color:#000;padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:800;display:inline-block;margin:5px}
  .btn2{background:#0088cc;color:#fff}</style></head><body>
    <h1 style="color:#00ffaa">🚀 AGENT 35 V12.6 DUAL FREE</h1>
    <div class="card"><p>Finnhub 60/min + TwelveData 8/min = R0 Forever - No Yahoo Block</p><p>Pairs: {{pairs}}</p><p>Users: {{total}} Active: {{active}} Signals: {{sig}}</p></div>
    <div class="card"><a class="btn" href="/pay">💳 Payment Page (Your Screenshot Look)</a><a class="btn" href="/dashboard">📊 Dashboard</a><a class="btn btn2" href="/scan">Scan</a><a class="btn btn2" href="/health">Health</a></div>
    <p style="font-size:12px;color:#8aa">Referral: /r/YOURCODE | 10 refs = Lifetime FREE | Bot @{{bot}}</p></body></html>
    """, pairs=", ".join(SCAN_PAIRS), total=total, active=active, sig=sig_count, bot=BOT_USERNAME)

@app.route('/pay')
@app.route('/pay/<code>')
def pay_page(code=None):
    # If no code, generate temp one for viewing
    if not code:
        code = f"AG35-{''.join(random.choices(string.ascii_uppercase+string.digits,k=8))}"
        referrer_name = "Direct"
        refs = 0
        tg_id = ""
    else:
        with app.app_context():
            u = User.query.filter_by(referral_code=code).first()
            referrer_name = (u.first_name or u.username) if u else "Friend"
            refs = u.referrals_count if u else 0
            tg_id = u.telegram_id if u else ""
        referrer_name = referrer_name
    return render_template_string(PAYMENT_TEMPLATE, code=code, bot=BOT_USERNAME, admin=BOT_USERNAME.replace('_Bot','') or BOT_USERNAME, referrer_name=referrer_name, refs=refs, tg_id=tg_id, render_url=RENDER_URL)

@app.route('/r/<code>')
def referral_redirect(code):
    # FULL REFERRAL SYSTEM - This is the link you share
    with app.app_context():
        referrer = User.query.filter_by(referral_code=code).first()
        ref_name = (referrer.first_name or referrer.username) if referrer and (referrer.first_name or referrer.username) else "Friend"
        refs = referrer.referrals_count if referrer else 0
        tg_id = ""
    # Show same payment look but with referrer info - this converts better
    return render_template_string(PAYMENT_TEMPLATE, code=code, bot=BOT_USERNAME, admin=BOT_USERNAME.replace('_Bot','') or BOT_USERNAME, referrer_name=ref_name, refs=refs, tg_id=tg_id, render_url=RENDER_URL)

@app.route('/dashboard')
def dashboard():
    with app.app_context():
        total=User.query.count(); active=User.query.filter(User.subscription_end>datetime.utcnow()).count()+User.query.filter_by(subscription_type="lifetime").count()
        trial=User.query.filter_by(subscription_type="trial").count(); lt=User.query.filter_by(subscription_type="lifetime").count()
        sig_total=Signal.query.count(); sig_24=Signal.query.filter(Signal.created_at>=datetime.utcnow()-timedelta(hours=24)).count()
        top=User.query.order_by(User.referrals_count.desc()).limit(10).all()
        last_sigs=Signal.query.order_by(Signal.created_at.desc()).limit(20).all()
        last_logs=ScanLog.query.order_by(ScanLog.created_at.desc()).limit(15).all()
        td="✅ YES" if os.environ.get('TWELVEDATA_API_KEY') else "❌ NO"; fh="✅ YES" if os.environ.get('FINNHUB_API_KEY') else "❌ NO"; bt="✅ YES" if BOT_TOKEN else "❌ NO"
        top_rows="".join([f"<tr><td>{i}</td><td>{(u.first_name or u.username or f'U{i}')[:14]}</td><td><b>{u.referrals_count}</b></td><td>{u.subscription_type}</td><td>{u.referral_code}</td><td><a style='color:#00ffaa' href='/r/{u.referral_code}'>/r/{u.referral_code}</a></td></tr>" for i,u in enumerate(top,1)])
        sig_rows="".join([f"<tr><td>{s.created_at.strftime('%m-%d %H:%M')}</td><td><b>{s.symbol}</b></td><td>{s.direction}</td><td>{s.score}/12</td><td>{s.quality[:15]}</td></tr>" for s in last_sigs])
        log_rows="".join([f"<div style='font-size:11px;margin:3px 0'>[{l.created_at.strftime('%H:%M')}] {l.message[:90]}</div>" for l in last_logs])

    return render_template_string("""
    <!DOCTYPE html><html><head><title>Dashboard V12.6</title><meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');
    body{font-family:Inter,Arial;background:#0d1b2a;color:#fff;margin:0;padding:14px}
  .card{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:16px;margin-bottom:12px}
  .btn{background:#00ffaa;color:#000;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:800;display:inline-block;margin:4px;font-size:13px}
  .btn2{background:#0088cc;color:#fff}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
  .stat{font-size:28px;font-weight:900;color:#00ffaa}
    table{width:100%;font-size:11px;border-collapse:collapse} th{background:#1a2a3a;padding:7px;text-align:left} td{padding:6px;border-bottom:1px solid rgba(255,255,255,0.07)}
    </style></head><body>
    <h1 style="color:#00ffaa;margin:4px 0">🚀 AGENT 35 V12.6 FULL DASHBOARD + REFERRAL</h1>
    <div style="color:#8aa;font-size:12px;margin-bottom:10px">DUAL FREE R0 | {{pairs}} | 5 min scan | Anti-spam 30 min</div>
    <div><a class="btn" href="/pay">💳 Pay Page (Screenshot)</a><a class="btn btn2" href="/scan">🔍 Scan Now</a><a class="btn btn2" href="/health">Health</a><a class="btn" style="background:#222;color:#fff" href="/leaderboard">🏆 Leaderboard</a></div>
    <div class="grid" style="margin-top:12px">
      <div class="card"><h3>👥 Users (Referral System)</h3><div class="stat">{{total}}</div>Active: {{active}} | Trial: {{trial}} | Lifetime: {{lt}}<br><small>10 refs = Lifetime FREE auto</small></div>
      <div class="card"><h3>📡 Signals</h3><div class="stat">{{sig_total}}</div>24h: {{sig_24}}<br>Engine: V12.6 SHIFT HUNTER</div>
      <div class="card"><h3>🔑 API Keys R0</h3>Twelve: {{td}}<br>Finnhub: {{fh}}<br>Bot: {{bt}}<br><small>68 req/min FREE</small></div>
      <div class="card"><h3>🔗 Referral Link Format</h3>Share: <b style="color:#00ffaa">{{render_url}}/r/YOURCODE</b><br>Example: /r/AG35-FREE-1234<br>After 10 paid refs, user becomes Lifetime auto</div>
    </div>
    <div class="grid" style="margin-top:12px">
      <div class="card"><h3>🏆 Top 10 Referrers - Full Referral System</h3><table><tr><th>#</th><th>Name</th><th>Refs</th><th>Type</th><th>Code</th><th>Link</th></tr>{{top_rows}}</table></div>
      <div class="card"><h3>📡 Last 20 Signals</h3><table><tr><th>Time</th><th>Sym</th><th>Dir</th><th>Score</th><th>Q</th></tr>{{sig_rows}}</table></div>
    </div>
    <div class="card" style="margin-top:12px"><h3>📝 Scanner Logs</h3>{{log_rows}}</div>
    </body></html>
    """, pairs=", ".join(SCAN_PAIRS), total=total, active=active, trial=trial, lt=lt, sig_total=sig_total, sig_24=sig_24, td=td, fh=fh, bt=bt, render_url=RENDER_URL, top_rows=top_rows, sig_rows=sig_rows, log_rows=log_rows)

@app.route('/scan')
def manual_scan():
    threading.Thread(target=scan_and_send).start()
    return jsonify({"status":"V12.6 DUAL FREE scan started","pay_page":f"{RENDER_URL}/pay","dashboard":f"{RENDER_URL}/dashboard","referral_example":f"{RENDER_URL}/r/AG35-XXXX"})

@app.route('/health')
def health():
    return jsonify({"status":"ok","engine":"V12.6 DUAL FREE + REFERRAL + PAYMENT LOOK","twelvedata_key":"YES" if os.environ.get('TWELVEDATA_API_KEY') else "NO - ADD ENV","finnhub_key":"YES" if os.environ.get('FINNHUB_API_KEY') else "NO - ADD ENV","bot_token":"YES" if BOT_TOKEN else "NO","pairs":SCAN_PAIRS,"cost":"R0","pay_page":"/pay - Your screenshot look","referral":"/r/CODE - Full system with 10=Lifetime"})

@app.route('/stats')
def stats():
    with app.app_context():
        total=User.query.count(); active=User.query.filter(User.subscription_end>datetime.utcnow()).count()+User.query.filter_by(subscription_type="lifetime").count()
        sigs=Signal.query.order_by(Signal.created_at.desc()).limit(20).all()
        html=f"<h2>Stats V12.6</h2>Users: {total} Active: {active}<br><h3>Last 20 Signals</h3>"
        for s in sigs: html+=f"{s.created_at.strftime('%m-%d %H:%M')} - {s.symbol} {s.direction} {s.score}/12 {s.quality}<br>"
        html+='<br><a href="/dashboard">Dashboard</a> | <a href="/pay">Pay Page</a>'
        return html

@app.route('/leaderboard')
def leaderboard():
    with app.app_context():
        top=User.query.order_by(User.referrals_count.desc()).limit(20).all()
        html="<h2>🏆 Referral Leaderboard - 10 refs = Lifetime FREE</h2><p>Share your link: /r/YOURCODE</p>"
        for i,u in enumerate(top,1):
            name=u.first_name or u.username or f"User{i}"
            html+=f"{i}. {name} - {u.referrals_count} refs - {u.subscription_type} - Code: {u.referral_code} - Link: /r/{u.referral_code}<br>"
        html+='<br><a href="/dashboard">Back to Dashboard</a> | <a href="/pay">Pay Page</a>'
        return html

# ========== TRADINGVIEW WEBHOOK ==========
@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    try:
        data=request.get_json(force=True)
        if data.get('event')=="DELETE": return jsonify({"status":"ignored"})
        symbol=data.get('symbol','XAUUSD').replace('.X','').replace('=X','').replace('/','')
        if symbol=="GOLD": symbol="XAUUSD"
        entry=float(data.get('entry',0)); sl=float(data.get('sl',0)); tp=float(data.get('tp',0))
        if entry==0 or sl==0: return jsonify({"status":"invalid"})
        direction="BUY" if entry>sl else "SELL"
        with app.app_context():
            db.session.add(Signal(symbol=symbol,direction=direction,entry=entry,sl=sl,tp=tp,score=10,quality="TV FVG",bias="TV",confluence="[]")); db.session.commit()
        return jsonify({"status":"forwarded"})
    except Exception as e:
        return jsonify({"error":str(e)}),400

# ========== TELEGRAM BOT - FULL REFERRAL SYSTEM ==========
@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    try:
        data=request.get_json(force=True)
        if 'message' not in data: return jsonify({"ok":True})
        msg=data['message']; chat_id=str(msg['chat']['id']); text=msg.get('text','').strip()
        username=msg['from'].get('username',''); first_name=msg['from'].get('first_name','')
        with app.app_context():
            user=User.query.filter_by(telegram_id=chat_id).first()
            if text.startswith('/start'):
                parts=text.split(); ref_code=parts[1].strip() if len(parts)>1 else None
                if not user:
                    new_code=generate_ref_code(username or first_name)
                    while User.query.filter_by(referral_code=new_code).first(): new_code=generate_ref_code(username or first_name)
                    user=User(telegram_id=chat_id,username=username,first_name=first_name,referral_code=new_code,referred_by=ref_code,subscription_type="trial",subscription_end=datetime.utcnow()+timedelta(days=3))
                    db.session.add(user); db.session.commit()
                    if ref_code:
                        referrer=User.query.filter_by(referral_code=ref_code).first()
                        if referrer and referrer.telegram_id!=chat_id:
                            referrer.referrals_count+=1
                            db.session.add(ReferralPayment(referrer_code=ref_code,referred_telegram_id=chat_id,amount=500,status="pending"))
                            if referrer.referrals_count>=10 and referrer.subscription_type!="lifetime":
                                referrer.subscription_type="lifetime"
                                referrer.subscription_end=datetime.utcnow()+timedelta(days=365*10)
                                send_telegram(referrer.telegram_id, f"🎉 **LIFETIME UNLOCKED!**\nYou got {referrer.referrals_count} referrals! Now Lifetime FREE!\nYour link: {RENDER_URL}/r/{referrer.referral_code}")
                            else:
                                send_telegram(referrer.telegram_id, f"👥 New referral joined!\n{first_name or username} via your link\nProgress: {referrer.referrals_count}/10 for Lifetime\nYour link: {RENDER_URL}/r/{referrer.referral_code}")
                            db.session.commit()
                    send_telegram(chat_id, f"""
🚀 **AGENT 35 V12.6 DUAL FREE - Welcome!**

Your **Payment Page** (Your screenshot look):
{RENDER_URL}/pay/{user.referral_code}

Your **Referral Link** (Earn Lifetime):
`{RENDER_URL}/r/{user.referral_code}`

Share it - 10 paid = **LIFETIME FREE auto!**

**Pricing:**
• R500 Yearly
• R5000 Lifetime
• Refer 10 = FREE

**Commands:**
/pay - Payment page with Capitec details
/referral - Your referral stats
/status - Sub & refs
/pairs - Choose 5 pairs
/scan - Manual scan
/dashboard - Open dashboard
/leaderboard - Top referrers

Trial ends: {user.subscription_end.strftime('%Y-%m-%d %H:%M')}
                    """)
                else:
                    user.last_seen=datetime.utcnow(); db.session.commit()
                    send_telegram(chat_id, f"Welcome back {first_name}!\nCode: `{user.referral_code}` Refs: {user.referrals_count}/10\nPay: {RENDER_URL}/pay/{user.referral_code}\nLink: {RENDER_URL}/r/{user.referral_code}")

            elif text.startswith('/status'):
                if not user: send_telegram(chat_id, "Please /start first")
                else:
                    active=check_subscription(user); emoji="✅ ACTIVE" if active else "❌ EXPIRED"
                    end=user.subscription_end.strftime('%Y-%m-%d %H:%M') if user.subscription_end else "None"
                    send_telegram(chat_id, f"📊 **STATUS**\nType: {user.subscription_type.upper()} {emoji}\nEnds: {end}\nRefs: {user.referrals_count}/10\nCode: `{user.referral_code}`\nPay: {RENDER_URL}/pay/{user.referral_code}\nLink: {RENDER_URL}/r/{user.referral_code}")

            elif text.startswith('/referral'):
                if not user: send_telegram(chat_id, "Please /start first")
                else:
                    send_telegram(chat_id, f"🔗 **REFERRAL SYSTEM - 10 = LIFETIME FREE**\n\nYour Link:\n`{RENDER_URL}/r/{user.referral_code}`\n\nPayment Page:\n{RENDER_URL}/pay/{user.referral_code}\n\nStats: {user.referrals_count}/10\nNeeded: {max(0,10-user.referrals_count)} more\n\nShare: 🚀 Agent 35 5M SMC R500 Yearly, refer 10 = Lifetime FREE! Join: {RENDER_URL}/r/{user.referral_code}")

            elif text.startswith('/pay'):
                code=user.referral_code if user else "AG35-DEMO-1234"
                send_telegram(chat_id, f"💳 **PAYMENT PAGE - Screenshot Look**\n{RENDER_URL}/pay/{code}\n\nBank: Capitec\nAccount: 2586572676\nRef: `{code}`\n\nAfter pay click 'I Paid' button on page")

            elif text.startswith('/pairs'):
                if not user: send_telegram(chat_id, "Please /start first")
                else: send_telegram(chat_id, f"🎯 Choose 5 pairs\nSend like: `XAUUSD,EURUSD,GBPUSD,GBPJPY,NAS100`\nAvailable: {', '.join(SCAN_PAIRS)}\nCurrent: {', '.join(get_user_pairs(user))}")

            elif ',' in text and len(text)<80 and not text.startswith('/'):
                if user:
                    chosen=[p.strip().upper().replace('GOLD','XAUUSD') for p in text.split(',')][:5]
                    valid=[p for p in chosen if p in SCAN_PAIRS]
                    if valid: user.selected_pairs=json.dumps(valid); db.session.commit(); send_telegram(chat_id, f"✅ Pairs: {', '.join(valid)}")
                    else: send_telegram(chat_id, f"❌ Invalid. Use: {', '.join(SCAN_PAIRS)}")

            elif text.startswith('/scan'):
                if not user: send_telegram(chat_id, "Please /start first")
                elif not check_subscription(user): send_telegram(chat_id, f"❌ Expired. Pay: {RENDER_URL}/pay/{user.referral_code if user else ''}")
                else: send_telegram(chat_id, f"🔍 V12.6 scan {len(SCAN_PAIRS)} pairs..."); threading.Thread(target=scan_and_send).start()

            elif text.startswith('/leaderboard'):
                top=User.query.order_by(User.referrals_count.desc()).limit(10).all()
                txt="🏆 **TOP 10 - 10 refs = Lifetime FREE**\n\n"
                for i,u in enumerate(top,1):
                    name=u.first_name or u.username or f"User{i}"
                    txt+=f"{i}. {name} - {u.referrals_count} refs - {u.subscription_type}\n"
                send_telegram(chat_id, txt)

            elif text.startswith('/dashboard'):
                send_telegram(chat_id, f"📊 Dashboard: {RENDER_URL}/dashboard\nPay Page: {RENDER_URL}/pay/{user.referral_code if user else ''}")

            elif text.startswith('/journal'):
                parts=text.split()
                if len(parts)>=3:
                    try: s=parts[1].upper(); res=parts[2].lower(); prof=float(parts[3]) if len(parts)>3 else 0; db.session.add(Journal(telegram_id=chat_id,symbol=s,result=res,profit=prof,direction="BUY",entry=0,sl=0,tp=0)); db.session.commit(); send_telegram(chat_id,f"✅ Journal {s} {res} {prof}")
                    except: send_telegram(chat_id,"Use: /journal SYMBOL win/loss profit")
                else:
                    if user:
                        j=Journal.query.filter_by(telegram_id=chat_id).all(); wins=len([x for x in j if x.result=="win"]); total=len(j); wr=wins/total*100 if total>0 else 0
                        send_telegram(chat_id, f"📔 JOURNAL Total: {total} Wins: {wins} Winrate: {wr:.1f}%\nLog: /journal XAUUSD win 150")

            else:
                if user: send_telegram(chat_id, "Commands: /status /referral /pay /pairs /scan /leaderboard /dashboard /journal\nSend 5 pairs like: XAUUSD,EURUSD,GBPUSD,GBPJPY,NAS100")

        return jsonify({"ok":True})
    except Exception as e:
        print(f"TG webhook err {e}"); import traceback; traceback.print_exc(); return jsonify({"ok":True})

@app.route('/admin/activate/<telegram_id>/<type_>')
def admin_activate(telegram_id,type_):
    if request.args.get('secret')!=ADMIN_SECRET: return "Unauthorized",401
    with app.app_context():
        user=User.query.filter_by(telegram_id=telegram_id).first()
        if not user: return f"User {telegram_id} not found"
        if type_=="yearly": user.subscription_type="yearly"; user.subscription_end=datetime.utcnow()+timedelta(days=365)
        elif type_=="lifetime": user.subscription_type="lifetime"; user.subscription_end=datetime.utcnow()+timedelta(days=365*10)
        db.session.commit()
        if user.referred_by:
            rp=ReferralPayment.query.filter_by(referred_telegram_id=telegram_id,status="pending").first()
            if rp: rp.status="confirmed"; db.session.commit()
        send_telegram(telegram_id, f"✅ Activated {type_.upper()}! Pay page: {RENDER_URL}/pay/{user.referral_code}")
        return f"Activated {telegram_id} as {type_} - Ref: {user.referral_code}"

if __name__=='__main__':
    print(f"🚀 Agent 35 V12.6 DUAL FREE + SCREENSHOT PAY LOOK + FULL REFERRAL starting")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',10000)))
