import os, ccxt, requests
import pandas as pd
import numpy as np
import datetime
import pytz

# --- ตั้งค่า TRAGOONAEK NO.1 (ฉบับปลุกชีพ - ไวเท่าหน้าจอ) ---
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'

PO_USER = os.getenv('PUSHOVER_USER_KEY')
PO_TOKEN = os.getenv('PUSHOVER_API_TOKEN')
TG_TOKEN = os.getenv('TELEGRAM_TOKEN')
TG_CHAT_ID = os.getenv('CHAT_ID')
OKX_KEY = os.getenv('OKX_API_KEY')
OKX_SECRET = os.getenv('OKX_SECRET_KEY')
OKX_PW = os.getenv('OKX_PASSPHRASE')

def get_thai_time():
    tz_thai = pytz.timezone('Asia/Bangkok')
    return datetime.datetime.now(tz_thai).strftime('%H:%M:%S')

def send_all_alerts(msg):
    if PO_USER and PO_TOKEN:
        try:
            requests.post("https://api.pushover.net/1/messages.json", data={
                "token": PO_TOKEN, "user": PO_USER, "message": msg,
                "title": "🚨 TRAGOONAEK SIGNAL!", "sound": "siren", "priority": 2,
                "retry": 30, "expire": 3600
            }, timeout=15)
        except: pass
    if TG_TOKEN and TG_CHAT_ID:
        try:
            url = f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage'
            requests.post(url, data={'chat_id': TG_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}, timeout=15)
        except: pass

def calculate_sk22_logic(df):
    # 1. RSI (ปรับให้กลับมาเป็น Simple Moving Average เพื่อให้ไวเท่าหน้าจอ)
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
    rs = gain / loss.replace(0, 0.00001)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 2. Stochastic RSI
    rsi_low = df['rsi'].rolling(window=14).min()
    rsi_high = df['rsi'].rolling(window=14).max()
    stoch_rsi = 100 * (df['rsi'] - rsi_low) / (rsi_high - rsi_low).replace(0, 0.00001)
    df['k'] = stoch_rsi.rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()

    # 3. ATR 14 (สำหรับ SL เส้นสีเงิน)
    tr = pd.concat([df['high']-df['low'], abs(df['high']-df['close'].shift()), abs(df['low']-df['close'].shift())], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()

    # 4. Divergence Logic (ปรับให้มองย้อนหลังได้ไกลขึ้น)
    df['is_bull_div'] = (df['low'].shift(1).rolling(5).min() < df['low'].shift(10).rolling(5).min()) & \
                        (df['rsi'].shift(1).rolling(5).min() > df['rsi'].shift(10).rolling(5).min())
    df['is_bear_div'] = (df['high'].shift(1).rolling(5).max() > df['high'].shift(10).rolling(5).max()) & \
                        (df['rsi'].shift(1).rolling(5).max() < df['rsi'].shift(10).rolling(5).max())

    return df

def check_signal():
    exchange = ccxt.okx({'apiKey': OKX_KEY, 'secret': OKX_SECRET, 'password': OKX_PW})
    now_thai = get_thai_time()
    print(f"--- [TRAGOONAEK MONITORING: {now_thai}] ---")
    
    for symbol in SYMBOLS:
        try:
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','vol'])
            df = calculate_sk22_logic(df)
            last, prev = df.iloc[-1], df.iloc[-2]

            # --- เงื่อนไข Trigger (ฉบับแก้ทาง: เน้นให้เตือนตามหน้าจอ) ---
            # LONG: K อยู่เหนือ D แล้ว และ (K < 30 หรือ มี Bull Div) และ RSI ไม่หักหัวลง
            long_trigger = (last['k'] > last['d']) and \
                          (last['k'] < 30 or last['is_bull_div']) and \
                          (last['rsi'] >= prev['rsi'] - 0.5) # เผื่อระยะ RSI นิดหน่อย

            # SHORT: K อยู่ต่ำกว่า D แล้ว และ (K > 70 หรือ มี Bear Div) และ RSI ไม่หักหัวขึ้น
            short_trigger = (last['k'] < last['d']) and \
                           (last['k'] > 70 or last['is_bear_div']) and \
                           (last['rsi'] <= prev['rsi'] + 0.5)

            if long_trigger:
                sl = round(last['low'] - (last['atr'] * 1.5), 4)
                send_all_alerts(f"🚀 *[LONG {symbol}]*\n💰 ราคา: {last['close']}\n🛑 SL: {sl}\n🕒 {now_thai}")
                print(f"🔍 {symbol:9} ✅ SIGNAL SENT")
            elif short_trigger:
                sl = round(last['high'] + (last['atr'] * 1.5), 4)
                send_all_alerts(f"🔻 *[SHORT {symbol}]*\n💰 ราคา: {last['close']}\n🛑 SL: {sl}\n🕒 {now_thai}")
                print(f"🔍 {symbol:9} ✅ SIGNAL SENT")
            else:
                print(f"🔍 {symbol:9} | K:{last['k']:5.1f} | RSI:{last['rsi']:4.1f} | No Signal")

        except Exception as e:
            print(f"⚠️ Error {symbol}: {e}")
    
    print(f"--- [FINISHED] ---")

if __name__ == "__main__":
    check_signal()
