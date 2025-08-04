# main.py — TP Adaptif + EMA99 + Debug (tanpa HTML, async send, guards, rate-limit)

import os
import asyncio
import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ========= ENV =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")  # contoh: "12345,67890"
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))  # bisa 6 jika ingin RSI(6)

# ========= LIST PAIRS (lengkap) =========
PAIRS = [
    "SEIUSDT","RAYUSDT","PENDLEUSDT","JUPUSDT","ENAUSDT","CRVUSDT","ENSUSDT",
    "FORMUSDT","TAOUSDT","ALGOUSDT","XTZUSDT","CAKEUSDT","HBARUSDT","NEXOUSDT",
    "GALAUSDT","IOTAUSDT","THETAUSDT","CFXUSDT","WIFUSDT","BTCUSDT","ETHUSDT",
    "BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT",
    "AAVEUSDT","ATOMUSDT","INJUSDT","QNTUSDT","ARBUSDT","NEARUSDT","SUIUSDT",
    "LDOUSDT","WLDUSDT","FETUSDT","GRTUSDT","PYTHUSDT","ASRUSDT","HYPERUSDT","TRXUSDT"
]

BINANCE = "https://api.binance.com"

# ========= TP ADAPTIF =========
TP_CONFIG = {
    "LOW":    {"TP1": 0.05, "TP2": 0.08},  # contoh: ADA, XRP
    "MEDIUM": {"TP1": 0.06, "TP2": 0.10},  # contoh: CRV, CFX, SEI
    "HIGH":   {"TP1": 0.08, "TP2": 0.13},  # contoh: WIF, JUP, RAY
}
TOKEN_TYPE = {
    "ADAUSDT": "LOW", "XRPUSDT": "LOW", "DOGEUSDT": "LOW",
    "CRVUSDT": "MEDIUM", "CFXUSDT": "MEDIUM", "SEIUSDT": "MEDIUM",
    "WIFUSDT": "HIGH", "JUPUSDT": "HIGH", "RAYUSDT": "HIGH",
}
DEFAULT_CAT = "MEDIUM"

# ========= HELPERS =========
def is_allowed(user_id: int) -> bool:
    # Jika ALLOWED_IDS kosong, izinkan semua (untuk testing); jika ada, harus ada di daftar
    return (user_id in ALLOWED_USERS) if ALLOWED_USERS else True

async def reply_long(update: Update, text: str, chunk: int = 3500):
    """Kirim pesan panjang dengan pemotongan otomatis (tanpa HTML)."""
    for i in range(0, len(text), chunk):
        await update.message.reply_text(text[i:i+chunk], disable_web_page_preview=True)

def fetch_klines(symbol: str, interval: str, limit: int = 120):
    url = f"{BINANCE}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        return data if isinstance(data, list) else None
    except Exception:
        return None

