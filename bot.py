import os
import ccxt
import pandas as pd
import numpy as np
import requests
import time

# [1] รายชื่อเหรียญที่ต้องการเฝ้าดู
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'HYPE/USDT']
TIMEFRAME = '15m'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
        requests.post(url, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'})
    except: pass

def calculate_indicators(df):
    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # Stochastic RSI (14, 3, 3)
    rsi_min = df['rsi'].rolling(window=14).min()
    rsi_max = df['rsi'].rolling(window=14).max()
    stoch_rsi = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min)
    df['k'] = stoch_rsi.rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()

    # EMA 200
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    return df

def check_signal():
    # เปลี่ยนเป็น OKX เพื่อเลี่ยงการบล็อก IP จาก GitHub
    exchange = ccxt.okx()
    print(f"--- Bot Starting Scan: {len(SYMBOLS)} Coins ---")
    
    for symbol in SYMBOLS:
        try:
            # ดึงข้อมูลจาก OKX (Timeframe 15m)
            bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=400)
            df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
            df = calculate_indicators(df)

            # Divergence Logic (Swing 5)
            w = 5
            df['p_high'] = df['high'].iloc[w:-w].where((df['high'] == df['high'].rolling(w*2+1, center=True).max()))
            df['p_low'] = df['low'].iloc[w:-w].where((df['low'] == df['low'].rolling(w*2+1, center=True).min()))

            ph = df.dropna(subset=['p_high']).tail(2)
            pl = df.dropna(subset=['p_low']).tail(2)
            is_bull, is_bear = False, False
            if len(ph) >= 2 and ph['high'].iloc[-1] > ph['high'].iloc[-2] and ph['rsi'].iloc[-1] < ph['rsi'].iloc[-2]: is_bear = True
            if len(pl) >= 2 and pl['low'].iloc[-1] < pl['low'].iloc[-2] and pl['rsi'].iloc[-1] > pl['rsi'].iloc[-2]: is_bull = True

            last, prev = df.iloc[-1], df.iloc[-2]
            trend = "📈 Above EMA200" if last['close'] > last['ema200'] else "📉 Below EMA200"

            # [SK 22 Logic]
            long_trigger = (prev['k'] < prev['d'] and last['k'] > last['d']) and \
                           (last['k'] < 25 or (is_bull and last['k'] < 50)) and \
                           (last['rsi'] >= prev['rsi'])

            short_trigger = (prev['k'] > prev['d'] and last['k'] < last['d']) and \
                            (last['k'] > 75 or (is_bear and last['k'] > 50)) and \
                            (last['rsi'] <= prev['rsi'])

            if long_trigger:
                msg = f"🚀 *[SK22 LONG]*\n*Coin:* {symbol}\n*Price:* {last['close']}\n*Trend:* {trend}" + ("\n🔥 *+ Bull Div*" if is_bull else "")
                send_telegram(msg)
            elif short_trigger:
                msg = f"🔻 *[SK22 SHORT]*\n*Coin:* {symbol}\n*Price:* {last['close']}\n*Trend:* {trend}" + ("\n🔥 *+ Bear Div*" if is_bear else "")
                send_telegram(msg)

            print(f"Checked {symbol}: K={last['k']:.2f}, RSI={last['rsi']:.2f}")
            time.sleep(1) 

        except Exception as e:
            print(f"Error checking {symbol}: {e}")

if __name__ == "__main__":
    check_signal()
