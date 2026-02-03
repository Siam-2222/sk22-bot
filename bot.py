import os, ccxt, requests, time
import pandas as pd
import numpy as np

# [1] รายชื่อเหรียญที่พี่วิทยาเฝ้าดู
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'

# [2] ดึงรหัสลับจาก GitHub
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
PO_USER = os.getenv('PUSHOVER_USER_KEY')
PO_TOKEN = os.getenv('PUSHOVER_API_TOKEN')

def send_all_alerts(msg):
    # 1. ส่ง Telegram (ติ๊งเดียวเหมือนเดิม)
    if TELEGRAM_TOKEN and CHAT_ID:
        url_tg = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
        requests.post(url_tg, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'})

    # 2. ส่ง Pushover (ไซเรนฉุกเฉิน ดังลากยาว)
    if PO_USER and PO_TOKEN:
        url_po = "https://api.pushover.net/1/messages.json"
        data = {
            "token": PO_TOKEN,
            "user": PO_USER,
            "message": msg,
            "title": "🚨 SK22 SIGNAL!!",
            "sound": "siren",        # เสียงไซเรน
            "priority": 2,           # ระดับฉุกเฉิน (Emergency)
            "retry": 30,             # ถ้าพี่ไม่กดปิด ให้ดังซ้ำทุก 30 วินาที
            "expire": 3600           # ให้ดังซ้ำไปเรื่อยๆ นานสูงสุด 1 ชม.
        }
        requests.post(url_po, data=data)

def calculate_indicators(df):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, 1)
    df['rsi'] = 100 - (100 / (1 + rs))
    rsi_min, rsi_max = df['rsi'].rolling(window=14).min(), df['rsi'].rolling(window=14).max()
    df['k'] = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min).replace(0, 1)
    df['k'] = df['k'].rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    return df

def check_signal():
    exchange = ccxt.okx()
    print(f"--- [SK22+SIREN] Scanning: {len(SYMBOLS)} Coins ---")
    for symbol in SYMBOLS:
        try:
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
            df = calculate_indicators(pd.DataFrame(bars, columns=['time','open','high','low','close','vol']))
            last, prev = df.iloc[-1], df.iloc[-2]
            
            # สูตร SK22 จูนใหม่
            long_trigger = (prev['k'] < prev['d'] and last['k'] > last['d']) and (last['k'] < 25)
            short_trigger = (prev['k'] > prev['d'] and last['k'] < last['d']) and (last['k'] > 75)

            if long_trigger:
                send_all_alerts(f"🚀 *[LONG]* {symbol}\nPrice: {last['close']}\nK: {last['k']:.2f}")
            elif short_trigger:
                send_all_alerts(f"🔻 *[SHORT]* {symbol}\nPrice: {last['close']}\nK: {last['k']:.2f}")
            print(f"{symbol} Checked: K={last['k']:.2f}")
        except Exception as e: print(f"Error {symbol}: {e}")

if __name__ == "__main__":
    check_signal()
