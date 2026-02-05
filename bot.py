import os, ccxt, requests
import pandas as pd
import numpy as np
import datetime
import pytz

# --- การตั้งค่าบอท TRAGOONAEK NO.1 (รุ่นทดสอบระบบแจ้งเตือนด่วน) ---
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '5m'      # ปรับจาก 15m เป็น 5m เพื่อให้สัญญาณมาไวขึ้น
SWING_LOOKBACK = 5    
CHOCH_WINDOW = 30     # ขยายจาก 15 เป็น 30 เพื่อให้แจ้งเตือนง่ายขึ้นในการทดสอบ

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
    if PO_USER and PO_TOKEN:
        try:
            url_po = "https://api.pushover.net/1/messages.json"
            data = {"token": PO_TOKEN, "user": PO_USER, "message": msg, "title": "🚨 TRAGOONAEK ALERT!", "sound": "siren", "priority": 1}
            requests.post(url_po, data=data, timeout=15)
        except: pass

def calculate_sk22_logic(df):
    # [1] RSI & Stochastic RSI (Wilder's Smoothing)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))
    alpha = 1 / 14
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 0.00001)
    df['rsi'] = 100 - (100 / (1 + rs))

    rsi_min = df['rsi'].rolling(window=14).min()
    rsi_max = df['rsi'].rolling(window=14).max()
    df['stoch_rsi'] = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min).replace(0, 0.00001)
    df['k'] = df['stoch_rsi'].rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # [2] ระบบหาระยะ CHoCH
    df['is_ph'] = df['high'][(df['high'].shift(SWING_LOOKBACK) < df['high']) & (df['high'].shift(-SWING_LOOKBACK) < df['high'])]
    df['is_pl'] = df['low'][(df['low'].shift(SWING_LOOKBACK) > df['low']) & (df['low'].shift(-SWING_LOOKBACK) > df['low'])]
    df['last_ph'] = df['is_ph'].ffill()
    df['last_pl'] = df['is_pl'].ffill()
    df['is_choch_up'] = (df['close'] > df['last_ph'].shift(1))
    df['is_choch_down'] = (df['close'] < df['last_pl'].shift(1))
    
    # [3] ระบบนับแท่ง Bars Since CHoCH
    def bars_since(series):
        indices = np.where(series)[0]
        if len(indices) == 0: return 999
        return (len(series) - 1) - indices[-1]

    bars_since_up = bars_since(df['is_choch_up'])
    bars_since_down = bars_since(df['is_choch_down'])
    
    # [4] Divergence (เช็คย้อนหลัง 10 แท่ง)
    df['bull_div'] = (df['low'] < df['low'].shift(10)) & (df['rsi'] > df['rsi'].shift(10))
    df['bear_div'] = (df['high'] > df['high'].shift(10)) & (df['rsi'] < df['rsi'].shift(10))
    
    return df, bars_since_up, bars_since_down

def check_signal():
    exchange = ccxt.okx({'apiKey': OKX_KEY, 'secret': OKX_SECRET, 'password': OKX_PW, 'timeout': 15000})
    now_thai = get_thai_time()
    print(f"--- [TRAGOONAEK SCAN: {now_thai}] ---")
    
    for symbol in SYMBOLS:
        try:
            print(f"🔍 {symbol}", end=" ", flush=True)
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=300)
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','vol'])
            ticker = exchange.fetch_ticker(symbol)
            df.at[df.index[-1], 'close'] = ticker['last']
            
            df, bars_since_up, bars_since_down = calculate_sk22_logic(df)
            last, prev = df.iloc[-1], df.iloc[-2]

            # เงื่อนไข Trigger
            long_trigger = (prev['k'] <= prev['d'] and last['k'] > last['d']) and \
                          (last['k'] < 25 or last['bull_div']) and \
                          (last['rsi'] >= prev['rsi']) and \
                          (bars_since_up <= CHOCH_WINDOW)

            short_trigger = (prev['k'] >= prev['d'] and last['k'] < last['d']) and \
                           (last['k'] > 75 or last['bear_div']) and \
                           (last['rsi'] <= prev['rsi']) and \
                           (bars_since_down <= CHOCH_WINDOW)

            # พ่นค่า K และ RSI ออกมาดูหน้างาน
            print(f"| K: {last['k']:.2f} | RSI: {last['rsi']:.2f} | Up: {bars_since_up} | Down: {bars_since_down}", end=" ")

            if long_trigger:
                msg = f"🚀 *[LONG {symbol} 5m]*\n💰 Entry: {last['close']}\n🕒 Time: {now_thai}\n✨ CHoCH: {bars_since_up} bars ago"
                send_all_alerts(msg)
                print("✅ [SIGNAL! SENT]")
            elif short_trigger:
                msg = f"🔻 *[SHORT {symbol} 5m]*\n💰 Entry: {last['close']}\n🕒 Time: {now_thai}\n✨ CHoCH: {bars_since_down} bars ago"
                send_all_alerts(msg)
                print("✅ [SIGNAL! SENT]")
            else:
                print("❌ No fresh signal")

        except Exception as e:
            print(f"⚠️ Error: {e}")

    print(f"--- [FINISH] ---")

if __name__ == "__main__":
    check_signal()
