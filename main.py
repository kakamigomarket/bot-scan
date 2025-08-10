from __future__ import annotations
import os, time, asyncio, logging, traceback, json, html
from typing import Dict, Tuple, List, Optional
import aiohttp
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from decimal import Decimal, ROUND_HALF_UP  # <-- tambah untuk pembulatan presisi

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ALLOWED_IDS = os.getenv("ALLOWED_IDS", "")
ALLOWED_USERS = [int(x.strip()) for x in ALLOWED_IDS.split(",") if x.strip().isdigit()]
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN belum diset di environment.")

HTTP_CONCURRENCY = int(os.getenv("HTTP_CONCURRENCY", "12"))
ANALYSIS_CONCURRENCY = int(os.getenv("ANALYSIS_CONCURRENCY", "8"))

THRESHOLD_RETAIL = float(os.getenv("THRESHOLD_RETAIL", "2.4"))
THRESHOLD_PRO    = float(os.getenv("THRESHOLD_PRO", "3.3"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "90"))
MAX_SIGNALS      = int(os.getenv("MAX_SIGNALS", "20"))

FEE_PCT_PER_SIDE = float(os.getenv("FEE_PCT_PER_SIDE", "0.001"))    # 0.1% per side
SLIPPAGE_PCT     = float(os.getenv("SLIPPAGE_PCT", "0.0002"))       # 0.02%
MIN_NET_TP1_PCT  = float(os.getenv("MIN_NET_TP1_PCT", "0.25"))      # ambang net min utk TP1 (%)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("signal-bot-enhanced")

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

STRATEGIES: Dict[str, Dict[str, float]] = {
    "🔴 Jemput Bola": {"rsi_limit": 40, "volume_min_usd": 1_000_000},
    "🟡 Rebound Swing": {"rsi_limit": 50, "volume_min_usd": 1_500_000},
    "🟢 Scalping Breakout": {"rsi_limit": 60, "volume_min_usd": 3_000_000},
}

TF_INTERVALS: Dict[str, str] = {"TF15": "15m", "TF1h": "1h", "TF4h": "4h"}
SR_WINDOW = {"15m": 30, "1h": 50, "4h": 80}

ADX_MIN = 12.0
ATR_PCT_MIN_BREAKOUT = 0.05
AVG_TRADES_MIN = 30

MODE_PROFILES = {
    "retail": {"ADX_MIN":15.0,"ATR_PCT_MIN_BREAKOUT":0.05,"AVG_TRADES_MIN":50,"REQUIRE_2_TF":False,"THRESH":THRESHOLD_RETAIL},
    "pro":    {"ADX_MIN":25.0,"ATR_PCT_MIN_BREAKOUT":0.15,"AVG_TRADES_MIN":200,"REQUIRE_2_TF":True,"THRESH":THRESHOLD_PRO},
}

def kb_main() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["🟢 Retail Mode","🧠 Pro Mode"],["ℹ️ Info","🆘 Help"]],
        resize_keyboard=True
    )

def kb_mode() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["🔴 Jemput Bola"],["🟡 Rebound Swing"],["🟢 Scalping Breakout"],["⬅️ Kembali"]],
        resize_keyboard=True
    )

def ema_series(values: List[float], period: int) -> List[float]:
    if len(values) < period: return []
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append((v - out[-1]) * k + out[-1])
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
        if avg_loss == 0 and avg_gain == 0:
            rs = 1.0
        elif avg_loss == 0:
            rs = float("inf")
        elif avg_gain == 0:
            rs = 0.0
        else:
            rs = avg_gain/avg_loss
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
        up = highs[i]-highs[i-1]
        down = lows[i-1]-lows[i]
        plus_dm.append(up if (up>down and up>0) else 0.0)
        minus_dm.append(down if (down>up and down>0) else 0.0)
        trs.append(true_range(highs[i], lows[i], closes[i-1]))
    def wilder(arr: List[float], p: int) -> List[float]:
        if len(arr) < p: return []
        sm = [sum(arr[:p])]
        for x in arr[p:]:
            sm.append(sm[-1] - (sm[-1]/p) + x)
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
    for x in dx[period:]:
        adx_vals.append((adx_vals[-1]*(period-1)+x)/period)
    return (plus_di[-1], minus_di[-1], adx_vals[-1])

