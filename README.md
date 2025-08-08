# Bot Scan - Crypto Spot Trading Signal

Bot ini berfungsi untuk melakukan **scan dan analisa market crypto** (spot) secara otomatis, lalu mengirimkan sinyal ke Telegram.

Repo: [github.com/kakamigomarket/bot-scan](https://github.com/kakamigomarket/bot-scan)

---

## 🚀 Fitur
- Analisa otomatis harga crypto menggunakan API exchange.
- Mengirimkan notifikasi sinyal trading ke Telegram.
- Bisa dijalankan di **Railway** 24/7.
- Mudah dikonfigurasi lewat environment variables.

# 🧠  Versi Pro Fitur yang Sudah Aktif


## ✅ STRUKTUR FITUR BOT SAAT INI

##  🔍 1. Multi-Strategi Trading

- 🔴 Jemput Bola – Entry saat oversold (RSI < 40), cocok swing aman

- 🟡 Rebound Swing – Entry saat mulai naik dari MA/EMA, semi-trend

- 🟢 Scalping Breakout – Entry saat breakout, momentum cepat


## 📊 2. Indikator Teknikal Otomatis

- EMA7, EMA25, EMA99 → validasi arah & posisi harga

- RSI(6) → deteksi oversold/overbought

- ATR(14) → dasar volatilitas & TP dinamis

- MACD Histogram → konfirmasi arah tren

- Volume 24h & Volume Spike

- Trend Strength (berbasis EMA slope & volume)

- Candle Pattern Detection (Doji, Hammer, Engulfing)

- Support/Resistance Proximity

- Divergence (Bullish/Bearish)


## 💰 3. Take Profit Dinamis Hybrid

- TP dihitung berdasarkan kombinasi:

- ATR × multiplier

- Minimum % (agar fee dan slippage tetap cuan)

- Konfigurasi khusus tiap strategi:


## Strategi	TP1	TP2 Hybrid Dinamis

- 🔴 Jemput Bola	≥%	≥%

- 🟡 Rebound Swing	≥%	≥%

- 🟢 Scalping Breakout	≥%	≥%



## 🧠 4. Sistem Validasi Cerdas

- Confidence Score (0–5) dari:

- Candle pattern

- Divergence

- Dekat support/resistance

- Volume spike
  
- Support patah

- Hanya menampilkan sinyal jika skor ≥ 3 dan valid di ≥ 2 timeframe


## 📈 5. Multi-Timeframe Analyzer

- Validasi TF: 15m, 1h, 4h, 1D

- Hanya menampilkan pair yang konsisten di ≥2 TF


## 📉 6. Filter Berdasarkan Trend BTC

- Cek arah tren BTC (EMA & RSI)

- Jika BTC bearish, hanya strategi Jemput Bola yang aktif


## 🤖 7. Bot Telegram Interaktif

- Menu: Start / Strategi / Info / Help

- Proteksi akses (ALLOWED_USERS)

- Siap dijalankan via local, VPS, atau Railway


## ⚙️ 8. Performa & Keamanan

- Menggunakan caching untuk API agar efisien

- Error handling dan logging aktif

- Tidak rawan spam karena sinyal difilter ketat


# 🏁 Siap digunakan untuk:

- Manual entry trading spot

- Melacak sinyal berkualitas dari 70+ koin ( bisa ditambahkan lagi )

- Sinyal masuk langsung dari Telegram


---

# 📦 Persyaratan
- **Python 3.9+**
- API Key dari exchange (contoh: Binance API)
- Token Bot Telegram dan Chat/User ID
- Akun **Railway** (untuk deployment 24/7)

---

# 🛠 Instalasi Lokal

1. Clone repository
   ```bash
   git clone https://github.com/kakamigomarket/bot-scan.git
   cd bot-scan

2. Install dependencies

pip install -r requirements.txt

3. Buat file .env di root folder:

TELEGRAM_BOT_TOKEN=isi_token_bot_telegram
TELEGRAM_USER_ID=isi_user_id_telegram
API_KEY=isi_api_key_exchange
API_SECRET=isi_api_secret_exchange

4. Jalankan bot

python main.py

---

## ☁️ Deployment di Railway

1. Fork repository ini atau upload script kamu ke GitHub.

2. Login ke Railway → https://railway.app

3. Buat New Project → pilih Deploy from GitHub repo → sambungkan dengan repo ini.

4. Masuk ke menu Variables di Railway, tambahkan:

- TELEGRAM_BOT_TOKEN

- TELEGRAM_USER_ID

- API_KEY

- API_SECRET

5. Pastikan Start Command di menu Settings:

python main.py

6. Klik Deploy dan bot akan berjalan 24/7.

---

# ⚠️ Catatan Penting

- Jangan upload file .env ke GitHub (sudah di-.gitignore).

- API key adalah informasi sensitif, hanya simpan di Railway Variables atau .env lokal.

- Jika menggunakan Binance API, aktifkan hanya izin read-only untuk keamanan.

---

# 📄 Lisensi
Proyek ini dilisensikan di bawah MIT License.

---

## 📬 Kontak
Jika ada pertanyaan atau saran, bisa hubungi via Telegram: @KikioOreo





