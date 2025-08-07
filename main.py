import os
import requests
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# ========== KONFIGURASI BOT ==========
BOT_TOKEN = os.getenv("BOT_TOKEN") or "ISI_TOKEN_BOT_DISINI"
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "123456789")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

PAIRS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "SOLUSDT", "TRXUSDT", "DOGEUSDT", "ADAUSDT",
    "XLMUSDT", "SUIUSDT", "BCHUSDT", "LINKUSDT", "HBARUSDT", "AVAXUSDT", "LTCUSDT", "TONUSDT",
    "SHIBUSDT", "UNIUSDT", "DOTUSDT", "DAIUSDT", "PEPEUSDT", "ENAUSDT", "AAVEUSDT", "TAOUSDT",
    "NEARUSDT", "ETCUSDT", "ONDOUSDT", "APTUSDT", "ICPUSDT", "POLUSDT", "PENGUUSDT", "ALGOUSDT",
    "VETUSDT", "ARBUSDT", "ATOMUSDT", "BONKUSDT", "RENDERUSDT", "WLDUSDT", "TRUMPUSDT", "SEIUSDT",
    "FILUSDT", "FETUSDT", "JUPUSDT", "FORMUSDT", "QNTUSDT", "INJUSDT", "CRVUSDT", "STXUSDT",
    "TIAUSDT", "OPUSDT", "CFXUSDT", "FLOKIUSDT", "IMXUSDT", "GRTUSDT", "ENSUSDT", "PAXGUSDT",
    "CAKEUSDT", "WIFUSDT", "KAIAUSDT", "LDOUSDT", "NEXOUSDT", "XTZUSDT",
    "SUSDT", "VIRTUALUSDT", "AUSDT",
    "THETAUSDT", "IOTAUSDT", "JASMYUSDT", "RAYUSDT", "GALAUSDT", "DEXEUSDT", "SANDUSDT", "PENDLEUSDT"
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

# ========== FUNGSI API ==========

def get_price(symbol): 
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=10)
        return float(r.json()["price"])
    except:
        return -1

def get_volume(symbol): 
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}", timeout=10)
        return float(r.json()["quoteVolume"])
    except:
        return 0

# ========== LOGIKA ANALISA ==========

def detect_candle_pattern(opens, closes, highs, lows):
    o, c, h, l = opens[-1], closes[-1], highs[-1], lows[-1]
    body = abs(c - o)
    range_ = h - l
    if range_ == 0: return ""
    upper = h - max(o, c)
    lower = min(o, c) - l
    if body <= 0.1 * range_: return "Doji"
    if lower > 2 * body and upper < body: return "Hammer"
    if closes[-2] < opens[-2] and c > o and c > opens[-2] and o < closes[-2]: return "Engulfing"
    return ""

def detect_divergence(prices, rsis):
    if len(prices) < 5: return ""
    p1, p2, r1, r2 = prices[-5], prices[-1], rsis[-5], rsis[-1]
    if p2 > p1 and r2 < r1: return "🔻 Bearish Divergence"
    if p2 < p1 and r2 > r1: return "🔺 Bullish Divergence"
    return ""

def proximity_to_support_resistance(closes):
    recent = closes[-10:]
    support, resistance, price = min(recent), max(recent), closes[-1]
    dist_support = (price - support) / support * 100
    dist_resist = (resistance - price) / resistance * 100
    if dist_support < 2: return "Dekat Support"
    if dist_resist < 2: return "Dekat Resistance"
    return ""

def is_volume_spike(volumes):
    avg = sum(volumes[-20:-1]) / 19
    return volumes[-1] > 1.5 * avg

def calculate_macd(closes):
    ema12 = [sum(closes[i-11:i+1])/12 for i in range(11, len(closes))]
    ema26 = [sum(closes[i-25:i+1])/26 for i in range(25, len(closes))]
    macd = [e1 - e2 for e1, e2 in zip(ema12[-len(ema26):], ema26)]
    signal = [sum(macd[i-8:i+1])/9 for i in range(8, len(macd))]
    hist = [m - s for m, s in zip(macd[-len(signal):], signal)]
    return hist[-1] if hist else 0

def trend_strength(closes, volumes):
    ema10 = sum(closes[-10:]) / 10
    ema30 = sum(closes[-30:]) / 30
    slope = ema10 - ema30
    avg_vol = sum(volumes[-20:]) / 20
    if slope > 0 and volumes[-1] > 1.2 * avg_vol: return "Uptrend 🔼"
    if slope < 0 and volumes[-1] > 1.2 * avg_vol: return "Downtrend 🔽"
    return "Sideways ⏸️"

# ========== ANALISA STRATEGI ==========

