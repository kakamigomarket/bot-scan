import os
import requests
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

PAIRS = [
    "SEIUSDT","RAYUSDT","PENDLEUSDT","JUPUSDT","ENAUSDT","CRVUSDT","ENSUSDT",
    "FORMUSDT","TAOUSDT","ALGOUSDT","XTZUSDT","CAKEUSDT","HBARUSDT","NEXOUSDT",
    "GALAUSDT","IOTAUSDT","THETAUSDT","CFXUSDT","WIFUSDT","BTCUSDT","ETHUSDT",
    "BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT",
    "AAVEUSDT","ATOMUSDT","INJUSDT","QNTUSDT","ARBUSDT","NEARUSDT","SUIUSDT",
    "LDOUSDT","WLDUSDT","FETUSDT","GRTUSDT","PYTHUSDT","ASRUSDT","HYPERUSDT",
    "TRXUSDT"
]

STRATEGIES = {
    "🔴 Jemput Bola": {"label": "Jemput Bola", "tp1_pct": 7, "tp2_pct": 12, "rsi_limit": 40, "ema_pct": 0.90, "volume_min": 2_000_000},
    "🟡 Rebound Swing": {"label": "Rebound Swing", "tp1_pct": 5, "tp2_pct": 9, "rsi_limit": 50, "ema_pct": 0.95, "volume_min": 3_000_000},
    "🟢 Scalping Breakout": {"label": "Scalping Breakout", "tp1_pct": 3, "tp2_pct": 6, "rsi_limit": 60, "ema_pct": 0.98, "volume_min": 5_000_000}
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

def get_ema_rsi(symbol: str, interval: str, length: int = 14) -> tuple:
    try:
        res = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=100", timeout=10)
        data = res.json()
        closes = [float(k[4]) for k in data]
        rsi_data = closes[-(length+1):]
        deltas = [rsi_data[i+1] - rsi_data[i] for i in range(length)]
        gains = [delta if delta > 0 else 0 for delta in deltas]
        losses = [-delta if delta < 0 else 0 for delta in deltas]
        avg_gain = sum(gains) / length
        avg_loss = sum(losses) / length
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi = round(100 - (100 / (1 + rs)), 2)
        ema21 = sum(closes[-21:]) / 21
        ema99 = sum(closes[-99:]) / 99
        return rsi, round(ema21, 4), round(ema99, 4)
    except:
        return -1, -1, -1

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
            "🔴 Jemput Bola\nfokus pada token yang oversold. ✅ Untuk strategi akumulasi cepat saat koreksi dalam.\n\n"
            "🟡 Rebound Swing\nideal untuk momentum reversal ringan. ✅ Untuk strategi rotasi swing harian.\n\n"
            "🟢 Scalping Breakout\ncocok menangkap awal breakout. ✅ Untuk scalping cepat berbasis volume & momentum."
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
            await update.message.reply_text("⛔ Akses ditolak. Silakan hubungi admin untuk aktivasi.")
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
            rsi_cache = {}
            ema21_cache = {}

            for tf_label, tf_interval in TF_INTERVALS.items():
                rsi, ema21, ema99 = get_ema_rsi(pair, tf_interval)
                if -1 in (rsi, ema21, ema99):
                    continue
                if price < ema21 and price > strategy["ema_pct"] * ema99 and rsi < strategy["rsi_limit"]:
                    valid_tfs.append(tf_label)
                    rsi_cache[tf_label] = rsi
                    ema21_cache[tf_label] = ema21

            if len(valid_tfs) >= 3:
                tf_main = valid_tfs[0]
                tf_note = f"Note: Valid di {', '.join(valid_tfs)} {'✔️'*len(valid_tfs)}"
                tp1 = round(price * (1 + strategy["tp1_pct"] / 100), 4)
                tp2 = round(price * (1 + strategy["tp2_pct"] / 100), 4)

                msg = (
                    f"{text} Mode • {tf_main}\n\n"
                    f"✅ {pair}\n"
                    f"Harga = ${price:.3f} | EMA21 = ${ema21_cache[tf_main]:.3f} | RSI = {rsi_cache[tf_main]}\n"
                    f"📈 Volume: ${volume:,.0f}\n\n"
                    f"🎯 Entry: ${price:.3f}\n"
                    f"🎯 TP1: ${tp1} (+{strategy['tp1_pct']}%)\n"
                    f"🎯 TP2: ${tp2} (+{strategy['tp2_pct']}%)\n\n"
                    f"{tf_note}"
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
