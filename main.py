import requests
import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Ambil dari Railway
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


def get_rsi(symbol, interval="1h"):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
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


def get_ema99(symbol, interval="1h"):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=120"
        res = requests.get(url, timeout=10)
        data = res.json()
        closes = [float(entry[4]) for entry in data]
        if len(closes) < 99:
            return None
        ema = sum(closes[-99:]) / 99  # Simple average as approximation
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


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE, interval="1h"):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("🚫 Maaf, kamu tidak diizinkan menggunakan bot ini.")
        return

    await update.message.reply_text(f"🔍 Memindai RSI + EMA99 ({interval})...")

    jemput_bola = []

    for pair in PAIRS:
        price, change, volume = get_pair_data(pair)
        rsi = get_rsi(pair, interval)
        ema = get_ema99(pair, interval)

        if None in (price, rsi, volume, ema):
            continue

        if rsi < 40:
            posisi = "🔽 Di bawah EMA99" if price < ema else "🔼 Di atas EMA99"
            jemput_bola.append({
                "pair": pair,
                "rsi": rsi,
                "price": price,
                "volume": volume,
                "posisi": posisi
            })

    if jemput_bola:
        jemput_bola = sorted(jemput_bola, key=lambda x: x["rsi"])
        pesan = f"📉 <b>Sinyal Jemput Bola RSI ({interval}):</b>\n\n"
        for item in jemput_bola:
            pesan += (
                f"🔹 <b>{item['pair']}</b>\n"
                f"• RSI: {item['rsi']} (Oversold)\n"
                f"• Harga: ${item['price']:.4f} | Vol: ${item['volume']:.2f}\n"
                f"• Posisi: {item['posisi']}\n\n"
            )
        await update.message.reply_text(pesan, parse_mode="HTML")
    else:
        await update.message.reply_text(f"✅ Tidak ada pair dengan RSI < 40 di TF {interval}.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("🚫 Maaf, kamu tidak diizinkan menggunakan bot ini.")
        return

    keyboard = [
        ["/scan_15m", "/scan_1h"],
        ["/scan_4h", "/scan_1d"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "👋 Selamat datang!\nSilakan pilih time frame untuk sinyal Jemput Bola RSI:",
        reply_markup=reply_markup
    )

# Handler TF
async def scan_15m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await scan(update, context, interval="15m")

async def scan_1h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await scan(update, context, interval="1h")

async def scan_4h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await scan(update, context, interval="4h")

async def scan_1d(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await scan(update, context, interval="1d")

# Main App
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan_15m", scan_15m))
    app.add_handler(CommandHandler("scan_1h", scan_1h))
    app.add_handler(CommandHandler("scan_4h", scan_4h))
    app.add_handler(CommandHandler("scan_1d", scan_1d))
    print("🚀 Bot Telegram siap menerima perintah /start /scan_1h /scan_4h dst")
    app.run_polling()

if __name__ == "__main__":
    main()
