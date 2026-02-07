import os, ccxt, requests, json
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

TG_TOKEN = os.getenv('TELEGRAM_TOKEN')
TG_CHAT_ID = os.getenv('CHAT_ID')

PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_API_TOKEN = os.getenv('PUSHOVER_API_TOKEN')

OKX_KEY = os.getenv('OKX_API_KEY')
OKX_SECRET = os.getenv('OKX_SECRET_KEY')
OKX_PW = os.getenv('OKX_PASSPHRASE')

TZ_TH = pytz.timezone('Asia/Bangkok')
# ==========================================

def thai_now():
    return datetime.datetime.now(TZ_TH)

def thai_time():
    return thai_now().strftime('%Y-%m-%d %H:%M:%S')

def today_str():
    return thai_now().strftime('%Y-%m-%d')

def is_sleep_time():
    return 0 <= thai_now().hour < 6

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

def notify(msg):
    send_telegram(msg)
    send_pushover(msg)

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

    return df

# ---------- MAIN ----------
def run():
    print(f"\n🚀 RUN START | {thai_time()}")

    if is_sleep_time():
        print("🌙 SLEEP MODE (00:00–05:59 TH)")
        return

    state = load_state()
    today = today_str()

    if thai_now().hour == 6 and state.get("wakeup") != today:
        notify("☀️ BOT WAKE UP | 06:00 TH")
        state["wakeup"] = today
        save_state(state)

    ex = ccxt.okx({
        'apiKey': OKX_KEY,
        'secret': OKX_SECRET,
        'password': OKX_PW,
        'enableRateLimit': True
    })
    ex.load_markets()

    for sym in SYMBOLS:
        if sym not in ex.markets:
            print(f"⚠️ {sym} NOT AVAILABLE")
            continue

        print(f"\n⏳ SCANNING {sym} | {thai_time()}")

        df = pd.DataFrame(
            ex.fetch_ohlcv(sym, TIMEFRAME, limit=200),
            columns=['t','open','high','low','close','v']
        )

        df = indicators(df)
        prev, last = df.iloc[-2], df.iloc[-1]

        entry = last['close']

        uptrend = entry > last['ema200'] and last['ema50'] > last['ema200']
        downtrend = entry < last['ema200'] and last['ema50'] < last['ema200']

        print(
            f"Trend | Up:{uptrend} Down:{downtrend} | "
            f"K:{last['k']:.1f} D:{last['d']:.1f} Close:{entry}"
        )

        # ===== LONG =====
        if uptrend and prev['k'] < prev['d'] and last['k'] > last['d'] and last['k'] < 40:
            sl = prev['low']
            tp = entry + (entry - sl) * 2

            print(
                f"✅ LONG SIGNAL {sym} | "
                f"K cross UP & K<40 | Entry:{entry:.4f} SL:{sl:.4f} TP:{tp:.4f}"
            )

            notify(
                f"📈 LONG {sym}\n"
                f"🕒 {thai_time()}\n\n"
                f"Entry: {entry:.4f}\n"
                f"SL: {sl:.4f}\n"
                f"TP: {tp:.4f}"
            )

        # ===== SHORT =====
        elif downtrend and prev['k'] > prev['d'] and last['k'] < last['d'] and last['k'] > 60:
            sl = prev['high']
            tp = entry - (sl - entry) * 2

            print(
                f"✅ SHORT SIGNAL {sym} | "
                f"K cross DOWN & K>60 | Entry:{entry:.4f} SL:{sl:.4f} TP:{tp:.4f}"
            )

            notify(
                f"📉 SHORT {sym}\n"
                f"🕒 {thai_time()}\n\n"
                f"Entry: {entry:.4f}\n"
                f"SL: {sl:.4f}\n"
                f"TP: {tp:.4f}"
            )

        else:
            print("❌ NO SIGNAL")

    print(f"\n✅ RUN FINISHED | {thai_time()}")

if __name__ == "__main__":
    run()
