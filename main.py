"""
Crypto Signal Bot – Async Refactor (aiohttp + better TA)

Add-ons (Aug 2025):
- Multi‑Timeframe (MTF) confirmation (TF15 confirms TF1h for direction)
- ADX/DMI filter (trend strength)
- Volatility regime via ATR%
- Liquidity guard (avg trades/candle)
- Weighted confidence score (no partial TP/TSL). SL ATR only as info.

Requirements:
- python-telegram-bot >= 21.0
- aiohttp >= 3.9

ENV variables (Railway / .env):
- BOT_TOKEN           -> token bot Telegram
- ALLOWED_IDS         -> daftar user id, dipisah koma. contoh: "123,456"

"""

from __future__ import annotations

import os
import time
import math
import asyncio
import logging
from typing import Dict, Tuple, List, Optional

import aiohttp
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
)

# ===================== CONFIG & GLOBALS =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN belum diset di environment.")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("signal-bot")

# Concurrency limits
HTTP_CONCURRENCY = int(os.getenv("HTTP_CONCURRENCY", "12"))
ANALYSIS_CONCURRENCY = int(os.getenv("ANALYSIS_CONCURRENCY", "8"))

# Threshold & knobs (mudah di-tune)
ADX_MIN = 22.0              # minimal adx untuk anggap trend cukup kuat
ATR_PCT_MIN_BREAKOUT = 0.12 # %; hindari breakout saat volatilitas sangat tipis
AVG_TRADES_MIN = 120        # rata-rata trades/candle minimum (liquidity guard)
REQUIRE_2_TF = True         # butuh minimal 2 TF valid untuk alert

# Pairs & Strategy setup
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
    "🔴 Jemput Bola": {"rsi_limit": 40, "volume_min_usd": 2_000_000},
    "🟡 Rebound Swing": {"rsi_limit": 50, "volume_min_usd": 3_000_000},
    "🟢 Scalping Breakout": {"rsi_limit": 60, "volume_min_usd": 5_000_000},
}

TF_INTERVALS = {
    "TF15": "15m",
    "TF1h": "1h",
    "TF4h": "4h",
    "TF1d": "1d",
}

# Window support/resistance per TF
SR_WINDOW = {
    "15m": 30,
    "1h": 50,
    "4h": 80,
    "1d": 120,
}

# ===================== UTIL: INDICATORS =====================

def ema_series(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append((v - out[-1]) * k + out[-1])
    return out


def rsi_series(closes: List[float], period: int = 14) -> List[float]:
    if len(closes) < period + 1:
        return []
    deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsis: List[float] = []
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0 and avg_gain == 0:
            rs = 1.0
        elif avg_loss == 0:
            rs = float('inf')
        elif avg_gain == 0:
            rs = 0.0
        else:
            rs = avg_gain / avg_loss
        rsi = (100.0 if rs == float('inf') else 0.0) if rs in (float('inf'), 0.0) else (100 - 100 / (1 + rs))
        rsis.append(rsi)
    return rsis


def macd_histogram(closes: List[float]) -> float:
    if len(closes) < 35:
        return 0.0
    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    # align lengths
    min_len = min(len(ema12), len(ema26))
    macd_line = [a - b for a, b in zip(ema12[-min_len:], ema26[-min_len:])]
    signal = ema_series(macd_line, 9)
    return round((macd_line[-1] - signal[-1]) if signal else 0.0, 4)


def true_range(h: float, l: float, pc: float) -> float:
    return max(h - l, abs(h - pc), abs(l - pc))


def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 0.0
    trs: List[float] = []
    for i in range(1, len(closes)):
        trs.append(true_range(highs[i], lows[i], closes[i-1]))
    return sum(trs[-period:]) / period

# --- DMI/ADX ---

def dmi_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Tuple[float, float, float]:
    """Return (+DI, -DI, ADX)."""
    if len(closes) <= period + 1:
        return (0.0, 0.0, 0.0)
    # True Range & directional movement
    trs: List[float] = []
    plus_dm: List[float] = []
    minus_dm: List[float] = []
    for i in range(1, len(closes)):
        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]
        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
        trs.append(true_range(highs[i], lows[i], closes[i-1]))
    # Wilder's smoothing
    def wilder_smooth(arr: List[float], p: int) -> List[float]:
        if len(arr) < p:
            return []
        smoothed = [sum(arr[:p])]
        for x in arr[p:]:
            smoothed.append(smoothed[-1] - (smoothed[-1] / p) + x)
        return smoothed
    atr_w = [x / period for x in wilder_smooth(trs, period)]
    pdm_w = [x / period for x in wilder_smooth(plus_dm, period)]
    mdm_w = [x / period for x in wilder_smooth(minus_dm, period)]
    if not atr_w or not pdm_w or not mdm_w:
        return (0.0, 0.0, 0.0)
    plus_di = [100 * (p / t) if t else 0.0 for p, t in zip(pdm_w[-len(atr_w):], atr_w)]
    minus_di = [100 * (m / t) if t else 0.0 for m, t in zip(mdm_w[-len(atr_w):], atr_w)]
    dx = [100 * abs(p - m) / (p + m) if (p + m) else 0.0 for p, m in zip(plus_di, minus_di)]
    if len(dx) < period:
        return (plus_di[-1], minus_di[-1], 0.0)
    # ADX as Wilder's smoothed DX
    adx_vals = [sum(dx[:period]) / period]
    for x in dx[period:]:
        adx_vals.append((adx_vals[-1] * (period - 1) + x) / period)
    return (plus_di[-1], minus_di[-1], adx_vals[-1])