def detect_candle_pattern(opens: List[float], closes: List[float], highs: List[float], lows: List[float]) -> str:
    if not opens or not closes: return ""
    o,c,h,l = opens[-1], closes[-1], highs[-1], lows[-1]
    body = abs(c-o); rng = max(h-l, 1e-9)
    upper = h - max(o,c); lower = min(o,c) - l
    if body <= 0.1*rng: return "Doji"
    if lower > 2*body and upper < body: return "Hammer"
    if len(closes) >= 2 and closes[-2] < opens[-2] and c>o and c>opens[-2] and o<closes[-2]:
        return "Engulfing"
    if len(closes) >= 2:
        prev_o, prev_c = opens[-2], closes[-2]
        body_prev = abs(prev_c - prev_o)
        if prev_c < prev_o and c > o and c > prev_o and body_prev <= body * 0.3:
            return "Morning Star"
    return ""

def detect_divergence(prices: List[float], rsis: List[float]) -> str:
    if len(prices)<5 or len(rsis)<5: return ""
    p1,p2 = prices[-5], prices[-1]
    r1,r2 = rsis[-5], rsis[-1]
    if p2>p1 and r2<r1: return "🔻 Bearish Divergence"
    if p2<p1 and r2>r1: return "🔺 Bullish Divergence"
    return ""

def proximity_to_sr(closes: List[float], tf: str) -> str:
    win = SR_WINDOW.get(tf,30)
    recent = closes[-win:]
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
    ema10 = sum(closes[-10:])/10
    ema30 = sum(closes[-30:])/30
    slope = ema10 - ema30
    avg_vol = sum(volumes[-20:])/20
    if slope>0 and volumes[-1]>1.2*avg_vol: return "Uptrend 🔼"
    if slope<0 and volumes[-1]>1.2*avg_vol: return "Downtrend 🔽"
    return "Sideways ⏸️"

class BinanceClient:
    BASE = "https://api.binance.com"
    def __init__(self, session: aiohttp.ClientSession, http_sem: asyncio.Semaphore):
        self.sess = session
        self.http_sem = http_sem
        self.cache: Dict[str, Dict[str, Tuple[object, float]]] = {"price": {}, "ticker24": {}, "klines": {}, "exinfo": {}}
        self.ttl = {"price": 30, "ticker24": 30, "klines": 20, "exinfo": 21600}  # exinfo 6 jam

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
            except Exception:
                if attempt == 2: raise
                await asyncio.sleep(0.3 * (attempt+1))

    def _fresh(self, bucket: str, key: str) -> bool:
        if key not in self.cache[bucket]: return False
        return (time.time() - self.cache[bucket][key][1]) < self.ttl[bucket]

    async def price(self, symbol: str) -> float:
        if self._fresh("price", symbol):
            return float(self.cache["price"][symbol][0])
        data = await self._get("/api/v3/ticker/price", {"symbol": symbol})
        price = float(data["price"])
        self.cache["price"][symbol] = (price, time.time())
        return price

    async def ticker24h(self, symbol: str) -> dict:
        if self._fresh("ticker24", symbol):
            return self.cache["ticker24"][symbol][0]
        data = await self._get("/api/v3/ticker/24hr", {"symbol": symbol})
        self.cache["ticker24"][symbol] = (data, time.time())
        return data

    async def book_ticker(self, symbol: str) -> dict:
        key = f"book:{symbol}"
        if self._fresh("price", key):
            return self.cache["price"][key][0]
        data = await self._get("/api/v3/ticker/bookTicker", {"symbol": symbol})
        self.cache["price"][key] = (data, time.time())
        return data

    async def symbol_info(self, symbol: str) -> dict:
        """Ambil tickSize & stepSize untuk symbol, cache 6 jam."""
        if self._fresh("exinfo", symbol):
            return self.cache["exinfo"][symbol][0]
        data = await self._get("/api/v3/exchangeInfo", {"symbol": symbol})
        try:
            sym = data["symbols"][0]
            price_tick = 0.0
            qty_step = 0.0
            for f in sym.get("filters", []):
                if f.get("filterType") == "PRICE_FILTER":
                    price_tick = float(f.get("tickSize", 0.0))
                elif f.get("filterType") == "LOT_SIZE":
                    qty_step = float(f.get("stepSize", 0.0))
            info = {"price_tick": price_tick, "qty_step": qty_step}
        except Exception:
            info = {"price_tick": 0.0, "qty_step": 0.0}
        self.cache["exinfo"][symbol] = (info, time.time())
        return info

    async def klines(self, symbol: str, interval: str, limit: int = 120) -> List[List[float]]:
        key = f"{symbol}:{interval}:{limit}"
        if self._fresh("klines", key):
            return self.cache["klines"][key][0]
        data = await self._get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
        self.cache["klines"][key] = (data, time.time())
        return data

