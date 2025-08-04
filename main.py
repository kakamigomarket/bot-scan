# main.py — Debug + EMA99 + TP • RESILIENT (tanpa HTML, async send, guards, rate-limit)

import os
import asyncio
import requests
from typing import List, Tuple, Optional
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

# Atur RSI period via env jika mau (mis. RSI_PERIOD=6)
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))

PAIRS = [
    "SEIUSDT","RAYUSDT","PENDLEUSDT","JUPUSDT","ENAUSDT","CRVUSDT","ENSUSDT",
    "FORMUSDT","TAOUSDT","ALGOUSDT","XTZUSDT","CAKEUSDT","HBARUSDT","NEXOUSDT",
    "GALAUSDT","IOTAUSDT","THETAUSDT","CFXUSDT","WIFUSDT","BTCUSDT","ETHUSDT",
    "BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT",
    "AAVEUSDT","ATOMUSDT","INJUSDT","QNTUSDT","ARBUSDT","NEARUSDT","SUIUSDT",
    "LDOUSDT","WLDUSDT","FETUSDT","GRTUSDT","PYTHUSDT","ASRUSDT","HYPERUSDT","TRXUSDT"
]

BINANCE = "https://api.binance.com"


# ---------- Helpers ----------
def is_allowed(user_id: int) -> bool:
    return (user_id in ALLOWED_USERS) if ALLOWED_USERS else True

async def reply_long(update: Update, text: str, chunk: int = 3500):
    """Kirim pesan panjang dengan pemotongan otomatis (tanpa HTML)."""
    for i in range(0, len(text), chunk):
        await update.message.reply_text(text[i:i+chunk], disable_web_page_preview=True)

def fetch_klines(symbol: str, interval: str, limit: int = 120):
    url = f"{BINANCE}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        return data if isinstance(data, list) else None
    except Exception:
        return None

def fetch_ticker(symbol: str):
    url = f"{BINANCE}/api/v3/ticker/24hr?symbol={symbol}"
    try:
        res = requests.get(url, timeout=10)
        d = res.json()
        return float(d["lastPrice"]), float(d["priceChangePercent"]), float(d["quoteVolume"])
    except Exception:
        return None, None, None

def ema(values: list, period: int):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e

def rsi(values: list, period: int = 14):
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
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def volume_breakout(klines, mult: float = 1.3):
    """True jika volume candle terakhir >= mult × avg 20 candle sebelumnya.
       None jika data tidak cukup."""
    try:
        if len(klines) < 22:
            return None
        vols = [float(k[5]) for k in klines[:-1]]
        avg = sum(vols[-20:]) / 20
        now = float(klines[-1][5])
        return now >= mult * avg
    except Exception:
        return None


# ---------- Core (debug) ----------
def debug_signal(pair: str, interval: str):
    price, change, vol = fetch_ticker(pair)
    if price is None or change is None:
        return f"\n❌ {pair} | Note: gagal ambil ticker"

    kl = fetch_klines(pair, interval, 120)
    if not kl:
        return f"\n❌ {pair} | Note: gagal ambil klines"

    closes = [float(k[4]) for k in kl]
    if len(closes) < 100:  # perlu data cukup untuk EMA99
        return f"\n❌ {pair} | Note: data candle kurang (punya {len(closes)}, perlu ≥100)"

    rsi_val = rsi(closes, RSI_PERIOD)
    ema21v = ema(closes, 21)
    ema99v = ema(closes, 99)
    if rsi_val is None or ema21v is None or ema99v is None:
        return f"\n❌ {pair} | Note: indikator tidak cukup (RSI/EMA None)"

    last = closes[-1]
    vol_break = volume_breakout(kl, mult=1.3)

    # Fokus hanya RSI < 40
    if rsi_val >= 40:
        return None

    reasons, passed = [], True

    if not (last > ema21v):
        reasons.append("harga ≤ EMA21"); passed = False

    if vol_break is None:
        reasons.append("data volume kurang"); passed = False
    elif not vol_break:
        reasons.append("volume lemah"); passed = False

    if change is not None and change > 10:
        reasons.append("sudah naik >10% 24h"); passed = False

    if not (last >= (ema99v * 0.95)):
        reasons.append(f"terlalu jauh di bawah EMA99 ({last:.4f} < 95% EMA99)"); passed = False

    status = "✅" if passed else "❌"
    notes = ", ".join(reasons) if reasons else "semua syarat terpenuhi"

    tp_note = ""
    if passed:
        entry_low = ema21v
        entry_high = last
        tp1 = entry_high * 1.05
        tp2 = entry_high * 1.09
        tp_note = (
            f"• Entry: ${entry_low:.4f} – ${entry_high:.4f}\n"
            f"• TP1: ${tp1:.4f} (+5%) | TP2: ${tp2:.4f} (+9%)"
        )

    return (
        f"\n{status} {pair} | RSI({RSI_PERIOD})={rsi_val:.2f} | Harga=${last:.4f} | "
        f"EMA21=${ema21v:.4f} | EMA99=${ema99v:.4f}\n"
        f"Note: {notes}\n{tp_note}"
    )


# ---------- Bot handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_allowed(uid):
        await update.message.reply_text("🚫 Tidak diizinkan.")
        return
    kb = [["/scan_15m", "/scan_1h"], ["/scan_4h", "/scan_1d"]]
    await update.message.reply_text(
        "📊 Ketik /scan_1h untuk sinyal debug. Perintah lain: /scan_15m /scan_4h /scan_1d",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE, tf: str):
    uid = update.effective_user.id
    if not is_allowed(uid):
        await update.message.reply_text("🚫 Tidak diizinkan.")
        return

    await update.message.reply_text(f"🔍 Scan Jemput Bola TF {tf} (Debug Mode)...")

    lines = []
    for p in PAIRS:
        try:
            sig = debug_signal(p, tf)
            if sig:
                lines.append(sig)
        except Exception:
            # Jangan biarkan 1 pair membuat seluruh loop gagal
            lines.append(f"\n❌ {p} | Note: internal error saat proses")
        await asyncio.sleep(0.08)  # ramah rate-limit

    if not lines:
        await update.message.reply_text("✅ Tidak ada token dengan RSI < 40 saat ini.")
    else:
        header = f"📈 Debug Sinyal RSI < 40 • TF {tf}\n"
        await reply_long(update, header + "".join(lines))

async def scan_15m(update: Update, context: ContextTypes.DEFAULT_TYPE): await scan(update, context, "15m")
async def scan_1h(update: Update, context: ContextTypes.DEFAULT_TYPE):  await scan(update, context, "1h")
async def scan_4h(update: Update, context: ContextTypes.DEFAULT_TYPE):  await scan(update, context, "4h")
async def scan_1d(update: Update, context: ContextTypes.DEFAULT_TYPE):  await scan(update, context, "1d")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN belum diatur di Railway")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan_15m", scan_15m))
    app.add_handler(CommandHandler("scan_1h", scan_1h))
    app.add_handler(CommandHandler("scan_4h", scan_4h))
    app.add_handler(CommandHandler("scan_1d", scan_1d))
    print("🤖 Bot aktif (Debug Mode + EMA99 + TP). Perintah: /scan_1h /scan_4h /start")
    app.run_polling()

if __name__ == "__main__":
    main()