# --- Patterns & helpers ---

def detect_candle_pattern(opens: List[float], closes: List[float], highs: List[float], lows: List[float]) -> str:
    o, c, h, l = opens[-1], closes[-1], highs[-1], lows[-1]
    body = abs(c - o)
    rng = max(h - l, 1e-9)
    upper = h - max(o, c)
    lower = min(o, c) - l
    if body <= 0.1 * rng:
        return "Doji"
    if lower > 2 * body and upper < body:
        return "Hammer"
    if closes[-2] < opens[-2] and c > o and c > opens[-2] and o < closes[-2]:
        return "Engulfing"
    return ""


def detect_divergence(prices: List[float], rsis: List[float]) -> str:
    if len(prices) < 5 or len(rsis) < 5:
        return ""
    p1, p2 = prices[-5], prices[-1]
    r1, r2 = rsis[-5], rsis[-1]
    if p2 > p1 and r2 < r1:
        return "🔻 Bearish Divergence"
    if p2 < p1 and r2 > r1:
        return "🔺 Bullish Divergence"
    return ""


def proximity_to_sr(closes: List[float], tf: str) -> str:
    win = SR_WINDOW.get(tf, 30)
    recent = closes[-win:]
    support, resistance, price = min(recent), max(recent), closes[-1]
    if support <= 0 or resistance <= 0:
        return ""
    dist_support = (price - support) / support * 100
    dist_resist = (resistance - price) / resistance * 100
    if dist_support < 2:
        return "Dekat Support"
    if dist_resist < 2:
        return "Dekat Resistance"
    return ""


def is_volume_spike(volumes: List[float]) -> bool:
    if len(volumes) < 21:
        return False
    avg = sum(volumes[-20:-1]) / 19
    return volumes[-1] > 1.5 * avg if avg > 0 else False


def trend_strength(closes: List[float], volumes: List[float]) -> str:
    if len(closes) < 30 or len(volumes) < 20:
        return "Sideways ⏸️"
    ema10 = sum(closes[-10:]) / 10
    ema30 = sum(closes[-30:]) / 30
    slope = ema10 - ema30
    avg_vol = sum(volumes[-20:]) / 20
    if slope > 0 and volumes[-1] > 1.2 * avg_vol:
        return "Uptrend 🔼"
    if slope < 0 and volumes[-1] > 1.2 * avg_vol:
        return "Downtrend 🔽"
    return "Sideways ⏸️"

# ===================== BINANCE CLIENT (async + cache) =====================

