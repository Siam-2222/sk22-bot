import os, ccxt, requests, json
import pandas as pd
import numpy as np
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

# ---------- INDICATORS (แก้ไขเงื่อนไขเพิ่มระบบ SK 22) ----------
def indicators(df):
    # EMA 200 (ใช้ดูแนวรับแนวต้าน)
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

    # RSI & Stochastic RSI (ปรับให้แม่นยำขึ้น)
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 0.00001)
    df['rsi'] = 100 - (100 / (1 + rs))

    rsi_low = df['rsi'].rolling(14).min()
    rsi_high = df['rsi'].rolling(14).max()
    stoch = 100 * (df['rsi'] - rsi_low) / (rsi_high - rsi_low).replace(0, 0.00001)
    df['k'] = stoch.rolling(3).mean()
    df['d'] = df['k'].rolling(3).mean()

    # ATR สำหรับ SL เส้นสีเงิน (ATR 1.5)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = true_range.rolling(14).mean()

    # ระบบ Divergence
    df['is_bull_div'] = (df['low'].shift(1).rolling(5).min() < df['low'].shift(10).rolling(5).min()) & \
                        (df['rsi'].shift(1).rolling(5).min() > df['rsi'].shift(10).rolling(5).min())
    df['is_bear_div'] = (df['high'].shift(1).rolling(5).max() > df['high'].shift(10).rolling(5).max()) & \
                        (df['rsi'].shift(1).rolling(5).max() < df['rsi'].shift(10).rolling(5).max())

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

        # --- แก้ไขเงื่อนไข Trigger: ถอด EMA กรองออก เพื่อให้เข้าได้ไวตามหน้าจอ TradingView ---
        # LONG: K ตัด D ขึ้น และ (K < 25 หรือ มี Bull Div)
        long_trigger = (prev['k'] <= prev['d'] and last['k'] > last['d']) and \
                      (last['k'] < 25 or (last['is_bull_div'] and last['k'] < 50)) and \
                      (last['rsi'] >= prev['rsi'])

        # SHORT: K ตัด D ลง และ (K > 75 หรือ มี Bear Div)
        short_trigger = (prev['k'] >= prev['d'] and last['k'] < last['d']) and \
                       (last['k'] > 75 or (last['is_bear_div'] and last['k'] > 50)) and \
                       (last['rsi'] <= prev['rsi'])

        print(
            f"Stats | K:{last['k']:.1f} D:{last['d']:.1f} RSI:{last['rsi']:.1f} | "
            f"BullDiv:{last['is_bull_div']} BearDiv:{last['is_bear_div']}"
        )

        # ===== LONG =====
        if long_trigger:
            sl = round(entry - (last['atr'] * 1.5), 4)
            tp = round(entry + (entry - sl) * 2, 4)

            print(f"✅ LONG SIGNAL {sym} | Entry:{entry:.4f} SL:{sl:.4f} TP:{tp:.4f}")

            notify(
                f"📈 LONG {sym}\n"
                f"🕒 {thai_time()}\n\n"
                f"Entry: {entry:.4f}\n"
                f"SL: {sl:.4f}\n"
                f"TP: {tp:.4f}"
            )

        # ===== SHORT =====
        elif short_trigger:
            sl = round(entry + (last['atr'] * 1.5), 4)
            tp = round(entry - (sl - entry) * 2, 4)

            print(f"✅ SHORT SIGNAL {sym} | Entry:{entry:.4f} SL:{sl:.4f} TP:{tp:.4f}")

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
