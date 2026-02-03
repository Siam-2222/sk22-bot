import os
import ccxt
import pandas as pd
import numpy as np
import requests

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

def calculate_indicators(df):
    # 1. RSI Calculation (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # 2. Stochastic RSI (14, 3, 3)
    rsi_min = df['rsi'].rolling(window=14).min()
    rsi_max = df['rsi'].rolling(window=14).max()
    stoch_rsi = 100 * (df['rsi'] - rsi_min) / (rsi_max - rsi_min)
    df['k'] = stoch_rsi.rolling(window=3).mean()
    df['d'] = df['k'].rolling(window=3).mean()

    # 3. EMA 200
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    return df

def check_signal():
    try:
        exchange = ccxt.binance()
        bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=400)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
        
        df = calculate_indicators(df)

        # Pivot Points (Swing Left/Right 5)
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
        trend = "📈 Above EMA200" if last['close'] > last['ema200'] else "📉 Below EMA200"

        # Signal Logic (SK 22)
        # LONG: CrossOver(K,D) & (K < 25 or (BullDiv & K < 50)) & RSI Up
        long_trigger = (prev['k'] < prev['d'] and last['k'] > last['d']) and \
                       (last['k'] < 25 or (is_bull and last['k'] < 50)) and \
                       (last['rsi'] >= prev['rsi'])

        # SHORT: CrossUnder(K,D) & (K > 75 or (BearDiv & K < 50)) & RSI Down
        short_trigger = (prev['k'] > prev['d'] and last['k'] < last['d']) and \
                        (last['k'] > 75 or (is_bear and last['k'] > 50)) and \
                        (last['rsi'] <= prev['rsi'])

        if long_trigger:
            msg = f"🚀 *[SK22 LONG]*\n*Price:* {last['close']}\n*Trend:* {trend}" + ("\n🔥 *+ Bull Div*" if is_bull else "")
            send_telegram(msg)
        elif short_trigger:
            msg = f"🔻 *[SK22 SHORT]*\n*Price:* {last['close']}\n*Trend:* {trend}" + ("\n🔥 *+ Bear Div*" if is_bear else "")
            send_telegram(msg)

        print(f"Bot Checked {SYMBOL}: K={last['k']:.2f}, RSI={last['rsi']:.2f}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_signal()
