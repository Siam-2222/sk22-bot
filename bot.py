import os
import ccxt
import pandas as pd
import pandas_ta as ta
import requests

# --- Config ---
SYMBOL = 'BTC/USDT'
TIMEFRAME = '15m'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
        requests.post(url, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'})
    except Exception as e:
        print(f"Telegram Error: {e}")

def check_signal():
    try:
        exchange = ccxt.binance()
        # ดึงข้อมูลเผื่อไว้ 500 แท่งเพื่อคำนวณ EMA200 และ Pivot
        bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=500)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])

        # [1] คำนวณ RSI และ Stochastic RSI (ตามสูตร Pine Script)
        df['rsi'] = ta.rsi(df['close'], length=14)
        stoch_df = ta.stochrsi(df['close'], length=14, rsi_length=14, k=3, d=3)
        df['k'] = stoch_df.iloc[:, 0]
        df['d'] = stoch_df.iloc[:, 1]
        df['ema200'] = ta.ema(df['close'], length=200)

        # [2] ระบบ Pivot High/Low (Swing Left 5, Right 5)
        # หมายเหตุ: Pivot จะคอนเฟิร์มช้าไป 5 แท่ง (swing_right)
        window = 5
        df['p_high'] = df['high'].iloc[window:-window].where(
            (df['high'] == df['high'].rolling(window*2+1, center=True).max())
        )
        df['p_low'] = df['low'].iloc[window:-window].where(
            (df['low'] == df['low'].rolling(window*2+1, center=True).min())
        )

        # [3] คำนวณ Divergence (เทียบ Pivot 2 จุดล่าสุด)
        ph_idx = df.dropna(subset=['p_high']).index
        pl_idx = df.dropna(subset=['p_low']).index
        
        is_bull_div = False
        is_bear_div = False

        if len(ph_idx) >= 2:
            # Bearish Div: Price Higher High แต่ RSI Lower High
            if df['high'].loc[ph_idx[-1]] > df['high'].loc[ph_idx[-2]] and \
               df['rsi'].loc[ph_idx[-1]] < df['rsi'].loc[ph_idx[-2]]:
                is_bear_div = True
                
        if len(pl_idx) >= 2:
            # Bullish Div: Price Lower Low แต่ RSI Higher Low
            if df['low'].loc[pl_idx[-1]] < df['low'].loc[pl_idx[-2]] and \
               df['rsi'].loc[pl_idx[-1]] > df['rsi'].loc[pl_idx[-2]]:
                is_bull_div = True

        # [4] เงื่อนไขการส่งสัญญาณ (อิงตาม Pine Script ล่าสุด)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # ค้นหาจุดตัด (Crossover / Crossunder)
        cross_over = prev['k'] < prev['d'] and last['k'] > last['d']
        cross_under = prev['k'] > prev['d'] and last['k'] < last['d']

        long_trigger = cross_over and (last['k'] < 25 or (is_bull_div and last['k'] < 50)) and (last['rsi'] >= prev['rsi'])
        short_trigger = cross_under and (last['k'] > 75 or (is_bear_div and last['k'] > 50)) and (last['rsi'] <= prev['rsi'])

        # [5] การแจ้งเตือน
        trend = "📈 Above EMA200" if last['close'] > last['ema200'] else "📉 Below EMA200"
        if long_trigger:
            msg = f"🚀 *[SK22 LONG]*\n*Symbol:* {SYMBOL}\n*Price:* {last['close']}\n*Trend:* {trend}"
            if is_bull_div: msg += "\n🔥 *+ Bullish Divergence*"
            send_telegram(msg)
            print("Signal Found: LONG")
            
        elif short_trigger:
            msg = f"🔻 *[SK22 SHORT]*\n*Symbol:* {SYMBOL}\n*Price:* {last['close']}\n*Trend:* {trend}"
            if is_bear_div: msg += "\n🔥 *+ Bearish Divergence*"
            send_telegram(msg)
            print("Signal Found: SHORT")
        else:
            print(f"Checked {SYMBOL}: No Signal (K:{last['k']:.2f}, RSI:{last['rsi']:.2f})")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_signal()
