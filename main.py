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
    "LDOUSDT", "WLDUSDT", "FETUSDT", "GRTUSDT", "PYTHUSDT", "ASRUSDT", "HYPERUSDT", "TRXUSDT"
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

# ==================== INDICATORS ====================

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

    if body <= 0.1 * candle_range:
        return "Doji"
    if lower_wick > 2 * body and upper_wick < body:
        return "Hammer"
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

def calculate_macd(closes):
    ema12 = [sum(closes[i-11:i+1])/12 for i in range(11, len(closes))]
    ema26 = [sum(closes[i-25:i+1])/26 for i in range(25, len(closes))]
    macd_line = [e12 - e26 for e12, e26 in zip(ema12[-len(ema26):], ema26)]
    signal_line = [sum(macd_line[i-8:i+1])/9 for i in range(8, len(macd_line))]
    histogram = [m - s for m, s in zip(macd_line[-len(signal_line):], signal_line)]
    return histogram[-1] if histogram else 0

def trend_strength(closes, volumes):
    ema_short = sum(closes[-10:]) / 10
    ema_long = sum(closes[-30:]) / 30
    slope = ema_short - ema_long
    avg_vol = sum(volumes[-20:]) / 20
    vol_boost = volumes[-1] > 1.2 * avg_vol
    if slope > 0 and vol_boost:
        return "Uptrend 🔼"
    elif slope < 0 and vol_boost:
        return "Downtrend 🔽"
    else:
        return "Sideways ⏸️"

# ==================== STRATEGY ====================

def analisa_strategi_pro(symbol, strategy, price, volume, tf_interval):
    try:
        res = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={tf_interval}&limit=100", timeout=10)
        data = res.json()
        closes = [float(k[4]) for k in data]
        highs = [float(k[2]) for k in data]
        lows = [float(k[3]) for k in data]
        opens = [float(k[1]) for k in data]
        volumes = [float(k[5]) for k in data]
        if len(closes) < 100: return None

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

        is_valid = False
        if strategy == "🔴 Jemput Bola":
            is_valid = price < ema25 and price > 0.9 * ema99 and rsi < 40
        elif strategy == "🟡 Rebound Swing":
            is_valid = price < ema25 and price > ema7 and rsi < 50
        elif strategy == "🟢 Scalping Breakout":
            is_valid = price > ema7 and price > ema25 and price > ema99 and rsi >= 60
        if not is_valid:
            return None

        candle = detect_candle_pattern(opens, closes, highs, lows)
        divergence = detect_divergence(closes, [rsi] * len(closes))
        support_zone = proximity_to_support_resistance(closes)
        volume_spike = is_volume_spike(volumes)
        support_warning = price < 0.985 * ema25 and price < 0.97 * ema7
        tp1 = round(price + atr * 1.0, 4)
        tp2 = round(price + atr * 1.8, 4)
        tp1_pct = round((tp1 - price) / price * 100, 2)
        tp2_pct = round((tp2 - price) / price * 100, 2)
        trend = trend_strength(closes, volumes)
        macd_hist = calculate_macd(closes)

        score = 0
        if candle: score += 1
        if "Divergence" in divergence: score += 1
        if "Dekat" in support_zone: score += 1
        if volume_spike: score += 1
        if not support_warning: score += 1

        if score < 3:
            return None

        label_score = f"🎯 Confidence Score: {score}/5"
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
        if candle: msg += f"📌 Pattern: {candle}\n"
        if divergence: msg += f"{divergence}\n"
        if support_zone: msg += f"📍 {support_zone}\n"
        if volume_spike: msg += "💥 Volume Spike\n"
        if support_warning: msg += "⚠️ *Waspada! Support patah*\n"
        msg += f"📊 Trend: {trend}\n"
        if macd_hist > 0:
            msg += "🧬 MACD Cross: Bullish\n"
        elif macd_hist < 0:
            msg += "🧬 MACD Cross: Bearish\n"

        return msg
    except Exception as e:
        return None

# ==================== BOT HANDLER ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["1️⃣ Trading Spot"], ["2️⃣ Info"], ["3️⃣ Help"]]
    await update.message.reply_text("📌 Pilih Strategi Multi-TF:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "1️⃣ Trading Spot":
        keyboard = [["🔴 Jemput Bola"], ["🟡 Rebound Swing"], ["🟢 Scalping Breakout"], ["🔙 Kembali ke Menu Utama"]]
        await update.message.reply_text("📊 Pilih Mode Strategi:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

     elif text == "2️⃣ Info":
        msg = """
🔹 Pilih strategi & analisa otomatis semua koin. Klik tombol Trading Spot untuk scan otomatis sinyal dari semua koin.

📌 SARAN WAKTU IDEAL

🔴 Jemput Bola (Oversold / Akumulasi)
⏰ Pagi: 07.30–08.30 WIB
• Pas banget setelah sesi malam Amerika berakhir
• Banyak koin dalam kondisi koreksi atau baru rebound
• Ideal untuk menangkap harga bawah

🟡 Rebound Swing (Momentum Balik Arah)
⏰ Siang – Sore: 12.00–15.00 WIB
• Waktu tenang antara sesi Asia & Eropa
• Ideal untuk pantau reversal awal, sinyal mulai muncul
• Cocok buat swing trader yang ingin hold 1–2 hari

🟢 Scalping Breakout (Momentum Cepat)
⏰ Malam: 19.00–22.00 WIB
• Awal pembukaan sesi US → banyak breakout terjadi
• Volume besar masuk
• Ideal untuk scalping cepat atau jual besok pagi

⚠️ Disclaimer: BOT ini bukan penasihat keuangan. Gunakan secara bijak dan tetap DYOR.
"""
        await update.message.reply_text(msg)
        return

    elif text in STRATEGIES:
        if user_id not in ALLOWED_USERS:
            await update.message.reply_text("⛔ Akses ditolak.")
            return

        await update.message.reply_text(f"🔍 Memindai sinyal untuk *{text}*...\nTunggu beberapa detik...", parse_mode="Markdown")
        strategy = STRATEGIES[text]
        results = []

        for pair in PAIRS:
            price = get_price(pair)
            volume = get_volume(pair)
            if price == -1 or volume < strategy["volume_min"]:
                continue

            valid_msgs = []
            for tf_label, tf_interval in TF_INTERVALS.items():
                msg = analisa_strategi_pro(pair, text, price, volume, tf_interval)
                if msg:
                    valid_msgs.append(msg)

            if len(valid_msgs) >= 2:
                results.append(valid_msgs[0])

        if results:
            for msg in results:
                await update.message.reply_text(msg, parse_mode="Markdown")
                await asyncio.sleep(0.5)
            await update.message.reply_text("✅ *Selesai scan. Semua sinyal layak ditampilkan.*", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Tidak ada sinyal strategi yang layak saat ini.")
    else:
        await update.message.reply_text("⛔ Perintah tidak dikenali.")

# ==================== MAIN ====================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
