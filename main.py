
import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

# Dummy data dan fungsi placeholder
def get_price(symbol): return 0.903
def get_ema(symbol, tf): return 0.901
def get_rsi(symbol, tf): return 47.21
def get_volume(symbol): return 5000000
def get_valid_tfs(symbol): return ["15m", "1h", "3h"]

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔️ Akses ditolak.")
        return

    label = "Scalping Breakout"
    symbol = "CRVUSDT"
    price = get_price(symbol)
    ema = get_ema(symbol, "15m")
    rsi = get_rsi(symbol, "15m")
    volume = get_volume(symbol)
    valid_tfs = get_valid_tfs(symbol)

    emoji = "🟢"
    tf_label = f"{emoji} {label} Mode • TF{valid_tfs[0]}"
    entry = price
    tp1 = round(entry * 1.03, 4)
    tp2 = round(entry * 1.06, 4)
    msg = (
        f"{tf_label}

"
        f"✅ {symbol}
"
        f"Harga = ${entry} | EMA21 = ${ema} | RSI = {rsi}
"
        f"📈 Volume Breakout | Candle impulsif

"
        f"🎯 Entry: ${entry}
"
        f"🎯 TP1: ${tp1} (+3%)
"
        f"🎯 TP2: ${tp2} (+6%)

"
        f"Note: Valid di {', '.join(valid_tfs)} ✔️" * len(valid_tfs)
    )

    await update.message.reply_text(msg)

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("scan", scan))

if __name__ == "__main__":
    app.run_polling()
