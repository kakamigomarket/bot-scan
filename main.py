import requests
import os
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

def get_rsi(symbol, interval="1h"):
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}USDT&interval={interval}&limit=100"
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

    await update.message.reply_text(f"🔍 Memindai RSI ({interval})...")

    jemput_bola = []

    for pair in PAIRS:
        symbol = pair.replace("USDT", "")
        price, change, volume = get_pair_data(pair)
        rsi = get_rsi(symbol, interval)

        if None in (price, rsi, volume):
            continue

        if rsi < 40:
            jemput_bola.append({
                "pair": pair,
                "rsi": rsi,
                "price": price,
                "volume": volume
            })

    if jemput_bola:
        jemput_bola = sorted(jemput_bola, key=lambda x: x["rsi"])
        pesan = f"📉 <b>Sinyal Jemput Bola RSI ({interval}):</b>\n\n"
        for item in jemput_bola:
            pesan += (
                f"🔹 <b>{item['pair']}</b>\n"
                f"• RSI: {item['rsi']}\n"
                f"• Harga: ${item['price']:.3f} | Vol: ${item['volume']:.2f}\n\n"
            )
        await update.message.reply_text(pesan, parse_mode="HTML")
    else:
        await update.message.reply_text(f"✅ Tidak ada pair dengan RSI < 40 di TF {interval}.")

# Handler untuk tiap TF
async def scan_15m(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await scan(update, context, interval="15m")

async def scan_1h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await scan(update, context, interval="1h")

async def scan_4h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await scan(update, context, interval="4h")

async def scan_1d(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await scan(update, context, interval="1d")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("scan_15m", scan_15m))
    app.add_handler(CommandHandler("scan_1h", scan_1h))
    app.add_handler(CommandHandler("scan_4h", scan_4h))
    app.add_handler(CommandHandler("scan_1d", scan_1d))
    print("🚀 Bot Telegram siap menerima perintah /scan_15m /scan_1h /scan_4h /scan_1d")
    app.run_polling()

if __name__ == "__main__":
    main()
