import os, ccxt, requests, json
import pandas as pd
import datetime, pytz

# ================= CONFIG =================
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT']
TIMEFRAME = '15m'
STATE_FILE = 'signal_state.json'

TG_TOKEN = os.getenv('TELEGRAM_TOKEN')
TG_CHAT_ID = os.getenv('CHAT_ID')

PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_API_TOKEN = os.getenv('PUSHOVER_API_TOKEN')

OKX_KEY = os.getenv('OKX_API_KEY')
OKX_SECRET = os.getenv('OKX_SECRET_KEY')
OKX_PW = os.getenv('OKX_PASSPHRASE')
# ==========================================


def thai_now():
    return datetime.datetime.now(pytz.timezone('Asia/Bangkok'))


def thai_time_str():
    return thai_now().strftime('%Y-%m-%d %H:%M:%S')


def is_sleep_time():
    hour = thai_now().hour
    return 0 <= hour < 7   # 00:00 - 06:59


def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}


def save_state(s):
    json.dump(s, open(STATE_FILE, 'w'))


def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
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


def run():
    print("🚀 BOT STARTED | TF 15m")
    print("🕒 Thai Time:", thai_time_str())

    # ===== STOP TIME 00:00 - 07:00 =====
    if is_sleep_time():
        print("🌙 BOT SLEEP TIME (00:00 - 07:00 TH)")
        print("⛔ Skip all trading logic\n")
        return

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
        print(f"\n⏳ Checking {sym}")

        df = pd.DataFrame(
            ex.fetch_ohlcv(sym, TIMEFRAME, limit=200),
            columns=['t','open','high','low','close','v']
        )
        df = indicators(df)

        prev, last = df.iloc[-2], df.iloc[-1]

        uptrend = last['close'] > last['ema200'] and last['ema50'] > last['ema200']
        downtrend = last['close'] < last['ema200'] and last['ema50'] < last['ema200']

        print(
            f"Trend | Up:{uptrend} Down:{downtrend} | "
            f"K:{last['k']:.1f} D:{last['d']:.1f} Close:{last['close']}"
        )

        key = f"{sym}_{TIMEFRAME}"

        # ===== STAGE 1 : SIGNAL =====
        if uptrend and prev['k'] < prev['d'] and last['k'] > last['d'] and last['k'] < 40:
            if state.get(key) != 'LONG_SIGNAL':
                print(f"⚠️ SIGNAL LONG {sym}")
                notify(f"⚠️ SIGNAL LONG {sym}\nเตรียมเข้า\n🕒 {now}", sound="pushover")
                state[key] = 'LONG_SIGNAL'

        if downtrend and prev['k'] > prev['d'] and last['k'] < last['d'] and last['k'] > 60:
            if state.get(key) != 'SHORT_SIGNAL':
                print(f"⚠️ SIGNAL SHORT {sym}")
                notify(f"⚠️ SIGNAL SHORT {sym}\nเตรียมเข้า\n🕒 {now}", sound="pushover")
                state[key] = 'SHORT_SIGNAL'

        # ===== STAGE 2 : ENTRY =====
        if state.get(key) == 'LONG_SIGNAL' and last['close'] > last['ema50']:
            atr = last['atr']
            print(f"🚀 ENTRY LONG {sym}")
            notify(
                f"🚀 ENTRY LONG {sym}\n"
                f"💰 {last['close']}\n"
                f"🎯 TP1 {round(last['close']+atr,4)}\n"
                f"🎯 TP2 {round(last['close']+2*atr,4)}\n"
                f"🎯 TP3 {round(last['close']+3*atr,4)}\n"
                f"🛑 SL {round(last['close']-1.5*atr,4)}\n🕒 {now}"
            )
            state[key] = 'IN_LONG'

        if state.get(key) == 'SHORT_SIGNAL' and last['close'] < last['ema50']:
            atr = last['atr']
            print(f"🔻 ENTRY SHORT {sym}")
            notify(
                f"🔻 ENTRY SHORT {sym}\n"
                f"💰 {last['close']}\n"
                f"🎯 TP1 {round(last['close']-atr,4)}\n"
                f"🎯 TP2 {round(last['close']-2*atr,4)}\n"
                f"🎯 TP3 {round(last['close']-3*atr,4)}\n"
                f"🛑 SL {round(last['close']+1.5*atr,4)}\n🕒 {now}"
            )
            state[key] = 'IN_SHORT'

    save_state(state)
    print("\n✅ BOT FINISHED\n")


if __name__ == "__main__":
    run()
