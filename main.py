
from __future__ import annotations
import os, time, asyncio, logging, traceback, math
from typing import Dict, Tuple, List, Optional
import aiohttp
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# ========= ENV & LOGGING =========
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN belum diset di environment.")

HTTP_CONCURRENCY = int(os.getenv("HTTP_CONCURRENCY", "12"))
ANALYSIS_CONCURRENCY = int(os.getenv("ANALYSIS_CONCURRENCY", "8"))

# Retail dilonggarkan (dibanding default lama)
THRESHOLD_RETAIL = float(os.getenv("THRESHOLD_RETAIL", "3.0"))  # sebelumnya 3.2
THRESHOLD_PRO    = float(os.getenv("THRESHOLD_PRO", "3.8"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "90"))
MAX_SIGNALS      = int(os.getenv("MAX_SIGNALS", "20"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("signal-bot")

# ========= STRATEGI, PAIRS, TF =========
PAIRS = [
    "BTCUSDT","ETHUSDT","XRPUSDT","BNBUSDT","SOLUSDT","TRXUSDT","DOGEUSDT","ADAUSDT",
    "XLMUSDT","SUIUSDT","BCHUSDT","LINKUSDT","HBARUSDT","AVAXUSDT","LTCUSDT","TONUSDT",
    "SHIBUSDT","UNIUSDT","DOTUSDT","DAIUSDT","PEPEUSDT","ENAUSDT","AAVEUSDT","TAOUSDT",
    "NEARUSDT","ETCUSDT","ONDOUSDT","APTUSDT","ICPUSDT","POLUSDT","PENGUUSDT","ALGOUSDT",
    "VETUSDT","ARBUSDT","ATOMUSDT","BONKUSDT","RENDERUSDT","WLDUSDT","TRUMPUSDT","SEIUSDT",
    "FILUSDT","FETUSDT","FLOKIUSDT","QNTUSDT","INJUSDT","CRVUSDT","STXUSDT","TIAUSDT",
    "OPUSDT","CFXUSDT","IMXUSDT","GRTUSDT","ENSUSDT","PAXGUSDT","CAKEUSDT","WIFUSDT",
    "KAIAUSDT","LDOUSDT","NEXOUSDT","XTZUSDT","SUSDT","VIRTUALUSDT","AUSDT","THETAUSDT",
    "IOTAUSDT","JASMYUSDT","RAYUSDT","GALAUSDT","DEXEUSDT","SANDUSDT","PENDLEUSDT"
]

STRATEGIES = {
    "🔴 Jemput Bola": {"rsi_limit": 40, "volume_min_usd": 2_000_000},
    "🟡 Rebound Swing": {"rsi_limit": 50, "volume_min_usd": 3_000_000},
    "🟢 Scalping Breakout": {"rsi_limit": 60, "volume_min_usd": 5_000_000},
}

TF_INTERVALS = {"TF15": "15m", "TF1h": "1h", "TF4h": "4h"}  # 1d tidak di-scan penuh

SR_WINDOW = {"15m": 30, "1h": 50, "4h": 80}
ADX_MIN = 22.0
ATR_PCT_MIN_BREAKOUT = 0.12
AVG_TRADES_MIN = 120

# Retail dilonggarkan
MODE_PROFILES = {
    "retail": {"ADX_MIN":15.0,"ATR_PCT_MIN_BREAKOUT":0.05,"AVG_TRADES_MIN":50,"REQUIRE_2_TF":False,"THRESH":THRESHOLD_RETAIL},
    "pro":    {"ADX_MIN":25.0,"ATR_PCT_MIN_BREAKOUT":0.15,"AVG_TRADES_MIN":200,"REQUIRE_2_TF":True,"THRESH":THRESHOLD_PRO},
}

# ========= KEYBOARD =========
def kb_main():
    # Tampil untuk semua user (strategi iklan)
    return ReplyKeyboardMarkup(
        [["🟢 Retail Mode","🧠 Pro Mode"],["ℹ️ Info","🆘 Help"]],
        resize_keyboard=True
    )

def kb_mode():
    return ReplyKeyboardMarkup(
        [["🔴 Jemput Bola"],["🟡 Rebound Swing"],["🟢 Scalping Breakout"],["⬅️ Kembali"]],
        resize_keyboard=True
    )

# ========= UTIL INDIKATOR =========
def ema_series(values: List[float], period: int) -> List[float]:
    if len(values) < period: return []
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]: out.append((v - out[-1]) * k + out[-1])
    return out

def rsi_series(closes: List[float], period: int = 14) -> List[float]:
    if len(closes) < period + 1: return []
    deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsis: List[float] = []
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain*(period-1)+gains[i]) / period
        avg_loss = (avg_loss*(period-1)+losses[i]) / period
        if avg_loss == 0 and avg_gain == 0: rs = 1.0
        elif avg_loss == 0: rs = float("inf")
        elif avg_gain == 0: rs = 0.0
        else: rs = avg_gain/avg_loss
        rsi = 100.0 if rs == float("inf") else (0.0 if rs == 0.0 else (100 - 100/(1+rs)))
        rsis.append(rsi)
    return rsis

