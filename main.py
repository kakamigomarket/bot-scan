import os, logging, asyncio, traceback
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED = [int(x) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("diag")

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))[:1500]
    log.error(f"ERROR: {err}")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    if ALLOWED and uid not in ALLOWED:
        await update.message.reply_text("Akses ditolak.")
        return
    await update.message.reply_text("pong ✅")

async def log_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else "unknown"
    kind = "callback" if update.callback_query else "message" if update.message else "other"
    log.info(f"UPDATE RECEIVED kind={kind} from={uid}")

async def post_startup(app):
    me = await app.bot.get_me()
    log.warning(f"BOT STARTED as @{me.username} id={me.id}")
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        log.warning("Webhook deleted with drop_pending_updates=True")
    except Exception as e:
        log.warning(f"delete_webhook failed: {e}")
    try:
        if ALLOWED:
            await app.bot.send_message(ALLOWED[0], f"Bot @{me.username} aktif. Kirim /ping di chat ini.")
    except Exception as e:
        log.info(f"notify failed: {e}")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN kosong")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(MessageHandler(filters.ALL, log_all), group=-1)
    app.add_error_handler(on_error)
    app.post_init = post_startup
    log.info("Starting polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)

if __name__ == "__main__":
    main()
