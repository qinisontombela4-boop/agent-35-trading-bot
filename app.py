"""
AGENT 35 - app.py V12.6 ULTIMATE FINAL + ALL FIXES + FULL DASHBOARD
Your V12.5 + Dual Free Fix + Dashboard
"""

import os
import json
import random
import string
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, redirect
from flask_sqlalchemy import SQLAlchemy
import requests
from trading_engine import full_multi_tf_analysis

app = Flask(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///agent35.db')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'agent35-final-v12-secret-key-2024')

db = SQLAlchemy(app)

# FIXED: Support both names - fixes your ENV typo screenshot
BOT_TOKEN = os.environ.get('BOT_TOKEN', '') or os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://agent-35-trading-bot.onrender.com').rstrip('/')
BOT_USERNAME = os.environ.get('BOT_USERNAME', 'Agent35_Signals_Bot')
ADMIN_ID = os.environ.get('ADMIN_ID', '')

# FIXED FOR DUAL FREE - 10 PAIRS = R0 FOREVER
SCAN_PAIRS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURJPY", "USDZAR", "BTCUSD", "NAS100", "US30"]

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(100))
    first_name = db.Column(db.String(100))
    referral_code = db.Column(db.String(20), unique=True)
    referred_by = db.Column(db.String(20), nullable=True)
    subscription_type = db.Column(db.String(20), default="trial")
    subscription_end = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=3))
    is_active = db.Column(db.Boolean, default=True)
    selected_pairs = db.Column(db.Text, default=json.dumps(["XAUUSD","EURUSD","GBPUSD","GBPJPY","EURJPY"]))
    referrals_count = db.Column(db.Integer, default=0)
    total_earned = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

class Signal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20))
    direction = db.Column(db.String(10))
    entry = db.Column(db.Float)
    sl = db.Column(db.Float)
    tp = db.Column(db.Float)
    score = db.Column(db.Integer)
    quality = db.Column(db.String(50))
    bias = db.Column(db.String(300))
    confluence = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    result = db.Column(db.String(20), default="pending")
    pips = db.Column(db.Float, default=0)

class ReferralPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    referrer_code = db.Column(db.String(20))
    referred_telegram_id = db.Column(db.String(100))
    amount = db.Column(db.Float, default=500)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ScanLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Journal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.String(100))
    symbol = db.Column(db.String(20))
    direction = db.Column(db.String(10))
    entry = db.Column(db.Float)
    sl = db.Column(db.Float)
    tp = db.Column(db.Float)
    result = db.Column(db.String(20))
    profit = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

def generate_ref_code(username="USER"):
    base = (username[:3].upper() if username and len(username)>=3 else "AG35")
    base = ''.join([c for c in base if c.isalnum()])
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"AG35-{base}-{code}"

def send_telegram(chat_id, text, parse_mode="Markdown", reply_markup=None):
    if not BOT_TOKEN:
        print(f"[MOCK TG {chat_id}]: {text[:200]}")
        return True
    try:
        url = f"{TELEGRAM_API}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code!= 200:
            print(f"TG Error {r.text}")
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram send error: {e}")
        return False

def get_user_pairs(user):
    try:
        return json.loads(user.selected_pairs)
    except:
        return ["XAUUSD","EURUSD","GBPUSD","GBPJPY","EURJPY"]

def check_subscription(user):
    if not user:
        return False
    if user.subscription_type == "lifetime":
        return True
    if user.subscription_end and user.subscription_end > datetime.utcnow():
        return True
    return False

def format_signal_msg(analysis, source="SCANNER"):
    symbol = analysis['symbol']
    direction = analysis['direction']
    emoji = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    quality = analysis.get('quality','')
    entry = analysis['entry']
    sl = analysis['sl']
    tp = analysis['tp']
    score = analysis.get('score',0)
    bias = analysis.get('bias','')
    confluence = analysis.get('confluence',[])
    risk = abs(entry - sl)
    src_tag = "🤖 AUTO SCAN V12.6 DUAL FREE" if source == "SCANNER" else "⚡ TRADINGVIEW SMC"
    msg = f"""{emoji} **{symbol} | {quality}**
{src_tag}

**ENTRY:** `{entry:.5f}`
**SL:** `{sl:.5f}`
**TP:** `{tp:.5f}`
**RR:** 1:2.5 | **Risk:** {risk:.5f}
**Score:** {score}/12

**BIAS:** {bias}

**CONFLUENCE:**
"""
    for c in confluence[:7]:
        msg += f"• {c}\n"
    msg += f"""
⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
🧠 V12.6 DUAL FREE - 5M OB+MB+FVG+CHoCH + Premium/Discount
⚠️ Risk 1% max.
"""
    return msg

