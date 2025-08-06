import os
import requests
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

PAIRS = [
    "SEIUSDT", "RAYUSDT", "PENDLEUSDT", "JUPUSDT", "ENAUSDT", "CRVUSDT", "ENSUSDT",
    "FORMUSDT", "TAOUSDT", "ALGOUSDT", "XTZUSDT", "CAKEUSDT", "HBARUSDT", "NEXOUSDT",
    "GALAUSDT", "IOTAUSDT", "THETAUSDT", "CFXUSDT", "WIFUSDT", "BTCUSDT", "ETHUSDT",
    "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT",
    "AAVEUSDT", "ATOMUSDT", "INJUSDT", "QNTUSDT", "ARBUSDT", "NEARUSDT", "SUIUSDT",
    "LDOUSDT", "WLDUSDT", "FETUSDT", "GRTUSDT", "PYTHUSDT", "ASRUSDT", "HYPERUSDT",
    "TRXUSDT"
]

STRATEGIES = {
    "🔴 Jemput Bola": {"rsi_limit": 40, "volume_min": 2_000_000},
    "🟡 Rebound Swing": {"rsi_limit": 50, "volume_min": 3_000_000},
    "🟢 Scalping Breakout": {"rsi_limit": 60, "volume_min": 5_000_000}
}

TF_INTERVALS = {
    "TF15": "15m",
    "TF1h": "1h",
    "TF4h": "4h",
    "TF1d": "1d"
}

def get_price(symbol: str) -> float:
    try:
        res = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=10)
        return float(res.json()["price"])
    except:
        return -1

def get_volume(symbol: str) -> float:
    try:
        res = requests.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}", timeout=10)
        return float(res.json()["quoteVolume"])
    except:
        return 0

def get_indicators(symbol: str, interval: str):
    try:
        res = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=100", timeout=10)
        data = res.json()
        closes = [float(k[4]) for k in data]
        highs = [float(k[2]) for k in data]
        lows = [float(k[3]) for k in data]

        if len(closes) < 100:
            return -1, -1, -1, -1, -1

        # RSI(6)
        rsi_len = 6
        deltas = [closes[i+1] - closes[i] for i in range(-rsi_len-1, -1)]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains) / rsi_len
        avg_loss = sum(losses) / rsi_len
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi = round(100 - (100 / (1 + rs)), 2)

        # EMA
        ema7 = sum(closes[-7:]) / 7
        ema25 = sum(closes[-25:]) / 25
        ema99 = sum(closes[-99:]) / 99

        # ATR(14)
        tr = [highs[i] - lows[i] for i in range(-14, 0)]
        atr = sum(tr) / 14

        return rsi, round(ema7, 4), round(ema25, 4), round(ema99, 4), round(atr, 4)
    except:
        return -1, -1, -1, -1, -1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
   keyboard = [["#️⃣ Trading Spot"], ["*️⃣ Info"], ["*️⃣ Help"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("📌 Pilih Strategi Multi-TF:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "#️⃣ Trading Spot":
        keyboard = [
            ["🔴 Jemput Bola"], ["🟡 Rebound Swing"], ["🟢 Scalping Breakout"],
            ["🔙 Kembali ke Menu Utama"]
        ]
        await update.message.reply_text("📊 Pilih Mode Strategi:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    elif text == "*️⃣ Info":
        msg = (
            "Klik Tombol Trading Spot, maka BOT otomatis menganalisa dan memberikan signal untuk koin yang memiliki potensi layak entry\n\n"
            "setiap mode strategi memiliki gaya Trading berbeda sehingga sesuaikan kebutuhan anda\n\n"
            "🔴 Jemput Bola\nToken oversold. ✅ Strategi akumulasi saat koreksi dalam.\n\n"
            "🟡 Rebound Swing\nMomentum reversal ringan. ✅ Untuk rotasi swing harian.\n\n"
            "🟢 Scalping Breakout\nTangkap awal breakout. ✅ Scalping cepat volume tinggi."
             "Disclaimer. BOT ini bukan penasehat keuangan, gunakan secara bijak dan tentu nya tetap DYOR"\n\n"
        )
        await update.message.reply_text(msg)
        return

    elif text == "*️⃣ Help":
        msg = (
            "Bot scan harga crypto spot Binance real-time.\n"
            "Cocok untuk trader berbasis strategi EMA & RSI.\n\n"
            "Hubungi @KikioOreo untuk aktivasi akses penuh."
        )
        await update.message.reply_text(msg)
        return

    elif text == "🔙 Kembali ke Menu Utama":
        return await start(update, context)

    elif text in STRATEGIES:
        if user_id not in ALLOWED_USERS:
            await update.message.reply_text("⛔ Akses ditolak. Silakan hubungi admin. klik Tombol Help untuk Bantuan")
            return

        await update.message.reply_text(f"🔍 Memindai sinyal untuk *{text}*...\nTunggu beberapa detik...", parse_mode="Markdown")
        strategy = STRATEGIES[text]
        results = []

        for pair in PAIRS:
            price = get_price(pair)
            volume = get_volume(pair)
            if price == -1 or volume < strategy["volume_min"]:
                continue

            valid_tfs = []
            tf_data = {}

            for tf_label, tf_interval in TF_INTERVALS.items():
                rsi, ema7, ema25, ema99, atr = get_indicators(pair, tf_interval)
                if -1 in (rsi, ema7, ema25, ema99, atr):
                    continue

                is_valid = False
                if text == "🔴 Jemput Bola":
                    is_valid = price < ema25 and price > 0.9 * ema99 and rsi < 40
                elif text == "🟡 Rebound Swing":
                    is_valid = price < ema25 and price > ema7 and rsi < 50
                elif text == "🟢 Scalping Breakout":
                    is_valid = price > ema7 and price > ema25 and price > ema99 and rsi >= 60

                if is_valid:
                    valid_tfs.append(tf_label)
                    tf_data[tf_label] = (rsi, ema7, ema25, ema99, atr)

            if len(valid_tfs) >= 3:
                tf_main = valid_tfs[0]
                rsi_val, ema7_val, ema25_val, ema99_val, atr = tf_data[tf_main]
                tp1 = round(price + atr * 1.0, 4)
                tp2 = round(price + atr * 1.8, 4)
                warning = ""
                if price < 0.985 * ema25 and price < 0.97 * ema7:
                    warning = "\n⚠️ *Waspada! Support patah*"

                msg = (
                    f"{text} Mode • {tf_main}\n\n"
                    f"✅ {pair}\n"
                    f"Harga: ${price:.3f}\n"
                    f"EMA7: ${ema7_val:.3f} | EMA25: ${ema25_val:.3f} | EMA99: ${ema99_val:.3f}\n"
                    f"RSI(6): {rsi_val} | ATR(14): {atr}\n"
                    f"📈 Volume: ${volume:,.0f}\n\n"
                    f"🎯 Entry: ${price:.3f}\n"
                    f"🎯 TP1: ${tp1}\n"
                    f"🎯 TP2: ${tp2}\n\n"
                    f"Note: Valid di {', '.join(valid_tfs)} {'✔️'*len(valid_tfs)}{warning}"
                )
                results.append(msg)

        if results:
            for msg in results:
                await update.message.reply_text(msg, parse_mode="Markdown")
                await asyncio.sleep(0.5)
            await update.message.reply_text("✅ *Selesai scan. Semua sinyal layak sudah ditampilkan.*", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Tidak ada sinyal strategi yang layak saat ini.")
        return

    else:
        await update.message.reply_text("⛔ Perintah tidak dikenali.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
