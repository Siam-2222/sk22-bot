import os, ccxt, requests, json, time
import pandas as pd
import datetime, pytz

# ================= CONFIG =================
SYMBOLS = [
    'BTC/USDT',
    'ETH/USDT',
    'SOL/USDT',
    'DOGE/USDT',
    'HYPE/USDT'
]

TIMEFRAME = '15m'
STATE_FILE = 'signal_state.json'
SCAN_INTERVAL = 900  # 15 นาที

TG_TOKEN = os.getenv('TELEGRAM_TOKEN')
TG_CHAT_ID = os.getenv('CHAT_ID')

PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_API_TOKEN = os.getenv('PUSHOVER_API_TOKEN')

OKX_KEY = os.getenv('OKX_API_KEY')
OKX_SECRET = os.getenv('OKX_SECRET_KEY')
OKX_PW = os.getenv('OKX_PASSPHRASE')
# ==========================================

TZ_TH = pytz.timezone('Asia/Bangkok')

# ---------- TIME ----------
def thai_now():
    return datetime.datetime.now(TZ_TH)

def thai_time_str():
    return thai_now().strftime('%Y-%m-%d %H:%M:%S')

def today_str():
    return thai_now().strftime('%Y-%m-%d')

def is_sleep_time():
    return 0 <= thai_now().hour < 6  # 00:00–05:59

def wait_for_next_15m():
    now = thai_now()
    minute = now.minute
    wait_min = 15 - (minute % 15)
    next_run = (now + datetime.timedelta(minutes=wait_min)).replace(second=0, microsecond=0)
    wait_sec = int((next_run - now).total_seconds())
    print(f"⏰ WAIT SYNC TO 15m | NEXT {next_run.strftime('%H:%M:%S')}")
    time.sleep(wait_sec)

# ---------- STATE ----------
def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}

def save_state(s):
    json.dump(s, open(STATE_FILE, 'w'), indent=2)

# ---------- NOTIFY ----------
def send_telegram(msg):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data={"chat_id": TG_CHAT_ID, "text": msg},
        timeout=10
    )

def send_pushover(msg, sound="cashregister"):
    if not PUSHOVER_API_TOKEN or not PUSHOVER_USER_KEY:
        return
    requests.post(
        "https://api.pushover.net/1/messages.json",
        data={
            "token": PUSHOVER_API_TOKEN,
            "user": PUSHOVER_USER_KEY,
            "message": msg,
            "sound": sound
        },
        timeout=10
    )

def notify(msg, sound="cashregister"):
    send_telegram(msg)
    send_pushover(msg, sound)

# ---------- INDICATORS ----------
def indicators(df):
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()

    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.ewm(alpha=1/14).mean() / loss.ewm(alpha=1/14).mean()
    df['rsi'] = 100 - (100 / (1 + rs))

    rsi_low = df['rsi'].rolling(14).min()
    rsi_high = df['rsi'].rolling(14).max()
    stoch = 100 * (df['rsi'] - rsi_low) / (rsi_high - rsi_low)
    df['k'] = stoch.rolling(3).mean()
    df['d'] = df['k'].rolling(3).mean()

    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    return df

# ---------- SCAN ----------
def scan():
    print(f"\n🔄 SCAN STARTED | {thai_time_str()}")

    ex = ccxt.okx({
        'apiKey': OKX_KEY,
        'secret': OKX_SECRET,
        'password': OKX_PW,
        'enableRateLimit': True
    })
    ex.load_markets()

    state = load_state()
    today = today_str()

    for sym in SYMBOLS:
        if sym not in ex.markets:
            continue

        df = pd.DataFrame(
            ex.fetch_ohlcv(sym, TIMEFRAME, limit=200),
            columns=['t','open','high','low','close','v']
        )

        df = indicators(df)
        prev, last = df.iloc[-2], df.iloc[-1]

        uptrend = last['close'] > last['ema200'] and last['ema50'] > last['ema200']
        downtrend = last['close'] < last['ema200'] and last['ema50'] < last['ema200']

        key = f"{sym}_{TIMEFRAME}"
        day_key = f"{key}_date"

        if state.get(day_key) == today:
            continue  # 🔒 กันยิงซ้ำวันเดียว

        if uptrend and prev['k'] < prev['d'] and last['k'] > last['d'] and last['k'] < 40:
            notify(f"⚠️ SIGNAL LONG {sym}\n🕒 {thai_time_str()}")
            state[key] = 'LONG'
            state[day_key] = today

        if downtrend and prev['k'] > prev['d'] and last['k'] < last['d'] and last['k'] > 60:
            notify(f"⚠️ SIGNAL SHORT {sym}\n🕒 {thai_time_str()}")
            state[key] = 'SHORT'
            state[day_key] = today

    save_state(state)
    print(f"✅ SCAN FINISHED | {thai_time_str()}")

# ---------- LOOP ----------
if __name__ == "__main__":
    print("🚀 BOT STARTED | TF 15m")
    state = load_state()

    while True:
        now = thai_now()

        if is_sleep_time():
            print(f"🌙 SLEEP MODE | {thai_time_str()}")
            time.sleep(300)
            continue

        # 🔔 แจ้งเตือนตอนตื่น
        if now.hour == 6 and state.get("last_wakeup") != today_str():
            notify("☀️ BOT WAKE UP | START SCANNING 06:00")
            state["last_wakeup"] = today_str()
            save_state(state)

        wait_for_next_15m()
        scan()