async def regime_for(symbol: str, client: BinanceClient, interval: str) -> str:
    try:
        data = await client.klines(symbol, interval, 99)
        closes = [float(k[4]) for k in data]
        ema7 = sum(closes[-7:])/7
        ema25 = sum(closes[-25:])/25
        ema99 = sum(closes[-99:])/99
        rsi_last = rsi_series(closes,14)
        r = rsi_last[-1] if rsi_last else 50
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
    try:
        data = await client.klines(symbol, "1d", 99)
        closes = [float(k[4]) for k in data]
        ema7 = sum(closes[-7:])/7
        ema25 = sum(closes[-25:])/25
        ema99 = sum(closes[-99:])/99
        rsi_last = rsi_series(closes,14)
        r = rsi_last[-1] if rsi_last else 50
        if closes[-1] > ema7 > ema25 > ema99 and r > 55: return "UP"
        if closes[-1] < ema7 < ema25 < ema99 and r < 45: return "DOWN"
        return "SIDEWAYS"
    except Exception:
        return "SIDEWAYS"

def pct(a: float, b: float) -> float:
    if b == 0: return 0.0
    return round((a-b)/b*100, 2)

# ======== FORMAT & ROUNDING BERDASARKAN TICK ========

def _decimals_from_tick(tick: float) -> int:
    if tick <= 0: return 8
    s = f"{tick:.10f}".rstrip('0').rstrip('.')
    if '.' in s:
        return len(s.split('.')[1])
    return 0

def _round_to_tick(value: float, tick: float) -> float:
    if tick <= 0: return value
    dval = Decimal(str(value))
    dtick = Decimal(str(tick))
    # pembulatan normal ke jumlah desimal tick
    q = dval.quantize(dtick, rounding=ROUND_HALF_UP)
    return float(q)

def format_price_by_decimals(x: float, decimals: int) -> str:
    # selalu pakai jumlah desimal dari tick Binance
    fmt = f"{{:,.{decimals}f}}"
    return fmt.format(x)

# =====================================================

def load_weights() -> Dict[str, float]:
    defaults = {
        "mtf":1.2,"adx":1.2,"atrpct":0.8,"div":0.7,"zone":0.6,"vol":0.6,"macd":0.4,"candle":0.4,"support_ok":0.6
    }
    raw = os.getenv("WEIGHTS_JSON")
    if not raw:
        return defaults
    try:
        custom = json.loads(raw)
        for k,v in custom.items():
            if k in defaults and isinstance(v,(int,float)):
                defaults[k] = float(v)
        return defaults
    except Exception as e:
        log.warning(f"Invalid WEIGHTS_JSON: {e}. Using default weights.")
        return defaults