last_signals = {}

def scan_and_send():
    print(f"[{datetime.utcnow()}] Starting V12.6 DUAL FREE scan for {len(SCAN_PAIRS)} pairs...")
    with app.app_context():
        try:
            for symbol in SCAN_PAIRS:
                if symbol in last_signals:
                    if datetime.utcnow() - last_signals[symbol] < timedelta(minutes=30):
                        continue
                analysis = full_multi_tf_analysis(symbol, rr_target=2.5)
                if analysis.get('signal') and analysis.get('score',0) >= 5:
                    print(f"✅ SIGNAL FOUND {symbol} {analysis['direction']} Score {analysis['score']} {analysis['quality']}")
                    last_signals[symbol] = datetime.utcnow()
                    sig = Signal(symbol=symbol, direction=analysis['direction'], entry=analysis['entry'], sl=analysis['sl'], tp=analysis['tp'], score=analysis['score'], quality=analysis['quality'], bias=analysis['bias'], confluence=json.dumps(analysis['confluence']))
                    db.session.add(sig)
                    db.session.commit()
                    users = User.query.filter_by(is_active=True).all()
                    msg = format_signal_msg(analysis, source="SCANNER")
                    sent = 0
                    for u in users:
                        if not check_subscription(u):
                            continue
                        pairs = get_user_pairs(u)
                        if symbol not in pairs:
                            continue
                        if send_telegram(u.telegram_id, msg):
                            sent += 1
                            time.sleep(0.06)
                    if ADMIN_ID:
                        send_telegram(ADMIN_ID, f"📡 V12.6 Signal {symbol} sent to {sent} users\n{analysis['reason']}")
                    db.session.add(ScanLog(message=f"SIGNAL {symbol} {analysis['direction']} Score {analysis['score']} -> {sent} users | {analysis['reason']}"))
                    db.session.commit()
                else:
                    print(f"⏭️ {symbol}: {analysis.get('reason','No signal')} Score:{analysis.get('score',0)}")
                time.sleep(4) # FIXED from 1 to 4 for free API

        except Exception as e:
            print(f"CRITICAL Scan error: {e}")
            import traceback
            traceback.print_exc()

def background_scanner():
    while True:
        try:
            scan_and_send()
        except Exception as e:
            print(f"Background scanner loop error: {e}")
        time.sleep(300)

if not hasattr(app, 'scanner_started'):
    t = threading.Thread(target=background_scanner, daemon=True)
    t.start()
    app.scanner_started = True
    print(f"✅ Background 5m scanner started for {len(SCAN_PAIRS)} pairs - V12.6 DUAL FREE")

@app.route('/')
def home():
    with app.app_context():
        total = User.query.count()
        active = User.query.filter(User.subscription_end > datetime.utcnow()).count() + User.query.filter_by(subscription_type="lifetime").count()
        sig_count = Signal.query.count()
        last_sig = Signal.query.order_by(Signal.created_at.desc()).first()
    return render_template_string("""
    <!DOCTYPE html><html><head><title>Agent 35 V12.6</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{font-family:Arial;background:#0f0f0f;color:#fff;padding:20px;text-align:center}
  .card{background:#1a1a1a;padding:20px;border-radius:15px;margin:10px auto;max-width:500px;border:1px solid #333}
  .btn{background:#00ffaa;color:#000;padding:12px 25px;border-radius:10px;text-decoration:none;display:inline-block;margin:5px;font-weight:bold}
  .btn-blue{background:#0088cc;color:#fff}
    </style></head>
    <body>
    <h1>🚀 AGENT 35 V12.6 DUAL FREE</h1>
    <div class="card">
        <h3>🧠 Engine: DUAL FREE ACTIVE - No Yahoo Block</h3>
        <p>Finnhub 60/min + TwelveData 8/min = R0</p>
        <p>5M FVG + OB/MB Breaker + BOS/CHoCH Shift + Premium/Discount</p>
        <p><b>Pairs:</b> {{pairs}}</p>
        <p>Users: {{total}} | Active: {{active}} | Signals: {{sig_count}}</p>
        {% if last_sig %}
        <p>Last: {{last_sig.symbol}} {{last_sig.direction}} {{last_sig.quality}} {{last_sig.created_at}}</p>
        {% endif %}
    </div>
    <div class="card">
        <a class="btn" href="/dashboard">📊 FULL DASHBOARD</a>
        <a class="btn" href="/scan">🔍 Manual Scan</a>
        <a class="btn btn-blue" href="/stats">📊 Stats</a>
        <a class="btn btn-blue" href="/leaderboard">🏆 Leaderboard</a>
        <a class="btn btn-blue" href="/health">💚 Health</a>
    </div>
    <p>Bot: @{{bot}} | Render: {{url}}</p>
    </body></html>
    """, pairs=", ".join(SCAN_PAIRS), total=total, active=active, sig_count=sig_count, last_sig=last_sig, bot=BOT_USERNAME, url=RENDER_URL)