class BinanceClient:
    BASE = "https://api.binance.com"

    def __init__(self, session: aiohttp.ClientSession, http_sem: asyncio.Semaphore):
        self.sess = session
        self.http_sem = http_sem
        # cache: {bucket: {symbol: (value, ts)}}
        self.cache: Dict[str, Dict[str, Tuple[float, float]]] = {
            "price": {},
            "volume": {},
            "ticker24": {},
        }
        self.ttl = {
            "price": 30,
            "volume": 60,
            "ticker24": 30,
        }

    def _fresh(self, bucket: str, symbol: str) -> bool:
        if symbol not in self.cache[bucket]:
            return False
        _, ts = self.cache[bucket][symbol]
        return (time.time() - ts) < self.ttl[bucket]

    async def _get(self, path: str, params: Optional[dict] = None):
        url = f"{self.BASE}{path}"
        async with self.http_sem:
            async with self.sess.get(url, params=params, timeout=10) as r:
                if r.status != 200:
                    text = await r.text()
                    raise RuntimeError(f"HTTP {r.status}: {text[:120]}")
                return await r.json()

    async def price(self, symbol: str) -> float:
        if self._fresh("price", symbol):
            return self.cache["price"][symbol][0]
        data = await self._get("/api/v3/ticker/price", {"symbol": symbol})
        price = float(data["price"])  # type: ignore
        self.cache["price"][symbol] = (price, time.time())
        return price

    async def ticker24h(self, symbol: str) -> dict:
        if self._fresh("ticker24", symbol):
            return {"cached": True, **{"data": self.cache["ticker24"][symbol][0]}}
        data = await self._get("/api/v3/ticker/24hr", {"symbol": symbol})
        self.cache["ticker24"][symbol] = (data, time.time())
        return {"cached": False, **{"data": data}}

    async def quote_volume_24h(self, symbol: str) -> float:
        t = await self.ticker24h(symbol)
        data = t["data"]
        return float(data.get("quoteVolume", 0.0))

    async def klines(self, symbol: str, interval: str, limit: int = 120) -> List[List[float]]:
        data = await self._get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
        return data  # raw kline rows

# ===================== MARKET STATE & MTF =====================

async def btc_market_trend(client: BinanceClient) -> str:
    try:
        data = await client.klines("BTCUSDT", "1h", 99)
        closes = [float(k[4]) for k in data]
        ema7 = sum(closes[-7:]) / 7
        ema25 = sum(closes[-25:]) / 25
        ema99 = sum(closes[-99:]) / 99
        rsi_last = rsi_series(closes, period=14)
        r = rsi_last[-1] if rsi_last else 50
        if closes[-1] > ema7 > ema25 > ema99 and r > 55:
            return "UP"
        if closes[-1] < ema7 < ema25 < ema99 and r < 45:
            return "DOWN"
        return "SIDEWAYS"
    except Exception as e:
        log.warning(f"btc_market_trend error: {e}")
        return "SIDEWAYS"

async def analisa_trend_ringkas(client: BinanceClient, symbol: str, tf: str = "1h") -> str:
    try:
        data = await client.klines(symbol, tf, 99)
        closes = [float(k[4]) for k in data]
        ema7 = sum(closes[-7:]) / 7
        ema25 = sum(closes[-25:]) / 25
        ema99 = sum(closes[-99:]) / 99
        rsi_last = rsi_series(closes, 14)
        r = rsi_last[-1] if rsi_last else 50
        if closes[-1] > ema7 > ema25 > ema99 and r > 55:
            return "UP"
        if closes[-1] < ema7 < ema25 < ema99 and r < 45:
            return "DOWN"
        return "SIDEWAYS"
    except Exception as e:
        log.info(f"analisa_trend_ringkas {symbol} {tf}: {e}")
        return "SIDEWAYS"

# ===================== STRATEGY ANALYZER =====================

