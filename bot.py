import os, ccxt, requests
import pandas as pd
import numpy as np
import datetime
import pytz

# --- ตั้งค่า TRAGOONAEK NO.1 (ฉบับปลุกชีพ - เน้นทำงาน ไม่เน้นนอน) ---
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
    # RSI แบบมาตรฐาน (เหมือนหน้าจอพี่)
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss.replace(0, 0.00001))))
    
    # Stochastic RSI
    rsi_low = df['rsi'].rolling(window=14).min()
    rsi_high = df['rsi'].rolling(window=14).max()
    stoch_rsi = 100 * (df['rsi'] - rsi_low) / (rsi_high - rsi_low).replace(0, 0.00001)
    df['k'] = stoch_rsi.rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()
    df['atr'] = (df['high'] - df['low']).rolling(window=14).mean()
    
    # เช็ก Bullish Divergence แบบง่ายๆ (ราคาลง rsi ขึ้น)
    df['is_bull_div'] = (df['low'] < df['low'].shift(10)) & (df['rsi'] > df['rsi'].shift(10))
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

            # --- เงื่อนไข Trigger (ฉบับช่างไฟวิทยา: เอาป้ายเป็นหลัก) ---
            # LONG: K อยู่โซนต่ำ (< 35) และ K งัดขึ้นจากเมื่อกี้นิดเดียวก็เอาเลย!
            long_trigger = (last['k'] < 35) and (last['k'] > prev['k'])
            
            # SHORT: K อยู่โซนสูง (> 65) และ K เริ่มหักหัวลง
            short_trigger = (last['k'] > 65) and (last['k'] < prev['k'])

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
