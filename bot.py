import os
import ccxt
import requests
import pandas as pd
import numpy as np
import datetime
import pytz

# --- การตั้งค่าบอท ---
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'
SWING_LOOKBACK = 5 
DATA_LIMIT = 500  # ปรับเป็น 500 เพื่อความแม่นยำของ EMA200

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
    # ส่งเข้า Telegram
    if TELEGRAM_TOKEN and CHAT_ID:
        try:
            url_tg = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
            requests.post(url_tg, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}, timeout=15)
        except: pass
    
    # ส่งเข้า Pushover
    if PO_USER and PO_TOKEN:
        try:
            url_po = "https://api.pushover.net/1/messages.json"
            data = {"token": PO_TOKEN, "user": PO_USER, "message": msg, "title": "🚨 SK22 ALERT!", "sound": "siren", "priority": 1}
            requests.post(url_po, data=data, timeout=15)
        except: pass

def calculate_sk22_logic(df):
    # 1. RSI (Wilder's Smoothing)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))
    alpha = 1 / 14
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 0.00001)
    df['rsi'] = 100 - (100 / (1 + rs))

    # 2. Stochastic RSI
    rsi_min = df['rsi'].rolling(window=14).min()
    rsi_max = df['rsi'].rolling(window=14).max()
    df['stoch_rsi'] = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min).replace(0, 0.00001)

    # 3. K และ D (SMA 3)
    df['k'] = df['stoch_rsi'].rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

    # 4. Divergence Logic
    def get_pivots(data, is_high):
        pivots = []
        for i in range(SWING_LOOKBACK, len(data) - SWING_LOOKBACK):
            part = data[i-SWING_LOOKBACK : i+SWING_LOOKBACK+1]
            if is_high and data[i] == max(part): pivots.append((i, data[i]))
            elif not is_high and data[i] == min(part): pivots.append((i, data[i]))
        return pivots

    ph = get_pivots(df['high'].values, True)
    pl = get_pivots(df['low'].values, False)
    is_bear_div, is_bull_div = False, False
    
    if len(ph) >= 2:
        if ph[-1][1] > ph[-2][1] and df['rsi'].iloc[ph[-1][0]] < df['rsi'].iloc[ph[-2][0]]: is_bear_div = True
    if len(pl) >= 2:
        if pl[-1][1] < pl[-2][1] and df['rsi'].iloc[pl[-1][0]] > df['rsi'].iloc[pl[-2][0]]: is_bull_div = True
    
    return df, is_bear_div, is_bull_div

def check_signal():
    exchange = ccxt.okx({
        'apiKey': OKX_KEY, 
        'secret': OKX_SECRET, 
        'password': OKX_PW,
        'enableRateLimit': True
    })
    
    now_thai = get_thai_time()
    print(f"--- [SK22 SCAN: {now_thai}] ---")
    
    for symbol in SYMBOLS:
        try:
            print(f"🔍 Checking {symbol}...", end=" ", flush=True)
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=DATA_LIMIT)
            if not bars: continue
                
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','vol'])
            
            # อัปเดตราคาล่าสุด
            ticker = exchange.fetch_ticker(symbol)
            curr_price = ticker['last']
            df.at[df.index[-1], 'close'] = curr_price 
            
            df, is_bear_div, is_bull_div = calculate_sk22_logic(df)
            last, prev = df.iloc[-1], df.iloc[-2]

            # ตรรกะการเข้าเทรด SK22
            long_trigger = (prev['k'] <= prev['d'] and last['k'] > last['d']) and \
                          (last['k'] < 25 or (is_bull_div and last['k'] < 50)) and \
                          (last['rsi'] >= prev['rsi'])

            short_trigger = (prev['k'] >= prev['d'] and last['k'] < last['d']) and \
                           (last['k'] > 75 or (is_bear_div and last['k'] > 50)) and \
                           (last['rsi'] <= prev['rsi'])

            if long_trigger:
                sl = round(last['low'] * 0.999, 4)
                msg = f"🚀 LONG {symbol}\n💰 ENTRY: {curr_price}\n🛡️ SL: {sl}\n🕒 TIME: {now_thai}"
                if is_bull_div: msg += "\n🔥 BULL DIV CONFIRMED!"
                send_all_alerts(msg)
                print("✅ SIGNAL FOUND")
            elif short_trigger:
                sl = round(last['high'] * 1.001, 4)
                msg = f"🔻 SHORT {symbol}\n💰 ENTRY: {curr_price}\n🛡️ SL: {sl}\n🕒 TIME: {now_thai}"
                if is_bear_div: msg += "\n🔥 BEAR DIV CONFIRMED!"
                send_all_alerts(msg)
                print("✅ SIGNAL FOUND")
            else:
                print("No signal")

        except Exception as e:
            print(f"⚠️ Skip: {e}")
            continue

if __name__ == "__main__":
    check_signal()
