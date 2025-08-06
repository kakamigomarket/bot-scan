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
            return -1, -1, -1, -1, -1, [], []

        # RSI(6)
        rsi_len = 6
        deltas = [closes[i+1] - closes[i] for i in range(-rsi_len-1, -1)]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains) / rsi_len
        avg_loss = sum(losses) / rsi_len
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi = round(100 - (100 / (1 + rs)), 2)

        ema7 = sum(closes[-7:]) / 7
        ema25 = sum(closes[-25:]) / 25
        ema99 = sum(closes[-99:]) / 99

        tr = [highs[i] - lows[i] for i in range(-14, 0)]
        atr = sum(tr) / 14

        return rsi, round(ema7, 4), round(ema25, 4), round(ema99, 4), round(atr, 4), closes[-15:], closes[-15:]
    except:
        return -1, -1, -1, -1, -1, [], []

def detect_divergence(prices, rsis):
    if len(prices) < 5 or len(rsis) < 5:
        return "–"
    low1, low2 = prices[-5], prices[-1]
    rsi1, rsi2 = rsis[-5], rsis[-1]

    if low2 < low1 and rsi2 > rsi1:
        return "Bullish Div ✅"
    elif low2 > low1 and rsi2 < rsi1:
        return "Bearish Div ⚠️"
    return "–"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["1️⃣ Trading Spot"], ["2️⃣ Info"], ["3️⃣ Help"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("📌 Pilih Strategi Multi-TF:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "1️⃣ Trading Spot":
        keyboard = [
            ["🔴 Jemput Bola"], ["🟡 Rebound Swing"], ["🟢 Scalping Breakout"],
            ["🔙 Kembali ke Menu Utama"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("📊 Pilih Mode Strategi:", reply_markup=reply_markup)
        return

    elif text == "2️⃣ Info":
        msg = (
            "Klik tombol Trading Spot untuk scan otomatis sinyal dari semua koin.\n"
            "Setiap mode strategi punya gaya entry berbeda:\n\n"
            "🔴 Jemput Bola\nToken oversold. Strategi akumulasi saat koreksi dalam.\n\n"
            "🟡 Rebound Swing\nMomentum reversal ringan. Untuk rotasi swing harian.\n\n"
            "🟢 Scalping Breakout\nTangkap awal breakout. Untuk scalping cepat.\n\n"
            "⚠️ Disclaimer: BOT ini bukan penasihat keuangan. Gunakan secara bijak dan tetap DYOR."
        )
        await update.message.reply_text(msg)
        return

    elif text == "3️⃣ Help":
        msg = (
            "Bot scan harga crypto spot Binance real-time.\n"
            "Cocok untuk trader berbasis EMA, RSI, dan Volume.\n\n"
            "Hubungi @KikioOreo untuk aktivasi akses penuh."
        )
        await update.message.reply_text(msg)
        return

    elif text == "🔙 Kembali ke Menu Utama":
        await start(update, context)
        return

    elif text in STRATEGIES:
        if user_id not in ALLOWED_USERS:
            await update.message.reply_text("⛔ Akses ditolak. Silakan hubungi admin.")
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
                rsi, ema7, ema25, ema99, atr, closes, rsis = get_indicators(pair, tf_interval)
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
                    tf_data[tf_label] = (rsi, ema7, ema25, ema99, atr, closes, rsis)

            if len(valid_tfs) >= 3:
                tf_main = valid_tfs[0]
                rsi_val, ema7_val, ema25_val, ema99_val, atr, closes, rsis = tf_data[tf_main]
                tp1 = round(price + atr * 1.0, 4)
                tp2 = round(price + atr * 1.8, 4)
                pct1 = round((tp1 - price) / price * 100, 2)
                pct2 = round((tp2 - price) / price * 100, 2)

                divergence = detect_divergence(closes, rsis)
                warning = "\n⚠️ *Waspada! Support patah*" if price < 0.985 * ema25 and price < 0.97 * ema7 else ""

                strength = "Strong ✅" if len(valid_tfs) >= 4 and rsi_val < strategy["rsi_limit"] else "Medium ⚠️" if len(valid_tfs) == 3 else "Weak ❌"

                msg = (
                    f"{text} Mode • {tf_main} • {strength}\n\n"
                    f"✅ {pair}\n"
                    f"Harga: ${price:.3f}\n"
                    f"EMA7: ${ema7_val:.3f} | EMA25: ${ema25_val:.3f} | EMA99: ${ema99_val:.3f}\n"
                    f"RSI(6): {rsi_val} | ATR: {atr} | {divergence}\n"
                    f"📈 Volume: ${volume:,.0f}\n\n"
                    f"🎯 Entry: ${price:.3f}\n"
                    f"🎯 TP1: ${tp1} (+{pct1}%)\n"
                    f"🎯 TP2: ${tp2} (+{pct2}%)\n\n"
                    f"Note: Valid di {', '.join(valid_tfs)} {'✔️'*len(valid_tfs)}{warning}"
                )
                results.append(msg)

        if results:
            for msg in results:
                await update.message.reply_text(msg, parse_mode="Markdown")
                await asyncio.sleep(0.4)
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
