"""
AGENT 35 - app.py V12.5 ULTIMATE FINAL
Features:
- V12 SHIFT HUNTER Engine (5m FVG + OB + MB Breaker + BOS/CHoCH Shift + Premium/Discount)
- 5 min auto-scanner
- TradingView Webhook /webhook for your 035 SMC Risk Manager Pine
- Full Referral System R500 / R5000 + Auto Lifetime after 10
- Telegram Bot: /start /status /pairs /referral /leaderboard /scan /pay /journal
- Flask Dashboard + Payment + Journal + Stats
- Anti-spam, Pair filtering, Subscription check
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

# ========== CONFIG ==========
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///agent35.db')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'agent35-final-v12-secret-key-2024')

db = SQLAlchemy(app)

BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""
RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://agent-35-trading-bot.onrender.com').rstrip('/')
BOT_USERNAME = os.environ.get('BOT_USERNAME', 'Agent35_Signals_Bot') # CHANGE THIS
ADMIN_ID = os.environ.get('ADMIN_ID', '') # Your Telegram ID

# Trading Pairs
SCAN_PAIRS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURJPY", "USDZAR", "EURZAR", "BTCUSD", "ETHUSD", "NAS100", "US30", "GER40"]

# ========== DATABASE MODELS ==========
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(100))
    first_name = db.Column(db.String(100))
    referral_code = db.Column(db.String(20), unique=True)
    referred_by = db.Column(db.String(20), nullable=True)
    subscription_type = db.Column(db.String(20), default="trial") # trial, yearly, lifetime, expired
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
    result = db.Column(db.String(20), default="pending") # pending, win, loss, be
    pips = db.Column(db.Float, default=0)

class ReferralPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    referrer_code = db.Column(db.String(20))
    referred_telegram_id = db.Column(db.String(100))
    amount = db.Column(db.Float, default=500)
    status = db.Column(db.String(20), default="pending") # pending, confirmed
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
    result = db.Column(db.String(20)) # win/loss/be
    profit = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ========== HELPERS ==========
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
    rr = "2.5"

    src_tag = "🤖 AUTO SCAN V12" if source == "SCANNER" else "⚡ TRADINGVIEW SMC"

    msg = f"""{emoji} **{symbol} | {quality}**
{src_tag}

**ENTRY:** `{entry:.5f}`
**SL:** `{sl:.5f}`
**TP:** `{tp:.5f}`
**RR:** 1:{rr} | **Risk:** {risk:.5f}
**Score:** {score}/12

**BIAS:** {bias}

**CONFLUENCE:**
"""
    for c in confluence[:7]:
        msg += f"• {c}\n"

    msg += f"""
⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
🧠 Engine: V12 SHIFT HUNTER - 5M OB+MB+FVG+CHoCH + Daily Premium/Discount