def macd_histogram(closes: List[float]) -> float:
    if len(closes) < 35: return 0.0
    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    n = min(len(ema12), len(ema26))
    macd_line = [a-b for a,b in zip(ema12[-n:], ema26[-n:])]
    signal = ema_series(macd_line, 9)
    return round((macd_line[-1]-signal[-1]) if signal else 0.0, 4)

def true_range(h: float, l: float, pc: float) -> float:
    return max(h-l, abs(h-pc), abs(l-pc))

def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) <= period: return 0.0
    trs = [true_range(highs[i], lows[i], closes[i-1]) for i in range(1, len(closes))]
    return sum(trs[-period:]) / period

def dmi_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Tuple[float,float,float]:
    if len(closes) <= period + 1: return (0.0,0.0,0.0)
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        up = highs[i]-highs[i-1]; down = lows[i-1]-lows[i]
        plus_dm.append(up if (up>down and up>0) else 0.0)
        minus_dm.append(down if (down>up and down>0) else 0.0)
        trs.append(true_range(highs[i], lows[i], closes[i-1]))
    def wilder(arr: List[float], p: int) -> List[float]:
        if len(arr) < p: return []
        sm = [sum(arr[:p])]
        for x in arr[p:]: sm.append(sm[-1] - (sm[-1]/p) + x)
        return sm
    atr_w = [x/period for x in wilder(trs, period)]
    pdm_w = [x/period for x in wilder(plus_dm, period)]
    mdm_w = [x/period for x in wilder(minus_dm, period)]
    if not atr_w or not pdm_w or not mdm_w: return (0.0,0.0,0.0)
    plus_di  = [100*(p/t) if t else 0.0 for p,t in zip(pdm_w[-len(atr_w):], atr_w)]
    minus_di = [100*(m/t) if t else 0.0 for m,t in zip(mdm_w[-len(atr_w):], atr_w)]
    dx = [100*abs(p-m)/(p+m) if (p+m) else 0.0 for p,m in zip(plus_di, minus_di)]
    if len(dx) < period: return (plus_di[-1], minus_di[-1], 0.0)
    adx_vals = [sum(dx[:period])/period]
    for x in dx[period:]: adx_vals.append((adx_vals[-1]*(period-1)+x)/period)
    return (plus_di[-1], minus_di[-1], adx_vals[-1])

def detect_candle_pattern(opens: List[float], closes: List[float], highs: List[float], lows: List[float]) -> str:
    o,c,h,l = opens[-1], closes[-1], highs[-1], lows[-1]
    body = abs(c-o); rng = max(h-l, 1e-9)
    upper = h - max(o,c); lower = min(o,c) - l
    if body <= 0.1*rng: return "Doji"
    if lower > 2*body and upper < body: return "Hammer"
    if len(closes) >= 2 and closes[-2] < opens[-2] and c>o and c>opens[-2] and o<closes[-2]: return "Engulfing"
    return ""

def detect_divergence(prices: List[float], rsis: List[float]) -> str:
    if len(prices)<5 or len(rsis)<5: return ""
    p1,p2 = prices[-5], prices[-1]; r1,r2 = rsis[-5], rsis[-1]
    if p2>p1 and r2<r1: return "🔻 Bearish Divergence"
    if p2<p1 and r2>r1: return "🔺 Bullish Divergence"
    return ""

