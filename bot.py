import os, ccxt, requests, time
import pandas as pd
import numpy as np

# [1] รายชื่อเหรียญที่เฝ้าดู
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'

# [2] ดึงรหัสลับจาก GitHub (ต้องตั้งชื่อให้ตรงใน Secrets นะครับพี่)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
PO_USER = os.getenv('PUSHOVER_USER_KEY')
PO_TOKEN = os.getenv('PUSHOVER_API_TOKEN')

def send_all_alerts(msg):
    # 1. ส่ง Telegram (แจ้งเตือนปกติ)
    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            url_tg = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
            requests.post(url_tg, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}, timeout=10)
        except Exception as e:
            print(f"Telegram Error: {e}")

    # 2. ส่ง Pushover (ไซเรนฉุกเฉิน ดังลากยาว)
    if PO_USER and PO_TOKEN:
        try:
            url_po = "https://api.pushover.net/1/messages.json"
            data = {
                "token": PO_TOKEN,
                "user": PO_USER,
                "message": msg,
                "title": "🚨 SK22 SIGNAL!!",
                "sound": "siren",        # เสียงไซเรน
                "priority": 2,           # ระดับฉุกเฉิน (Emergency)
                "retry": 30,             # ถ้าไม่กดปิด ให้ดังซ้ำทุก 30 วินาที
                "expire": 3600           # ให้ดังซ้ำนานสูงสุด 1 ชม.
            }
            requests.post(url_po, data=data, timeout=10)
        except Exception as e:
            print(f"Pushover Error: {e}")

def calculate_indicators(df):
    # คำนวณ Stochastic RSI ตามสูตร SK 22
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, 1)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    rsi_min = df['rsi'].rolling(window=14).min()
    rsi_max = df['rsi'].rolling(window=14).max()
    
    # กันกรณีหารด้วยศูนย์
    df['k'] = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min).replace(0, 1)
    df['k'] = df['k'].rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()
    
    # EMA 200 สำหรับดูเทรนหลัก
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    return df

def check_signal():
    # ใช้ OKX เพราะข้อมูลเหรียญใหม่ๆ อย่าง HYPE แม่นยำครับ
    exchange = ccxt.okx()
    print(f"--- [SK22+SIREN] Scanning: {len(SYMBOLS)} Coins ---")
    
    for symbol in SYMBOLS:
        try:
            # ดึงข้อมูลย้อนหลัง 100 แท่ง
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
            df = calculate_indicators(pd.DataFrame(bars, columns=['time','open','high','low','close','vol']))
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # --- เงื่อนไขเข้าเทรด SK 22 ---
            # LONG: K ตัด D ขึ้น และ K อยู่ในโซนต่ำกว่า 25
            long_trigger = (prev['k'] < prev['d'] and last['k'] > last['d']) and (last['k'] < 25)
            
            # SHORT: K ตัด D ลง และ K อยู่ในโซนสูงกว่า 75
            short_trigger = (prev['k'] > prev['d'] and last['k'] < last['d']) and (last['k'] > 75)

            if long_trigger:
                msg = f"🚀 *[LONG]* {symbol}\n💰 Price: {last['close']}\n📊 K-Value: {last['k']:.2f}\n📈 Trend: {'Above EMA200' if last['close'] > last['ema200'] else 'Below EMA200'}"
                send_all_alerts(msg)
            elif short_trigger:
                msg = f"🔻 *[SHORT]* {symbol}\n💰 Price: {last['close']}\n📊 K-Value: {last['k']:.2f}\n📉 Trend: {'Above EMA200' if last['close'] > last['ema200'] else 'Below EMA200'}"
                send_all_alerts(msg)
                
            print(f"{symbol} Checked: K={last['k']:.2f} D={last['d']:.2f}")
            
        except Exception as e:
            print(f"Error scanning {symbol}: {e}")

if __name__ == "__main__":
    check_signal()