async def analisa_strategi_pro(client: BinanceClient, symbol: str, strategy_name: str, price: float, vol24h: float, tf_interval: str, market_trend: str) -> Optional[str]:
    try:
        # Market regime gate: ketika BTC DOWN, hanya Jemput Bola yang diizinkan
        if market_trend == "DOWN" and strategy_name != "🔴 Jemput Bola":
            return None

        data = await client.klines(symbol, tf_interval, 120)
        closes = [float(k[4]) for k in data]
        opens = [float(k[1]) for k in data]
        highs = [float(k[2]) for k in data]
        lows = [float(k[3]) for k in data]
        volumes = [float(k[5]) for k in data]  # base volume per candle
        trades = [int(k[8]) for k in data]     # number of trades per candle

        # Liquidity guard
        avg_tf_trades = sum(trades[-20:]) / min(20, len(trades)) if trades else 0
        if avg_tf_trades < AVG_TRADES_MIN:
            return None

        # Indicators
        rsi_vals = rsi_series(closes, period=6)
        rsi_last = round(rsi_vals[-1], 2) if rsi_vals else 50
        ema7 = sum(closes[-7:]) / 7 if len(closes) >= 7 else closes[-1]
        ema25 = sum(closes[-25:]) / 25 if len(closes) >= 25 else sum(closes) / len(closes)
        ema99 = sum(closes[-99:]) / 99 if len(closes) >= 99 else sum(closes) / len(closes)
        atr14 = atr(highs, lows, closes, period=14)
        atr_pct = (atr14 / price) * 100 if price > 0 else 0.0
        plus_di, minus_di, adx_val = dmi_adx(highs, lows, closes, 14)

        # Volatility regime for breakout
        if strategy_name == "🟢 Scalping Breakout" and atr_pct < ATR_PCT_MIN_BREAKOUT:
            return None
        # ADX gate for all
        if adx_val < ADX_MIN:
            return None

        # MTF confirmation (confirm with 1h for TF15; 4h for TF1h)
        mtf_note = ""
        if tf_interval == "15m":
            htf = await analisa_trend_ringkas(client, symbol, "1h")
            mtf_note = f" (1h TF {htf})"
            if strategy_name == "🟢 Scalping Breakout" and htf != "UP":
                return None
            if strategy_name in ("🔴 Jemput Bola", "🟡 Rebound Swing") and htf == "UP":
                # Hindari counter-trend kuat saat HTF UP
                return None
        elif tf_interval == "1h":
            htf = await analisa_trend_ringkas(client, symbol, "4h")
            mtf_note = f" (4h TF {htf})"
            if strategy_name == "🟢 Scalping Breakout" and htf == "DOWN":
                return None

        # Validasi strategi
        is_valid = False
        if strategy_name == "🔴 Jemput Bola":
            is_valid = (price < ema25) and (price > 0.9 * ema99) and (rsi_last < 40)
        elif strategy_name == "🟡 Rebound Swing":
            is_valid = (price < ema25) and (price > ema7) and (rsi_last < 50)
        elif strategy_name == "🟢 Scalping Breakout":
            # pastikan close > high N-1 untuk breakout sederhana
            breakout_ok = closes[-1] > max(highs[-3:-1]) if len(highs) >= 3 else (price > ema7)
            is_valid = (price > ema7 > 0) and (price > ema25) and (price > ema99) and (rsi_last >= 60) and breakout_ok
        if not is_valid:
            return None

        # TP dinamis hybrid per strategi (tidak mengubah)
        tp_conf = {
            "🔴 Jemput Bola": {"mult": (1.8, 3.0), "min_pct": (0.007, 0.012)},
            "🟡 Rebound Swing": {"mult": (1.4, 2.4), "min_pct": (0.005, 0.009)},
            "🟢 Scalping Breakout": {"mult": (1.0, 1.8), "min_pct": (0.003, 0.006)},
        }
        conf = tp_conf.get(strategy_name, {"mult": (1.5, 2.5), "min_pct": (0.005, 0.01)})
        m1, m2 = conf["mult"]
        min1, min2 = conf["min_pct"]

        tp1_calc = price + atr14 * m1
        tp2_calc = price + atr14 * m2
        tp1_floor = price * (1 + min1)
        tp2_floor = price * (1 + min2)
        tp1 = round(max(tp1_calc, tp1_floor), 6)
        tp2 = round(max(tp2_calc, tp2_floor), 6)
        tp1_pct = round((tp1 - price) / price * 100, 2)
        tp2_pct = round((tp2 - price) / price * 100, 2)
        sl_atr = round(price - 1.2 * atr14, 6) if strategy_name != "🔴 Jemput Bola" else round(price - 0.8 * atr14, 6)

        # Signals & context
        rsi6_series = rsi_vals
        candle = detect_candle_pattern(opens, closes, highs, lows)
        divergence = detect_divergence(closes[-len(rsi6_series):], rsi6_series) if rsi6_series else ""
        zone = proximity_to_sr(closes, tf_interval)
        vol_spike = is_volume_spike(volumes)
        support_break = (price < 0.985 * ema25) and (price < 0.97 * ema7)
        trend = trend_strength(closes, volumes)
        macd_h = macd_histogram(closes)

        # Weighted confidence score
        score = 0.0
        weights = {
            "mtf": 1.5,
            "adx": 1.2,
            "atrpct": 0.8,
            "div": 0.7,
            "zone": 0.6,
            "vol": 0.6,
            "macd": 0.4,
            "candle": 0.4,
            "support_ok": 0.6,
        }
        # accumulate
        score += weights["mtf"]  # sudah lolos gate MTF
        if adx_val >= ADX_MIN: score += weights["adx"]
        if strategy_name == "🟢 Scalping Breakout" and atr_pct >= ATR_PCT_MIN_BREAKOUT: score += weights["atrpct"]
        if divergence: score += weights["div"]
        if zone and ("Dekat" in zone): score += weights["zone"]
        if vol_spike: score += weights["vol"]
        if macd_h > 0: score += weights["macd"]
        if candle: score += weights["candle"]
        if not support_break: score += weights["support_ok"]

        # Gate minimal skor (berbeda per strategi)
        min_score = 3.5 if strategy_name == "🟢 Scalping Breakout" else 3.0
        if score < min_score:
            return None

        # Compose message
        msg = [
            f"{strategy_name} • {tf_interval}",
            f"✅ {symbol}",
            f"Harga: ${price:.6f}",
            f"EMA7: {ema7:.6f} | EMA25: {ema25:.6f} | EMA99: {ema99:.6f}",
            f"RSI(6): {rsi_last} | ATR(14): {atr14:.6f} (ATR%: {atr_pct:.2f}%)",
            f"ADX(14): {adx_val:.2f}",
            f"📈 24h QuoteVol: ${vol24h:,.0f}",
            f"📉 Avg TF Vol (base): {sum(volumes[-20:]) / min(20, len(volumes)) if volumes else 0:,.2f}",
            f"🧪 Avg Trades/Candle: {avg_tf_trades:,.0f}{mtf_note}",
            "",
            f"🎯 Entry: ${price:.6f}",
            f"🎯 TP1: ${tp1} (+{tp1_pct}%)",
            f"🎯 TP2: ${tp2} (+{tp2_pct}%)",
            f"🛡️ SL (ATR): ${sl_atr}",
            f"🎯 Confidence Score: {round(score, 2)}/{5}",
        ]
        if candle:
            msg.append(f"📌 Pattern: {candle}")
        if divergence:
            msg.append(divergence)
        if zone:
            msg.append(f"📍 {zone}")
        if vol_spike:
            msg.append("💥 Volume Spike")
        if support_break:
            msg.append("⚠️ *Waspada! Support patah*")
        msg.append(f"📊 Trend: {trend}")
        msg.append(f"🧬 MACD: {'Bullish' if macd_h > 0 else 'Bearish'} ({macd_h})")

        return "
