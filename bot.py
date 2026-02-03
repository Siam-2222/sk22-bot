import os
import ccxt
import pandas as pd
import numpy as np
import requests

# พยายามนำเข้า pandas_ta ถ้าไม่ได้จะใช้ระบบคำนวณสำรอง
try:
    import pandas_ta as ta
    HAS_TA = True
except ImportError:
    HAS_TA = False

SYMBOL = 'BTC/USDT'
TIMEFRAME = '15m'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
        requests.post(url, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'})
    except: pass

def check_signal():
    try:
        exchange = ccxt.binance()
        bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=300)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])

        # --- Indicator Calculation ---
        if HAS_TA:
            df['rsi'] = ta.rsi(df['close'], length=14)
            stoch = ta.stochrsi(df['close'], length=14, rsi_length=14, k=3, d=3)
            df['k'], df['d'] = stoch.iloc[:, 0], stoch.iloc[:, 1]
            df['ema200'] = ta.ema(df['close'], length=200)
        else:
            # ระบบสำรอง (Manual Calculation) กรณีติดตั้ง library ไม่สำเร็จ
            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            # EMA 200
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
            # Stoch RSI (Simplified)
            rsi_min = df['rsi'].rolling(window=14).min()
            rsi_max = df['rsi'].rolling(window=14).max()
            df['k'] = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min)
            df['d'] = df['k'].rolling(window=3).mean()

        # Pivot Points
        w = 5
        df['p_high'] = df['high'].iloc[w:-w].where((df['high'] == df['high'].rolling(w*2+1, center=True).max()))
        df['p_low'] = df['low'].iloc[w:-w].where((df['low'] == df['low'].rolling(w*2+1, center=True).min()))

        # Divergence
        ph = df.dropna(subset=['p_high']).tail(2)
        pl = df.dropna(subset=['p_low']).tail(2)
        is_bull, is_bear = False, False
        if len(ph) >= 2 and ph['high'].iloc[-1] > ph['high'].iloc[-2] and ph['rsi'].iloc[-1] < ph['rsi'].iloc[-2]: is_bear = True
        if len(pl) >= 2 and pl['low'].iloc[-1] < pl['low'].iloc[-2] and pl['rsi'].iloc[-1] > pl['rsi'].iloc[-2]: is_bull = True

        last, prev = df.iloc[-1], df.iloc[-2]
        trend = "Above EMA200" if last['close'] > last['ema200'] else "Below EMA200"

        # Signal Logic
        if (prev['k'] < prev['d'] and last['k'] > last['d']) and (last['k'] < 25 or (is_bull and last['k'] < 50)):
            send_telegram(f"🚀 *[SK22 LONG]*\nPrice: {last['close']}\nTrend: {trend}" + ("\n🔥 Bull Div" if is_bull else ""))
        elif (prev['k'] > prev['d'] and last['k'] < last['d']) and (last['k'] > 75 or (is_bear and last['k'] < 50)):
            send_telegram(f"🔻 *[SK22 SHORT]*\nPrice: {last['close']}\nTrend: {trend}" + ("\n🔥 Bear Div" if is_bear else ""))

        print(f"Run Finished. Status: {'Full' if HAS_TA else 'Lite Mode'}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_signal()