⚠️ Risk 1% max. Set SL exactly.
"""
    return msg

# ========== SCANNER ENGINE ==========
last_signals = {} # symbol -> datetime

def scan_and_send():
    print(f"[{datetime.utcnow()}] Starting V12 5M SHIFT scan for {len(SCAN_PAIRS)} pairs...")
    with app.app_context():
        try:
            for symbol in SCAN_PAIRS:
                # Anti-spam 30 min per symbol
                if symbol in last_signals:
                    if datetime.utcnow() - last_signals[symbol] < timedelta(minutes=30):
                        continue

                analysis = full_multi_tf_analysis(symbol, rr_target=2.5)

                if analysis.get('signal') and analysis.get('score',0) >= 5:
                    print(f"✅ SIGNAL FOUND {symbol} {analysis['direction']} Score {analysis['score']} {analysis['quality']}")
                    last_signals[symbol] = datetime.utcnow()

                    # Save signal
                    sig = Signal(
                        symbol=symbol,
                        direction=analysis['direction'],
                        entry=analysis['entry'],
                        sl=analysis['sl'],
                        tp=analysis['tp'],
                        score=analysis['score'],
                        quality=analysis['quality'],
                        bias=analysis['bias'],
                        confluence=json.dumps(analysis['confluence'])
                    )
                    db.session.add(sig)
                    db.session.commit()

                    # Send to subscribers who selected this pair
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
                            time.sleep(0.06) # Avoid flood limit

                    # Admin summary
                    if ADMIN_ID:
                        send_telegram(ADMIN_ID, f"📡 V12 Signal {symbol} sent to {sent} users\n{analysis['reason']}")

                    db.session.add(ScanLog(message=f"SIGNAL {symbol} {analysis['direction']} Score {analysis['score']} -> {sent} users | {analysis['reason']}"))
                    db.session.commit()
                else:
                    print(f"⏭️ {symbol}: {analysis.get('reason','No signal')} Score:{analysis.get('score',0)}")
                time.sleep(1) # be nice to yfinance

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
        time.sleep(300) # 5 minutes

# Start scanner thread once
if not hasattr(app, 'scanner_started'):
    t = threading.Thread(target=background_scanner, daemon=True)
    t.start()
    app.scanner_started = True
    print("✅ Background 5m scanner started")

# ========== FLASK ROUTES ==========

@app.route('/')
def home():
    with app.app_context():
        total = User.query.count()
        active = User.query.filter(User.subscription_end > datetime.utcnow()).count() + User.query.filter_by(subscription_type="lifetime").count()
        sig_count = Signal.query.count()
        last_sig = Signal.query.order_by(Signal.created_at.desc()).first()

    return render_template_string("""
    <!DOCTYPE html><html><head><title>Agent 35 V12.5</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{font-family:Arial;background:#0f0f0f;color:#fff;padding:20px;text-align:center}
   .card{background:#1a1a1a;padding:20px;border-radius:15px;margin:10px auto;max-width:500px;border:1px solid #333}
   .btn{background:#00ffaa;color:#000;padding:12px 25px;border-radius:10px;text-decoration:none;display:inline-block;margin:5px;font-weight:bold}
   .btn-blue{background:#0088cc;color:#fff}
    </style></head>
    <body>
    <h1>🚀 AGENT 35 V12.5 SHIFT HUNTER</h1>
    <div class="card">
        <h3>🧠 Engine Status: ACTIVE</h3>
        <p>5M FVG + OB/MB Breaker + BOS/CHoCH Shift + Daily Premium/Discount</p>
        <p>Scanning every 5 minutes</p>
        <p><b>Pairs:</b> {{pairs}}</p>
        <p>Users: {{total}} | Active: {{active}} | Signals: {{sig_count}}</p>
        {% if last_sig %}
        <p>Last: {{last_sig.symbol}} {{last_sig.direction}} {{last_sig.quality}} {{last_sig.created_at}}</p>
        {% endif %}
    </div>
    <div class="card">
        <a class="btn" href="/scan">🔍 Manual Scan</a>
        <a class="btn btn-blue" href="/stats">📊 Stats</a>
        <a class="btn btn-blue" href="/leaderboard">🏆 Leaderboard</a>
        <a class="btn btn-blue" href="/health">💚 Health</a>
    </div>
    <p>Bot: @{{bot}} | Render: {{url}}</p>
    </body></html>
    """, pairs=", ".join(SCAN_PAIRS), total=total, active=active, sig_count=sig_count, last_sig=last_sig, bot=BOT_USERNAME, url=RENDER_URL)

@app.route('/stats')
def stats():
    with app.app_context():
        total_users = User.query.count()
        active = User.query.filter(User.subscription_end > datetime.utcnow()).count() + User.query.filter_by(subscription_type="lifetime").count()
        signals = Signal.query.order_by(Signal.created_at.desc()).limit(20).all()
        html = f"<h2>📊 Agent 35 Stats</h2>Total Users: {total_users}<br>Active: {active}<br><br><h3>Last 20 Signals</h3>"
        for s in signals:
            html += f"{s.created_at.strftime('%m-%d %H:%M')} - <b>{s.symbol} {s.direction}</b> {s.score}/12 {s.quality} Entry {s.entry} SL {s.sl}<br>"
        html += '<br><a href="/">Home</a>'
        return html

@app.route('/leaderboard')
def leaderboard():
    with app.app_context():
        top = User.query.order_by(User.referrals_count.desc()).limit(10).all()
        html = "<h2>🏆 Referral Leaderboard - Top 10</h2><p>10 Referrals = Lifetime FREE</p>"
        for i, u in enumerate(top, 1):
            name = u.username or u.first_name or f"User {u.id}"
            html += f"{i}. {name} - {u.referrals_count} refs - {u.subscription_type}<br>"
        html += '<br><a href="/">Home</a>'
        return html

@app.route('/scan')
def manual_scan():
    threading.Thread(target=scan_and_send).start()
    return jsonify({"status": "V12 5M scan started in background", "time": datetime.utcnow().isoformat(), "pairs": SCAN_PAIRS})

@app.route('/health')
def health():
    return jsonify({"status": "ok", "engine": "V12.5 SHIFT HUNTER", "pairs": SCAN_PAIRS, "last_signals": {k: v.isoformat() for k,v in last_signals.items()}, "time": datetime.utcnow().isoformat()})

# ========== TRADINGVIEW WEBHOOK - YOUR PINE INDICATOR ==========
@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    """
    Receives JSON from your 035 SMC Risk Manager Pine Script:
    {"event":"DRAW","user_id":1,"symbol":"XAUUSD","entry":...,"sl":...,"tp":...,"lots":...,"risk_usd":...,"box_id":"...","color":"#00ffaa"}
    """
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

        msg = f"""
⚡ **TRADINGVIEW SMC ALERT** - {box_id}

{'🟢' if direction=='BUY' else '🔴'} **{symbol} {direction}**

**Entry:** `{entry:.5f}`
**SL:** `{sl:.5f}`
**TP:** `{tp:.5f}`
**Lots:** {lots} | **Risk:** ${risk_usd} | **RR:** 1:{rr}

_Forwarded from your 035 SMC Risk Manager (FVG detected)_

⏰ {datetime.utcnow().strftime('%H:%M:%S UTC')}
"""

        with app.app_context():
            # If user_id is provided, send only to that user
            target_users = []
            if user_id_db:
                u = User.query.filter_by(id=user_id_db).first()
                if u:
                    target_users = [u]
            else:
                # Broadcast to all active who have this symbol
                all_users = User.query.filter_by(is_active=True).all()
                for u in all_users:
                    if not check_subscription(u): continue
                    if symbol in get_user_pairs(u):
                        target_users.append(u)

            sent = 0
            for u in target_users:
                if send_telegram(u.telegram_id, msg):
                    sent += 1

            if ADMIN_ID and sent == 0:
                send_telegram(ADMIN_ID, msg + f"\n\n(No active users for {symbol})")

            # Save as signal
            sig = Signal(symbol=symbol, direction=direction, entry=entry, sl=sl, tp=tp, score=10, quality="TRADINGVIEW FVG", bias=f"TV {box_id}", confluence=json.dumps([f"TV FVG {box_id}", f"Lots {lots} Risk ${risk_usd}"]))
            db.session.add(sig)
            db.session.commit()

        return jsonify({"status": "forwarded", "symbol": symbol, "sent": sent if 'sent' in locals() else 0})
    except Exception as e:
        print(f"TV Webhook error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 400

# ========== TELEGRAM BOT WEBHOOK ==========
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

            # /start with referral
            if text.startswith('/start'):
                parts = text.split()
                ref_code = parts[1].strip() if len(parts) > 1 else None

                if not user:
                    # Generate unique referral code
                    new_code = generate_ref_code(username or first_name)
                    while User.query.filter_by(referral_code=new_code).first():
                        new_code = generate_ref_code(username or first_name)

                    user = User(
                        telegram_id=chat_id,
                        username=username,
                        first_name=first_name,
                        referral_code=new_code,
                        referred_by=ref_code,
                        subscription_type="trial",
                        subscription_end=datetime.utcnow() + timedelta(days=3)
                    )
                    db.session.add(user)
                    db.session.commit()

                    # Referral bonus handling
                    if ref_code:
                        referrer = User.query.filter_by(referral_code=ref_code).first()
                        if referrer and referrer.telegram_id!= chat_id:
                            referrer.referrals_count += 1
                            # Track pending payment
                            rp = ReferralPayment(referrer_code=ref_code, referred_telegram_id=chat_id, amount=500, status="pending")
                            db.session.add(rp)

                            # Auto Lifetime after 10 referrals
                            if referrer.referrals_count >= 10 and referrer.subscription_type!= "lifetime":
                                referrer.subscription_type = "lifetime"
                                referrer.subscription_end = datetime.utcnow() + timedelta(days=365*10)
                                send_telegram(referrer.telegram_id, f"""
🎉 **CONGRATULATIONS! LIFETIME UNLOCKED!**

You got 10 referrals! Your subscription is now **LIFETIME FREE**.

Your Code: `{referrer.referral_code}`
Keep referring to earn!
                                """)
                            else:
                                send_telegram(referrer.telegram_id, f"""
👥 **New Referral Joined!**

`{first_name or username}` joined via your link!
Progress: **{referrer.referrals_count}/10** for Lifetime FREE

Your link: {RENDER_URL}/r/{referrer.referral_code}
                                """)
                            db.session.commit()

                    welcome = f"""
🚀 **AGENT 35 V12.5 SHIFT HUNTER - Welcome!**

I am a 5M SMC Sniper:

✅ **FVG** - Fair Value Gap (imbalance)
✅ **OB/MB** - Order Block + Breaker Block
✅ **BOS/CHoCH** - Shift detection BEFORE 4H sees it
✅ **Premium/Discount** - Buy Cheap (Discount), Sell Expensive (Premium)
✅ **MTF** - 5M entry + 15M/1H/4H/Daily bias

**Your Referral Link (Earn Lifetime):**
`{RENDER_URL}/r/{user.referral_code}`

Share it - 10 paid referrals = **LIFETIME FREE** auto!

**Commands:**
/pairs - Choose 5 pairs to follow
/status - Check subscription & referrals
/referral - Get your link & stats
/leaderboard - Top referrers
/scan - Trigger manual 5M scan
/pay - How to pay R500 Yearly / R5000 Lifetime
/journal - Log your trade result

**Pricing:**
• 3 Days FREE Trial (active now!)
• R500 Yearly
• R5000 Lifetime
• Refer 10 = Lifetime FREE

Trial ends: {user.subscription_end.strftime('%Y-%m-%d %H:%M')}
Let's catch SHIFT moves! 🔥
                    """
                    send_telegram(chat_id, welcome)
                else:
                    user.last_seen = datetime.utcnow()
                    db.session.commit()
                    send_telegram(chat_id, f"""
Welcome back {first_name}! 👋

**Your Code:** `{user.referral_code}`
**Link:** {RENDER_URL}/r/{user.referral_code}
**Refs:** {user.referrals_count}/10 for Lifetime

/status - subscription
/pairs - change pairs
/scan - manual scan
                    """)

            elif text.startswith('/status'):
                if not user:
                    send_telegram(chat_id, "Please /start first")
                else:
                    active = check_subscription(user)
                    status_emoji = "✅ ACTIVE" if active else "❌ EXPIRED"
                    end_str = user.subscription_end.strftime('%Y-%m-%d %H:%M UTC') if user.subscription_end else "None"
                    pairs = ", ".join(get_user_pairs(user))
                    send_telegram(chat_id, f"""
📊 **YOUR STATUS**

👤 {first_name} (@{username})
🆔 {chat_id}
🔗 Code: `{user.referral_code}`

💳 **Subscription:** {user.subscription_type.upper()} - {status_emoji}
📅 Ends: {end_str}

👥 **Referrals:** {user.referrals_count}/10 for Lifetime FREE
💰 Your Link: {RENDER_URL}/r/{user.referral_code}

🎯 **Pairs:** {pairs}

Use /pay to extend, /referral to share
                    """)

            elif text.startswith('/referral'):
                if not user:
                    send_telegram(chat_id, "Please /start first")
                else:
                    send_telegram(chat_id, f"""
🔗 **YOUR REFERRAL SYSTEM**

**Your Link:**
`{RENDER_URL}/r/{user.referral_code}`

**How it works:**
1. Share your link
2. Friend joins via link & pays R500
3. You get +1 referral
4. At 10 referrals = **LIFETIME FREE auto!**

**Your Stats:**
Referrals: {user.referrals_count}/10
Needed: {max(0,10-user.referrals_count)} more for Lifetime

**Zulu:**
Mema abangani abayi-10 abathengayo, uthole Lifetime MAHHALA!

**Share message:**
🚀 Agent 35 5M SMC Signals - R500 Yearly, mema 10 uthole Lifetime MAHHALA! Joyina ngelinki yami: {RENDER_URL}/r/{user.referral_code}
                    """)

            elif text.startswith('/pairs'):
                if not user:
                    send_telegram(chat_id, "Please /start first")
                else:
                    send_telegram(chat_id, f"""
🎯 **CHOOSE YOUR 5 PAIRS**

Send me exactly like this:
`XAUUSD,EURUSD,GBPUSD,GBPJPY,NAS100`

Available: {', '.join(SCAN_PAIRS)}

Your Current: {', '.join(get_user_pairs(user))}

You will only get signals for your 5.
                    """)

            elif ',' in text and len(text) < 80 and not text.startswith('/'):
                if user:
                    chosen = [p.strip().upper().replace('GOLD','XAUUSD') for p in text.split(',')][:5]
                    valid = [p for p in chosen if p in SCAN_PAIRS]
                    if len(valid) >= 1:
                        user.selected_pairs = json.dumps(valid)
                        user.last_seen = datetime.utcnow()
                        db.session.commit()
                        send_telegram(chat_id, f"✅ **Pairs updated!**\nNow following: {', '.join(valid)}\n\nYou will get 5M SHIFT signals only for these.")
                    else:
                        send_telegram(chat_id, f"❌ Invalid pairs. Use from: {', '.join(SCAN_PAIRS)}")

            elif text.startswith('/scan'):
                if not user:
                    send_telegram(chat_id, "Please /start first")
                elif not check_subscription(user):
                    send_telegram(chat_id, "❌ Subscription expired.\nUse /pay to renew - R500 Yearly or R5000 Lifetime\nRefer 10 = FREE Lifetime!")
                else:
                    send_telegram(chat_id, "🔍 **V12 5M SHIFT SCAN started...**\nScanning 13 pairs for FVG+OB+MB+CHoCH - takes ~30 sec\nYou will get signals if score >=5")
                    threading.Thread(target=scan_and_send).start()

            elif text.startswith('/pay') or text.startswith('/payment'):
                send_telegram(chat_id, f"""
💳 **PAYMENT - AGENT 35**

**Prices:**
• R500 Yearly
• R5000 Lifetime
• 3 Days Free Trial

**How to pay:**
1. EFT / Instant Pay - Capitec / FNB (Ask admin for details)
2. Send proof to admin
3. Admin activates within 1 hour

**Refer & Earn:**
Share your link: {RENDER_URL}/r/{user.referral_code if user else 'YOURCODE'}
10 paid referrals = Lifetime FREE auto!

**Contact Admin to pay:** @YourAdminUsername
Include your Telegram ID: `{chat_id}` and your code: `{user.referral_code if user else ''}`

After payment, /status will show ACTIVE
                """)

            elif text.startswith('/leaderboard'):
                top = User.query.order_by(User.referrals_count.desc()).limit(10).all()
                txt = "🏆 **TOP 10 REFERRERS**\n10 refs = Lifetime FREE\n\n"
                for i, u in enumerate(top, 1):
                    name = u.first_name or u.username or f"User{i}"
                    txt += f"{i}. {name} - {u.referrals_count} refs - {u.subscription_type}\n"
                send_telegram(chat_id, txt)

            elif text.startswith('/journal'):
                # Simple journal log
                parts = text.split()
                if len(parts) >= 3:
                    # /journal XAUUSD win 50
                    try:
                        symbol = parts[1].upper()
                        result = parts[2].lower()
                        profit = float(parts[3]) if len(parts) > 3 else 0
                        j = Journal(telegram_id=chat_id, symbol=symbol, result=result, profit=profit, direction="BUY", entry=0, sl=0, tp=0)
                        db.session.add(j)
                        db.session.commit()
                        send_telegram(chat_id, f"✅ Journal logged: {symbol} {result} {profit}")
                    except:
                        send_telegram(chat_id, "Use: /journal SYMBOL win/loss profit\nExample: /journal XAUUSD win 120")
                else:
                    # Show stats
                    if user:
                        journals = Journal.query.filter_by(telegram_id=chat_id).all()
                        wins = len([j for j in journals if j.result == "win"])
                        losses = len([j for j in journals if j.result == "loss"])
                        total = len(journals)
                        winrate = wins/total*100 if total>0 else 0
                        send_telegram(chat_id, f"""
📔 **YOUR JOURNAL**

Total: {total} | Wins: {wins} | Losses: {losses}
Winrate: {winrate:.1f}%

Log: /journal SYMBOL win/loss profit
Example: /journal XAUUSD win 150
                        """)

            elif text.startswith('/test'):
                if str(chat_id) == str(ADMIN_ID):
                    analysis = full_multi_tf_analysis("XAUUSD", rr_target=2.5)
                    send_telegram(chat_id, f"V12 Test XAUUSD:\n```{json.dumps(analysis, indent=2, default=str)[:3000]}```")
                else:
                    send_telegram(chat_id, "Admin only")

            else:
                # Unknown - help
                if user:
                    send_telegram(chat_id, """
❓ **Commands:**
/status - Your sub & referrals
/referral - Your link to earn Lifetime
/pairs - Choose 5 pairs
/scan - Manual 5M scan
/pay - How to pay
/journal - Log trades
/leaderboard - Top referrers

Send your 5 pairs like: `XAUUSD,EURUSD,GBPUSD,GBPJPY,NAS100`
                    """)

        return jsonify({"ok": True})
    except Exception as e:
        print(f"Telegram webhook error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"ok": True})

# ========== REFERRAL LANDING PAGE ==========
@app.route('/r/<code>')
def referral_redirect(code):
    with app.app_context():
        referrer = User.query.filter_by(referral_code=code).first()
        ref_name = referrer.first_name if referrer and referrer.first_name else "Friend"

    return render_template_string("""
    <!DOCTYPE html><html><head><title>Agent 35 - Join via {{code}}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
    body{font-family:Arial;background:#0a0a0a;color:#fff;padding:20px;text-align:center}
   .card{background:#1e1e1e;padding:30px;border-radius:20px;max-width:500px;margin:20px auto;border:1px solid #333}
   .btn{background:#00ffaa;color:#000;padding:18px 35px;border-radius:12px;text-decoration:none;display:inline-block;font-weight:bold;font-size:18px;margin:10px}
   .btn-tele{background:#0088cc;color:#fff}
   .badge{background:#00ffaa;color:#000;padding:5px 12px;border-radius:20px;font-size:12px}
    </style></head>
    <body>
    <h1>🚀 AGENT 35 V12.5</h1>
    <p>5M SHIFT HUNTER - SMC Sniper</p>
    <div class="card">
        <p>👋 <b>{{ref_name}}</b> invited you!</p>
        <p>Referral Code: <code>{{code}}</code></p>
        <h2>What you get:</h2>
        <p>✅ 5M FVG + Order Block + Breaker Block (MB)</p>
        <p>✅ BOS/CHoCH Shift Detection (early reversal)</p>
        <p>✅ Premium/Discount Zones - Buy Low, Sell High</p>
        <p>✅ Multi-Timeframe 5M/15M/1H/4H/Daily</p>
        <p>✅ Auto Telegram Alerts</p>
        <p>✅ TradingView Webhook Integration</p>
        <br>
        <a class="btn btn-tele" href="https://t.me/{{bot}}?start={{code}}">🚀 Join on Telegram - 3 Days FREE</a>
        <br><br>
        <p><span class="badge">R500 Yearly / R5000 Lifetime</span></p>
        <p>Refer 10 friends who pay = <b>Lifetime FREE</b> auto!</p>
        <br>
        <p style="font-size:12px;color:#888">After joining Telegram, use /pairs to choose 5 pairs, /status to check sub</p>
    </div>
    <div class="card">
        <h3>🔥 V12 Engine Features</h3>
        <p>Daily/4H = Premium/Discount Bias</p>
        <p>1H/15M = Structure Confirmation</p>
        <p>5M = FVG + OB + MB + CHoCH SHIFT</p>
        <p>Catches reversal BEFORE big TF shows it!</p>
    </div>
    </body></html>
    """, code=code, ref_name=ref_name, bot=BOT_USERNAME)

# ========== ADMIN ROUTES ==========
@app.route('/admin/activate/<telegram_id>/<type_>')
def admin_activate(telegram_id, type_):
    # Simple admin activation via link - secure with secret query param in production
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

        # Confirm referral payment if any
        if user.referred_by:
            rp = ReferralPayment.query.filter_by(referred_telegram_id=telegram_id, status="pending").first()
            if rp:
                rp.status = "confirmed"
                db.session.commit()

        send_telegram(telegram_id, f"✅ **Activated!** {type_.upper()} subscription active!\nUse /scan to start getting 5M SHIFT signals!")
        return f"Activated {telegram_id} as {type_}"

@app.route('/admin/broadcast', methods=['POST'])
def admin_broadcast():
    secret = request.args.get('secret')
    if secret!= os.environ.get('ADMIN_SECRET', 'admin123'):
        return "Unauthorized", 401
    data = request.get_json()
    message = data.get('message','')
    with app.app_context():
        users = User.query.filter_by(is_active=True).all()
        sent = 0
        for u in users:
            if check_subscription(u):
                if send_telegram(u.telegram_id, message):
                    sent += 1
                    time.sleep(0.05)
    return jsonify({"sent": sent})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Agent 35 V12.5 starting on port {port}")
    print(f"Engine: 5M SHIFT HUNTER - FVG+OB+MB+BOS/CHoCH+Premium/Discount")
    app.run(host='0.0.0.0', port=port)