".join(msg)
    except Exception as e:
        log.warning(f"analisa_strategi_pro error {symbol} {tf_interval}: {e}")
        return None

# ===================== TELEGRAM HANDLERS =====================

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackQueryHandler

WELCOME_KEYBOARD_INLINE = InlineKeyboardMarkup([
    [InlineKeyboardButton("🟢 Retail Mode", callback_data="mode:retail")],
    [InlineKeyboardButton("🧠 Pro Mode", callback_data="mode:pro")],
    [InlineKeyboardButton("ℹ️ Info", callback_data="info"), InlineKeyboardButton("🆘 Help", callback_data="help")],
])

STRAT_INLINE = lambda mode: InlineKeyboardMarkup([
    [InlineKeyboardButton("🟢 Scalping Breakout", callback_data=f"scan:{mode}:🟢 Scalping Breakout")],
    [InlineKeyboardButton("🟡 Rebound Swing", callback_data=f"scan:{mode}:🟡 Rebound Swing")],
    [InlineKeyboardButton("🔴 Jemput Bola", callback_data=f"scan:{mode}:🔴 Jemput Bola")],
    [InlineKeyboardButton("⬅️ Kembali", callback_data="back")],
])

async def _check_auth(update: Update) -> bool:
    user_id = (update.effective_user.id if update.effective_user else 0)
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        if update.message:
            await update.message.reply_text("⛔ Akses ditolak. Kamu tidak terdaftar sebagai pengguna.")
        elif update.callback_query:
            await update.callback_query.answer("Akses ditolak", show_alert=True)
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return
    await update.message.reply_text(
        "🤖 Selamat datang di Bot Sinyal Trading Crypto!
Pilih mode di bawah ini:",
        reply_markup=WELCOME_KEYBOARD_INLINE,
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💬 Hubungi admin @KikioOreo untuk bantuan atau aktivasi.")

async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """
📌 Jadwal Ideal Strategi:
🔴 Jemput Bola: 07.30–08.30 WIB
🟡 Rebound Swing: Siang–Sore
🟢 Scalping Breakout: Malam 19.00–22.00 WIB
Gunakan sesuai momentum pasar & arah BTC!
""".strip()
    )

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Masih support /scan <strategi>, default retail
    if not await _check_auth(update):
        return
    args = context.args or []
    if args:
        name = " ".join(args).strip()
        matched = None
        for k in STRATEGIES.keys():
            if name.lower() in k.lower():
                matched = k
                break
        if not matched:
            await update.message.reply_text("Strategi tidak dikenali. Pilih dari menu.")
            return
        await run_scan(update, context, matched, mode_profile="retail")
    else:
        await update.message.reply_text("Pilih mode terlebih dulu:", reply_markup=WELCOME_KEYBOARD_INLINE)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Fallback untuk user yang masih pakai keyboard lama
    if not await _check_auth(update):
        return
    text = (update.message.text or "").strip()
    if text == "2️⃣ Info":
        await info_cmd(update, context)
    elif text == "3️⃣ Help":
        await help_cmd(update, context)
    else:
        await update.message.reply_text("Silakan gunakan tombol di bawah ini:", reply_markup=WELCOME_KEYBOARD_INLINE)

