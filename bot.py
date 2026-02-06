import os, ccxt, requests
import pandas as pd
import numpy as np
import datetime
import pytz

# --- การตั้งค่าบอท TRAGOONAEK NO.1 (ฉบับสมบูรณ์) ---
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'       
SWING_LOOKBACK = 5     
CHOCH_WINDOW = 60      # หน้าต่างมองย้อนหลัง 60 แท่ง

# --- ดึงรหัสลับจาก GitHub Secrets (Pushover & Telegram) ---
PO_USER = os.getenv('PUSHOVER_USER_KEY')
PO_TOKEN = os.getenv('PUSHOVER_API_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

# API OKX
OKX_KEY = os.getenv('OKX_API_KEY')
OKX_SECRET = os.getenv('OKX_SECRET_KEY')
OKX_PW = os.getenv('OKX_PASSPHRASE')

def get_thai_time():
    """ดึงเวลาปัจจุบันเป็น Asia/Bangkok"""
    tz_thai = pytz.timezone('Asia/Bangkok')
    return datetime.datetime.now(tz_thai).strftime('%Y-%m-%d %H:%M:%S')

def send_all_alerts(msg):
    """ส่งแจ้งเตือนทั้ง Pushover (มีเสียงไซเรน) และ Telegram"""
    
    # [1] ระบบ Pushover (เน้นเสียงดัง)
    if PO_USER and PO_TOKEN:
        try:
            url_po = "https://api.pushover.net/1/messages.json"
            data_po = {
                "token": PO_TOKEN,
                "user": PO_USER,
                "message": msg,
                "title": "🚨 TRAGOONAEK ALERT!",
                "sound": "siren",      # ตั้งเสียงไซเรน
                "priority": 1          # บังคับให้ดังแม้เครื่องจะเงียบ
            }
            res = requests.post(url_po, data=data_po, timeout=15)
            if res.status_code != 200:
                print(f"❌ Pushover Fail: {res.text}")
        except Exception as e:
            print(f"⚠️ Pushover Error: {e}")

    # [2] ระบบ Telegram (สำรอง)
    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            url_tg = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
            requests.post(url_tg, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}, timeout=15)
        except Exception as e:
            print(f"⚠️ Telegram Error: {e}")

def calculate_sk22_logic(df):
    """คำนวณอินดิเคเตอร์ให้ตรงกับ TradingView"""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss.replace(0, 0.00001)
    df['rsi'] = 100 - (100 / (1 + rs))

    rsi_min = df['rsi'].rolling(window=14).min()
    rsi_max = df['rsi'].rolling(window=14).max()
    df['stoch_rsi'] = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min).replace(0, 0.00001)
    df['k'] = df['stoch_rsi'].rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()
    
    df['is_ph'] = df['high'][(df['high'].shift(SWING_LOOKBACK) < df['high']) & (df['high'].shift(-SWING_LOOKBACK) < df['high'])]
    df['is_pl'] = df['low'][(df['low'].shift(SWING_LOOKBACK) > df['low']) & (df['low'].shift(-SWING_LOOKBACK) > df['low'])]
    df['last_ph'] = df['is_ph'].ffill()
    df['last_pl'] = df['is_pl'].ffill()
    df['is_choch_up'] = (df['close'] > df['last_ph'].shift(1))
    df['is_choch_down'] = (df['close'] < df['last_pl'].shift(1))
    
    def bars_since(series):
        indices = np.where(series)[0]
        if len(indices) == 0: return 999
        return (len(series) - 1) - indices[-1]

    return df, bars_since(df['is_choch_up']), bars_since(df['is_choch_down'])

def check_signal():
    exchange = ccxt.okx({'apiKey': OKX_KEY, 'secret': OKX_SECRET, 'password': OKX_PW, 'enableRateLimit': True})
    now_thai = get_thai_time()
    print(f"--- [TRAGOONAEK START: {now_thai}] ---")
    
    # บรรทัดทดสอบ (ถ้าตั้งค่าถูก Pushover ต้องดังไซเรนทันทีที่รัน!)
    # send_all_alerts(f"📢 บอทช่างไฟวิทยา เริ่มรันระบบทดสอบเสียงไซเรน!\n🕒 {now_thai}")

    for symbol in SYMBOLS:
        try:
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=300)
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','vol'])
            ticker = exchange.fetch_ticker(symbol)
            df.at[df.index[-1], 'close'] = ticker['last']
            
            df, bs_up, bs_down = calculate_sk22_logic(df)
            last, prev = df.iloc[-1], df.iloc[-2]

            # --- เงื่อนไข Trigger ---
            long_trigger = (prev['k'] <= prev['d'] and last['k'] > last['d']) and (last['k'] < 50) and (bs_up <= CHOCH_WINDOW)
            short_trigger = (prev['k'] >= prev['d'] and last['k'] < last['d']) and (last['k'] > 50) and (bs_down <= CHOCH_WINDOW)

            sl_long = round(df['low'].tail(3).min(), 4)
            sl_short = round(df['high'].tail(3).max(), 4)

            print(f"🔍 {symbol:9} | K: {last['k']:5.2f} | Up: {bs_up:3} | Down: {bs_down:3}", end=" ")

            if long_trigger:
                msg = f"🚀 *[LONG {symbol}]*\n💰 Entry: {last['close']}\n🛑 SL: {sl_long}\n🕒 {now_thai}"
                send_all_alerts(msg)
                print("✅ [SIGNAL SENT]")
            elif short_trigger:
                msg = f"🔻 *[SHORT {symbol}]*\n💰 Entry: {last['close']}\n🛑 SL: {sl_short}\n🕒 {now_thai}"
                send_all_alerts(msg)
                print("✅ [SIGNAL SENT]")
            else:
                print("❌")

        except Exception as e:
            print(f"⚠️ Error {symbol}: {e}")

    print(f"--- [FINISHED] ---")

if __name__ == "__main__":
    check_signal()
