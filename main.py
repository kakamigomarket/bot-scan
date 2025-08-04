import os
import requests
from typing import List, Tuple, Optional
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

PAIRS = [
    "SEIUSDT", "RAYUSDT", "PENDLEUSDT", "JUPUSDT", "ENAUSDT",
    "CRVUSDT", "ENSUSDT", "FORMUSDT", "TAOUSDT", "ALGOUSDT",
    "XTZUSDT", "CAKEUSDT", "HBARUSDT", "NEXOUSDT", "GALAUSDT",
    "IOTAUSDT", "THETAUSDT", "CFXUSDT", "WIFUSDT", "BTCUSDT",
    "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "AAVEUSDT", "ATOMUSDT",
    "INJUSDT", "QNTUSDT", "ARBUSDT", "NEARUSDT", "SUIUSDT",
    "LDOUSDT", "WLDUSDT", "FETUSDT", "GRTUSDT",
    "PYTHUSDT", "ASRUSDT", "HYPERUSDT", "TRXUSDT"
]

BINANCE = "https://api.binance.com"

def is_allowed(user_id: int) -> bool:
    return (user_id in ALLOWED_USERS) if ALLOWED_USERS else True  # allow if not set (testing)

def fetch_klines(symbol: str, interval: str, limit: int = 50):
    url = f"{BINANCE}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        return data if isinstance(data, list) else None
    except Exception:
        return None