# ========== INLINE CALLBACKS ==========

MODE_PROFILES = {
    "retail": {
        "ADX_MIN": 20.0,
        "ATR_PCT_MIN_BREAKOUT": 0.08,
        "AVG_TRADES_MIN": 80,
        "REQUIRE_2_TF": False,
    },
    "pro": {
        "ADX_MIN": 25.0,
        "ATR_PCT_MIN_BREAKOUT": 0.15,
        "AVG_TRADES_MIN": 200,
        "REQUIRE_2_TF": True,
    },
}

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_auth(update):
        return
    q = update.callback_query
    data = q.data or ""

    if data == "info":
        await q.answer()
        await q.edit_message_text(
            """
📌 Jadwal Ideal Strategi:
🔴 Jemput Bola: 07.30–08.30 WIB
🟡 Rebound Swing: Siang–Sore
🟢 Scalping Breakout: Malam 19.00–22.00 WIB
Gunakan sesuai momentum pasar & arah BTC!
""".strip(),
            reply_markup=WELCOME_KEYBOARD_INLINE,
        )
        return
    if data == "help":
        await q.answer()
        await q.edit_message_text("💬 Hubungi admin @KikioOreo untuk bantuan atau aktivasi.", reply_markup=WELCOME_KEYBOARD_INLINE)
        return
    if data == "back":
        await q.answer()
        await q.edit_message_text("Pilih mode:", reply_markup=WELCOME_KEYBOARD_INLINE)
        return
    if data.startswith("mode:"):
        _, mode = data.split(":", 1)
        await q.answer()
        await q.edit_message_text(f"Mode **{mode.upper()}** dipilih. Pilih strategi:", parse_mode="Markdown", reply_markup=STRAT_INLINE(mode))
        return
    if data.startswith("scan:"):
        # scan:<mode>:<strategi>
        _, mode, strategy = data.split(":", 2)
        await q.answer("Memulai scan…")
        # simulasikan command run_scan tapi via callback
        fake_update = update
        await run_scan(fake_update, context, strategy, mode_profile=mode)
        return