def proximity_to_sr(closes: List[float], tf: str) -> str:
    win = SR_WINDOW.get(tf,30); recent = closes[-win:]
    support, resistance, price = min(recent), max(recent), closes[-1]
    if support<=0 or resistance<=0: return ""
    if (price-support)/support*100 < 2: return "Dekat Support"
    if (resistance-price)/resistance*100 < 2: return "Dekat Resistance"
    return ""

def is_volume_spike(volumes: List[float]) -> bool:
    if len(volumes) < 21: return False
    avg = sum(volumes[-20:-1])/19
    return volumes[-1] > 1.5*avg if avg>0 else False

def trend_strength(closes: List[float], volumes: List[float]) -> str:
    if len(closes)<30 or len(volumes)<20: return "Sideways ⏸️"
    ema10 = sum(closes[-10:])/10; ema30 = sum(closes[-30:])/30
    slope = ema10 - ema30; avg_vol = sum(volumes[-20:])/20
    if slope>0 and volumes[-1]>1.2*avg_vol: return "Uptrend 🔼"
    if slope<0 and volumes[-1]>1.2*avg_vol: return "Downtrend 🔽"
    return "Sideways ⏸️"

# ========= BINANCE CLIENT =========
class BinanceClient:
    BASE = "https://api.binance.com"
    def __init__(self, session: aiohttp.ClientSession, http_sem: asyncio.Semaphore):
        self.sess = session
        self.http_sem = http_sem
        self.cache: Dict[str, Dict[str, Tuple[object, float]]] = {"price": {}, "ticker24": {}, "klines": {}}
        self.ttl = {"price": 30, "ticker24": 30, "klines": 20}

    async def _get(self, path: str, params: Optional[dict] = None):
        url = f"{self.BASE}{path}"
        for attempt in range(3):
            try:
                async with self.http_sem:
                    async with self.sess.get(url, params=params, timeout=10) as r:
                        if r.status != 200:
                            txt = await r.text()
                            raise RuntimeError(f"HTTP {r.status}: {txt}")
                        return await r.json()
            except Exception as e:
                if attempt == 2: raise
                await asyncio.sleep(0.3 * (attempt+1))

    def _fresh(self, bucket: str, key: str) -> bool:
        if key not in self.cache[bucket]: return False
        return (time.time() - self.cache[bucket][key][1]) < self.ttl[bucket]

    async def price(self, symbol: str) -> float:
        if self._fresh("price", symbol): return float(self.cache["price"][symbol][0])
        data = await self._get("/api/v3/ticker/price", {"symbol": symbol})
        price = float(data["price"]); self.cache["price"][symbol] = (price, time.time()); return price

    async def ticker24h(self, symbol: str) -> dict:
        if self._fresh("ticker24", symbol): return self.cache["ticker24"][symbol][0]
        data = await self._get("/api/v3/ticker/24hr", {"symbol": symbol})
        self.cache["ticker24"][symbol] = (data, time.time()); return data

    async def klines(self, symbol: str, interval: str, limit: int = 120) -> List[List[float]]:
        key = f"{symbol}:{interval}:{limit}"
        if self._fresh("klines", key): return self.cache["klines"][key][0]
        data = await self._get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
        self.cache["klines"][key] = (data, time.time()); return data

# ========= TREND / REGIME =========
async def regime_for(symbol: str, client: BinanceClient, interval: str) -> str:
    try:
        data = await client.klines(symbol, interval, 99)
        closes = [float(k[4]) for k in data]
        ema7 = sum(closes[-7:])/7; ema25 = sum(closes[-25:])/25; ema99 = sum(closes[-99:])/99
        rsi_last = rsi_series(closes,14); r = rsi_last[-1] if rsi_last else 50
        if closes[-1] > ema7 > ema25 > ema99 and r > 55: return "UP"
        if closes[-1] < ema7 < ema25 < ema99 and r < 45: return "DOWN"
        return "SIDEWAYS"
    except Exception as e:
        log.info(f"regime_for {symbol} {interval}: {e}")
        return "SIDEWAYS"

