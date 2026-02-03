import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import os

# --- คอนฟิก (ดึงค่าจาก GitHub Secrets) ---
SYMBOL = 'BTC/USDT'
TIMEFRAME = '15m'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, data=payload)
    except:
        pass

def check_signal():
    try:
        exchange = ccxt.binance()
        bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=500)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])

        # [1] RSI / Stoch RSI / EMA
        df['rsi'] = ta.rsi(df['close'], length=14)
        # คำนวณ Stoch RSI ตามสูตร SK 22
        stoch = ta.stochrsi(df['close'], length=14, rsi_length=14, k=3, d=3)
        df['k'] = stoch.iloc[:, 0]
        df['d'] = stoch.iloc[:, 1]
        df['ema200'] = ta.ema(df['close'], length=200)

        # [2] ระบบ Pivot High/Low (Swing Left 5, Right 5)
        window = 5
        df['p_high'] = float('nan')
        df['p_low'] = float('nan')

        for i in range(window, len(df) - window):
            if df['high'].iloc[i] == df['high'].iloc[i-window : i+window+1].max():
                df.at[i, 'p_high'] = df['high'].iloc[i]
            if df['low'].iloc[i] == df['low'].iloc[i-window : i+window+1].min():
                df.at[i, 'p_low'] = df['low'].iloc[i]

        # เช็ค Divergence
        ph_df = df.dropna(subset=['p_high']).tail(2)
        pl_df = df.dropna(subset=['p_low']).tail(2)
        is_bull_div = False
        is_bear_div = False

        if len(ph_df) >= 2:
            if ph_df['high'].iloc[-1] > ph_df['high'].iloc[-2] and ph_df['rsi'].iloc[-1] < ph_df['rsi'].iloc[-2]:
                is_bear_div = True
        if len(pl_df) >= 2:
            if pl_df['low'].iloc[-1] < pl_df['low'].iloc[-2] and pl_df['rsi'].iloc[-1] > pl_df['rsi'].iloc[-2]:
                is_bull_div = True

        # [4] เงื่อนไข LONG/SHORT
        last = df.iloc[-1]
        prev = df.iloc[-2]

        long_trigger = (prev['k'] < prev['d'] and last['k'] > last['d']) and \
                       (last['k'] < 25 or (is_bull_div and last['k'] < 50)) and \
                       (last['rsi'] >= prev['rsi'])

        short_trigger = (prev['k'] > prev['d'] and last['k'] < last['d']) and \
                        (last['k'] > 75 or (is_bear_div and last['k'] < 50)) and \
                        (last['rsi'] <= prev['rsi'])

        msg = ""
        trend = "📈 Above EMA200" if last['close'] > last['ema200'] else "📉 Below EMA200"
        
        if long_trigger:
            msg = f"🚀 *[SK22 LONG]*\n*Price:* {last['close']}\n*Trend:* {trend}" + ("\n+ Bull Div" if is_bull_div else "")
        elif short_trigger:
            msg = f"🔻 *[SK22 SHORT]*\n*Price:* {last['close']}\n*Trend:* {trend}" + ("\n+ Bear Div" if is_bear_div else "")

        if msg:
            send_telegram(msg)
            print(f"Signal Found: {msg}")
        else:
            print(f"Checked {SYMBOL}: No signal. (K: {last['k']:.2f})")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_signal()