# ========== RUN SCAN DENGAN MODE PROFILE ==========

async def run_scan(update: Update, context: ContextTypes.DEFAULT_TYPE, strategy_name: str, mode_profile: str = "retail"):
    # Override knobs sesuai mode
    prof = MODE_PROFILES.get(mode_profile, MODE_PROFILES["retail"]) 
    global ADX_MIN, ATR_PCT_MIN_BREAKOUT, AVG_TRADES_MIN, REQUIRE_2_TF
    ADX_MIN = prof["ADX_MIN"]
    ATR_PCT_MIN_BREAKOUT = prof["ATR_PCT_MIN_BREAKOUT"]
    AVG_TRADES_MIN = prof["AVG_TRADES_MIN"]
    REQUIRE_2_TF = prof["REQUIRE_2_TF"]

    # kirim notifikasi awal
    if update.callback_query and update.effective_chat:
        await context.bot.send_message(update.effective_chat.id, f"🔍 [{mode_profile.upper()}] Memindai sinyal untuk strategi *{strategy_name}*...
Tunggu beberapa saat...", parse_mode="Markdown")
    elif update.message:
        await update.message.reply_text(f"🔍 [{mode_profile.upper()}] Memindai sinyal untuk strategi *{strategy_name}*...
Tunggu beberapa saat...", parse_mode="Markdown")

    http_sem = asyncio.Semaphore(HTTP_CONCURRENCY)
    analysis_sem = asyncio.Semaphore(ANALYSIS_CONCURRENCY)

    async with aiohttp.ClientSession(headers={"User-Agent": "SignalBot/1.0"}) as session:
        client = BinanceClient(session, http_sem)
        trend_btc = await btc_market_trend(client)

        async def pv(pair: str):
            try:
                price, t24 = await asyncio.gather(client.price(pair), client.ticker24h(pair))
                v_quote = float(t24["data"].get("quoteVolume", 0.0))
                return pair, price, v_quote
            except Exception as e:
                log.info(f"skip {pair}: {e}")
                return pair, None, None

        results = await asyncio.gather(*(pv(pair) for pair in PAIRS))
        valid_pairs = [(pair, p, v) for (pair, p, v) in results if isinstance(p, float) and isinstance(v, float)]

        strategy_cfg = STRATEGIES[strategy_name]
        vol_min = strategy_cfg["volume_min_usd"]
        valid_pairs = [(pair, p, v) for pair, p, v in valid_pairs if v >= vol_min]

        messages: List[str] = []

        async def analyze_pair(pair: str, price: float, vol24: float):
            nonlocal messages
            async with analysis_sem:
                tasks = [
                    analisa_strategi_pro(client, pair, strategy_name, price, vol24, tf, trend_btc)
                    for tf in TF_INTERVALS.values()
                ]
                out = await asyncio.gather(*tasks)
                valid = [m for m in out if m]
                if (len(valid) >= 2 if REQUIRE_2_TF else len(valid) >= 1):
                    messages.append(valid[0])

        await asyncio.gather(*(analyze_pair(pair, p, v) for pair, p, v in valid_pairs))

    target_chat = update.effective_chat.id if update.effective_chat else None
    if messages and target_chat:
        for m in messages[:20]:
            await context.bot.send_message(target_chat, m, parse_mode="Markdown")
            await asyncio.sleep(0.4)
        await context.bot.send_message(target_chat, "✅ *Scan selesai. Sinyal layak ditemukan.*", parse_mode="Markdown")
    elif target_chat:
        await context.bot.send_message(target_chat, "⚠️ Tidak ada sinyal layak saat ini. Coba di waktu lain.")

# ===================== MAIN =====================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("info", info_cmd))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Bot aktif dan berjalan...")
    app.run_polling()

# ===================== END =====================


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("info", info_cmd))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Bot aktif dan berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
