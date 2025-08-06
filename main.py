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

def get_ema_rsi(symbol: str, interval: str) -> tuple:
    try:
        res = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=100", timeout=10)
        data = res.json()
        closes = [float(k[4]) for k in data]

        # RSI(6)
        rsi_data = closes[-7:]
        deltas = [rsi_data[i+1] - rsi_data[i] for i in range(6)]
        gains = [delta if delta > 0 else 0 for delta in deltas]
        losses = [-delta if delta < 0 else 0 for delta in deltas]
        avg_gain = sum(gains) / 6
        avg_loss = sum(losses) / 6
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
    await update.message.reply_text("\ud83d\udccc Pilih Strategi Multi-TF:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "1️⃣ Trading Spot":
        keyboard = [["🔴 Jemput Bola"], ["🟡 Rebound Swing"], ["🟢 Scalping Breakout"], ["🔙 Kembali ke Menu Utama"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("\ud83d\udcc8 Pilih Mode Strategi Trading Spot:", reply_markup=reply_markup)
        return
    elif text == "2️⃣ Info":
        msg = (
            "\ud83d\udd34 Jemput Bola\nfokus pada token yang oversold. \u2705 Untuk strategi akumulasi cepat saat koreksi dalam.\n\n"
            "\ud83d\udfe1 Rebound Swing\nideal untuk momentum reversal ringan. \u2705 Untuk strategi rotasi swing harian.\n\n"
            "\ud83d\udfe2 Scalping Breakout\ncocok menangkap awal breakout. \u2705 Untuk scalping cepat berbasis volume & momentum."
        )
        await update.message.reply_text(msg)
        return
    elif text == "3️⃣ Help":
        msg = (
            "Telegram bot untuk scan harga crypto real-time dari market spot Binance.\n"
            "Diformulasikan untuk membantu para trader mencari cuan.\n\n"
            "Untuk aktivasi fitur trading silakan hubungi @KikioOreo"
        )
        await update.message.reply_text(msg)
        return
    elif text == "🔙 Kembali ke Menu Utama":
        return await start(update, context)

    elif text in STRATEGIES:
        if user_id not in ALLOWED_USERS:
            await update.message.reply_text("\u26d4\ufe0f Akses ditolak. Silakan hubungi admin untuk aktivasi.")
            return

        strategy = STRATEGIES[text]
        await update.message.reply_text(f"\ud83d\udd0d Memindai sinyal untuk *{text}*...\nTunggu beberapa detik...", parse_mode="Markdown")

        results = []
        for pair in PAIRS:
            price = get_price(pair)
            volume = get_volume(pair)
            if price == -1 or volume < strategy["volume_min"]:
                continue

            valid_tfs = []
            rsi_cache = {}
            ema7_cache = {}

            for tf_label, tf_interval in TF_INTERVALS.items():
                rsi, ema7, ema25, ema99 = get_ema_rsi(pair, tf_interval)
                if -1 in (rsi, ema7, ema25, ema99):
                    continue

                # VALIDASI KHUSUS PER STRATEGI
                if text == "🔴 Jemput Bola" and price < ema25 and price > 0.9 * ema99 and rsi < strategy["rsi_limit"]:
                    valid_tfs.append(tf_label)
                elif text == "🟡 Rebound Swing" and ema7 < price < ema25 and rsi < strategy["rsi_limit"]:
                    valid_tfs.append(tf_label)
                elif text == "🟢 Scalping Breakout" and price > ema7 and price > ema25 and price > ema99 and rsi >= strategy["rsi_limit"]:
                    valid_tfs.append(tf_label)

                rsi_cache[tf_label] = rsi
                ema7_cache[tf_label] = ema7

            if len(valid_tfs) >= 3:
                tf_main = valid_tfs[0]
                tf_note = f"Note: Valid di {', '.join(valid_tfs)} {'\u2714\ufe0f'*len(valid_tfs)}"
                tp1 = round(price * (1 + strategy["tp1_pct"] / 100), 4)
                tp2 = round(price * (1 + strategy["tp2_pct"] / 100), 4)

                msg = (
                    f"{text} Mode • {tf_main}\n\n"
                    f"\u2705 {pair}\n"
                    f"Harga = ${price:.3f} | EMA7 = ${ema7_cache[tf_main]:.3f} | RSI = {rsi_cache[tf_main]}\n"
                    f"\ud83d\udcc8 Volume: ${volume:,.0f}\n\n"
                    f"\ud83c\udf1f Entry: ${price:.3f}\n"
                    f"\ud83c\udf1f TP1: ${tp1} (+{strategy['tp1_pct']}%)\n"
                    f"\ud83c\udf1f TP2: ${tp2} (+{strategy['tp2_pct']}%)\n\n"
                    f"{tf_note}"
                )
                results.append(msg)

        if results:
            for msg in results:
                await update.message.reply_text(msg)
                await asyncio.sleep(0.5)
            await update.message.reply_text("\u2705 *Selesai scan. Semua sinyal layak sudah ditampilkan.*", parse_mode="Markdown")
        else:
            await update.message.reply_text("\u26a0\ufe0f Tidak ada sinyal strategi yang layak saat ini.")
        return

    else:
        await update.message.reply_text("\u26d4\ufe0f Perintah tidak dikenali.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
