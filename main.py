# ========== IMPORT & KONFIGURASI ==========

import os
import requests
import asyncio
import time
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN") or "ISI_TOKEN_BOT_DISINI"
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "123456789")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

# Cache harga dan volume
CACHE = {"price": {}, "volume": {}, "time": 0}

# ========== FUNGSI API DENGAN CACHE ==========

def get_price(symbol):
    now = time.time()
    if symbol in CACHE["price"] and now - CACHE["time"] < 60:
        return CACHE["price"][symbol]
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=10)
        price = float(r.json()["price"])
        CACHE["price"][symbol] = price
        CACHE["time"] = now
        return price
    except Exception as e:
        print(f"[ERROR get_price] {symbol}: {e}")
        return -1

def get_volume(symbol):
    now = time.time()
    if symbol in CACHE["volume"] and now - CACHE["time"] < 60:
        return CACHE["volume"][symbol]
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}", timeout=10)
        volume = float(r.json()["quoteVolume"])
        CACHE["volume"][symbol] = volume
        CACHE["time"] = now
        return volume
    except Exception as e:
        print(f"[ERROR get_volume] {symbol}: {e}")
        return 0

# ========== FUNGSI EMA & RSI AKURAT ==========

def ema(values, period):
    multiplier = 2 / (period + 1)
    ema_values = [sum(values[:period]) / period]
    for price in values[period:]:
        ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values

def calculate_rsi(closes, period=6):
    if len(closes) < period + 1:
        return 0
    deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period or 1
    rsis = []
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period or 1
        rs = avg_gain / avg_loss
        rsis.append(100 - (100 / (1 + rs)))
    return round(rsis[-1], 2) if rsis else 0

def calculate_macd(closes):
    if len(closes) < 35:
        return 0
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd_line = [a - b for a, b in zip(ema12[-len(ema26):], ema26)]
    signal_line = ema(macd_line, 9)
    hist = macd_line[-1] - signal_line[-1] if len(signal_line) else 0
    return round(hist, 4)

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

def btc_market_trend():
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=99"
        data = requests.get(url, timeout=10).json()
        closes = [float(k[4]) for k in data]
        rsi = calculate_rsi(closes)
        ema7 = sum(closes[-7:]) / 7
        ema25 = sum(closes[-25:]) / 25
        ema99 = sum(closes[-99:]) / 99
        if closes[-1] > ema7 > ema25 > ema99 and rsi > 55:
            return "UP"
        elif closes[-1] < ema7 < ema25 < ema99 and rsi < 45:
            return "DOWN"
        else:
            return "SIDEWAYS"
    except Exception as e:
        print(f"[ERROR btc_market_trend] {e}")
        return "SIDEWAYS"

def analisa_strategi_pro(symbol, strategy, price, volume, tf_interval, market_trend):
    try:
        if market_trend == "DOWN" and strategy != "🔴 Jemput Bola":
            return None  # hanya Jemput Bola yang dibolehkan saat trend turun

        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={tf_interval}&limit=100"
        data = requests.get(url, timeout=10).json()
        closes = [float(k[4]) for k in data]
        opens = [float(k[1]) for k in data]
        highs = [float(k[2]) for k in data]
        lows = [float(k[3]) for k in data]
        volumes_data = [float(k[5]) for k in data]

        rsi = calculate_rsi(closes)
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
        if not is_valid:
            return None

        candle = detect_candle_pattern(opens, closes, highs, lows)
        divergence = detect_divergence(closes, [rsi]*len(closes))
        zone = proximity_to_support_resistance(closes)
        vol_spike = is_volume_spike(volumes_data)
        support_patah = price < 0.985 * ema25 and price < 0.97 * ema7
        tp1, tp2 = round(price + atr * 1.0, 4), round(price + atr * 1.8, 4)
        tp1_pct, tp2_pct = round((tp1 - price) / price * 100, 2), round((tp2 - price) / price * 100, 2)
        trend = trend_strength(closes, volumes_data)
        macd_hist = calculate_macd(closes)

        # Hitung skor confidence + tf valid
        score = sum([
            bool(candle),
            "Divergence" in divergence,
            "Dekat" in zone,
            vol_spike,
            not support_patah
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
    except Exception as e:
        print(f"[ERROR analisa_strategi_pro] {symbol} {tf_interval}: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["1️⃣ Trading Spot", "2️⃣ Info"], ["3️⃣ Help"]]
    await update.message.reply_text("🤖 Selamat datang di Bot Sinyal Trading Crypto!\nPilih menu di bawah ini:", 
                                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Akses ditolak. Kamu tidak terdaftar sebagai pengguna.")
        return

    if text == "1️⃣ Trading Spot":
        keyboard = [["🔴 Jemput Bola"], ["🟡 Rebound Swing"], ["🟢 Scalping Breakout"], ["🔙 Kembali ke Menu Utama"]]
        await update.message.reply_text("📊 Pilih Mode Strategi:", 
                                        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

    elif text == "2️⃣ Info":
        await update.message.reply_text("""
📌 Jadwal Ideal Strategi:
🔴 Jemput Bola: 07.30–08.30 WIB
🟡 Rebound Swing: Siang–Sore
🟢 Scalping Breakout: Malam 19.00–22.00 WIB
Gunakan sesuai momentum pasar & arah BTC!
""")

    elif text == "3️⃣ Help":
        await update.message.reply_text("💬 Hubungi admin @KikioOreo untuk bantuan atau aktivasi.")

    elif text == "🔙 Kembali ke Menu Utama":
        await start(update, context)

    elif text in STRATEGIES:
        await update.message.reply_text(f"🔍 Memindai sinyal untuk strategi *{text}*...\nTunggu beberapa saat...", parse_mode="Markdown")
        strategy = STRATEGIES[text]
        trend_btc = btc_market_trend()

        hasil = []
        for pair in PAIRS:
            price = get_price(pair)
            volume = get_volume(pair)
            if price == -1 or volume < strategy["volume_min"]:
                continue

            valid_msgs = []
            for tf in TF_INTERVALS.values():
                msg = analisa_strategi_pro(pair, text, price, volume, tf, trend_btc)
                if msg: valid_msgs.append(msg)

            if len(valid_msgs) >= 2:
                hasil.append(valid_msgs[0])  # hanya kirim satu sinyal utama

        if hasil:
            for msg in hasil:
                await update.message.reply_text(msg, parse_mode="Markdown")
                await asyncio.sleep(0.5)
            await update.message.reply_text("✅ *Scan selesai. Sinyal layak ditemukan.*", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Tidak ada sinyal layak saat ini. Coba di waktu lain.")
    else:
        await update.message.reply_text("❌ Perintah tidak dikenali. Gunakan tombol menu.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
