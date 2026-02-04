import os, ccxt, requests, time
import pandas as pd
import numpy as np

SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'

# ดึงรหัสลับ API จาก GitHub Secrets
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
PO_USER = os.getenv('PUSHOVER_USER_KEY')
PO_TOKEN = os.getenv('PUSHOVER_API_TOKEN')

def send_all_alerts(msg):
    if TELEGRAM_TOKEN and CHAT_ID:
        url_tg = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
        requests.post(url_tg, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'})

    if PO_USER and PO_TOKEN:
        url_po = "https://api.pushover.net/1/messages.json"
        data = {
            "token": PO_TOKEN, "user": PO_USER, "message": msg,
            "title": "🚨 SK22 REAL-TIME!", "sound": "siren",
            "priority": 2, "retry": 30, "expire": 3600
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
    return df

def check_signal():
    # เรียกใช้ API OKX (Public API ไม่ต้องใส่ Key ก็ดึงราคาได้ครับ)
    exchange = ccxt.okx({'enableRateLimit': True})
    print(f"--- [SK22] Real-time Scanning via OKX API ---")
    
    for symbol in SYMBOLS:
        try:
            # 1. ดึงแท่งเทียน 100 แท่งล่าสุด
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','vol'])
            
            # 2. 🔥 จุดสำคัญ: ดึงราคาปัจจุบันจาก API Ticker มาเสียบทันที
            ticker = exchange.fetch_ticker(symbol)
            df.at[df.index[-1], 'close'] = ticker['last'] 
            
            df = calculate_indicators(df)
            last, prev = df.iloc[-1], df.iloc[-2]
            
            # เงื่อนไขแจ้งเตือน SK22
            long_trigger = (prev['k'] < prev['d'] and last['k'] > last['d']) and (last['k'] < 25)
            short_trigger = (prev['k'] > prev['d'] and last['k'] < last['d']) and (last['k'] > 75)

            if long_trigger:
                send_all_alerts(f"🚀 *[LONG]* {symbol}\nPrice: {ticker['last']}\nK: {last['k']:.2f}")
            elif short_trigger:
                send_all_alerts(f"🔻 *[SHORT]* {symbol}\nPrice: {ticker['last']}\nK: {last['k']:.2f}")
            
            print(f"{symbol}: {ticker['last']} | K={last['k']:.2f} D={last['d']:.2f}")
            
        except Exception as e: print(f"Error {symbol}: {e}")

if __name__ == "__main__":
    check_signal()