def fetch_ticker(symbol: str):
    url = f"{BINANCE}/api/v3/ticker/24hr?symbol={symbol}"
    try:
        r = requests.get(url, timeout=10)
        d = r.json()
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
        avg_gain = (avg_gain*(period-1) + gains[i]) / period
        avg_loss = (avg_loss*(period-1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def volume_breakout(klines, mult: float = 1.3):
    """Return (flag, now, avg). flag=True jika volume terakhir >= mult * avg20. None jika data kurang."""
    try:
        if len(klines) < 22:
            return None, 0.0, 0.0
        vols = [float(k[5]) for k in klines[:-1]]
        avg = sum(vols[-20:]) / 20
        now = float(klines[-1][5])
        return (now >= mult * avg), now, avg
    except Exception:
        return None, 0.0, 0.0

def dynamic_multiplier(rsi_val: float, vol_now: float, vol_avg: float, last: float, ema99v: float) -> float:
    """Hitung multiplier TP berbasis kondisi market. Batas 0.8–1.2 (aman)."""
    m = 1.0
    if rsi_val is not None and rsi_val < 30:   # oversold dalam → target lebih berani
        m += 0.10
    if vol_avg > 0 and vol_now >= 2.0 * vol_avg:  # ledakan volume → tambah target
        m += 0.10
    if ema99v is not None and last > ema99v:   # sudah di atas EMA99 → tren besar dukung
        m += 0.05
    # clamp
    if m > 1.20: m = 1.20
    if m < 0.80: m = 0.80
    return m

# ========= CORE (debug & sinyal) =========
def debug_signal(pair: str, interval: str):
    price, change, _ = fetch_ticker(pair)
    if price is None or change is None:
        return f"\n❌ {pair} | Note: gagal ambil ticker"

    kl = fetch_klines(pair, interval, 120)
    if not kl:
        return f"\n❌ {pair} | Note: gagal ambil klines"

    closes = [float(k[4]) for k in kl]
    if len(closes) < 100:
        return f"\n❌ {pair} | Note: data candle kurang (punya {len(closes)}, perlu ≥100)"

    rsi_val = rsi(closes, RSI_PERIOD)
    ema21v = ema(closes, 21)
    ema99v = ema(closes, 99)
    if rsi_val is None or ema21v is None or ema99v is None:
        return f"\n❌ {pair} | Note: indikator tidak cukup (RSI/EMA None)"

    last = closes[-1]
    vol_ok, v_now, v_avg = volume_breakout(kl, mult=1.3)

    # Fokus kandidat: RSI < 40
    if rsi_val >= 40:
        return None

    # Evaluasi filter
    reasons, passed = [], True
    if not (last > ema21v):                   reasons.append("harga ≤ EMA21"); passed = False
    if vol_ok is None:                        reasons.append("data volume kurang"); passed = False
    elif not vol_ok:                          reasons.append("volume lemah"); passed = False
    if change is not None and change > 10:    reasons.append("sudah naik >10% 24h"); passed = False
    if not (last >= ema99v * 0.95):           reasons.append(f"terlalu jauh di bawah EMA99 ({last:.4f} < 95% EMA99)"); passed = False

    status = "✅" if passed else "❌"
    notes = ", ".join(reasons) if reasons else "semua syarat terpenuhi"

    # Hitung TP adaptif bila lolos
    tp_note = ""
    if passed:
        cat = TOKEN_TYPE.get(pair, DEFAULT_CAT)
        base = TP_CONFIG.get(cat, TP_CONFIG[DEFAULT_CAT])
        mult = dynamic_multiplier(rsi_val, v_now, v_avg, last, ema99v)

        entry_low, entry_high = ema21v, last
        tp1 = entry_high * (1 + base["TP1"] * mult)
        tp2 = entry_high * (1 + base["TP2"] * mult)

        tp_note = (
            f"• Entry: ${entry_low:.4f} – ${entry_high:.4f}\n"
            f"• TP1: ${tp1:.4f} (+{base['TP1']*mult*100:.1f}%) | "
            f"TP2: ${tp2:.4f} (+{base['TP2']*mult*100:.1f}%)\n"
            f"• Cat: {cat} | Multiplier: {mult:.2f}"
        )

    return (
        f"\n{status} {pair} | RSI({RSI_PERIOD})={rsi_val:.2f} | Harga=${last:.4f} | "
        f"EMA21=${ema21v:.4f} | EMA99=${ema99v:.4f}\n"
        f"Note: {notes}\n{tp_note}"
    )

# ========= BOT HANDLERS =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_allowed(uid):
        await update.message.reply_text("🚫 Tidak diizinkan.")
        return
    kb = [["/scan_15m", "/scan_1h"], ["/scan_4h", "/scan_1d"]]
    await update.message.reply_text(
        "👋 Selamat datang!\n"
        "Perintah cepat:\n"
        "• Scan: /scan_15m /scan_1h /scan_4h /scan_1d\n"
        "RSI period bisa diatur via env: RSI_PERIOD (default 14)",
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
            # jangan biarkan satu pair menggagalkan semuanya
            lines.append(f"\n❌ {p} | Note: internal error saat proses")
        await asyncio.sleep(0.08)  # ramah rate-limit

    if not lines:
        await update.message.reply_text("✅ Tidak ada token kandidat RSI < 40 saat ini.")
    else:
        header = f"📈 Debug Sinyal RSI < 40 • TF {tf}\n"
        await reply_long(update, header + "".join(lines))

async def scan_15m(update: Update, context: ContextTypes.DEFAULT_TYPE): await scan(update, context, "15m")
async def scan_1h(update: Update, context: ContextTypes.DEFAULT_TYPE):  await scan(update, context, "1h")
async def scan_4h(update: Update, context: ContextTypes.DEFAULT_TYPE):  await scan(update, context, "4h")
async def scan_1d(update: Update, context: ContextTypes.DEFAULT_TYPE):  await scan(update, context, "1d")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN belum diatur di environment")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan_15m", scan_15m))
    app.add_handler(CommandHandler("scan_1h", scan_1h))
    app.add_handler(CommandHandler("scan_4h", scan_4h))
    app.add_handler(CommandHandler("scan_1d", scan_1d))
    print("🤖 Bot aktif (TP adaptif + EMA99 + Debug Mode). Perintah: /start /scan_1h /scan_4h")
    app.run_polling()

if __name__ == "__main__":
    main()