async def btc_regime_combo(client: BinanceClient) -> str:
    r1 = await regime_for("BTCUSDT", client, "1h")
    r4 = await regime_for("BTCUSDT", client, "4h")
    if r1 == r4: return r1
    if "UP" in (r1, r4) and "DOWN" in (r1, r4): return "SIDEWAYS"
    return "SIDEWAYS"

async def daily_regime_light(symbol: str, client: BinanceClient) -> str:
    # Filter ringan 1d untuk Jemput Bola & Reborn (tanpa scan penuh)
    try:
        data = await client.klines(symbol, "1d", 99)
        closes = [float(k[4]) for k in data]
        ema7 = sum(closes[-7:])/7; ema25 = sum(closes[-25:])/25; ema99 = sum(closes[-99:])/99
        rsi_last = rsi_series(closes,14); r = rsi_last[-1] if rsi_last else 50
        if closes[-1] > ema7 > ema25 > ema99 and r > 55: return "UP"
        if closes[-1] < ema7 < ema25 < ema99 and r < 45: return "DOWN"
        return "SIDEWAYS"
    except Exception:
        return "SIDEWAYS"

# ========= ANALISA =========
def pct(a: float, b: float) -> float:
    if b == 0: return 0.0
    return round((a-b)/b*100, 2)

def format_price(x: float) -> str:
    # Format adaptif: 2-6 desimal tergantung harga
    if x >= 100: return f"{x:,.2f}"
    if x >= 1: return f"{x:,.4f}"
    return f"{x:,.6f}"

async def analisa_pair_tf(client: BinanceClient, symbol: str, strategy_name: str, price: float, tf: str, adx_min: float, atr_min_breakout: float, avg_trades_min: int, btc_regime: str, require_mtf: bool) -> Optional[Dict]:
    try:
        data = await client.klines(symbol, tf, 120)
        closes = [float(k[4]) for k in data]; opens = [float(k[1]) for k in data]
        highs = [float(k[2]) for k in data]; lows = [float(k[3]) for k in data]
        volumes = [float(k[5]) for k in data]; trades = [int(k[8]) for k in data]

        # Filter likuiditas per TF
        avg_tf_trades = sum(trades[-20:]) / min(20, len(trades)) if trades else 0
        if avg_tf_trades < avg_trades_min: return None

        rsi6 = rsi_series(closes,6); rsi_last = round(rsi6[-1],2) if rsi6 else 50
        ema7 = sum(closes[-7:])/7 if len(closes)>=7 else closes[-1]
        ema25 = sum(closes[-25:])/25 if len(closes)>=25 else sum(closes)/len(closes)
        ema99 = sum(closes[-99:])/99 if len(closes)>=99 else sum(closes)/len(closes)
        atr14 = atr(highs,lows,closes,14); atr_pct = (atr14/price)*100 if price>0 else 0.0
        _,_,adx_val = dmi_adx(highs,lows,closes,14)

        # Gate BTC regime + strategi
        if strategy_name == "🟢 Scalping Breakout":
            if btc_regime != "UP": return None
            if atr_pct < atr_min_breakout: return None
        else:
            # Mean-revert butuh market non-UP agar lebih aman
            if btc_regime == "UP": return None

        if adx_val < adx_min: return None

        # MTF konfirmasi ringan
        mtf_note = ""
        if require_mtf:
            if tf == "15m":
                # minta konfirmasi 1h
                mtf_note = f" (1h TF {await regime_for(symbol, client, '1h')})"
            elif tf == "1h":
                mtf_note = f" (4h TF {await regime_for(symbol, client, '4h')})"

        # Validasi spesifik strategi
        valid = False
        if strategy_name == "🔴 Jemput Bola":
            valid = (price < ema25) and (price > 0.9*ema99) and (rsi_last < 40)
        elif strategy_name == "🟡 Rebound Swing":
            valid = (price < ema25) and (price > ema7) and (rsi_last < 50)
        elif strategy_name == "🟢 Scalping Breakout":
            breakout_ok = closes[-1] > max(highs[-3:-1]) if len(highs)>=3 else (price>ema7)
            valid = (price > ema7 > 0) and (price > ema25) and (price > ema99) and (rsi_last >= 60) and breakout_ok
        if not valid: return None

        # Hitung TP/SL
        tp_conf = {
            "🔴 Jemput Bola": {"mult": (1.8,3.0), "min_pct": (0.007,0.012), "sl_mult": 0.8},
            "🟡 Rebound Swing": {"mult": (1.4,2.4), "min_pct": (0.005,0.009), "sl_mult": 1.0},
            "🟢 Scalping Breakout": {"mult": (1.0,1.8), "min_pct": (0.003,0.006), "sl_mult": 1.2},
        }
        conf = tp_conf[strategy_name]
        m1,m2 = conf["mult"]; min1,min2 = conf["min_pct"]; slm = conf["sl_mult"]
        tp1_calc = price + atr14*m1; tp2_calc = price + atr14*m2
        tp1 = max(tp1_calc, price*(1+min1)); tp2 = max(tp2_calc, price*(1+min2))
        sl  = price - slm*atr14

        # Sinyal pendukung
        candle = detect_candle_pattern(opens,closes,highs,lows)
        divergence = detect_divergence(closes, rsi6) if rsi6 else ""
        zone = proximity_to_sr(closes, tf)
        vol_spike = is_volume_spike(volumes)
        support_break = (price < 0.985*ema25) and (price < 0.97*ema7)
        trend = trend_strength(closes, volumes)
        macd_h = macd_histogram(closes)

        # Skor confidence
        score = 0.0
        weights = {"mtf":1.2,"adx":1.2,"atrpct":0.8,"div":0.7,"zone":0.6,"vol":0.6,"macd":0.4,"candle":0.4,"support_ok":0.6}
        if require_mtf: score += weights["mtf"]
        if adx_val>=adx_min: score += weights["adx"]
        if strategy_name=="🟢 Scalping Breakout" and atr_pct>=ATR_PCT_MIN_BREAKOUT: score += weights["atrpct"]
        if divergence: score += weights["div"]
        if zone and "Dekat" in zone: score += weights["zone"]
        if vol_spike: score += weights["vol"]
        if macd_h>0: score += weights["macd"]
        if candle: score += weights["candle"]
        if not support_break: score += weights["support_ok"]

        return {
            "symbol": symbol, "tf": tf, "price": price,
            "tp1": tp1, "tp2": tp2, "sl": sl,
            "tp1_pct": pct(tp1, price), "tp2_pct": pct(tp2, price), "sl_pct": pct(sl, price),
            "ema7": ema7, "ema25": ema25, "ema99": ema99,
            "rsi": rsi_last, "atr": atr14, "atr_pct": round((atr14/price)*100,2) if price>0 else 0.0,
            "adx": adx_val, "avg_trades": avg_tf_trades, "trend": trend, "macd_h": macd_h,
            "note": mtf_note, "candle": candle, "divergence": divergence, "zone": zone, "vol_spike": vol_spike,
            "score": round(score,2)
        }
    except Exception as e:
        log.info(f"analisa {symbol} {tf} error: {e}")
        return None

