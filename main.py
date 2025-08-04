# main.py — Versi optimal sinyal Jemput Bola (filter efektif, tidak terlalu ketat)

import os
import requests
from typing import List, Tuple, Optional
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

PAIRS = ["SEIUSDT", "RAYUSDT", "PENDLEUSDT", "JUPUSDT", "ENAUSDT", "CRVUSDT", "ENSUSDT",
         "FORMUSDT", "TAOUSDT", "ALGOUSDT", "XTZUSDT", "CAKEUSDT", "HBARUSDT", "NEXOUSDT",
         "GALAUSDT", "IOTAUSDT", "THETAUSDT", "CFXUSDT", "WIFUSDT", "BTCUSDT", "ETHUSDT",
         "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT",
         "AAVEUSDT", "ATOMUSDT", "INJUSDT", "QNTUSDT", "ARBUSDT", "NEARUSDT", "SUIUSDT",
         "LDOUSDT", "WLDUSDT", "FETUSDT", "GRTUSDT", "PYTHUSDT", "ASRUSDT", "HYPERUSDT", "TRXUSDT"]

BINANCE = "https://api.binance.com"

def is_allowed(user_id: int) -> bool:
    return (user_id in ALLOWED_USERS) if ALLOWED_USERS else True

def fetch_klines(symbol: str, interval: str, limit: int = 50):
    url = f"{BINANCE}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url, timeout=10)
        return res.json()
    except:
        return None

def fetch_ticker(symbol: str):
    url = f"{BINANCE}/api/v3/ticker/24hr?symbol={symbol}"
    try:
        res = requests.get(url, timeout=10)
        d = res.json()
        return float(d['lastPrice']), float(d['priceChangePercent']), float(d['quoteVolume'])
    except:
        return None, None, None

def ema(values: List[float], period: int):
    k = 2 / (period + 1)
    ema_val = sum(values[:period]) / period
    for price in values[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val

def rsi(values: List[float], period: int = 14):
    if len(values) <= period:
        return None
    deltas = [values[i+1] - values[i] for i in range(len(values)-1)]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def volume_breakout(klines):
    try:
        vols = [float(k[5]) for k in klines[:-1]]
        avg = sum(vols[-20:]) / 20
        now = float(klines[-1][5])
        return now >= 1.3 * avg
    except:
        return False

def build_signal(pair: str, interval: str):
    price, change, vol = fetch_ticker(pair)
    if not price or change > 10:
        return None
    kl = fetch_klines(pair, interval, 50)
    if not kl: return None
    closes = [float(k[4]) for k in kl]
    rsi_val = rsi(closes)
    ema21v = ema(closes, 21)
    last = closes[-1]
    if rsi_val < 40 and last > ema21v and volume_breakout(kl):
        tp1 = last * 1.05
        tp2 = last * 1.09
        return f"\n🔹 <b>{pair}</b>\n" \
               f"• Harga: ${last:.4f} | RSI: {rsi_val:.2f} | EMA21: {ema21v:.4f}\n" \
               f"• Entry: ${ema21v:.4f} – ${last:.4f}\n" \
               f"• TP1: ${tp1:.4f} (+5.0%) | TP2: ${tp2:.4f} (+9.0%)\n"
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_allowed(uid):
        await update.message.reply_text("🚫 Tidak diizinkan.")
        return
    kb = [["/scan_15m", "/scan_1h"], ["/scan_4h", "/scan_1d"]]
    await update.message.reply_text("📊 Ketik /scan_1h untuk sinyal. Perintah lain: /scan_15m /scan_4h /scan_1d",
                                    reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE, tf: str):
    uid = update.effective_user.id
    if not is_allowed(uid):
        await update.message.reply_text("🚫 Tidak diizinkan.")
        return
    await update.message.reply_text(f"🔍 Scan Jemput Bola TF {tf}...")
    result = ""
    for p in PAIRS:
        sig = build_signal(p, tf)
        if sig:
            result += sig
    if not result:
        await update.message.reply_text("✅ Tidak ada sinyal valid saat ini.")
    else:
        await update.message.reply_text(f"📈 <b>Sinyal Jemput Bola ({tf})</b>\n{result}", parse_mode="HTML")

async def scan_15m(update: Update, context: ContextTypes.DEFAULT_TYPE): await scan(update, context, "15m")
async def scan_1h(update: Update, context: ContextTypes.DEFAULT_TYPE): await scan(update, context, "1h")
async def scan_4h(update: Update, context: ContextTypes.DEFAULT_TYPE): await scan(update, context, "4h")
async def scan_1d(update: Update, context: ContextTypes.DEFAULT_TYPE): await scan(update, context, "1d")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN belum diatur di Railway")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan_15m", scan_15m))
    app.add_handler(CommandHandler("scan_1h", scan_1h))
    app.add_handler(CommandHandler("scan_4h", scan_4h))
    app.add_handler(CommandHandler("scan_1d", scan_1d))
    print("🤖 Bot aktif. Perintah: /scan_1h /scan_4h /start")
    app.run_polling()

if __name__ == "__main__":
    main()
