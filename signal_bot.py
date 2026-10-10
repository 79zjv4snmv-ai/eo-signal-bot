import requests
import pandas as pd
import numpy as np
from telegram import Bot
from telegram.constants import ParseMode
import asyncio
from datetime import datetime

# ========== المفاتيح والإعدادات ==========
TELEGRAM_BOT_TOKEN = "8963611921:AAH0qsCoHPjpAf6sqpmkrfQ5bwLbdk6oAzo"
TELEGRAM_CHAT_ID = "373404939"
TWELVE_DATA_API_KEY = "4b8d4e01d3ec4c219f918fbdf849c35e"

SYMBOL = "EUR/USD"
TIMEFRAME = "1h"

# ========== جلب البيانات ==========
def fetch_data(symbol=SYMBOL, interval=TIMEFRAME, outputsize=100):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON"
    }
    r = requests.get(url, params=params, timeout=15)
    data = r.json()
    if "values" not in data:
        raise Exception(f"خطأ في جلب البيانات: {data}")
    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    return df

# ========== حساب المؤشرات ==========
def calculate_indicators(df):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=13, min_periods=14).mean()
    avg_loss = loss.ewm(com=13, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["Signal_Line"] = df["MACD"].ewm(span=9, adjust=False).mean()

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()
    return df

# ========== توليد الإشارة ==========
def generate_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    rsi = last["RSI"]
    macd = last["MACD"]
    signal_line = last["Signal_Line"]
    prev_macd = prev["MACD"]
    prev_signal = prev["Signal_Line"]
    price = last["close"]
    atr = last["ATR"]

    cross_up = prev_macd <= prev_signal and macd > signal_line
    cross_down = prev_macd >= prev_signal and macd < signal_line

    if cross_up and rsi > 30:
        sl = price - (atr * 1.5)
        tp = price + (atr * 3.0)
        return {
            "type": "BUY",
            "price": price,
            "sl": sl,
            "tp": tp,
            "rsi": rsi,
            "macd": macd,
            "reason": f"تقاطع MACD صاعد + RSI = {rsi:.1f}"
        }
    elif cross_down and rsi < 70:
        sl = price + (atr * 1.5)
        tp = price - (atr * 3.0)
        return {
            "type": "SELL",
            "price": price,
            "sl": sl,
            "tp": tp,
            "rsi": rsi,
            "macd": macd,
            "reason": f"تقاطع MACD هابط + RSI = {rsi:.1f}"
        }
    return None

# ========== إرسال الإشارة ==========
async def send_signal(signal, symbol):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    emoji = "🟢" if signal["type"] == "BUY" else "🔴"
    action = "شراء" if signal["type"] == "BUY" else "بيع"

    message = (
        f"{emoji} *إشارة {action}* — {symbol}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *السعر:* `{signal['price']:.5f}`\n"
        f"🛑 *وقف الخسارة:* `{signal['sl']:.5f}`\n"
        f"🎯 *الهدف:* `{signal['tp']:.5f}`\n"
        f"📊 *RSI:* `{signal['rsi']:.1f}`\n"
        f"📈 *MACD:* `{signal['macd']:.6f}`\n"
        f"📝 *السبب:* {signal['reason']}\n"
        f"⏰ *الوقت:* {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ _نفّذ الصفقة يدوياً على EO Broker_"
    )
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)

# ========== التشغيل الرئيسي ==========
async def main():
    print(f"🔍 فحص {SYMBOL} على إطار {TIMEFRAME}...")
    try:
        df = fetch_data()
        df = calculate_indicators(df)
        signal = generate_signal(df)

        if signal:
            print(f"✅ تم توليد إشارة: {signal['type']}")
            await send_signal(signal, SYMBOL)
        else:
            print("⏳ لا توجد إشارة حالية.")
    except Exception as e:
        print(f"❌ خطأ: {e}")

if __name__ == "__main__":
    asyncio.run(main())