def gross_to_net_pct(gross_pct: float) -> float:
    total_fee_pct = 2.0 * FEE_PCT_PER_SIDE * 100.0
    slip_pct = SLIPPAGE_PCT * 100.0
    return round(gross_pct - total_fee_pct - slip_pct, 2)

# ============== TP DINAMIS (MINIMAL PATCH) ==============

MIN_TP1_SMALL = float(os.getenv("MIN_TP1_SMALL", "3.0"))
MIN_TP2_SMALL = float(os.getenv("MIN_TP2_SMALL", "6.0"))
MIN_TP1_MID   = float(os.getenv("MIN_TP1_MID",   "2.0"))
MIN_TP2_MID   = float(os.getenv("MIN_TP2_MID",   "4.0"))
MIN_TP1_LARGE = float(os.getenv("MIN_TP1_LARGE", "1.2"))
MIN_TP2_LARGE = float(os.getenv("MIN_TP2_LARGE", "3.0"))

DTP_BREAKOUT_UP   = float(os.getenv("DTP_BREAKOUT_UP",   "1.10"))
DTP_BREAKOUT_SIDE = float(os.getenv("DTP_BREAKOUT_SIDE", "1.00"))
DTP_BREAKOUT_DOWN = float(os.getenv("DTP_BREAKOUT_DOWN", "0.90"))

SPREAD_MULT_FOR_TP1 = float(os.getenv("SPREAD_MULT_FOR_TP1", "1.8"))
LIQ_LOW_VOL    = float(os.getenv("LIQ_LOW_VOL",  "5000000"))
LIQ_HIGH_VOL   = float(os.getenv("LIQ_HIGH_VOL", "25000000"))
LIQ_LOW_FACTOR = float(os.getenv("LIQ_LOW_FACTOR", "1.10"))
LIQ_HIGH_FACTOR= float(os.getenv("LIQ_HIGH_FACTOR","0.95"))

ATR_LOW_PCT    = float(os.getenv("ATR_LOW_PCT",  "0.8"))
ATR_HIGH_PCT   = float(os.getenv("ATR_HIGH_PCT", "1.8"))
ATR_LOW_FACTOR = float(os.getenv("ATR_LOW_FACTOR","1.15"))
ATR_HIGH_FACTOR= float(os.getenv("ATR_HIGH_FACTOR","0.90"))

def _min_tp_pct_for_price(price: float) -> Tuple[float, float]:
    if price <= 0.01:
        return (MIN_TP1_SMALL, MIN_TP2_SMALL)
    if price <= 1.00:
        return (MIN_TP1_MID, MIN_TP2_MID)
    return (MIN_TP1_LARGE, MIN_TP2_LARGE)

def _btc_factor(strategy_name: str, btc_regime: str) -> float:
    if strategy_name == "🟢 Scalping Breakout":
        return {"UP": DTP_BREAKOUT_UP, "SIDEWAYS": DTP_BREAKOUT_SIDE, "DOWN": DTP_BREAKOUT_DOWN}.get(btc_regime, 1.0)
    return 1.0