# ===== FULL DASHBOARD - NEW FEATURE RESTORED =====
@app.route('/dashboard')
def dashboard():
    with app.app_context():
        total_users = User.query.count()
        active_users = User.query.filter(User.subscription_end > datetime.utcnow()).count() + User.query.filter_by(subscription_type="lifetime").count()
        trial_users = User.query.filter_by(subscription_type="trial").count()
        lifetime_users = User.query.filter_by(subscription_type="lifetime").count()
        total_signals = Signal.query.count()
        signals_today = Signal.query.filter(Signal.created_at >= datetime.utcnow() - timedelta(hours=24)).count()
        top_referrers = User.query.order_by(User.referrals_count.desc()).limit(10).all()
        last_signals_db = Signal.query.order_by(Signal.created_at.desc()).limit(20).all()
        last_users = User.query.order_by(User.created_at.desc()).limit(10).all()
        last_logs = ScanLog.query.order_by(ScanLog.created_at.desc()).limit(15).all()
        td_key = "✅ YES" if os.environ.get('TWELVEDATA_API_KEY') else "❌ NO"
        fh_key = "✅ YES" if os.environ.get('FINNHUB_API_KEY') else "❌ NO"
        bot_key = "✅ YES" if BOT_TOKEN else "❌ NO"
    html = f"""
    <!DOCTYPE html><html><head><title>Dashboard V12.6</title><meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
    body{{font-family:Arial;background:#0a0a0a;color:#fff;margin:0;padding:15px}}
  .header{{background:#1a1a1a;padding:20px;border-radius:15px;text-align:center;border:1px solid #00ffaa;margin-bottom:15px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:15px}}
  .card{{background:#1e1e1e;padding:18px;border-radius:15px;border:1px solid #333}}
  .card h3{{color:#00ffaa}}.stat{{font-size:28px;font-weight:bold;color:#00ffaa}}
  .btn{{background:#00ffaa;color:#000;padding:10px 18px;border-radius:8px;text-decoration:none;display:inline-block;margin:4px;font-weight:bold;font-size:14px}}
  .btn-blue{{background:#0088cc;color:#fff}} table{{width:100%;font-size:12px;border-collapse:collapse}} th{{background:#333;padding:8px;text-align:left}} td{{padding:6px;border-bottom:1px solid #333}}
  .live{{color:#00ffaa;animation:blink 1s infinite}} @keyframes blink{{50%{{opacity:0.3}}}}
    </style></head><body>
    <div class="header"><h1>🚀 AGENT 35 V12.6 FULL DASHBOARD</h1><p><span class="live">● LIVE</span> DUAL FREE - R0 | 5 min scan | {', '.join(SCAN_PAIRS)}</p>
    <a class="btn" href="/scan">🔍 Trigger Scan</a><a class="btn btn-blue" href="/health">💚 Health</a><a class="btn btn-blue" href="/">Home</a></div>
    <div class="grid">
        <div class="card"><h3>👥 Users</h3><div class="stat">{total_users}</div><p>Active: <b>{active_users}</b> | Trial: {trial_users} | Lifetime: {lifetime_users}</p></div>
        <div class="card"><h3>📡 Signals</h3><div class="stat">{total_signals}</div><p>Last 24h: <b>{signals_today}</b></p></div>
        <div class="card"><h3>🔑 API Keys - R0</h3><p>TwelveData: {td_key}</p><p>Finnhub: {fh_key}</p><p>Bot: {bot_key}</p><p>Limit: 68/min FREE</p></div>
        <div class="card"><h3>⚙️ Scanner</h3><p>Interval: 5 min</p><p>Pairs: {len(SCAN_PAIRS)}</p><p>Anti-spam: 30 min</p></div>
    </div>
    <div class="grid" style="margin-top:15px">
        <div class="card"><h3>🏆 Top Referrers</h3><table><tr><th>#</th><th>Name</th><th>Refs</th><th>Type</th></tr>
    """
    for i, u in enumerate(top_referrers, 1):
        name = (u.first_name or u.username or f"User{i}")[:15]
        html += f"<tr><td>{i}</td><td>{name}</td><td><b>{u.referrals_count}</b></td><td>{u.subscription_type}</td></tr>"
    html += """</table></div><div class="card"><h3>📋 Last 10 Users</h3><table><tr><th>Time</th><th>Name</th><th>Type</th></tr>"""
    for u in last_users:
        name = (u.first_name or u.username or "NoName")[:12]
        t = u.created_at.strftime('%m-%d %H:%M')
        html += f"<tr><td>{t}</td><td>{name}</td><td>{u.subscription_type}</td></tr>"
    html += """</table></div></div><div class="grid" style="margin-top:15px"><div class="card"><h3>📡 Last 20 Signals</h3><table><tr><th>Time</th><th>Symbol</th><th>Dir</th><th>Score</th></tr>"""
    for s in last_signals_db:
        t = s.created_at.strftime('%m-%d %H:%M')
        html += f"<tr><td>{t}</td><td><b>{s.symbol}</b></td><td>{s.direction}</td><td>{s.score}/12</td></tr>"
    html += """</table></div><div class="card"><h3>📝 Logs</h3>"""
    for log in last_logs:
        t = log.created_at.strftime('%H:%M')
        html += f"<p style='font-size:11px'>[{t}] {log.message[:80]}</p>"
    html += f"""</div></div><div class="card" style="margin-top:15px;text-align:center"><a class="btn" href="/scan">Scan</a><a class="btn btn-blue" href="/health">Health</a><p>Bot: @{BOT_USERNAME}</p></div></body></html>"""
    return html

