
import os
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

PAIRS = [
    "CRVUSDT", "ENSUSDT", "SEIUSDT"
]

STRATEGIES = {
    "🔴 Jemput Bola": "jemput",
    "🟡 Rebound Swing": "rebound",
    "🟢 Scalping Breakout": "scalping"
}

TF_LIST = ["15m", "1h", "4h", "1d"]

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
    strategy = STRATEGIES.get(text)
    if not strategy:
        await update.message.reply_text("Perintah tidak dikenali.")
        return

    found = False
    for tf in TF_LIST:
        await update.message.reply_text(f"🔍 Scan {strategy.upper()} TF {tf.upper()} (Debug Mode)...", parse_mode="Markdown")
        # Simulasi deteksi (pakai logika dummy di sini)
        if strategy == "scalping" and tf == "15m":
            msg = f"📊 Strategi {strategy.upper()} - Token Layak Entry ✅\n- CRVUSDT | RSI: 32.4 | Harga: $0.98 | TP1: +3%, TP2: +6%"
            await update.message.reply_text(msg, parse_mode="Markdown")
            found = True
        await asyncio.sleep(0.5)

    if not found:
        await update.message.reply_text("⚠️ Tidak ada sinyal strategi yang layak saat ini.", parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