# ========= MESSAGE FORMATTER =========
def format_price(x: float) -> str:
    if x >= 100: return f"{x:,.2f}"
    if x >= 1: return f"{x:,.4f}"
    return f"{x:,.6f}"

def build_message(strategy: str, mode: str, regime_btc: str, res: Dict, detail_extra: str = "", parse_html: bool = True) -> str:
    header = f"{strategy} • {res['tf']} • {mode.upper()}"
    line2  = f"✅ {res['symbol']} @ ${format_price(res['price'])}"
    line3  = f"TP1: ${format_price(res['tp1'])} (+{res['tp1_pct']}%)"
    line4  = f"TP2: ${format_price(res['tp2'])} (+{res['tp2_pct']}%)"
    line5  = f"SL : ${format_price(res['sl'])} ({res['sl_pct']}%)"
    line6  = f"Regime: BTC {regime_btc} | Confidence: {res['score']}/5"

    detail_lines = [
        "[DETAIL]",
        f"EMA7 {format_price(res['ema7'])} | EMA25 {format_price(res['ema25'])} | EMA99 {format_price(res['ema99'])}",
        f"RSI(6) {res['rsi']} | ATR(14) {format_price(res['atr'])} ({res['atr_pct']}%) | ADX(14) {round(res['adx'],2)}",
        f"Trend: {res['trend']} | MACD: {'Bullish' if res['macd_h']>0 else 'Bearish'} ({res['macd_h']})",
        f"Pattern: {res['candle'] or '-'} | Zone: {res['zone'] or '-'} | Volume Spike: {'Ya' if res['vol_spike'] else 'Tidak'}",
    ]
    if res.get("note"): detail_lines.append(res["note"])
    if detail_extra: detail_lines.append(detail_extra)

    if parse_html:
        spoiler = "<span class=\"tg-spoiler\">" + "\n".join(detail_lines) + "</span>"
    else:
        spoiler = "||" + "\n".join(detail_lines) + "||"

    return "\n".join([header, line2, line3, line4, line5, line6, "", spoiler])

