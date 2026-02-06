import os, ccxt, requests
import pandas as pd
import numpy as np
import datetime
import pytz

# --- การตั้งค่าบอท TRAGOONAEK NO.1 (ฉบับจูนความไวตามสคริปต์หน้าจอ) ---
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'       
SWING_LOOKBACK = 5     
CHOCH_WINDOW = 40      # ขยาย Window จาก 20 เป็น 40 เพื่อให้ดักสัญญาณได้กว้างขึ้น

# --- ดึงรหัสลับจาก GitHub Secrets ---
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

def calculate_sk22_logic(df):
    # [1] RSI & Stochastic RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 0.00001)
    df['rsi'] = 100 - (100 / (1 + rs))

    rsi_min = df['rsi'].rolling(window=14).min()
    rsi_max = df['rsi'].rolling(window=14).max()
    df['stoch_rsi'] = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min).replace(0, 0.00001)
    df['k'] = df['stoch_rsi'].rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # [2] ระบบหาระยะ CHoCH (แบบ Fast Fix)
    df['is_ph'] = df['high'][(df['high'].shift(SWING_LOOKBACK) < df['high']) & (df['high'].shift(-SWING_LOOKBACK) < df['high'])]
    df['is_pl'] = df['low'][(df['low'].shift(SWING_LOOKBACK) > df['low']) & (df['low'].shift(-SWING_LOOKBACK) > df['low'])]
    df['last_ph'] = df['is_ph'].ffill()
    df['last_pl'] = df['is_pl'].ffill()
    df['is_choch_up'] = (df['close'] > df['last_ph'].shift(1))
    df['is_choch_down'] = (df['close'] < df['last_pl'].shift(1))
    
    def bars_since(series):
        indices = np.where(series)[0]
        return (len(series) - 1) - indices[-1] if len(indices) > 0 else 999

    bars_since_up = bars_since(df['is_choch_up'])
    bars_since_down = bars_since(df['is_choch_down'])
    
    # [3] Divergence (เช็คย้อนหลัง 10 แท่ง)
    df['bull_div'] = (df['low'] < df['low'].shift(10)) & (df['rsi'] > df['rsi'].shift(10))
    df['bear_div'] = (df['high'] > df['high'].shift(10)) & (df['rsi'] < df['rsi'].shift(10))
    
    return df, bars_since_up, bars_since_down

def check_signal():
    exchange = ccxt.okx({'apiKey': OKX_KEY, 'secret': OKX_SECRET, 'password': OKX_PW, 'timeout': 15000})
    now_thai = get_thai_time()
    print(f"--- [TRAGOONAEK SCAN: {now_thai}] ---")
    
    for symbol in SYMBOLS:
        try:
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=300)
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','vol'])
            
            df, bars_since_up, bars_since_down = calculate_sk22_logic(df)
            last, prev = df.iloc[-1], df.iloc[-2]

            # ปรับจูนเงื่อนไขให้ไวขึ้น (K < 35 และ CHOCH_WINDOW 40)
            long_trigger = (last['k'] > last['d']) and \
                          (last['k'] < 35 or last['bull_div']) and \
                          (last['rsi'] >= prev['rsi']) and \
                          (bars_since_up <= CHOCH_WINDOW)

            short_trigger = (last['k'] < last['d']) and \
                           (last['k'] > 65 or last['bear_div']) and \
                           (last['rsi'] <= prev['rsi']) and \
                           (bars_since_down <= CHOCH_WINDOW)

            sl_long = round(df['low'].tail(2).min(), 4)
            sl_short = round(df['high'].tail(2).max(), 4)

            print(f"🔍 {symbol} | K: {last['k']:.2f} | Up: {bars_since_up}", end=" ")

            if long_trigger:
                msg = f"🚀 *[LONG {symbol} 15m]*\n💰 Entry: {last['close']}\n🛑 *SL: {sl_long}*\n🕒 Time: {now_thai}"
                send_all_alerts(msg)
                print("✅ [SIGNAL!]")
            elif short_trigger:
                msg = f"🔻 *[SHORT {symbol} 15m]*\n💰 Entry: {last['close']}\n🛑 *SL: {sl_short}*\n🕒 Time: {now_thai}"
                send_all_alerts(msg)
                print("✅ [SIGNAL!]")
            else:
                print("❌ No signal")

        except Exception as e:
            print(f"⚠️ Error: {e}")

if __name__ == "__main__":
    check_signal()
