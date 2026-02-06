import os, ccxt, requests
import pandas as pd
import numpy as np
import datetime
import pytz

# --- ตั้งค่า TRAGOONAEK NO.1 (ฉบับรันจริง 24 ชม.) ---
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'
SWING_LOOKBACK = 5

# ดึงรหัสลับจาก GitHub
PO_USER = os.getenv('PUSHOVER_USER_KEY')
PO_TOKEN = os.getenv('PUSHOVER_API_TOKEN')
TG_TOKEN = os.getenv('TELEGRAM_TOKEN')
TG_CHAT_ID = os.getenv('CHAT_ID')
OKX_KEY = os.getenv('OKX_API_KEY')
OKX_SECRET = os.getenv('OKX_SECRET_KEY')
OKX_PW = os.getenv('OKX_PASSPHRASE')

def get_thai_time():
    tz_thai = pytz.timezone('Asia/Bangkok')
    return datetime.datetime.now(tz_thai).strftime('%Y-%m-%d %H:%M:%S')

def send_all_alerts(msg):
    """ส่งแจ้งเตือนฉุกเฉินระดับ 2 (Siren) และ Telegram"""
    # [1] Pushover - Emergency Siren
    if PO_USER and PO_TOKEN:
        try:
            requests.post("https://api.pushover.net/1/messages.json", data={
                "token": PO_TOKEN, "user": PO_USER, "message": msg,
                "title": "🚨 TRAGOONAEK SIGNAL!", "sound": "siren", 
                "priority": 2, "retry": 30, "expire": 3600
            }, timeout=15)
        except: pass

    # [2] Telegram - Message
    if TG_TOKEN and TG_CHAT_ID:
        try:
            url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
            requests.post(url, data={'chat_id': TG_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}, timeout=15)
        except: pass

def calculate_sk22_logic(df):
    """คำนวณสูตรตาม Pine Script หน้าจอพี่วิทยา"""
    # RSI & Stoch RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss.replace(0, 0.00001))))
    
    rsi_low = df['rsi'].rolling(window=14).min()
    rsi_high = df['rsi'].rolling(window=14).max()
    df['k'] = (100 * (df['rsi'] - rsi_low) / (rsi_high - rsi_low).replace(0, 0.00001)).rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()

    # ATR (สำหรับ SL เส้นสีเงิน)
    tr = pd.concat([df['high']-df['low'], abs(df['high']-df['close'].shift()), abs(df['low']-df['close'].shift())], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()

    # Divergence 
    df['is_bear_div'] = (df['high'].shift(1).rolling(5).max() > df['high'].shift(10).rolling(5).max()) & \
                        (df['rsi'].shift(1).rolling(5).max() < df['rsi'].shift(10).rolling(5).max())
    df['is_bull_div'] = (df['low'].shift(1).rolling(5).min() < df['low'].shift(10).rolling(5).min()) & \
                        (df['rsi'].shift(1).rolling(5).min() > df['rsi'].shift(10).rolling(5).min())

    # CHoCH Detection
    df['last_ph'] = df['high'][(df['high'].shift(5) < df['high']) & (df['high'].shift(-5) < df['high'])].ffill().shift(1)
    df['last_pl'] = df['low'][(df['low'].shift(5) > df['low']) & (df['low'].shift(-5) > df['low'])].ffill().shift(1)
    
    def get_bars_since(condition):
        idx = np.where(condition)[0]
        return (len(df) - 1) - idx[-1] if len(idx) > 0 else 999

    bs_up = get_bars_since(df['close'] > df['last_ph'])
    bs_down = get_bars_since(df['close'] < df['last_pl'])

    return df, bs_up, bs_down

def check_signal():
    exchange = ccxt.okx({'apiKey': OKX_KEY, 'secret': OKX_SECRET, 'password': OKX_PW})
    now_thai = get_thai_time()
    print(f"--- [TRAGOONAEK MONITORING: {now_thai}] ---")
    
    for symbol in SYMBOLS:
        try:
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=300)
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','vol'])
            df, bs_up, bs_down = calculate_sk22_logic(df)
            last, prev = df.iloc[-1], df.iloc[-2]

            # LONG: K ตัด D ขึ้น และ (K < 25 หรือ มี Bull Div)
            long_trigger = (prev['k'] <= prev['d'] and last['k'] > last['d']) and \
                          (last['k'] < 25 or (last['is_bull_div'] and last['k'] < 50))
            
            # SHORT: K ตัด D ลง และ (K > 75 หรือ มี Bear Div)
            short_trigger = (prev['k'] >= prev['d'] and last['k'] < last['d']) and \
                           (last['k'] > 75 or (last['is_bear_div'] and last['k'] < 50))

            if long_trigger:
                sl = round(last['low'] - (last['atr'] * 1.5), 4)
                send_all_alerts(f"🚀 *[LONG {symbol}]*\n💰 Entry: {last['close']}\n🛑 SL: {sl}\n🕒 {now_thai}")
                print(f"🔍 {symbol:9} ✅ SIGNAL SENT")
            elif short_trigger:
                sl = round(last['high'] + (last['atr'] * 1.5), 4)
                send_all_alerts(f"🔻 *[SHORT {symbol}]*\n💰 Entry: {last['close']}\n🛑 SL: {sl}\n🕒 {now_thai}")
                print(f"🔍 {symbol:9} ✅ SIGNAL SENT")
            else:
                print(f"🔍 {symbol:9} | K: {last['k']:5.2f} | No Signal")

        except Exception as e:
            print(f"⚠️ Error {symbol}: {e}")
    
    print(f"--- [FINISHED] ---")

if __name__ == "__main__":
    check_signal()
