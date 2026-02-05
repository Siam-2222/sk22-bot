import os
import ccxt
import requests
import pandas as pd
import numpy as np
import datetime
import pytz

# --- การตั้งค่าบอท TRAGOONAEK NO.1 ---
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'
SWING_LOOKBACK = 5 
DATA_LIMIT = 500  
CHOCH_WINDOW = 15 

# --- ดึงรหัสลับจาก GitHub Secrets (ครบ 100% ตามที่พี่ใช้) ---
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
    # 1. ส่งเข้า Telegram
    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            url_tg = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
            requests.post(url_tg, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}, timeout=15)
        except: pass
    
    # 2. ส่งเข้า Pushover
    if PO_USER and PO_TOKEN:
        try:
            url_po = "https://api.pushover.net/1/messages.json"
            data = {
                "token": PO_TOKEN, 
                "user": PO_USER, 
                "message": msg, 
                "title": "🚨 TRAGOONAEK NO.1 ALERT!", 
                "sound": "siren", 
                "priority": 1
            }
            requests.post(url_po, data=data, timeout=15)
        except: pass

def calculate_sk22_logic(df):
    # [1] RSI (Wilder's Smoothing)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))
    alpha = 1 / 14
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 0.00001)
    df['rsi'] = 100 - (100 / (1 + rs))

    # [2] Stochastic RSI
    rsi_min = df['rsi'].rolling(window=14).min()
    rsi_max = df['rsi'].rolling(window=14).max()
    df['stoch_rsi'] = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min).replace(0, 0.00001)

    # [3] K และ D
    df['k'] = df['stoch_rsi'].rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()
    
    # [4] EMA 200 & ATR (สำหรับ SL)
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['tr'] = np.maximum(df['high'] - df['low'], 
                np.maximum(abs(df['high'] - df['close'].shift(1)), 
                           abs(df['low'] - df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(window=14).mean()

    # [5] CHoCH & Pivots Logic
    last_ph = df['high'].rolling(window=SWING_LOOKBACK*2+1, center=True).max()
    last_pl = df['low'].rolling(window=SWING_LOOKBACK*2+1, center=True).min()
    df['is_ph'] = np.where(df['high'] == last_ph, df['high'], np.nan)
    df['is_pl'] = np.where(df['low'] == last_pl, df['low'], np.nan)
    
    # หา Bars Since CHoCH
    df['choch_up'] = (df['close'] > df['is_ph'].ffill())
    df['choch_down'] = (df['close'] < df['is_pl'].ffill())
    
    # Divergence (เช็คย้อนหลัง 10 แท่ง)
    is_bull_div = (df['low'] < df['low'].shift(10)) & (df['rsi'] > df['rsi'].shift(10))
    is_bear_div = (df['high'] > df['high'].shift(10)) & (df['rsi'] < df['rsi'].shift(10))
    
    return df, is_bear_div.iloc[-1], is_bull_div.iloc[-1]

def check_signal():
    exchange = ccxt.okx({
        'apiKey': OKX_KEY, 'secret': OKX_SECRET, 'password': OKX_PW, 'enableRateLimit': True
    })
    now_thai = get_thai_time()
    print(f"--- [SK22 SCAN: {now_thai}] ---")
    
    for symbol in SYMBOLS:
        try:
            print(f"🔍 Checking {symbol}...", end=" ", flush=True)
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=DATA_LIMIT)
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','vol'])
            
            ticker = exchange.fetch_ticker(symbol)
            df.at[df.index[-1], 'close'] = ticker['last']
            
            df, is_bear_div, is_bull_div = calculate_sk22_logic(df)
            last, prev = df.iloc[-1], df.iloc[-2]

            # --- เงื่อนไข Trigger ตาม TRAGOONAEK NO.1 ---
            long_trigger = (prev['k'] <= prev['d'] and last['k'] > last['d']) and \
                          (last['k'] < 25 or is_bull_div) and \
                          (last['rsi'] >= prev['rsi'])

            short_trigger = (prev['k'] >= prev['d'] and last['k'] < last['d']) and \
                           (last['k'] > 75 or is_bear_div) and \
                           (last['rsi'] <= prev['rsi'])

            if long_trigger:
                sl = round(last['low'] - (last['atr'] * 1.5), 4) # มี SL แจ้งในข้อความครับ
                trend = "📈 Above EMA200" if last['close'] > last['ema200'] else "📉 Below EMA200"
                msg = f"🚀 *[LONG {symbol}]*\n💰 Entry: {last['close']}\n🛡️ SL: {sl}\n📊 Trend: {trend}\n🕒 Time: {now_thai}"
                if is_bull_div: msg += "\n🔥 BULL DIV CONFIRMED!"
                send_all_alerts(msg)
                print("✅ SENT")
            elif short_trigger:
                sl = round(last['high'] + (last['atr'] * 1.5), 4) # มี SL แจ้งในข้อความครับ
                trend = "📉 Below EMA200" if last['close'] < last['ema200'] else "📈 Above EMA200"
                msg = f"🔻 *[SHORT {symbol}]*\n💰 Entry: {last['close']}\n🛡️ SL: {sl}\n📊 Trend: {trend}\n🕒 Time: {now_thai}"
                if is_bear_div: msg += "\n🔥 BEAR DIV CONFIRMED!"
                send_all_alerts(msg)
                print("✅ SENT")
            else:
                print("No signal")

        except Exception as e:
            print(f"⚠️ Skip: {e}")

if __name__ == "__main__":
    check_signal()
