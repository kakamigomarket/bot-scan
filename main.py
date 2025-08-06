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
    "🔴 Jemput Bola": {"label": "Jemput Bola", "tp1_pct": 7, "tp2_pct": 12, "rsi_limit": 40, "volume_min": 2_000_000},
    "🟡 Rebound Swing": {"label": "Rebound Swing", "tp1_pct": 5, "tp2_pct": 9, "rsi_limit": 50, "volume_min": 3_000_000},
    "🟢 Scalping Breakout": {"label": "Scalping Breakout", "tp1_pct": 3, "tp2_pct": 6, "rsi_limit": 60, "volume_min": 5_000_000}
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

def get_indicators(symbol: str, interval: str) -> tuple:
    try:
        res = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=100", timeout=10)
        data = res.json()
        closes = [float(k[4]) for k in data]
        if len(closes) < 100:
            return -1, -1, -1, -1

        rsi_length = 6
        deltas = [closes[i+1] - closes[i] for i in range(-rsi_length-1, -1)]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains) / rsi_length
        avg_loss = sum(losses) / rsi_length
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi = round(100 - (100 / (1 + rs)), 2)

        ema7 = sum(closes[-7:]) / 7
        ema25 = sum(closes[-25:]) / 25
        ema99 = sum(closes[-99:]) / 99

        return rsi, round(ema7, 4), round(ema25, 4), round(ema99, 4)
    except:
        return -1, -1, -1, -1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["1️⃣ Trading Spot"], ["2️⃣ Info"], ["3️⃣ Help"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("📌 Pilih Strategi Multi-TF:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "1️⃣ Trading Spot":
        keyboard = [
            ["🔴 Jemput Bola"],
            ["🟡 Rebound Swing"],
            ["🟢 Scalping Breakout"],
            ["🔙 Kembali ke Menu Utama"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("📊 Pilih Mode Strategi Trading Spot:", reply_markup=reply_markup)
        return

    elif text == "2️⃣ Info":
        msg = (
            "🔴 Jemput Bola\nFokus pada token oversold. ✅ Untuk strategi akumulasi cepat saat koreksi dalam.\n\n"
            "🟡 Rebound Swing\nIdeal untuk momentum reversal ringan. ✅ Untuk strategi rotasi swing harian.\n\n"
            "🟢 Scalping Breakout\nCocok menangkap awal breakout. ✅ Untuk scalping cepat berbasis volume & momentum."
        )
        await update.message.reply_text(msg)
        return

    elif text == "3️⃣ Help":
        msg = (
            "Bot ini membantu scan harga crypto spot Binance secara real-time.\n"
            "Dirancang untuk trader yang ingin cuan efisien.\n\n"
            "Aktivasi bot hubungi @KikioOreo"
        )
        await update.message.reply_text(msg)
        return

    elif text == "🔙 Kembali ke Menu Utama":
        return await start(update, context)

    elif text in STRATEGIES:
        if user_id not in ALLOWED_USERS:
            await update.message.reply_text("⛔ Akses ditolak. Silakan hubungi admin.")
            return

        strategy = STRATEGIES[text]
        await update.message.reply_text(f"🔍 Memindai sinyal untuk *{text}*...\nTunggu beberapa detik...", parse_mode="Markdown")

        results = []
        for pair in PAIRS:
            price = get_price(pair)
            volume = get_volume(pair)
            if price == -1 or volume < strategy["volume_min"]:
                continue

            valid_tfs = []
            indicator_cache = {}

            for tf_label, tf_interval in TF_INTERVALS.items():
                rsi, ema7, ema25, ema99 = get_indicators(pair, tf_interval)
                if -1 in (rsi, ema7, ema25, ema99):
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
                    indicator_cache[tf_label] = (rsi, ema7, ema25, ema99)

            if len(valid_tfs) >= 3:
                tf_main = valid_tfs[0]
                rsi_val, ema7_val, ema25_val, ema99_val = indicator_cache[tf_main]
                tp1 = round(price * (1 + strategy["tp1_pct"] / 100), 4)
                tp2 = round(price * (1 + strategy["tp2_pct"] / 100), 4)
                note = f"Note: Valid di {', '.join(valid_tfs)} {'✔️'*len(valid_tfs)}"

                msg = (
                    f"{text} Mode • {tf_main}\n\n"
                    f"✅ {pair}\n"
                    f"Harga: ${price:.3f}\n"
                    f"EMA7: ${ema7_val:.3f} | EMA25: ${ema25_val:.3f} | EMA99: ${ema99_val:.3f}\n"
                    f"RSI(6): {rsi_val}\n"
                    f"📈 Volume: ${volume:,.0f}\n\n"
                    f"🎯 Entry: ${price:.3f}\n"
                    f"🎯 TP1: ${tp1} (+{strategy['tp1_pct']}%)\n"
                    f"🎯 TP2: ${tp2} (+{strategy['tp2_pct']}%)\n\n"
                    f"{note}"
                )
                results.append(msg)

        if results:
            for msg in results:
                await update.message.reply_text(msg)
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