@app.route('/stats')
def stats():
    with app.app_context():
        total_users = User.query.count()
        active = User.query.filter(User.subscription_end > datetime.utcnow()).count() + User.query.filter_by(subscription_type="lifetime").count()
        signals = Signal.query.order_by(Signal.created_at.desc()).limit(20).all()
        html = f"<h2>📊 Agent 35 Stats V12.6</h2>Total: {total_users}<br>Active: {active}<br><h3>Last 20</h3>"
        for s in signals:
            html += f"{s.created_at.strftime('%m-%d %H:%M')} - <b>{s.symbol} {s.direction}</b> {s.score}/12 {s.quality}<br>"
        html += '<br><a href="/dashboard">Dashboard</a> | <a href="/">Home</a>'
        return html

@app.route('/leaderboard')
def leaderboard():
    with app.app_context():
        top = User.query.order_by(User.referrals_count.desc()).limit(10).all()
        html = "<h2>🏆 Leaderboard - 10 refs = Lifetime FREE</h2>"
        for i, u in enumerate(top, 1):
            name = u.username or u.first_name or f"User {u.id}"
            html += f"{i}. {name} - {u.referrals_count} refs - {u.subscription_type}<br>"
        html += '<br><a href="/dashboard">Dashboard</a>'
        return html

@app.route('/scan')
def manual_scan():
    threading.Thread(target=scan_and_send).start()
    return jsonify({"status": "V12.6 DUAL FREE scan started", "time": datetime.utcnow().isoformat(), "pairs": SCAN_PAIRS, "dashboard": f"{RENDER_URL}/dashboard"})