def compute_dynamic_targets(
    strategy_name: str,
    price: float,
    atr14: float,
    atr_pct: float,
    btc_regime: str,
    vol24: float,
    spread_pct: float,
    sl_mult_base: float,
) -> Tuple[float, float, float]:
    base_mult = {
        "🔴 Jemput Bola":       (2.0, 3.8),
        "🟡 Rebound Swing":     (1.6, 2.8),
        "🟢 Scalping Breakout": (1.2, 2.0),
    }[strategy_name]

    f_btc = _btc_factor(strategy_name, btc_regime)
    f_atr = ATR_LOW_FACTOR if atr_pct <= ATR_LOW_PCT else (ATR_HIGH_FACTOR if atr_pct >= ATR_HIGH_PCT else 1.0)
    f_liq = LIQ_LOW_FACTOR if vol24 < LIQ_LOW_VOL else (LIQ_HIGH_FACTOR if vol24 > LIQ_HIGH_VOL else 1.0)

    m1 = base_mult[0] * f_btc * f_atr * f_liq
    m2 = base_mult[1] * f_btc * f_atr * f_liq

    tp1 = price + atr14 * m1
    tp2 = price + atr14 * m2
    sl  = price - sl_mult_base * atr14

    min1_pct, min2_pct = _min_tp_pct_for_price(price)
    tp1 = max(tp1, price * (1 + min1_pct/100.0))
    tp2 = max(tp2, price * (1 + min2_pct/100.0))

    total_fee_pct = (2.0 * FEE_PCT_PER_SIDE + SLIPPAGE_PCT) * 100.0
    gross_needed  = max(spread_pct * SPREAD_MULT_FOR_TP1, total_fee_pct + MIN_NET_TP1_PCT)
    tp1 = max(tp1, price * (1 + gross_needed/100.0))

    return tp1, tp2, sl

# ============== /TP DINAMIS ==============

