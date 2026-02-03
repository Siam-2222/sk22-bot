import ccxt
import pandas as pd
import requests
import os
import numpy as np

# --- CONFIG ---
SYMBOL = 'BTC/USDT'
TIMEFRAME = '15m'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')


# ---------- Indicator Functions ----------
def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def rsi(series, length=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(length).mean()
    avg_loss = loss.rolling(length).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def stoch_rsi(close, length=14, smooth_k=3, smooth_d=3):
    rsi_val = rsi(close, length)
    min_rsi = rsi_val.rolling(length).min()
    max_rsi = rsi_val.rolling(length).max()

    stoch = (rsi_val - min_rsi) / (max_rsi - min_rsi) * 100
    k = stoch.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    return k, d


# ---------- Telegram ----------
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Missing Telegram config")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, data=payload)


# ---------- Signal Logic ----------
def check_signal():
    exchange = ccxt.binance()
    bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=500)

    df = pd.DataFrame(
        bars, columns=["time", "open", "high", "low", "close", "vol"]
    )

    # Indicators
    df["ema200"] = ema(df["close"], 200)
    df["rsi"] = rsi(df["close"], 14)
    df["k"], df["d"] = stoch_rsi(df["close"])

    # Pivot High / Low
    df["p_high"] = df["high"][
        df["high"] == df["high"].rolling(11, center=True).max()
    ]
    df["p_low"] = df["low"][
        df["low"] == df["low"].rolling(11, center=True).min()
    ]

    ph = df.dropna(subset=["p_high"]).tail(2)
    pl = df.dropna(subset=["p_low"]).tail(2)

    is_bear_div = (
        len(ph) == 2
        and ph["high"].iloc[-1] > ph["high"].iloc[-2]
        and df["rsi"].loc[ph.index[-1]] < df["rsi"].loc[ph.index[-2]]
    )

    is_bull_div = (
        len(pl) == 2
        and pl["low"].iloc[-1] < pl["low"].iloc[-2]
        and df["rsi"].loc[pl.index[-1]] > df["rsi"].loc[pl.index[-2]]
    )

    last = df.iloc[-1]
    prev = df.iloc[-2]

    long_trigger = (
        prev["k"] < prev["d"]
        and last["k"] > last["d"]
        and (last["k"] < 25 or (is_bull_div and last["k"] < 50))
        and last["rsi"] >= prev["rsi"]
    )

    short_trigger = (
        prev["k"] > prev["d"]
        and last["k"] < last["d"]
        and (last["k"] > 75 or (is_bear_div and last["k"] > 50))
        and last["rsi"] <= prev["rsi"]
    )

    trend = "📈 Above EMA200" if last["close"] > last["ema200"] else "📉 Below EMA200"

    if long_trigger:
        div = " + Bull Div" if is_bull_div else ""
        send_telegram(
            f"🚀 *[SK22 LONG]*\nPrice: {last['close']}\nTrend: {trend}{div}"
        )
        print("LONG Signal Sent")

    elif short_trigger:
        div = " + Bear Div" if is_bear_div else ""
        send_telegram(
            f"🔻 *[SK22 SHORT]*\nPrice: {last['close']}\nTrend: {trend}{div}"
        )
        print("SHORT Signal Sent")
    else:
        print(f"No Signal | K={last['k']:.2f} RSI={last['rsi']:.2f}")


if __name__ == "__main__":
    check_signal()
