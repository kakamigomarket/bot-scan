# bot-scan

🧠  Versi Pro Fitur yang Sudah Aktif


✅ STRUKTUR FITUR BOT SAAT INI

🔍 1. Multi-Strategi Trading

🔴 Jemput Bola – Entry saat oversold (RSI < 40), cocok swing aman

🟡 Rebound Swing – Entry saat mulai naik dari MA/EMA, semi-trend

🟢 Scalping Breakout – Entry saat breakout, momentum cepat


📊 2. Indikator Teknikal Otomatis

EMA7, EMA25, EMA99 → validasi arah & posisi harga

RSI(6) → deteksi oversold/overbought

ATR(14) → dasar volatilitas & TP dinamis

MACD Histogram → konfirmasi arah tren

Volume 24h & Volume Spike

Trend Strength (berbasis EMA slope & volume)

Candle Pattern Detection (Doji, Hammer, Engulfing)

Support/Resistance Proximity

Divergence (Bullish/Bearish)


💰 3. Take Profit Dinamis Hybrid

TP dihitung berdasarkan kombinasi:

ATR × multiplier

Minimum % (agar fee dan slippage tetap cuan)

Konfigurasi khusus tiap strategi:


Strategi	TP1	TP2

🔴 Jemput Bola	≥7%	≥12%

🟡 Rebound Swing	≥5%	≥9%

🟢 Scalping Breakout	≥3%	≥6%



🧠 4. Sistem Validasi Cerdas

Confidence Score (0–5) dari:

Candle pattern

Divergence

Dekat support/resistance

Volume spike
Support patah

Hanya menampilkan sinyal jika skor ≥ 3 dan valid di ≥ 2 timeframe


📈 5. Multi-Timeframe Analyzer

Validasi TF: 15m, 1h, 4h, 1D

Hanya menampilkan pair yang konsisten di ≥2 TF


📉 6. Filter Berdasarkan Trend BTC

Cek arah tren BTC (EMA & RSI)

Jika BTC bearish, hanya strategi Jemput Bola yang aktif


🤖 7. Bot Telegram Interaktif

Menu: Start / Strategi / Info / Help

Proteksi akses (ALLOWED_USERS)

Siap dijalankan via local, VPS, atau Railway


⚙️ 8. Performa & Keamanan

Menggunakan caching untuk API agar efisien

Error handling dan logging aktif

Tidak rawan spam karena sinyal difilter ketat


🏁 Siap digunakan untuk:

Manual entry trading spot

Melacak sinyal berkualitas dari 70+ koin

Sinyal masuk langsung dari Telegram


