
from __future__ import annotations
import os, time, asyncio, logging
from typing import Dict, Tuple, List, Optional
import aiohttp
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN belum diset di environment.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("signal-bot")

# Konfigurasi mode
HTTP_CONCURRENCY = int(os.getenv("HTTP_CONCURRENCY", "12"))
ANALYSIS_CONCURRENCY = int(os.getenv("ANALYSIS_CONCURRENCY", "8"))

# Retail Mode dilonggarkan
MODE_PROFILES = {
    "retail": {"ADX_MIN":15.0,"ATR_PCT_MIN_BREAKOUT":0.05,"AVG_TRADES_MIN":50,"REQUIRE_2_TF":False},
    "pro":    {"ADX_MIN":25.0,"ATR_PCT_MIN_BREAKOUT":0.15,"AVG_TRADES_MIN":200,"REQUIRE_2_TF":True},
}

# Tombol keyboard
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🟢 Retail Mode", "🧠 Pro Mode"],
        ["ℹ️ Info", "🆘 Help"]
    ],
    resize_keyboard=True
)

async def _check_auth(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else 0
    if ALLOWED_USERS and uid not in ALLOWED_USERS:
        if update.message:
            await update.message.reply_text("⛔ Akses ditolak. Kamu tidak terdaftar sebagai pengguna.", reply_markup=ReplyKeyboardRemove())
        elif update.callback_query:
            await update.callback_query.answer("Akses ditolak", show_alert=True)
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Selamat datang di Bot Sinyal Trading Crypto!
Pilih menu di bawah ini:",
        reply_markup=MAIN_KEYBOARD
    )

async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = "\n".join([
        "📌 Jadwal Ideal Strategi:",
        "🔴 Jemput Bola: 07.30–08.30 WIB",
        "🟡 Rebound Swing: Siang–Sore",
        "🟢 Scalping Breakout: Malam 19.00–22.00 WIB",
        "Gunakan sesuai momentum pasar & arah BTC!",
    ])
    await update.message.reply_text(txt)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💬 Hubungi admin @KikioOreo untuk bantuan atau aktivasi.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🟢 Retail Mode":
        if not await _check_auth(update): return
        await update.message.reply_text("🔍 Memulai scan untuk Retail Mode...")
    elif text == "🧠 Pro Mode":
        if not await _check_auth(update): return
        await update.message.reply_text("🔍 Memulai scan untuk Pro Mode...")
    elif text == "ℹ️ Info":
        await info_cmd(update, context)
    elif text == "🆘 Help":
        await help_cmd(update, context)
    else:
        await update.message.reply_text("Gunakan menu di bawah ini:", reply_markup=MAIN_KEYBOARD)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    log.info("Bot aktif dan berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