def analisa_strategi_pro(symbol, strategy, price, volume, tf_interval):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={tf_interval}&limit=100"
        data = requests.get(url, timeout=10).json()
        closes = [float(k[4]) for k in data]
        opens = [float(k[1]) for k in data]
        highs = [float(k[2]) for k in data]
        lows = [float(k[3]) for k in data]
        volumes_data = [float(k[5]) for k in data]

        deltas = [closes[i+1] - closes[i] for i in range(-7, -1)]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        rs = (sum(gains)/6) / (sum(losses)/6 or 1)
        rsi = round(100 - 100 / (1 + rs), 2)

        ema7 = sum(closes[-7:]) / 7
        ema25 = sum(closes[-25:]) / 25
        ema99 = sum(closes[-99:]) / 99
        tr14 = [highs[i] - lows[i] for i in range(-14, 0)]
        atr = sum(tr14) / 14

        # Validasi strategi
        is_valid = False
        if strategy == "🔴 Jemput Bola":
            is_valid = price < ema25 and price > 0.9 * ema99 and rsi < 40
        elif strategy == "🟡 Rebound Swing":
            is_valid = price < ema25 and price > ema7 and rsi < 50
        elif strategy == "🟢 Scalping Breakout":
            is_valid = price > ema7 and price > ema25 and price > ema99 and rsi >= 60
        if not is_valid: return None

        # Indikator tambahan
        candle = detect_candle_pattern(opens, closes, highs, lows)
        divergence = detect_divergence(closes, [rsi]*len(closes))
        zone = proximity_to_support_resistance(closes)
        vol_spike = is_volume_spike(volumes_data)
        support_patah = price < 0.985 * ema25 and price < 0.97 * ema7
        tp1, tp2 = round(price + atr * 1.0, 4), round(price + atr * 1.8, 4)
        tp1_pct, tp2_pct = round((tp1 - price) / price * 100, 2), round((tp2 - price) / price * 100, 2)
        trend = trend_strength(closes, volumes_data)
        macd_hist = calculate_macd(closes)

        score = sum([
            bool(candle), "Divergence" in divergence, "Dekat" in zone,
            vol_spike, not support_patah
        ])

        if score < 3:
            return None

        msg = f"""{strategy} • {tf_interval}
✅ {symbol}
Harga: ${price:.3f}
EMA7: {ema7:.3f} | EMA25: {ema25:.3f} | EMA99: {ema99:.3f}
RSI(6): {rsi} | ATR(14): {atr:.4f}
📈 Volume: ${volume:,.0f}

🎯 Entry: ${price:.3f}
🎯 TP1: ${tp1} (+{tp1_pct}%)
🎯 TP2: ${tp2} (+{tp2_pct}%)
🎯 Confidence Score: {score}/5
"""
        if candle: msg += f"📌 Pattern: {candle}\n"
        if divergence: msg += f"{divergence}\n"
        if zone: msg += f"📍 {zone}\n"
        if vol_spike: msg += "💥 Volume Spike\n"
        if support_patah: msg += "⚠️ *Waspada! Support patah*\n"
        msg += f"📊 Trend: {trend}\n"
        msg += f"🧬 MACD Cross: {'Bullish' if macd_hist > 0 else 'Bearish'}\n"
        return msg
    except:
        return None

# ========== BOT HANDLER ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["1️⃣ Trading Spot", "2️⃣ Info"], ["3️⃣ Help"]]
    await update.message.reply_text("🤖 Selamat datang! Pilih menu di bawah ini:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "1️⃣ Trading Spot":
        keyboard = [["🔴 Jemput Bola"], ["🟡 Rebound Swing"], ["🟢 Scalping Breakout"], ["🔙 Kembali ke Menu Utama"]]
        await update.message.reply_text("📊 Pilih Mode Strategi:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

    elif text == "2️⃣ Info":
        await update.message.reply_text("""
📌 Jadwal Ideal:
🔴 Jemput Bola: Pagi 07.30–08.30 WIB
🟡 Rebound Swing: Siang–Sore
🟢 Scalping Breakout: Malam 19.00–22.00 WIB
Gunakan sesuai momentum. Tetap DYOR ya!
""")

    elif text == "3️⃣ Help":
        await update.message.reply_text("💬 Hubungi @KikioOreo untuk panduan & aktivasi akses.")

    elif text == "🔙 Kembali ke Menu Utama":
        await start(update, context)

    elif text in STRATEGIES:
        if user_id not in ALLOWED_USERS:
            await update.message.reply_text("⛔ Akses ditolak.")
            return
        await update.message.reply_text(f"🔍 Memindai sinyal untuk *{text}*...\nTunggu beberapa detik...", parse_mode="Markdown")

        strategy = STRATEGIES[text]
        hasil = []
        for pair in PAIRS:
            price = get_price(pair)
            volume = get_volume(pair)
            if price == -1 or volume < strategy["volume_min"]:
                continue
            valid_tf = [analisa_strategi_pro(pair, text, price, volume, tf) for tf in TF_INTERVALS.values()]
            valid_msgs = [msg for msg in valid_tf if msg]
            if len(valid_msgs) >= 2:
                hasil.append(valid_msgs[0])

        if hasil:
            for msg in hasil:
                await update.message.reply_text(msg, parse_mode="Markdown")
                await asyncio.sleep(0.5)
            await update.message.reply_text("✅ *Selesai scan. Sinyal layak ditemukan.*", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Tidak ada sinyal strategi yang layak saat ini.")
    else:
        await update.message.reply_text("⛔ Perintah tidak dikenali.")

# ========== MAIN FUNCTION ==========

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
