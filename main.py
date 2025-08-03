# main.py

import requests
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Ambil token dari environment (Railway)
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Daftar pair
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

# Ambil data RSI dari Binance (interval 1h)
def get_rsi(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1h&limit=100"
        response = requests.get(url)
        data = response.json()

        # Ambil harga penutupan
        closes = [float(entry[4]) for entry in data]

        # Hitung RSI 14 secara manual
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

# Ambil data harga, volume, dll
def get_pair_data(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        res = requests.get(url)
        data = res.json()
        price = float(data['lastPrice'])
        change = float(data['priceChangePercent'])
        volume = float(data['quoteVolume'])
        return price, change, volume
    except:
        return None, None, None

# Handler perintah /scan
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Memindai data semua pair, tunggu sebentar...")

    jemput_bola = []
    laporan_lengkap = []

    for pair in PAIRS:
        price, change, volume = get_pair_data(pair)
        rsi = get_rsi(pair.replace("USDT", ""))
        if price is None or rsi is None:
            continue

        baris = f"{pair}: ${price:.4f} | 24h: {change:.2f}% | Vol: {volume/1_000_000:.2f}M | RSI: {rsi}"
        laporan_lengkap.append(baris)

        if rsi < 40:
            jemput_bola.append("🟡 " + baris)

    if laporan_lengkap:
        await update.message.reply_text("📊 **Laporan Lengkap**\n\n" + "\n".join(laporan_lengkap[:40]))
        if len(laporan_lengkap) > 40:
            await update.message.reply_text("\n".join(laporan_lengkap[40:]))

    if jemput_bola:
        await update.message.reply_text("📉 **Sinyal Jemput Bola (RSI < 40):**\n\n" + "\n".join(jemput_bola))
    else:
        await update.message.reply_text("✅ Tidak ada pair dengan RSI < 40 saat ini.")

# Fungsi utama
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("scan", scan))
    print("🚀 Bot Telegram siap menerima perintah /scan")
    app.run_polling()

if __name__ == "__main__":
    main()
