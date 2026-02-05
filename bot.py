import os, ccxt, requests
import pandas as pd
import numpy as np
import datetime
import pytz

# --- การตั้งค่าบอท TRAGOONAEK NO.1 ---
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
PO_USER = os.getenv('PUSHOVER_USER_KEY')
PO_TOKEN = os.getenv('PUSHOVER_API_TOKEN')
OKX_KEY = os.getenv('OKX_API_KEY')
OKX_SECRET = os.getenv('OKX_SECRET_KEY')
OKX_PW = os.getenv('OKX_PASSPHRASE')

def get_thai_time():
    tz_thai = pytz.timezone('Asia/Bangkok')
    return datetime.datetime.now(tz_thai).strftime('%H:%M:%S')

def send_all_alerts(msg):
    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            url_tg = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
            requests.post(url_tg, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}, timeout=15)
        except: pass
    if PO_USER and PO_TOKEN:
        try:
            url_po = "https://api.pushover.net/1/messages.json"
            data = {"token": PO_TOKEN, "user": PO_USER, "message": msg, "title": "🚨 TRAGOONAEK NO.1", "sound": "siren", "priority": 1}
            requests.post(url_po, data=data, timeout=15)
        except: pass

def calculate_sk22_logic(df):
    # [1] RSI (Wilder's Smoothing)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 0.00001)
    df['rsi'] = 100 - (100 / (1 + rs))

    # [2] Stochastic RSI
    rsi_min = df['rsi'].rolling(window=14).min()
    rsi_max = df['rsi'].rolling(window=14).max()
    df['stoch_rsi'] = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min).replace(0, 0.00001)

    # [3] K และ D (SMA 3)
    df['k'] = df['stoch_rsi'].rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()
    
    # [4] EMA 200 & ATR
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['tr'] = np.maximum(df['high'] - df['low'], np.maximum(abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(window=14).mean()

    # [5] Simple Divergence (เช็คย้อนหลัง 5 แท่ง เพื่อความไว)
    df['bull_div'] = (df['low'] < df['low'].shift(5)) & (df['rsi'] > df['rsi'].shift(5))
    df['bear_div'] = (df['high'] > df['high'].shift(5)) & (df['rsi'] < df['rsi'].shift(5))
    
    return df

def check_signal():
    exchange = ccxt.okx({'apiKey': OKX_KEY, 'secret': OKX_SECRET, 'password': OKX_PW, 'timeout': 15000})
    now_thai = get_thai_time()
    print(f"--- [SK22 SCAN START: {now_thai}] ---")
    
    for symbol in SYMBOLS:
        try:
            print(f"🔍 {symbol}", end=" ", flush=True)
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=150)
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','vol'])
            
            ticker = exchange.fetch_ticker(symbol)
            df.at[df.index[-1], 'close'] = ticker['last']
            
            df = calculate_sk22_logic(df)
            last, prev = df.iloc[-1], df.iloc[-2]

            # เงื่อนไข Trigger (เน้นความแม่นยำตามป้าย)
            long_trigger = (prev['k'] <= prev['d'] and last['k'] > last['d']) and \
                          (last['k'] < 25 or last['bull_div']) and (last['rsi'] >= prev['rsi'])

            short_trigger = (prev['k'] >= prev['d'] and last['k'] < last['d']) and \
                           (last['k'] > 75 or last['bear_div']) and (last['rsi'] <= prev['rsi'])

            print(f"| K: {last['k']:.2f} | D: {last['d']:.2f}", end=" ")

            if long_trigger:
                sl = round(last['low'] - (last['atr'] * 1.5), 4)
                msg = f"🚀 *[LONG {symbol}]*\n💰 Entry: {last['close']}\n🛡️ SL: {sl}\n🕒 Time: {now_thai}"
                send_all_alerts(msg)
                print("✅ [SIGNAL!]")
            elif short_trigger:
                sl = round(last['high'] + (last['atr'] * 1.5), 4)
                msg = f"🔻 *[SHORT {symbol}]*\n💰 Entry: {last['close']}\n🛡️ SL: {sl}\n🕒 Time: {now_thai}"
                send_all_alerts(msg)
                print("✅ [SIGNAL!]")
            else:
                print("❌ No signal")

        except Exception as e:
            print(f"⚠️ Error: {e}")

    print(f"--- [SCAN FINISHED] ---")

if __name__ == "__main__":
    check_signal()
