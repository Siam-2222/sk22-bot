import os, ccxt, requests
import pandas as pd
import numpy as np

# [1] รายชื่อเหรียญที่พี่วิทยาเฝ้าดู
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'

# [2] ดึงรหัสลับจาก GitHub Secrets (7 ตัวที่พี่ใส่ไว้)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
PO_USER = os.getenv('PUSHOVER_USER_KEY')
PO_TOKEN = os.getenv('PUSHOVER_API_TOKEN')
# API OKX ส่วนตัว
OKX_KEY = os.getenv('OKX_API_KEY')
OKX_SECRET = os.getenv('OKX_SECRET_KEY')
OKX_PW = os.getenv('OKX_PASSPHRASE')

def send_all_alerts(msg):
    # 1. ส่ง Telegram
    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            url_tg = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
            requests.post(url_tg, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}, timeout=10)
        except: pass

    # 2. ส่ง Pushover ไซเรน
    if PO_USER and PO_TOKEN:
        try:
            url_po = "https://api.pushover.net/1/messages.json"
            data = {
                "token": PO_TOKEN, "user": PO_USER, "message": msg,
                "title": "🚨 SK22 REAL-TIME!", "sound": "siren",
                "priority": 2, "retry": 30, "expire": 3600
            }
            requests.post(url_po, data=data, timeout=10)
        except: pass

def calculate_indicators(df):
    # สูตร Stochastic RSI ตามแบบฉบับ SK 22
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, 1)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    rsi_min = df['rsi'].rolling(window=14).min()
    rsi_max = df['rsi'].rolling(window=14).max()
    
    df['k'] = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min).replace(0, 1)
    df['k'] = df['k'].rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()
    
    # EMA 200 ดูเทรนหลัก
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    return df

def check_signal():
    # เชื่อมต่อ API OKX แบบระบุตัวตน (Real-time)
    exchange = ccxt.okx({
        'apiKey': OKX_KEY,
        'secret': OKX_SECRET,
        'password': OKX_PW,
        'enableRateLimit': True
    })
    
    print(f"--- [SK22] Real-time Scanning with OKX API ---")
    
    for symbol in SYMBOLS:
        try:
            # 1. ดึงแท่งเทียนย้อนหลัง
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','vol'])
            
            # 2. 🔥 ไม้ตาย: ดึงราคาปัจจุบัน ณ วินาทีนี้มาใส่ในสูตร
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            df.at[df.index[-1], 'close'] = current_price 
            
            df = calculate_indicators(df)
            last, prev = df.iloc[-1], df.iloc[-2]
            
            # เงื่อนไขแจ้งเตือน SK22 (K ตัด D และอยู่ในโซน 25/75)
            long_trigger = (prev['k'] < prev['d'] and last['k'] > last['d']) and (last['k'] < 25)
            short_trigger = (prev['k'] > prev['d'] and last['k'] < last['d']) and (last['k'] > 75)

            trend_status = "Above EMA200" if current_price > last['ema200'] else "Below EMA200"

            if long_trigger:
                msg = f"🚀 *[LONG]* {symbol}\n💰 Price: {current_price}\n📊 K: {last['k']:.2f}\n📈 Trend: {trend_status}"
                send_all_alerts(msg)
            elif short_trigger:
                msg = f"🔻 *[SHORT]* {symbol}\n💰 Price: {current_price}\n📊 K: {last['k']:.2f}\n📉 Trend: {trend_status}"
                send_all_alerts(msg)
            
            print(f"{symbol}: {current_price} | K={last['k']:.2f} D={last['d']:.2f} ({trend_status})")
            
        except Exception as e:
            print(f"Error {symbol}: {e}")

if __name__ == "__main__":
    check_signal()
