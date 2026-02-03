import os
import ccxt
import pandas as pd
import pandas_ta as ta
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
    except:
        pass

def check_signal():
    try:
        exchange = ccxt.binance()
        bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=500)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])

        # Indicators
        df['rsi'] = ta.rsi(df['close'], length=14)
        stoch = ta.stochrsi(df['close'], length=14, rsi_length=14, k=3, d=3)
        df['k'], df['d'] = stoch.iloc[:, 0], stoch.iloc[:, 1]
        df['ema200'] = ta.ema(df['close'], length=200)

        # Pivot Points (Swing 5)
        window = 5
        df['p_high'] = df['high'].iloc[window:-window].where((df['high'] == df['high'].rolling(window*2+1, center=True).max()))
        df['p_low'] = df['low'].iloc[window:-window].where((df['low'] == df['low'].rolling(window*2+1, center=True).min()))

        # Divergence logic (Fixed)
        ph = df.dropna(subset=['p_high']).tail(2)
        pl = df.dropna(subset=['p_low']).tail(2)
        is_bull_div, is_bear_div = False, False

        if len(ph) >= 2:
            if ph['high'].iloc[-1] > ph['high'].iloc[-2] and ph['rsi'].iloc[-1] < ph['rsi'].iloc[-2]:
                is_bear_div = True
        if len(pl) >= 2:
            if pl['low'].iloc[-1] < pl['low'].iloc[-2] and pl['rsi'].iloc[-1] > pl['rsi'].iloc[-2]:
                is_bull_div = True

        last, prev = df.iloc[-1], df.iloc[-2]
        cross_over = prev['k'] < prev['d'] and last['k'] > last['d']
        cross_under = prev['k'] > prev['d'] and last['k'] < last['d']

        # Entry Conditions
        long_trigger = cross_over and (last['k'] < 25 or (is_bull_div and last['k'] < 50)) and (last['rsi'] >= prev['rsi'])
        short_trigger = cross_under and (last['k'] > 75 or (is_bear_div and last['k'] < 50)) and (last['rsi'] <= prev['rsi'])

        if long_trigger:
            send_telegram(f"🚀 *[SK22 LONG]*\n*Price:* {last['close']}\n*Trend:* {'📈 Above EMA200' if last['close'] > last['ema200'] else '📉 Below EMA200'}" + ("\n🔥 + Bull Div" if is_bull_div else ""))
        elif short_trigger:
            send_telegram(f"🔻 *[SK22 SHORT]*\n*Price:* {last['close']}\n*Trend:* {'📈 Above EMA200' if last['close'] > last['ema200'] else '📉 Below EMA200'}" + ("\n🔥 + Bear Div" if is_bear_div else ""))
        
        print(f"Bot Ran Successfully: K={last['k']:.2f}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_signal()
