import requests
import os
import numpy as np
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

PAIRS = [
    "SEIUSDT", "RAYUSDT", "PENDLEUSDT", "JUPUSDT", "ENAUSDT",
    "CRVUSDT", "ENSUSDT", "FORMUSDT", "TAOUSDT", "ALGOUSDT",
    "XTZUSDT", "CAKEUSDT", "HBARUSDT", "NEXOUSDT", "GALAUSDT",
    "IOTAUSDT", "THETAUSDT", "CFXUSDT", "WIFUSDT", "BTCUSDT",
    "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "AAVEUSDT", "ATOMUSDT",
    "INJUSDT", "QNTUSDT", "ARBUSDT", "NEARUSDT", "SUIUSDT",
    "LDOUSDT", "WLDUSDT", "FETUSDT", "GRTUSDT",
    "PYTHUSDT", "ASRUSDT", "HYPERUSDT", "TRXUSDT"
]

def get_rsi(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}USDT&interval=1h&limit=100"
        response = requests.get(url, timeout=10)
        data = response.json()
        closes = [float(entry[4]) for entry in data]
        deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
        gains = [delta if delta > 0 else 0 for delta in deltas]
        losses = [-delta if delta < 0 else 0 for delta in deltas]
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)
    except:
        return None

def get_ema99(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=100"
        res = requests.get(url, timeout=10)
        data = res.json()
        closes = [float(entry[4]) for entry in data]
        if len(closes) < 99:
            return None
        weights = np.exp(np.linspace(-1., 0., 99))
        weights /= weights.sum()
        ema = np.convolve(closes, weights, mode='valid')[-1]
        return round(ema, 4)
    except:
        return None

def get_pair_data(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        res = requests.get(url, timeout=10)
        data = res.json()
        price = float(data['lastPrice'])
        change = float(data['priceChangePercent'])
        volume = float(data['quoteVolume'])
        return price, change, volume
    except:
        return None, None, None

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("🚫 Maaf, kamu tidak diizinkan menggunakan bot ini.")
        return

    await update.message.reply_text("🔍 Memindai data semua pair, tunggu sebentar...")

    jemput_bola = []

    for pair in PAIRS:
        symbol = pair.replace("USDT", "")
        price, change, volume = get_pair_data(pair)
        rsi = get_rsi(symbol)
        ema99 = get_ema99(pair)

        if None in (price, rsi, volume, ema99):
            continue

        if rsi < 40:
            posisi = "🔽 Di bawah EMA99" if price < ema99 else "🔼 Di atas EMA99"
            jemput_bola.append({
                "pair": pair,
                "rsi": rsi,
                "price": price,
                "volume": volume,
                "posisi": posisi
            })

    if jemput_bola:
        jemput_bola = sorted(jemput_bola, key=lambda x: x["rsi"])
        pesan = "📉 <b>Sinyal Jemput Bola:</b>\n\n"
        for item in jemput_bola:
            pesan += (
                f"🔹 <b>{item['pair']}</b> (Jemput Bola)\n"
                f"• RSI: {item['rsi']} (Oversold)\n"
                f"• Harga: ${item['price']:.3f} | Vol: ${item['volume']:.2f}\n"
                f"• Posisi: {item['posisi']}\n\n"
            )
        await update.message.reply_text(pesan, parse_mode="HTML")
    else:
        await update.message.reply_text("✅ Tidak ada pair dengan RSI < 40 saat ini.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("scan", scan))
    print("🚀 Bot Telegram siap menerima perintah /scan")
    app.run_polling()

if __name__ == "__main__":
    main()
