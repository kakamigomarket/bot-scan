
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
    "LDOUSDT","WLDUSDT","FETUSDT","GRTUSDT","PYTHUSDT","ASRUSDT","HYPERUSDT","TRXUSDT"
]

STRATEGIES = {
    "🔴 Jemput Bola": {"label": "JEMPUT BOLA", "tp1_pct": 7, "tp2_pct": 12, "rsi_limit": 40, "ema_pct": 0.90, "volume_min": 2_000_000},
    "🟡 Rebound Swing": {"label": "REBOUND SWING", "tp1_pct": 5, "tp2_pct": 9, "rsi_limit": 50, "ema_pct": 0.95, "volume_min": 3_000_000},
    "🟢 Scalping Breakout": {"label": "SCALPING", "tp1_pct": 3, "tp2_pct": 6, "rsi_limit": 60, "ema_pct": 0.98, "volume_min": 5_000_000}
}

TF_INTERVALS = {
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d"
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
        await update.message.reply_text("⛔ Perintah tidak dikenali.")
        return

    label = strategy["label"]
    tp1_pct = strategy["tp1_pct"]
    tp2_pct = strategy["tp2_pct"]
    rsi_limit = strategy["rsi_limit"]
    ema_pct = strategy["ema_pct"]
    volume_min = strategy["volume_min"]

    found_any = False

    for tf_label, tf_interval in TF_INTERVALS.items():
        await update.message.reply_text(f"🔍 Scan {label} TF {tf_label.upper()} (Real-Time)...")
        found = False
        for pair in PAIRS:
            price = get_price(pair)
            volume = get_volume(pair)
            rsi, ema21, ema99 = get_ema_rsi(pair, tf_interval)

            if -1 in (price, rsi, ema21, ema99):
                continue
            if volume < volume_min:
                continue
            if price > ema21 or price < ema_pct * ema99:
                continue
            if rsi >= rsi_limit:
                continue

            tp1 = round(price * (1 + tp1_pct / 100), 4)
            tp2 = round(price * (1 + tp2_pct / 100), 4)

            msg = (
                f"📊 Strategi {label} - Token Layak Entry ✅\n"
                f"- {pair} | RSI: {rsi} | Harga: ${price:.4f}\n"
                f"EMA21: ${ema21}, EMA99: ${ema99}, Volume: ${volume:,.0f}\n"
                f"Entry: ${price:.4f}\n"
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