@app.route('/health')
def health():
    return jsonify({"status": "ok", "engine": "V12.6 DUAL FREE - Finnhub + TwelveData - R0", "twelvedata_key": "YES" if os.environ.get('TWELVEDATA_API_KEY') else "NO - ADD TWELVEDATA_API_KEY", "finnhub_key": "YES" if os.environ.get('FINNHUB_API_KEY') else "NO - ADD FINNHUB_API_KEY", "bot_token": "YES" if BOT_TOKEN else "NO", "pairs": SCAN_PAIRS, "cost": "R0 - FREE FOREVER", "dashboard": "/dashboard", "last_signals": {k: v.isoformat() for k,v in last_signals.items()}, "time": datetime.utcnow().isoformat()})

@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    try:
        data = request.get_json(force=True)
        print(f"[TV WEBHOOK] {data}")
        if data.get('event') == "DELETE":
            return jsonify({"status": "ignored delete box"})
        symbol_raw = data.get('symbol', 'XAUUSD')
        symbol = symbol_raw.replace('.X','').replace('=X','').replace('/','')
        if symbol == "GOLD": symbol = "XAUUSD"
        entry = float(data.get('entry', 0))
        sl = float(data.get('sl', 0))
        tp = float(data.get('tp', 0))
        lots = data.get('lots', 0)
        risk_usd = data.get('risk_usd', 0)
        rr = data.get('rr', 2.0)
        box_id = data.get('box_id','')
        color = data.get('color','')
        user_id_db = data.get('user_id', None)
        if entry == 0 or sl == 0:
            return jsonify({"status": "invalid entry/sl"})
        direction = "BUY" if entry > sl else "SELL"
        if color == "#00ffaa": direction = "BUY"
        if color == "#ff0055": direction = "SELL"
        msg = f"⚡ **TV SMC ALERT** - {box_id}\n{'🟢' if direction=='BUY' else '🔴'} **{symbol} {direction}**\nEntry: {entry:.5f} SL: {sl:.5f} TP: {tp:.5f}\nLots: {lots} Risk: ${risk_usd} RR: 1:{rr}"
        with app.app_context():
            target_users = []
            if user_id_db:
                u = User.query.filter_by(id=user_id_db).first()
                if u:
                    target_users = [u]
            else:
                all_users = User.query.filter_by(is_active=True).all()
                for u in all_users:
                    if not check_subscription(u): continue
                    if symbol in get_user_pairs(u):
                        target_users.append(u)
            sent = 0
            for u in target_users:
                if send_telegram(u.telegram_id, msg):
                    sent += 1
            sig = Signal(symbol=symbol, direction=direction, entry=entry, sl=sl, tp=tp, score=10, quality="TRADINGVIEW FVG", bias=f"TV {box_id}", confluence=json.dumps([f"TV FVG {box_id}", f"Lots {lots} Risk ${risk_usd}"]))
            db.session.add(sig)
            db.session.commit()
        return jsonify({"status": "forwarded", "symbol": symbol, "sent": sent})
    except Exception as e:
        print(f"TV Webhook error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 400

@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    try:
        data = request.get_json(force=True)
        if 'message' not in data:
            return jsonify({"ok": True})
        msg = data['message']
        chat_id = str(msg['chat']['id'])
        text = msg.get('text', '').strip()
        username = msg['from'].get('username', '')
        first_name = msg['from'].get('first_name', '')
        with app.app_context():
            user = User.query.filter_by(telegram_id=chat_id).first()
            if text.startswith('/start'):
                parts = text.split()
                ref_code = parts[1].strip() if len(parts) > 1 else None
                if not user:
                    new_code = generate_ref_code(username or first_name)
                    while User.query.filter_by(referral_code=new_code).first():
                        new_code = generate_ref_code(username or first_name)
                    user = User(telegram_id=chat_id, username=username, first_name=first_name, referral_code=new_code, referred_by=ref_code, subscription_type="trial", subscription_end=datetime.utcnow() + timedelta(days=3))
                    db.session.add(user)
                    db.session.commit()
                    if ref_code:
                        referrer = User.query.filter_by(referral_code=ref_code).first()
                        if referrer and referrer.telegram_id!= chat_id:
                            referrer.referrals_count += 1
                            rp = ReferralPayment(referrer_code=ref_code, referred_telegram_id=chat_id, amount=500, status="pending")
                            db.session.add(rp)
                            if referrer.referrals_count >= 10 and referrer.subscription_type!= "lifetime":
                                referrer.subscription_type = "lifetime"
                                referrer.subscription_end = datetime.utcnow() + timedelta(days=365*10)
                                send_telegram(referrer.telegram_id, f"🎉 LIFETIME UNLOCKED! You got 10 refs!")
                            else:
                                send_telegram(referrer.telegram_id, f"👥 New Referral! {first_name} joined! {referrer.referrals_count}/10 for Lifetime")
                            db.session.commit()
                    welcome = f"🚀 **AGENT 35 V12.6 DUAL FREE - Welcome!**\n\nYour Link: `{RENDER_URL}/r/{user.referral_code}`\n10 refs = Lifetime FREE auto!\n\nCommands:\n/pairs - Choose 5 pairs\n/status - Check sub\n/referral - Get link\n/dashboard - Open Dashboard\n/scan - Manual scan\n\nTrial ends: {user.subscription_end.strftime('%Y-%m-%d %H:%M')}"
                    send_telegram(chat_id, welcome)
                else:
                    user.last_seen = datetime.utcnow()
                    db.session.commit()
                    send_telegram(chat_id, f"Welcome back {first_name}! Code: `{user.referral_code}` Refs: {user.referrals_count}/10\n/dashboard for full dashboard")
            elif text.startswith('/status'):
                if not user:
                    send_telegram(chat_id, "Please /start first")
                else:
                    active = check_subscription(user)
                    status_emoji = "✅ ACTIVE" if active else "❌ EXPIRED"
                    end_str = user.subscription_end.strftime('%Y-%m-%d %H:%M UTC') if user.subscription_end else "None"
                    pairs = ", ".join(get_user_pairs(user))
                    send_telegram(chat_id, f"📊 **STATUS**\nSub: {user.subscription_type.upper()} {status_emoji}\nEnds: {end_str}\nRefs: {user.referrals_count}/10\nPairs: {pairs}\nCode: `{user.referral_code}`\nDashboard: {RENDER_URL}/dashboard")
            elif text.startswith('/referral'):
                if user:
                    send_telegram(chat_id, f"🔗 **REFERRAL**\nLink: `{RENDER_URL}/r/{user.referral_code}`\nRefs: {user.referrals_count}/10 for Lifetime")
            elif text.startswith('/pairs'):
                if not user:
                    send_telegram(chat_id, "Please /start first")
                else:
                    send_telegram(chat_id, f"🎯 **CHOOSE 5 PAIRS**\nSend like: `XAUUSD,EURUSD,GBPUSD,GBPJPY,NAS100`\nAvailable: {', '.join(SCAN_PAIRS)}\nCurrent: {', '.join(get_user_pairs(user))}")
            elif ',' in text and len(text) < 80 and not text.startswith('/'):
                if user:
                    chosen = [p.strip().upper().replace('GOLD','XAUUSD') for p in text.split(',')][:5]
                    valid = [p for p in chosen if p in SCAN_PAIRS]
                    if len(valid) >= 1:
                        user.selected_pairs = json.dumps(valid)
                        user.last_seen = datetime.utcnow()
                        db.session.commit()
                        send_telegram(chat_id, f"✅ Pairs updated: {', '.join(valid)}")
                    else:
                        send_telegram(chat_id, f"❌ Invalid. Use from: {', '.join(SCAN_PAIRS)}")
            elif text.startswith('/scan'):
                if not user:
                    send_telegram(chat_id, "Please /start first")
                elif not check_subscription(user):
                    send_telegram(chat_id, "❌ Expired. Use /pay to renew")
                else:
                    send_telegram(chat_id, f"🔍 V12.6 scan started for {len(SCAN_PAIRS)} pairs...")
                    threading.Thread(target=scan_and_send).start()
            elif text.startswith('/pay'):
                send_telegram(chat_id, f"💳 R500 Yearly / R5000 Lifetime\nYour Code: `{user.referral_code if user else ''}` ID: `{chat_id}` Contact admin")
            elif text.startswith('/leaderboard'):
                top = User.query.order_by(User.referrals_count.desc()).limit(10).all()
                txt = "🏆 **TOP 10**\n10 refs = Lifetime FREE\n\n"
                for i, u in enumerate(top, 1):
                    name = u.first_name or u.username or f"User{i}"
                    txt += f"{i}. {name} - {u.referrals_count} refs - {u.subscription_type}\n"
                send_telegram(chat_id, txt)
            elif text.startswith('/dashboard'):
                send_telegram(chat_id, f"📊 **FULL DASHBOARD**\n{RENDER_URL}/dashboard\n\nSee users, signals, keys, logs, referrers")
            elif text.startswith('/journal'):
                parts = text.split()
                if len(parts) >= 3:
                    try:
                        symbol = parts[1].upper()
                        result = parts[2].lower()
                        profit = float(parts[3]) if len(parts) > 3 else 0
                        j = Journal(telegram_id=chat_id, symbol=symbol, result=result, profit=profit, direction="BUY", entry=0, sl=0, tp=0)
                        db.session.add(j)
                        db.session.commit()
                        send_telegram(chat_id, f"✅ Journal: {symbol} {result} {profit}")
                    except:
                        send_telegram(chat_id, "Use: /journal SYMBOL win/loss profit")
                else:
                    if user:
                        journals = Journal.query.filter_by(telegram_id=chat_id).all()
                        wins = len([j for j in journals if j.result == "win"])
                        losses = len([j for j in journals if j.result == "loss"])
                        total = len(journals)
                        winrate = wins/total*100 if total>0 else 0
                        send_telegram(chat_id, f"📔 JOURNAL Total: {total} Wins: {wins} Losses: {losses} Winrate: {winrate:.1f}%")
            else:
                if user:
                    send_telegram(chat_id, "Commands: /status /referral /pairs /scan /pay /journal /leaderboard /dashboard")
        return jsonify({"ok": True})
    except Exception as e:
        print(f"TG webhook error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"ok": True})

@app.route('/r/<code>')
def referral_redirect(code):
    with app.app_context():
        referrer = User.query.filter_by(referral_code=code).first()
        ref_name = referrer.first_name if referrer and referrer.first_name else "Friend"
    return render_template_string("""
    <!DOCTYPE html><html><head><title>Agent 35 - {{code}}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{font-family:Arial;background:#0a0a0a;color:#fff;padding:20px;text-align:center}
  .card{background:#1e1e1e;padding:30px;border-radius:20px;max-width:500px;margin:20px auto;border:1px solid #333}
  .btn{background:#00ffaa;color:#000;padding:18px 35px;border-radius:12px;text-decoration:none;display:inline-block;font-weight:bold}
  .btn-tele{background:#0088cc;color:#fff}
  .badge{background:#00ffaa;color:#000;padding:5px 12px;border-radius:20px;font-size:12px}
    </style></head><body>
    <h1>🚀 AGENT 35 V12.6 DUAL FREE</h1>
    <p>5M SHIFT HUNTER - No Yahoo Block - R0 Forever</p>
    <div class="card">
        <p>👋 <b>{{ref_name}}</b> invited you! Code: {{code}}</p>
        <p>✅ 5M FVG + OB/MB Breaker + BOS/CHoCH</p>
        <p>✅ Premium/Discount + MTF</p>
        <p>✅ Finnhub+TwelveData FREE</p>
        <a class="btn btn-tele" href="https://t.me/{{bot}}?start={{code}}">🚀 Join Telegram - 3 Days FREE</a>
        <br><br><p><span class="badge">R500 Yearly / R5000 Lifetime</span></p><p>Refer 10 = <b>Lifetime FREE</b></p>
    </div></body></html>
    """, code=code, ref_name=ref_name, bot=BOT_USERNAME)

@app.route('/admin/activate/<telegram_id>/<type_>')
def admin_activate(telegram_id, type_):
    secret = request.args.get('secret')
    if secret!= os.environ.get('ADMIN_SECRET', 'admin123'):
        return "Unauthorized", 401
    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            return f"User {telegram_id} not found"
        if type_ == "yearly":
            user.subscription_type = "yearly"
            user.subscription_end = datetime.utcnow() + timedelta(days=365)
        elif type_ == "lifetime":
            user.subscription_type = "lifetime"
            user.subscription_end = datetime.utcnow() + timedelta(days=365*10)
        db.session.commit()
        if user.referred_by:
            rp = ReferralPayment.query.filter_by(referred_telegram_id=telegram_id, status="pending").first()
            if rp:
                rp.status = "confirmed"
                db.session.commit()
        send_telegram(telegram_id, f"✅ Activated {type_.upper()}!")
        return f"Activated {telegram_id} as {type_}"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Agent 35 V12.6 DUAL FREE + DASHBOARD starting on port {port}")
    app.run(host='0.0.0.0', port=port)
