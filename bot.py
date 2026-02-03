import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import os

# --- คอนฟิก (ไม่ต้องใส่เลขตรงนี้ ให้ไปใส่ใน GitHub Secrets) ---
SYMBOL = 'BTC/USDT'
TIMEFRAME = '1h'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

def send_telegram(msg):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
    requests.post(url, data=payload)

def check_signal():
    try:
        exchange = ccxt.binance()
        # ดึงข้อมูล 500 แท่งเพื่อให้คำนวณ EMA200 และ Pivot ได้แม่นยำ
        bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=500)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])

        # [1] คำนวณ RSI / Stoch RSI / EMA
        df['rsi'] = ta.rsi(df['close'], length=14)
        stoch_rsi = ta.stochrsi(df['close'], length=14, rsi_length=14, k=3, d=3)
        df['k'] = stoch_rsi['STOCHRSIk_14_14_3_3']
        df['d'] = stoch_rsi['STOCHRSId_14_14_3_3']
        df['ema200'] = ta.ema(df['close'], length=200)

        # [2] จำลอง Pivot High/Low (Swing Left 5, Right 5)
        # หาจุดสูงสุด/ต่ำสุดในระยะ 11 แท่ง (5-1-5)
        df['p_high'] = df['high'][(df['high'] == df['high'].rolling(11, center=True).max())]
        df['p_low'] = df['low'][(df['low'] == df['low'].rolling(11, center=True).min())]

        # ดึงค่า Pivot ล่าสุด 2 จุดมาเช็ค Divergence
        ph_points = df.dropna(subset=['p_high']).tail(2)
        pl_points = df.dropna(subset=['p_low']).tail(2)

        is_bull_div = False
        is_bear_div = False

        if len(ph_points) == 2:
            # Bear Div: ราคาสูงขึ้น แต่ RSI ต่ำลง
            if ph_points['high'].iloc[-1] > ph_points['high'].iloc[-2] and \
               df['rsi'].loc[ph_points.index[-1]] < df['rsi'].loc[ph_points.index[-2]]:
                is_bear_div = True

        if len(pl_points) == 2:
            # Bull Div: ราคาต่ำลง แต่ RSI สูงขึ้น
            if pl_points['low'].iloc[-1] < pl_points['low'].iloc[-2] and \
               df['rsi'].loc[pl_points.index[-1]] > df['rsi'].loc[pl_points.index[-2]]:
                is_bull_div = True

        # [4] เงื่อนไข LONG/SHORT
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # ค้นหาจุดตัด (Crossover/Crossunder)
        long_trigger = (prev['k'] < prev['d'] and last['k'] > last['d']) and \
                       (last['k'] < 25 or (is_bull_div and last['k'] < 50)) and \
                       (last['rsi'] >= prev['rsi'])

        short_trigger = (prev['k'] > prev['d'] and last['k'] < last['d']) and \
                        (last['k'] > 75 or (is_bear_div and last['k'] < 50)) and \
                        (last['rsi'] <= prev['rsi'])

        # ส่งข้อความ
        msg = ""
        trend = "📈 Above EMA200" if last['close'] > last['ema200'] else "📉 Below EMA200"
        
        if long_trigger:
            div_text = " + Bull Div" if is_bull_div else ""
            msg = f"🚀 *[SK22 LONG]*\n*Price:* {last['close']}\n*Trend:* {trend}{div_text}"
        elif short_trigger:
            div_text = " + Bear Div" if is_bear_div else ""
            msg = f"🔻 *[SK22 SHORT]*\n*Price:* {last['close']}\n*Trend:* {trend}{div_text}"

        if msg:
            send_telegram(msg)
            print("Signal Sent!")
        else:
            print(f"Checking {SYMBOL}... No Signal")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_signal()