async def analisa_pair_tf(
    client: BinanceClient, symbol: str, strategy_name: str, price: float, tf: str,
    adx_min: float, atr_min_breakout: float, avg_trades_min: int,
    btc_regime: str, require_mtf: bool, vol24: float, spread_pct: float
) -> Optional[Dict]:
    try:
        data = await client.klines(symbol, tf, 120)
        closes = [float(k[4]) for k in data]
        opens  = [float(k[1]) for k in data]
        highs  = [float(k[2]) for k in data]
        lows   = [float(k[3]) for k in data]
        volumes= [float(k[5]) for k in data]
        trades = [int(k[8])   for k in data]

        avg_tf_trades = sum(trades[-20:]) / min(20, len(trades)) if trades else 0
        if avg_tf_trades < avg_trades_min:
            return None

        rsi6 = rsi_series(closes,6)
        rsi_last = round(rsi6[-1],2) if rsi6 else 50
        ema7  = sum(closes[-7:])/7 if len(closes)>=7 else closes[-1]
        ema25 = sum(closes[-25:])/25 if len(closes)>=25 else sum(closes)/len(closes)
        ema99 = sum(closes[-99:])/99 if len(closes)>=99 else sum(closes)/len(closes)
        atr14 = atr(highs,lows,closes,14)
        atr_pct = (atr14/price)*100 if price>0 else 0.0
        _,_,adx_val = dmi_adx(highs,lows,closes,14)

        if strategy_name == "🟢 Scalping Breakout":
            if btc_regime != "UP":
                return None
            if atr_pct < atr_min_breakout:
                return None
        else:
            if btc_regime == "UP":
                allow_pullback = (tf in ("15m","1h")) and (rsi_last < 38) and (price < ema7*0.995)
                if not allow_pullback:
                    return None

        if adx_val < adx_min:
            return None

        mtf_note = ""
        if require_mtf:
            if tf == "15m":
                mtf_note = f" (1h TF {await regime_for(symbol, client, '1h')})"
            elif tf == "1h":
                mtf_note = f" (4h TF {await regime_for(symbol, client, '4h')})"

        valid = False
        if strategy_name == "🔴 Jemput Bola":
            valid = (price < ema25) and (price > 0.9*ema99) and (rsi_last < 40)
        elif strategy_name == "🟡 Rebound Swing":
            valid = (price < ema25) and (price > ema7) and (rsi_last < 50)
        elif strategy_name == "🟢 Scalping Breakout":
            breakout_ok = closes[-1] > max(highs[-3:-1]) if len(highs) >= 3 else (price > ema7)
            valid = (price > ema7 > 0) and (price > ema25) and (price > ema99) and (rsi_last >= 60) and breakout_ok
        if not valid:
            return None

        # === Ambil tickSize & set desimal ===
        sinfo = await client.symbol_info(symbol)
        price_tick = float(sinfo.get("price_tick", 0.0) or 0.0)
        decimals = _decimals_from_tick(price_tick)

        # === TP DINAMIS ===
        sl_mult_base = {"🔴 Jemput Bola": 0.9, "🟡 Rebound Swing": 1.1, "🟢 Scalping Breakout": 1.3}[strategy_name]
        tp1, tp2, sl = compute_dynamic_targets(
            strategy_name=strategy_name,
            price=price,
            atr14=atr14,
            atr_pct=atr_pct,
            btc_regime=btc_regime,
            vol24=vol24,
            spread_pct=spread_pct,
            sl_mult_base=sl_mult_base
        )

        # Bulatkan semua harga ke tick Binance
        price_q = _round_to_tick(price, price_tick) if price_tick > 0 else price
        tp1_q   = _round_to_tick(tp1,   price_tick) if price_tick > 0 else tp1
        tp2_q   = _round_to_tick(tp2,   price_tick) if price_tick > 0 else tp2
        sl_q    = _round_to_tick(sl,    price_tick) if price_tick > 0 else sl
        # === /TP DINAMIS ===

        candle = detect_candle_pattern(opens,closes,highs,lows)
        divergence = detect_divergence(closes, rsi6) if rsi6 else ""
        zone = proximity_to_sr(closes, tf)
        vol_spike = is_volume_spike(volumes)
        support_break = (price < 0.985*ema25) and (price < 0.97*ema7)
        trend = trend_strength(closes, volumes)
        macd_h = macd_histogram(closes)

        weights = load_weights()
        score = 0.0
        if require_mtf: score += weights["mtf"]
        if adx_val>=adx_min: score += weights["adx"]
        if strategy_name=="🟢 Scalping Breakout" and atr_pct>=atr_min_breakout: score += weights["atrpct"]
        if divergence: score += weights["div"]
        if zone and "Dekat" in zone: score += weights["zone"]
        if vol_spike: score += weights["vol"]
        if macd_h>0: score += weights["macd"]
        if candle: score += weights["candle"]
        if not support_break: score += weights["support_ok"]

        return {
            "symbol": symbol, "tf": tf, "price": price_q,
            "tp1": tp1_q, "tp2": tp2_q, "sl": sl_q,
            "tp1_pct": pct(tp1_q, price_q), "tp2_pct": pct(tp2_q, price_q), "sl_pct": pct(sl_q, price_q),
            "ema7": ema7, "ema25": ema25, "ema99": ema99,
            "rsi": rsi_last, "atr": atr14,
            "atr_pct": round((atr14/price_q)*100,2) if price_q>0 else 0.0,
            "adx": adx_val, "avg_trades": avg_tf_trades, "trend": trend, "macd_h": macd_h,
            "note": mtf_note, "candle": candle, "divergence": divergence,
            "zone": zone, "vol_spike": vol_spike,
            "score": round(score,2),
            "decimals": decimals  # <-- kirim jumlah desimal utk format output
        }
    except Exception as e:
        log.info(f"analisa {symbol} {tf} error: {e}")
        return None

def sanitize(s: str) -> str:
    return html.escape(s, quote=False)

