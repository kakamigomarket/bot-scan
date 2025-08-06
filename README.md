# bot-scan

🧠 Versi Pro Fitur yang Sudah Aktif (Full)
📊 Indikator & Analisa Teknikal:
✅ EMA7, EMA25, EMA99

✅ RSI(6)

✅ ATR(14) → digunakan untuk TP1 & TP2 dinamis

✅ Volume 24 jam

✅ Volume Spike (vs MA20)

✅ Trend Strength (berdasarkan slope EMA + volume)

✅ MACD Histogram Cross (Bullish / Bearish)

✅ Pola Candle: Doji, Hammer, Engulfing

✅ Divergence (Bullish / Bearish)

✅ Deteksi Proximity ke Support / Resistance

🎯 Sinyal & Strategi:
✅ Tiga mode strategi:

🔴 Jemput Bola (akumulasi RSI < 40)

🟡 Rebound Swing (RSI < 50 + struktur balik arah)

🟢 Scalping Breakout (RSI > 60 + breakout)

✅ Validasi multi-timeframe: Pair hanya tampil jika minimal 2 TF valid

✅ Estimasi Take Profit otomatis:

TP1 = +1.0 ATR

TP2 = +1.8 ATR

Estimasi % ke TP juga ditampilkan

🔔 Peringatan & Visual:
✅ ⚠️ Notifikasi “Support Patah” jika harga turun jauh dari EMA7 & EMA25

✅ 🎯 Confidence Score (0–5) berdasarkan sinyal teknikal yang terpenuhi

✅ Mode tampilan sinyal langsung dikirim ke Telegram (tidak hanya log)

🔒 Keamanan:
✅ Filter hanya untuk user ID yang diizinkan (ALLOWED_USERS)

✅ Tidak ada perintah /scan bebas — hanya bisa dari tombol menu
