
import os
import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

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

MIN_VOLUME = 3_000_000

TP_CONFIG = {
    "jemput": (7, 12),
    "rebound": (5, 9),
    "scalp": (3, 6)
}

async def fetch_data(pair):
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"
    response = requests.get(url)
    data = response.json()
    price = float(data["lastPrice"])
    volume = float(data["quoteVolume"])
    return price, volume

async def fetch_klines(pair, interval="15m", limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={pair}&interval={interval}&limit={limit}"
    response = requests.get(url)
    return response.json()

def calculate_rsi(prices, period=14):
    gains = []
    losses = []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_ema(prices, period):
    k = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = (price - ema) * k + ema
    return ema

async def analyze_pair(pair, strategy):
    price, volume = await fetch_data(pair)
    if volume < MIN_VOLUME:
        return None

    klines = await fetch_klines(pair, interval="15m", limit=100)
    closes = [float(k[4]) for k in klines]
    rsi = calculate_rsi(closes)
    ema21 = calculate_ema(closes[-21:], 21)
    ema99 = calculate_ema(closes[-99:], 99)

    valid = False
    if strategy == "jemput":
        valid = rsi < 40 and price <= ema21 and price >= ema99 * 0.95
    elif strategy == "rebound":
        valid = 38 <= rsi <= 45 and abs(price - ema21) / ema21 < 0.01
    elif strategy == "scalp":
        valid = 40 <= rsi <= 60 and price > ema21 and volume > MIN_VOLUME * 1.5

    if not valid:
        return None

    tp1_pct, tp2_pct = TP_CONFIG[strategy]
    tp1 = price * (1 + tp1_pct / 100)
    tp2 = price * (1 + tp2_pct / 100)

    return {
        "pair": pair,
        "price": price,
        "rsi": round(rsi, 2),
        "ema21": round(ema21, 4),
        "entry": round(price, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6)
    }

async def scan_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE, strategy: str):
    if update.effective_user.id not in ALLOWED_USERS:
        return

    await update.message.reply_text(f"🔍 Mendeteksi sinyal strategi *{strategy.upper()}*...\nTunggu sebentar...", parse_mode="Markdown")

    results = []
    for pair in PAIRS:
        result = await analyze_pair(pair, strategy)
        if result:
            results.append(result)

    if not results:
        await update.message.reply_text("❌ Tidak ada token yang layak entry saat ini.")
        return

    msg = f"📊 Strategi {strategy.upper()} - Token Layak Entry ✅\n\n"
    for res in results:
        msg += (
            f"✅ *{res['pair']}*\n"
            f"💰 Harga: ${res['price']}\n"
            f"📉 RSI: {res['rsi']} | EMA21: {res['ema21']}\n"
            f"🎯 Entry: ${res['entry']}\n"
            f"🎯 TP1: ${res['tp1']}\n"
            f"🎯 TP2: ${res['tp2']}\n"
            f"🟢 Status: LAYAK ENTRY ✅\n\n"
        )

    await update.message.reply_text(msg.strip(), parse_mode="Markdown")

async def handle_jemput(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await scan_strategy(update, context, strategy="jemput")

async def handle_rebound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await scan_strategy(update, context, strategy="rebound")

async def handle_scalp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await scan_strategy(update, context, strategy="scalp")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        return
    keyboard = [[
        "🟥 Jemput Bola", "🟡 Rebound Swing", "🟢 Scalping Breakout"
    ]]
    await update.message.reply_text(
        "📌 Pilih Strategi Analisa:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🟥 Jemput Bola":
        await scan_strategy(update, context, strategy="jemput")
    elif text == "🟡 Rebound Swing":
        await scan_strategy(update, context, strategy="rebound")
    elif text == "🟢 Scalping Breakout":
        await scan_strategy(update, context, strategy="scalp")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("jemput", handle_jemput))
    app.add_handler(CommandHandler("rebound", handle_rebound))
    app.add_handler(CommandHandler("scalp", handle_scalp))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("scan", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("strategi", start))
    app.add_handler(CommandHandler("pantau", start))
    app.add_handler(CommandHandler("monitor", start))
    app.add_handler(CommandHandler("cek", start))
    app.add_handler(CommandHandler("go", start))
    app.add_handler(CommandHandler("aktif", start))
    app.add_handler(CommandHandler("signal", start))
    app.add_handler(CommandHandler("trigger", start))
    app.add_handler(CommandHandler("command", start))
    app.add_handler(CommandHandler("analisa", start))
    app.add_handler(CommandHandler("sinyal", start))
    app.add_handler(CommandHandler("watchlist", start))
    app.add_handler(CommandHandler("token", start))
    app.add_handler(CommandHandler("entry", start))
    app.add_handler(CommandHandler("layakentry", start))
    app.add_handler(CommandHandler("tombol", start))
    app.add_handler(CommandHandler("telegram", button_handler))
    app.run_polling()
