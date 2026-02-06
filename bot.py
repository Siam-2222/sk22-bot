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


# ---------- TIME ----------
def thai_now():
    return datetime.datetime.now(pytz.timezone('Asia/Bangkok'))


def thai_time_str():
    return thai_now().strftime('%Y-%m-%d %H:%M:%S')


def is_sleep_time():
    hour = thai_now().hour
    return hour < 6   # พัก 00:00 – 05:59


# ---------- STATE ----------
def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}


def save_state(s):
    json.dump(s, open(STATE_FILE, 'w'), indent=2)


# ---------- NOTIFY ----------
def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT_ID, "text": msg},
            timeout=10
        )
    except Exception as e:
        print("❌ Telegram error:", e)


def send_pushover(msg, sound="cashregister"):
    try:
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
    except Exception as e:
        print("❌ Pushover error:", e)


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
    print("\n🔄 SCAN STARTED |", thai_time_str())

    ex = ccxt.okx({
        'apiKey': OKX_KEY,
        'secret': OKX_SECRET,
        'password': OKX_PW,
        'enableRateLimit': True
    })
    ex.load_markets()

    state = load_state()
    now = thai_time_str()

    for sym in SYMBOLS:
        if sym not in ex.markets:
            print(f"⚠️ {sym} NOT AVAILABLE — SKIP")
            continue

        print(f"\n⏳ Checking {sym} | {thai_time_str()}")

        try:
            df = pd.DataFrame(
                ex.fetch_ohlcv(sym, TIMEFRAME, limit=200),
                columns=['t','open','high','low','close','v']
            )
        except Exception as e:
            print(f"❌ Fetch error {sym}:", e)
            continue

        df = indicators(df)
        prev, last = df.iloc[-2], df.iloc[-1]

        uptrend = last['close'] > last['ema200'] and last['ema50'] > last['ema200']
        downtrend = last['close'] < last['ema200'] and last['ema50'] < last['ema200']

        print(
            f"Trend | Up:{uptrend} Down:{downtrend} | "
            f"K:{last['k']:.1f} D:{last['d']:.1f} Close:{last['close']}"
        )

        key = f"{sym}_{TIMEFRAME}"

        if uptrend and prev['k'] < prev['d'] and last['k'] > last['d'] and last['k'] < 40:
            if state.get(key) != 'LONG_SIGNAL':
                notify(f"⚠️ SIGNAL LONG {sym}\n🕒 {now}")
                state[key] = 'LONG_SIGNAL'

        if downtrend and prev['k'] > prev['d'] and last['k'] < last['d'] and last['k'] > 60:
            if state.get(key) != 'SHORT_SIGNAL':
                notify(f"⚠️ SIGNAL SHORT {sym}\n🕒 {now}")
                state[key] = 'SHORT_SIGNAL'

        if state.get(key) == 'LONG_SIGNAL' and last['close'] > last['ema50']:
            atr = last['atr']
            notify(
                f"🚀 ENTRY LONG {sym}\n"
                f"💰 {last['close']}\n"
                f"🎯 TP {round(last['close']+atr,4)}\n"
                f"🛑 SL {round(last['close']-1.5*atr,4)}\n🕒 {now}"
            )
            state[key] = 'IN_LONG'

        if state.get(key) == 'SHORT_SIGNAL' and last['close'] < last['ema50']:
            atr = last['atr']
            notify(
                f"🔻 ENTRY SHORT {sym}\n"
                f"💰 {last['close']}\n"
                f"🎯 TP {round(last['close']-atr,4)}\n"
                f"🛑 SL {round(last['close']+1.5*atr,4)}\n🕒 {now}"
            )
            state[key] = 'IN_SHORT'

    save_state(state)
    print("✅ SCAN FINISHED |", thai_time_str())


# ---------- LOOP ----------
if __name__ == "__main__":
    print("🚀 BOT STARTED | TF 15m | AUTO LOOP")

    while True:
        if is_sleep_time():
            print(f"🌙 SLEEP MODE | {thai_time_str()} (พักถึง 06:00)")
            time.sleep(300)
            continue

        scan()
        print(f"⏳ WAIT 15 MINUTES...\n")
        time.sleep(SCAN_INTERVAL)