# ========= STATE =========
LAST_SENT: Dict[Tuple[str,str], float] = {}

def cooldown_ok(symbol: str, strategy: str) -> bool:
    t = LAST_SENT.get((symbol, strategy), 0)
    return (time.time() - t) >= COOLDOWN_MINUTES * 60

def mark_sent(symbol: str, strategy: str):
    LAST_SENT[(symbol, strategy)] = time.time()

# ========= AUTH HELPERS =========
def is_allowed(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else 0
    return (not ALLOWED_USERS) or (uid in ALLOWED_USERS)

# ========= TELEGRAM HANDLERS =========
async def post_startup(app):
    me = await app.bot.get_me()
    await app.bot.delete_webhook(drop_pending_updates=True)
    log.warning(f"BOT STARTED as @{me.username} id={me.id}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # TIDAK pakai whitelist, agar semua user bisa lihat tombol
    context.user_data["mode"] = None
    await update.message.reply_text("Silakan pilih mode:", reply_markup=kb_main())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # TIDAK pakai whitelist
    await update.message.reply_text("💬 Hubungi admin @KikioOreo untuk bantuan atau aktivasi.", reply_markup=kb_main())

async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # TIDAK pakai whitelist
    txt = "\n".join([
        "📌 Jadwal Ideal Strategi:",
        "🔴 Jemput Bola: 07.30–08.30 WIB",
        "🟡 Rebound Swing: Siang–Sore",
        "🟢 Scalping Breakout: Malam 19.00–22.00 WIB",
        "Gunakan sesuai momentum pasar & arah BTC!",
    ])
    await update.message.reply_text(txt, reply_markup=kb_main())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Tidak blok awal, tapi gate saat akses mode/strategi
    text = (update.message.text or "").strip()

    if text == "🟢 Retail Mode":
        if not is_allowed(update):
            await update.message.reply_text("⛔ Akses ditolak. Hubungi admin untuk aktivasi.", reply_markup=kb_main()); return
        context.user_data["mode"] = "retail"
        await update.message.reply_text("Retail Mode dipilih. Pilih strategi:", reply_markup=kb_mode()); return

    if text == "🧠 Pro Mode":
        if not is_allowed(update):
            await update.message.reply_text("⛔ Akses ditolak. Hubungi admin untuk aktivasi.", reply_markup=kb_main()); return
        context.user_data["mode"] = "pro"
        await update.message.reply_text("Pro Mode dipilih. Pilih strategi:", reply_markup=kb_mode()); return

    if text == "ℹ️ Info":
        await info_cmd(update, context); return

    if text == "🆘 Help":
        await help_cmd(update, context); return

    if text == "⬅️ Kembali":
        context.user_data["mode"] = None
        await update.message.reply_text("Kembali ke menu utama.", reply_markup=kb_main()); return

    if text in STRATEGIES.keys():
        if not is_allowed(update):
            await update.message.reply_text("⛔ Akses ditolak. Hubungi admin untuk aktivasi.", reply_markup=kb_main()); return

        mode = context.user_data.get("mode")
        if mode not in ("retail","pro"):
            await update.message.reply_text("Pilih mode dulu ya.", reply_markup=kb_main()); return
        await update.message.reply_text(f"🔍 [{mode.upper()}] Memindai sinyal untuk strategi {text}...\nTunggu beberapa saat...", reply_markup=kb_mode())
        await run_scan(update, context, text, mode_profile=mode)
        await update.message.reply_text("Selesai. Kembali ke menu utama.", reply_markup=kb_main()); return

    await update.message.reply_text("Perintah tidak dikenali. Gunakan tombol.", reply_markup=kb_main())

# ========= SCAN PIPELINE =========
async def run_scan(update: Update, context: ContextTypes.DEFAULT_TYPE, strategy_name: str, mode_profile: str="retail"):
    prof = MODE_PROFILES[mode_profile]
    adx_min = prof["ADX_MIN"]
    atr_breakout = prof["ATR_PCT_MIN_BREAKOUT"]
    avg_trades_min = prof["AVG_TRADES_MIN"]
    require_2_tf = prof["REQUIRE_2_TF"]
    thresh = prof["THRESH"]

    http_sem = asyncio.Semaphore(HTTP_CONCURRENCY)
    analysis_sem = asyncio.Semaphore(ANALYSIS_CONCURRENCY)

    async with aiohttp.ClientSession(headers={"User-Agent": "SignalBot/1.0"}) as session:
        client = BinanceClient(session, http_sem)
        btc_regime = await btc_regime_combo(client)

        # Preload price & 24h volume
        async def pv(pair: str):
            try:
                price = await client.price(pair)
                t24 = await client.ticker24h(pair)
                vol_q = float(t24.get("quoteVolume", 0.0))
                return pair, price, vol_q
            except Exception as e:
                log.info(f"skip {pair}: {e}"); return pair, None, None

        results = await asyncio.gather(*(pv(p) for p in PAIRS))
        vol_min = STRATEGIES[strategy_name]["volume_min_usd"]
        valid_pairs = [(pair,p,v) for (pair,p,v) in results if isinstance(p,float) and isinstance(v,float) and v >= vol_min]

        messages: List[str] = []
        seen_symbol: set = set()

        async def analyze_pair(pair: str, price: float):
            # Dedup by cooldown first
            if not cooldown_ok(pair, strategy_name):
                return
            daily_ok = True
            if strategy_name in ("🔴 Jemput Bola","🟡 Rebound Swing"):
                dr = await daily_regime_light(pair, client)
                if dr == "UP":  # filter ringan: hindari counter-trend terhadap up harian kuat
                    daily_ok = False
            if not daily_ok:
                return

            # kumpulkan kandidat di beberapa TF, pilih terbaik
            async with analysis_sem:
                tasks = [analisa_pair_tf(client, pair, strategy_name, price, tf, adx_min, atr_breakout, avg_trades_min, btc_regime, require_2_tf) for tf in TF_INTERVALS.values()]
                out = await asyncio.gather(*tasks)
                cand = [r for r in out if r and r["score"] >= thresh]
                if not cand: return
                best = max(cand, key=lambda x: x["score"])

                # dedup per symbol (ambil 1 terbaik)
                if pair in seen_symbol: return
                seen_symbol.add(pair)

                # build message ringkas + spoiler detail (HTML)
                msg = build_message(strategy_name, mode_profile, btc_regime, best)
                messages.append((pair, msg))

        await asyncio.gather(*(analyze_pair(pair, p) for pair,p,_ in valid_pairs))

    # Kirim hasil (limit + cooldown mark)
    if not messages:
        await update.message.reply_text("⚠️ Tidak ada sinyal layak saat ini. Coba di waktu lain.")
        return

    messages = messages[:MAX_SIGNALS]
    for pair, msg in messages:
        await update.message.reply_text(msg, parse_mode="HTML")
        mark_sent(pair, strategy_name)
        await asyncio.sleep(0.4)

    await update.message.reply_text(f"✅ Scan selesai. Ditemukan {len(messages)} sinyal.")

# ========= ERROR HANDLER & MAIN =========
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))[:1500]
    log.error(f"Unhandled error: {context.error}\n{err}")
    try:
        owner = ALLOWED_USERS[0] if ALLOWED_USERS else None
        if owner: await context.bot.send_message(owner, f"⚠️ Bot error:\n{err}")
    except Exception:
        pass

async def post_startup(app):
    me = await app.bot.get_me()
    await app.bot.delete_webhook(drop_pending_updates=True)
    log.warning(f"BOT STARTED as @{me.username} id={me.id}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("info", info_cmd))
    app.add_handler(CommandHandler("ping", lambda u,c: u.message.reply_text("pong ✅", reply_markup=kb_main())))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)
    app.post_init = post_startup
    log.info("Bot aktif dan berjalan…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
