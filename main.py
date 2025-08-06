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

def detect_candle_pattern(opens, closes, highs, lows):
    # Simple pattern: Hammer, Engulfing, Doji, Morning Star
    last_open = opens[-1]
    last_close = closes[-1]
    last_high = highs[-1]
    last_low = lows[-1]
    body = abs(last_close - last_open)
    candle_range = last_high - last_low

    if candle_range == 0:
        return ""

    upper_wick = last_high - max(last_open, last_close)
    lower_wick = min(last_open, last_close) - last_low

    # Doji
    if body <= 0.1 * candle_range:
        return "Doji"

    # Hammer
    if lower_wick > 2 * body and upper_wick < body:
        return "Hammer"

    # Bullish Engulfing
    if closes[-2] < opens[-2] and last_close > last_open and last_close > opens[-2] and last_open < closes[-2]:
        return "Engulfing"

    return ""

def detect_divergence(prices, rsis):
    if len(prices) < 5 or len(rsis) < 5:
        return ""
    p1, p2 = prices[-5], prices[-1]
    r1, r2 = rsis[-5], rsis[-1]
    if p2 > p1 and r2 < r1:
        return "🔻 Bearish Divergence"
    elif p2 < p1 and r2 > r1:
        return "🔺 Bullish Divergence"
    else:
        return ""

def proximity_to_support_resistance(closes):
    recent = closes[-10:]
    support = min(recent)
    resistance = max(recent)
    price = closes[-1]
    distance_support = (price - support) / support * 100
    distance_resistance = (resistance - price) / resistance * 100
    if distance_support < 2:
        return "Dekat Support"
    elif distance_resistance < 2:
        return "Dekat Resistance"
    else:
        return ""

def is_volume_spike(volumes):
    avg_volume = sum(volumes[-20:-1]) / 19
    return volumes[-1] > 1.5 * avg_volume

def analisa_strategi_pro(symbol, strategy, price, volume, tf_interval):
    try:
        # Fetch data
        res = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={tf_interval}&limit=100", timeout=10)
        data = res.json()
        closes = [float(k[4]) for k in data]
        highs = [float(k[2]) for k in data]
        lows = [float(k[3]) for k in data]
        opens = [float(k[1]) for k in data]
        volumes = [float(k[5]) for k in data]

        if len(closes) < 100:
            return None

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

        # Logika strategi utama
        is_valid = False
        if strategy == "🔴 Jemput Bola":
            is_valid = price < ema25 and price > 0.9 * ema99 and rsi < 40
        elif strategy == "🟡 Rebound Swing":
            is_valid = price < ema25 and price > ema7 and rsi < 50
        elif strategy == "🟢 Scalping Breakout":
            is_valid = price > ema7 and price > ema25 and price > ema99 and rsi >= 60

        if not is_valid:
            return None

        # Tambahan PRO
        candle = detect_candle_pattern(opens, closes, highs, lows)
        divergence = detect_divergence(closes, [rsi] * len(closes))  # optional simplification
        support_zone = proximity_to_support_resistance(closes)
        volume_spike = is_volume_spike(volumes)
        support_warning = price < 0.985 * ema25 and price < 0.97 * ema7

        # TP Dinamis pakai ATR
        tp1 = round(price + atr * 1.0, 4)
        tp2 = round(price + atr * 1.8, 4)
        tp1_pct = round((tp1 - price) / price * 100, 2)
        tp2_pct = round((tp2 - price) / price * 100, 2)

        # Confidence Score
        score = 0
        if candle: score += 1
        if "Divergence" in divergence: score += 1
        if "Dekat" in support_zone: score += 1
        if volume_spike: score += 1
        if not support_warning: score += 1
        label_score = f"🎯 Confidence Score: {score}/5"

        # Format output
        msg = (
            f"{strategy} Mode • {tf_interval}\n\n"
            f"✅ {symbol}\n"
            f"Harga: ${price:.3f}\n"
            f"EMA7: {ema7:.3f} | EMA25: {ema25:.3f} | EMA99: {ema99:.3f}\n"
            f"RSI(6): {rsi} | ATR(14): {atr:.4f}\n"
            f"📈 Volume: ${volume:,.0f}\n\n"
            f"🎯 Entry: ${price:.3f}\n"
            f"🎯 TP1: ${tp1} (+{tp1_pct}%)\n"
            f"🎯 TP2: ${tp2} (+{tp2_pct}%)\n\n"
            f"{label_score}\n"
        )
        if candle:
            msg += f"📌 Pattern: {candle}\n"
        if divergence:
            msg += f"{divergence}\n"
        if support_zone:
            msg += f"📍 {support_zone}\n"
        if volume_spike:
            msg += "💥 Volume Spike\n"
        if support_warning:
            msg += "⚠️ *Waspada! Support patah*\n"

        return msg
    except Exception as e:
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "1️⃣ Trading Spot":
        keyboard = [
            ["🔴 Jemput Bola"], ["🟡 Rebound Swing"], ["🟢 Scalping Breakout"],
            ["🔙 Kembali ke Menu Utama"]
        ]
        await update.message.reply_text("📊 Pilih Mode Strategi:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
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

            for tf_label, tf_interval in TF_INTERVALS.items():
                msg = analisa_strategi_pro(pair, text, price, volume, tf_interval)
                if msg:
                    results.append(msg)
                    break  # tampilkan 1 per pair (TF terbaik)

        if results:
            for msg in results:
                await update.message.reply_text(msg, parse_mode="Markdown")
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