def fetch_ticker(symbol: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    url = f"{BINANCE}/api/v3/ticker/24hr?symbol={symbol}"
    try:
        res = requests.get(url, timeout=10)
        d = res.json()
        return float(d["lastPrice"]), float(d["priceChangePercent"]), float(d["quoteVolume"])
    except Exception:
        return None, None, None

def ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period  # SMA seed
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e

def rsi(values: List[float], period: int = 14) -> Optional[float]:
    if len(values) <= period:
        return None
    deltas = [values[i+1] - values[i] for i in range(len(values) - 1)]
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

def volume_breakout(klines: List[List], multiplier: float = 1.3) -> Optional[bool]:
    try:
        if len(klines) < 22:
            return None
        vols = [float(k[5]) for k in klines[:-1]]
        avg = sum(vols[-20:]) / 20
        now = float(klines[-1][5])
        return now >= multiplier * avg
    except Exception:
        return None

def reply_long(update: Update, text: str):
    """Split long messages to avoid Telegram 4096 char limit."""
    CHUNK = 3500
    if len(text) <= CHUNK:
        return update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
    for i in range(0, len(text), CHUNK):
        update.message.reply_text(text[i:i+CHUNK], parse_mode="HTML", disable_web_page_preview=True)

def evaluate_pair(pair: str, interval: str) -> dict:
    """
    Return dict with:
      - ok (bool): whether it passes filters (RSI<40, close>EMA21, vol breakout, change<=10)
      - reason (list[str]): reasons for fail/success
      - metrics: rsi, close, ema21, vol_ok, change, volume
    """
    result = {
        "pair": pair, "ok": False, "reasons": [],
        "rsi": None, "close": None, "ema21": None,
        "vol_ok": None, "change": None, "volume": None
    }

    price, change, volume = fetch_ticker(pair)
    if price is None or change is None or volume is None:
        result["reasons"].append("❌ Gagal fetch ticker")
        return result
    result["close"] = price
    result["change"] = change
    result["volume"] = volume

    if change > 10:
        result["reasons"].append(f"❌ Pump >10% (change {change:.2f}%) → di-skip")
        return result

    kl = fetch_klines(pair, interval, 50)
    if not kl:
        result["reasons"].append("❌ Gagal fetch klines")
        return result

    closes = [float(k[4]) for k in kl]
    rsi14 = rsi(closes, 14)
    ema21v = ema(closes, 21)
    vol_ok = volume_breakout(kl, multiplier=1.3)

    result["rsi"] = rsi14
    result["ema21"] = ema21v
    result["vol_ok"] = vol_ok

    if rsi14 is None:
        result["reasons"].append("❌ RSI tidak tersedia")
    elif rsi14 < 40:
        result["reasons"].append(f"✅ RSI14 {rsi14:.2f} < 40")
    else:
        result["reasons"].append(f"❌ RSI14 {rsi14:.2f} ≥ 40")

    if ema21v is None:
        result["reasons"].append("❌ EMA21 tidak tersedia")
    elif price > ema21v:
        result["reasons"].append(f"✅ Close {price:.6f} > EMA21 {ema21v:.6f}")
    else:
        result["reasons"].append(f"❌ Close {price:.6f} ≤ EMA21 {ema21v:.6f}")

    if vol_ok is None:
        result["reasons"].append("❌ Data volume breakout tidak cukup")
    elif vol_ok:
        result["reasons"].append("✅ Volume breakout ≥ 1.3x rata-rata")
    else:
        result["reasons"].append("❌ Volume breakout < 1.3x rata-rata")

    if (rsi14 is not None and rsi14 < 40) and (ema21v is not None and price > ema21v) and (vol_ok is True):
        result["ok"] = True
        result["reasons"].append("🎯 LULUS semua filter (RSI, EMA21, Volume)")
    else:
        result["reasons"].append("⛔ Tidak lulus filter")

    return result

def build_signal_from_eval(ev: dict) -> Optional[str]:
    if not ev["ok"]:
        return None
    last = ev["close"]
    ema21v = ev["ema21"]
    tp1 = last * 1.05
    tp2 = last * 1.09
    return (
        f"\n🔹 <b>{ev['pair']}</b>\n"
        f"• Harga: ${last:.6f} | RSI: {ev['rsi']:.2f} | EMA21: {ema21v:.6f}\n"
        f"• Entry: ${ema21v:.6f} – ${last:.6f}\n"
        f"• TP1: ${tp1:.6f} (+5.0%) | TP2: ${tp2:.6f} (+9.0%)\n"
    )

def build_debug_line(ev: dict) -> str:
    rsi_txt = "N/A" if ev["rsi"] is None else f"{ev['rsi']:.2f}"
    ema_txt = "N/A" if ev["ema21"] is None else f"{ev['ema21']:.6f}"
    vol_txt = "N/A" if ev["vol_ok"] is None else ("✅" if ev["vol_ok"] else "❌")
    change_txt = "N/A" if ev["change"] is None else f"{ev['change']:.2f}%"
    base = (
        f"\n🔸 <b>{ev['pair']}</b>\n"
        f"• Change 24h: {change_txt}\n"
        f"• RSI14: {rsi_txt} | Close: ${ev['close']:.6f} | EMA21: {ema_txt} | VolOK: {vol_txt}\n"
        f"• Alasan:\n  - " + "\n  - ".join(ev["reasons"])
    )
    if ev["ok"]:
        base += "\n✅ <b>DITERIMA</b>"
    else:
        base += "\n❌ <b>DITOLAK</b>"
    return base

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_allowed(uid):
        await update.message.reply_text("🚫 Tidak diizinkan.")
        return
    kb = [["/scan_15m", "/scan_1h"], ["/scan_4h", "/scan_1d"], ["/debug_15m", "/debug_1h"], ["/debug_4h", "/debug_1d"]]
    await update.message.reply_text(
        "👋 Selamat datang!\n"
        "Perintah cepat:\n"
        "• Scan: /scan_15m /scan_1h /scan_4h /scan_1d\n"
        "• Debug: /debug_15m /debug_1h /debug_4h /debug_1d\n"
        "Debug menampilkan alasan detail kenapa pair diterima/ditolak.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def scan_core(update: Update, interval: str, debug: bool):
    await update.message.reply_text(f"🔍 Memindai TF {interval}{' (DEBUG)' if debug else ''}...")
    accepted = []
    debug_lines = []
    for p in PAIRS:
        ev = evaluate_pair(p, interval)
        if debug:
            debug_lines.append(build_debug_line(ev))
        sig = build_signal_from_eval(ev)
        if sig:
            accepted.append((ev["rsi"], sig))

    if debug:
        header = f"🧪 <b>Hasil Debug TF {interval}</b>\n"
        reply_long(update, header + "".join(debug_lines) if debug_lines else header + "— Tidak ada data —")

    if accepted:
        accepted.sort(key=lambda x: (x[0] if x[0] is not None else 999))
        body = "".join([s for _, s in accepted])
        reply_long(update, f"📈 <b>Sinyal Jemput Bola ({interval})</b>\n" + body)
    else:
        await update.message.reply_text(f"✅ Tidak ada sinyal valid di TF {interval}.")

async def scan_15m(update: Update, context: ContextTypes.DEFAULT_TYPE): await scan_core(update, "15m", debug=False)
async def scan_1h(update: Update, context: ContextTypes.DEFAULT_TYPE):  await scan_core(update, "1h",  debug=False)
async def scan_4h(update: Update, context: ContextTypes.DEFAULT_TYPE):  await scan_core(update, "4h",  debug=False)
async def scan_1d(update: Update, context: ContextTypes.DEFAULT_TYPE):  await scan_core(update, "1d",  debug=False)

async def debug_15m(update: Update, context: ContextTypes.DEFAULT_TYPE): await scan_core(update, "15m", debug=True)
async def debug_1h(update: Update, context: ContextTypes.DEFAULT_TYPE):  await scan_core(update, "1h",  debug=True)
async def debug_4h(update: Update, context: ContextTypes.DEFAULT_TYPE):  await scan_core(update, "4h",  debug=True)
async def debug_1d(update: Update, context: ContextTypes.DEFAULT_TYPE):  await scan_core(update, "1d",  debug=True)

def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN belum diatur di Railway")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan_15m", scan_15m))
    app.add_handler(CommandHandler("scan_1h", scan_1h))
    app.add_handler(CommandHandler("scan_4h", scan_4h))
    app.add_handler(CommandHandler("scan_1d", scan_1d))
    app.add_handler(CommandHandler("debug_15m", debug_15m))
    app.add_handler(CommandHandler("debug_1h", debug_1h))
    app.add_handler(CommandHandler("debug_4h", debug_4h))
    app.add_handler(CommandHandler("debug_1d", debug_1d))

    print("🤖 Bot aktif. Perintah: /scan_15m /scan_1h /scan_4h /scan_1d | Debug: /debug_15m /debug_1h /debug_4h /debug_1d")
    app.run_polling()

if __name__ == "__main__":
    main()
