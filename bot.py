import os, ccxt, requests
import pandas as pd
import numpy as np
import datetime
import pytz

SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'
SWING_LOOKBACK = 5 

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
            requests.post(url_tg, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}, timeout=10)
        except: pass
    if PO_USER and PO_TOKEN:
        try:
            url_po = "https://api.pushover.net/1/messages.json"
            data = {"token": PO_TOKEN, "user": PO_USER, "message": msg, "title": "🚨 SK22 DYNAMIC!", "sound": "siren", "priority": 2, "retry": 30, "expire": 3600}
            requests.post(url_po, data=data, timeout=10)
        except: pass

def calculate_dynamic_sk22(df):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss.replace(0, 1))))
    rsi_min, rsi_max = df['rsi'].rolling(14).min(), df['rsi'].rolling(14).max()
    df['k'] = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min).replace(0, 1)
    df['k'] = df['k'].rolling(3).mean()
    df['d'] = df['k'].rolling(3).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

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
    exchange = ccxt.okx({'apiKey': OKX_KEY, 'secret': OKX_SECRET, 'password': OKX_PW, 'enableRateLimit': True})
    now_thai = get_thai_time()
    print(f"--- [SK22 START SCAN: {now_thai}] ---") # บอกเวลาเริ่มสแกน
    
    for symbol in SYMBOLS:
        try:
            # รายงานว่ากำลังตรวจเหรียญไหน
            print(f"🔍 Checking {symbol}...") 
            
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=300)
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','vol'])
            ticker = exchange.fetch_ticker(symbol)
            curr_price = ticker['last']
            df.at[df.index[-1], 'close'] = curr_price 
            df, is_bear_div, is_bull_div = calculate_dynamic_sk22(df)
            last, prev = df.iloc[-1], df.iloc[-2]
            is_uptrend = curr_price > last['ema200']
            
            # โชว์ค่า K/D ให้พี่ดูใน Log ด้วย
            print(f"   > Price: {curr_price} | K: {last['k']:.2f} | D: {last['d']:.2f}")

            long_trigger = (prev['k'] < prev['d'] and last['k'] > last['d']) and (last['k'] < 25 or (is_bull_div and last['k'] < 50)) and (last['rsi'] >= prev['rsi'])
            short_trigger = (prev['k'] > prev['d'] and last['k'] < last['d']) and (last['k'] > 75 or (is_bear_div and last['k'] > 50)) and (last['rsi'] <= prev['rsi'])

            if long_trigger:
                sl = round(last['low'] * 0.999, 4)
                grade = "🏆 [PREMIUM]" if is_uptrend else "⚠️ [NORMAL]"
                msg = f"{grade} - LONG {symbol} {'+ Bull Div' if is_bull_div else ''}\n🕒 TIME: {now_thai}\n💰 ENTRY: {curr_price}\n🛡️ SL: {sl}\n{'⭐ Confidence: 90%' if is_uptrend else '❗ Counter-Trend'}"
                send_all_alerts(msg)
                print(f"   ✅ SIGNAL FOUND: LONG {symbol}")
            elif short_trigger:
                sl = round(last['high'] * 1.001, 4)
                grade = "🏆 [PREMIUM]" if not is_uptrend else "⚠️ [NORMAL]"
                msg = f"{grade} - SHORT {symbol} {'+ Bear Div' if is_bear_div else ''}\n🕒 TIME: {now_thai}\n💰 ENTRY: {curr_price}\n🛡️ SL: {sl}\n{'⭐ Confidence: 90%' if not is_uptrend else '❗ Counter-Trend'}"
                send_all_alerts(msg)
                print(f"   ✅ SIGNAL FOUND: SHORT {symbol}")
            else:
                print(f"   ❌ No Signal for {symbol}")

        except Exception as e: 
            print(f"   ⚠️ Error scanning {symbol}: {e}")

    print(f"--- [SCAN FINISHED] ---")

if __name__ == "__main__":
    check_signal()
