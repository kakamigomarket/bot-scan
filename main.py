
import os
import requests
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

PAIRS = [
    "CRVUSDT", "SUIUSDT", "SEIUSDT", "ENAUSDT", "RAYUSDT"
]

STRATEGIES = {
    "🔴 Jemput Bola": {"label": "JEMPUT BOLA", "tp1_pct": 7, "tp2_pct": 12, "rsi_limit": 40},
    "🟡 Rebound Swing": {"label": "REBOUND SWING", "tp1_pct": 5, "tp2_pct": 9, "rsi_limit": 50},
    "🟢 Scalping Breakout": {"label": "SCALPING", "tp1_pct": 3, "tp2_pct": 6, "rsi_limit": 60}
}

TF_INTERVALS = {
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d"
}

def get_price(symbol: str) -> float:
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        response = requests.get(url, timeout=10)
        if response.ok:
            return float(response.json()["price"])
    except:
        pass
    return -1

def get_rsi(symbol: str, interval: str, length: int = 14) -> float:
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={length+1}"
    try:
        response = requests.get(url, timeout=10)
        if response.ok:
            closes = [float(candle[4]) for candle in response.json()]
            deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
            gains = [delta if delta > 0 else 0 for delta in deltas]
            losses = [-delta if delta < 0 else 0 for delta in deltas]
            avg_gain = sum(gains) / length
            avg_loss = sum(losses) / length
            if avg_loss == 0:
                return 100
            rs = avg_gain / avg_loss
            return round(100 - (100 / (1 + rs)), 2)
    except:
        pass
    return -1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        return
    keyboard = [[key] for key in STRATEGIES.keys()]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("📌 Pilih Strategi Analisa:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        return
    text = update.message.text.strip()
    strategy_config = STRATEGIES.get(text)
    if not strategy_config:
        await update.message.reply_text("⛔ Perintah tidak dikenali.")
        return

    label = strategy_config["label"]
    tp1_pct = strategy_config["tp1_pct"]
    tp2_pct = strategy_config["tp2_pct"]
    rsi_limit = strategy_config["rsi_limit"]
    found_any = False

    for tf_label, tf_interval in TF_INTERVALS.items():
        await update.message.reply_text(f"🔍 Scan {label} TF {tf_label.upper()} (Real-Time)...")
        found = False
        for pair in PAIRS:
            harga = get_price(pair)
            rsi = get_rsi(pair, tf_interval)
            if harga == -1 or rsi == -1:
                continue
            if rsi < rsi_limit:
                tp1 = round(harga * (1 + tp1_pct / 100), 4)
                tp2 = round(harga * (1 + tp2_pct / 100), 4)
                msg = (
                    f"📊 Strategi {label} - Token Layak Entry ✅\n"
                    f"- {pair} | RSI: {rsi} | Entry: ${harga:.4f} | "
                    f"TP1: ${tp1} (+{tp1_pct}%), TP2: ${tp2} (+{tp2_pct}%)"
                )
                await update.message.reply_text(msg)
                found = True
                found_any = True
                await asyncio.sleep(0.5)

        if not found:
            await update.message.reply_text("⚠️ Tidak ada sinyal strategi yang layak saat ini.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