def build_message(strategy: str, mode: str, regime_btc: str, res: Dict, detail_extra: str = "", parse_html: bool = True) -> str:
    decimals = int(res.get("decimals", 4))  # fallback 4
    header = f"{sanitize(strategy)} • {sanitize(res['tf'])} • {sanitize(mode.upper())}"
    line2  = f"✅ {sanitize(res['symbol'])} @ ${format_price_by_decimals(res['price'], decimals)}"

    tp1_gross = res['tp1_pct']
    tp2_gross = res['tp2_pct']
    sl_gross  = res['sl_pct']

    line3  = f"TP1: ${format_price_by_decimals(res['tp1'], decimals)} (+{tp1_gross}%)"
    line4  = f"TP2: ${format_price_by_decimals(res['tp2'], decimals)} (+{tp2_gross}%)"
    line5  = f"SL : ${format_price_by_decimals(res['sl'],  decimals)} ({sl_gross}%)"
    line6  = f"Regime: BTC {sanitize(regime_btc)} | Confidence: {res['score']}/5"

    detail_lines = [
        "[DETAIL]",
        f"EMA7 {format_price_by_decimals(res['ema7'], decimals)} | EMA25 {format_price_by_decimals(res['ema25'], decimals)} | EMA99 {format_price_by_decimals(res['ema99'], decimals)}",
        f"RSI(6) {res['rsi']} | ATR(14) {format_price_by_decimals(res['atr'], decimals)} ({res['atr_pct']}%) | ADX(14) {round(res['adx'],2)}",
        f"Trend: {sanitize(res['trend'])} | MACD: {'Bullish' if res['macd_h']>0 else 'Bearish'} ({res['macd_h']})",
        f"Pattern: {sanitize(res['candle'] or '-')} | Zone: {sanitize(res['zone'] or '-')} | Volume Spike: {'Ya' if res['vol_spike'] else 'Tidak'}",
    ]
    if res.get("note"): detail_lines.append(sanitize(res["note"]))
    if detail_extra: detail_lines.append(sanitize(detail_extra))

    if parse_html:
        spoiler = "<span class=\"tg-spoiler\">" + "\n".join(detail_lines) + "</span>"
    else:
        spoiler = "||" + "\n".join(detail_lines) + "||"

    return "\n".join([header, line2, line3, line4, line5, line6, "", spoiler])

LAST_SENT: Dict[Tuple[str,str], float] = {}

def cooldown_ok(symbol: str, strategy: str) -> bool:
    t = LAST_SENT.get((symbol, strategy), 0)
    return (time.time() - t) >= COOLDOWN_MINUTES * 60

def mark_sent(symbol: str, strategy: str):
    LAST_SENT[(symbol, strategy)] = time.time()

