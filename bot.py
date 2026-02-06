import os, ccxt, requests, json
import pandas as pd
import datetime, pytz

# ================= CONFIG =================
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT']
TIMEFRAME = '15m'
STATE_FILE = 'signal_state.json'

TG_TOKEN = os.getenv('TELEGRAM_TOKEN')
TG_CHAT_ID = os.getenv('CHAT_ID')

PO_TOKEN = os.getenv('PUSHOVER_API_TOKEN')
PO_USER = os.getenv('PUSHOVER_USER_KEY')

OKX_KEY = os.getenv('OKX_API_KEY')
OKX_SECRET = os.getenv('OKX_SECRET_KEY')
OKX_PW = os.getenv('OKX_PASSPHRASE')

# ========================================


def thai_time():
    return datetime.datetime.now(
        pytz.timezone('Asia/Bangkok')
    ).strftime('%H:%M:%S')


def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {}


def save_state(s):
    json.dump(s, open(STATE_FILE, 'w'))


def send(msg):
    # ----- Telegram -----
    if TG_TOKEN and TG_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                data={
                    "chat_id": TG_CHAT_ID,
                    "text": msg,
                    "parse_mode": "Markdown"
                },
                timeout=10
            )
        except:
            pass

    # ----- Pushover -----
    if PO_TOKEN and PO_USER:
        try:
            requests.post(
                "https://api.pushover.net/1/messages.json",
                data={
                    "token": PO_TOKEN,
                    "user": PO_USER,
                    "title": "TRADING SIGNAL",
                    "message": msg,
                    "sound": "siren"
                },
                timeout=10
            )
        except:
            pass


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
    ex = ccxt.okx({
        'apiKey': OKX_KEY,
        'secret': OKX_SECRET,
        'password': OKX_PW,
        'enableRateLimit': True
    })
    ex.load_markets()

    state = load_state()
    now = thai_time()

    for sym in SYMBOLS:
        df = pd.DataFrame(
            ex.fetch_ohlcv(sym, TIMEFRAME, limit=200),
            columns=['t','open','high','low','close','v']
        )

        df = indicators(df)
        prev, last = df.iloc[-2], df.iloc[-1]

        uptrend = last['close'] > last['ema200'] and last['ema50'] > last['ema200']
        downtrend = last['close'] < last['ema200'] and last['ema50'] < last['ema200']

        key = f"{sym}_{TIMEFRAME}"

        # ========= STAGE 1 : SIGNAL =========
        if uptrend and prev['k'] < prev['d'] and last['k'] > last['d'] and last['k'] < 40:
            if state.get(key) != 'LONG_SIGNAL':
                send(f"⚠️ *SIGNAL LONG {sym}*\nTF 15m\n🕒 {now}")
                state[key] = 'LONG_SIGNAL'

        if downtrend and prev['k'] > prev['d'] and last['k'] < last['d'] and last['k'] > 60:
            if state.get(key) != 'SHORT_SIGNAL':
                send(f"⚠️ *SIGNAL SHORT {sym}*\nTF 15m\n🕒 {now}")
                state[key] = 'SHORT_SIGNAL'

        # ========= STAGE 2 : ENTRY =========
        if state.get(key) == 'LONG_SIGNAL' and last['close'] > last['ema50']:
            atr = last['atr']
            send(
                f"🚀 *ENTRY LONG {sym}*\n"
                f"💰 {last['close']}\n"
                f"🎯 TP1 {round(last['close']+atr,4)}\n"
                f"🎯 TP2 {round(last['close']+2*atr,4)}\n"
                f"🎯 TP3 {round(last['close']+3*atr,4)}\n"
                f"🛑 SL {round(last['close']-1.5*atr,4)}\n🕒 {now}"
            )
            state[key] = 'IN_LONG'

        if state.get(key) == 'SHORT_SIGNAL' and last['close'] < last['ema50']:
            atr = last['atr']
            send(
                f"🔻 *ENTRY SHORT {sym}*\n"
                f"💰 {last['close']}\n"
                f"🎯 TP1 {round(last['close']-atr,4)}\n"
                f"🎯 TP2 {round(last['close']-2*atr,4)}\n"
                f"🎯 TP3 {round(last['close']-3*atr,4)}\n"
                f"🛑 SL {round(last['close']+1.5*atr,4)}\n🕒 {now}"
            )
            state[key] = 'IN_SHORT'

    save_state(state)


if __name__ == "__main__":
    run()