def is_allowed(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else 0
    return (not ALLOWED_USERS) or (uid in ALLOWED_USERS)

async def post_startup(app):
    me = await app.bot.get_me()
    await app.bot.delete_webhook(drop_pending_updates=True)
    log.warning(f"BOT STARTED as @{me.username} id={me.id}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = None
    await update.message.reply_text("Silakan pilih mode:", reply_markup=kb_main())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💬 Hubungi admin @KikioOreo untuk bantuan atau aktivasi.", reply_markup=kb_main())

async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = "\n".join([
        "📌 Jadwal Ideal Strategi:",
        "🔴 Jemput Bola: 07.30–08.30 WIB",
        "🟡 Rebound Swing: Siang–Sore",
        "🟢 Scalping Breakout: Malam 19.00–22.00 WIB",
        "Gunakan sesuai momentum pasar & arah BTC!",
    ])
    await update.message.reply_text(txt, reply_markup=kb_main())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text(
            f"🔍 [{mode.upper()}] Memindai sinyal untuk strategi {text}...\nTunggu beberapa saat...",
            reply_markup=kb_mode()
        )
        await run_scan(update, context, text, mode_profile=mode)
        await update.message.reply_text("Selesai. Kembali ke menu utama.", reply_markup=kb_main()); return

    await update.message.reply_text("Perintah tidak dikenali. Gunakan tombol.", reply_markup=kb_main())

async def run_scan(update: Update, context: ContextTypes.DEFAULT_TYPE, strategy_name: str, mode_profile: str="retail"):
    prof = MODE_PROFILES[mode_profile]
    adx_min         = prof["ADX_MIN"]
    atr_breakout    = prof["ATR_PCT_MIN_BREAKOUT"]
    avg_trades_min  = prof["AVG_TRADES_MIN"]
    require_2_tf    = prof["REQUIRE_2_TF"]
    thresh          = prof["THRESH"]

    http_sem    = asyncio.Semaphore(HTTP_CONCURRENCY)
    analysis_sem = asyncio.Semaphore(ANALYSIS_CONCURRENCY)

    async with aiohttp.ClientSession(headers={"User-Agent": "SignalBot/1.0"}) as session:
        client = BinanceClient(session, http_sem)
        btc_regime = await btc_regime_combo(client)

        async def pv(pair: str):
            try:
                price = await client.price(pair)
                t24 = await client.ticker24h(pair)
                vol_q = float(t24.get("quoteVolume", 0.0))

                bt = await client.book_ticker(pair)
                bid = float(bt.get("bidPrice", 0.0) or 0.0)
                ask = float(bt.get("askPrice", 0.0) or 0.0)
                mid = (bid + ask)/2 if (bid>0 and ask>0) else price
                spread_pct = ((ask - bid)/mid * 100.0) if (bid>0 and ask>0 and mid>0) else 0.0

                return pair, price, vol_q, spread_pct
            except Exception as e:
                log.info(f"skip {pair}: {e}")
                return pair, None, None, None

        results = await asyncio.gather(*(pv(p) for p in PAIRS))
        vol_min = STRATEGIES[strategy_name]["volume_min_usd"]
        valid_pairs = [(pair, p, v, s) for (pair, p, v, s) in results
                       if isinstance(p, float) and isinstance(v, float) and v >= vol_min]

        messages: List[str] = []
        seen_symbol: set = set()

        async def analyze_pair(pair: str, price: float, vol24: float, spread_pct: float):
            if not cooldown_ok(pair, strategy_name):
                return
            daily_ok = True
            if strategy_name in ("🔴 Jemput Bola","🟡 Rebound Swing"):
                dr = await daily_regime_light(pair, client)
                if dr == "UP":
                    daily_ok = False
            if not daily_ok:
                return

            async with analysis_sem:
                tasks = [
                    analisa_pair_tf(
                        client, pair, strategy_name, price, tf,
                        adx_min, atr_breakout, avg_trades_min,
                        btc_regime, require_2_tf, vol24, spread_pct
                    )
                    for tf in TF_INTERVALS.values()
                ]
                out = await asyncio.gather(*tasks)
                cand = [r for r in out if r and r["score"] >= thresh]
                if not cand:
                    return
                best = max(cand, key=lambda x: x["score"])

                if pair in seen_symbol:
                    return
                seen_symbol.add(pair)

                msg = build_message(strategy_name, mode_profile, btc_regime, best)
                messages.append((pair, msg))

        await asyncio.gather(*(analyze_pair(pair, p, v, s) for pair, p, v, s in valid_pairs))

    if not messages:
        await update.message.reply_text("⚠️ Tidak ada sinyal layak saat ini. Coba di waktu lain.")
        return

    messages = messages[:MAX_SIGNALS]
    for pair, msg in messages:
        await update.message.reply_text(msg, parse_mode="HTML")
        mark_sent(pair, strategy_name)
        await asyncio.sleep(0.4)

    await update.message.reply_text(f"✅ Scan selesai. Ditemukan {len(messages)} sinyal.")

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))[:1500]
    log.error(f"Unhandled error: {context.error}\n{err}")
    try:
        owner = ALLOWED_USERS[0] if ALLOWED_USERS else None
        if owner:
            await context.bot.send_message(owner, f"⚠️ Bot error:\n{err}")
    except Exception:
        pass

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("info", info_cmd))
    app.add_handler(CommandHandler("ping", lambda u,c: u.message.reply_text("pong ✅", reply_markup=kb_main())))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)
    app.post_init = post_startup
    log.info("Enhanced bot aktif dan berjalan…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
