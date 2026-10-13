# Diet Scan 🥗

Aplikasi diet pribadi (PWA) untuk dipakai berdua. Foto makanan → AI mengenali item & porsi →
nilai gizi diambil dari database ahli gizi → catatan kalori harian, riwayat berat badan, dan chat dengan AI coach.

## Struktur

```
app/main.py        API (FastAPI)
app/ai.py          Panggilan ke 9router (scan foto + chat coach)
app/db.py          SQLite, rumus target kalori, pencarian makanan
static/            Tampilan aplikasi (PWA: bisa di-install ke HP)
import_gizi.py     Import database gizi dari Excel/CSV
deploy/            Skrip & runbook deploy ke VPS
contoh_gizi.csv    Contoh format data gizi
```

## 1. Jalankan di laptop

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env      # lalu isi .env
.venv\Scripts\python import_gizi.py data_gizi_dari_ahli_gizi.xlsx --replace
.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload
```

Buka http://localhost:8000

## 2. Isi `.env`

| Variabel | Isi |
|---|---|
| `AI_BASE_URL` | URL 9router + `/v1`, mis. `http://IP:20128/v1` |
| `AI_API_KEY` | API key dari dashboard 9router |
| `AI_VISION_MODEL` | Nama combo untuk scan foto |
| `AI_CHAT_MODEL` | Nama combo untuk chat coach (mis. `free`) |
| `USERS` | `username:PIN` dipisah koma |
| `SECRET_KEY` | String acak, **jangan dibagikan** |

**Saran untuk 9router:** buat combo baru, mis. `scan`, dengan strategi **Fallback** dan isi model
vision saja (gemini-3.x-flash). Combo `free` (Round Robin) bergantian ke model yang berbeda-beda,
jadi format jawaban JSON hasil scan bisa tidak konsisten.

## 3. Import data gizi

```bash
python import_gizi.py data_gizi.xlsx --replace
```

- Kolom dideteksi otomatis dari header (Nama, Energi/Kalori, Protein, Lemak, Karbohidrat, Serat, Berat porsi, URT).
- Script menampilkan kolom yang terdeteksi. Kalau ada yang salah, timpa manual, mis. `--col-kcal "Energi (Kal)"`.
- Nilai dianggap **per 100 gram**. Kalau data kamu per porsi/per gram lain, pakai `--per 1` dst.
- Sheet lain: `--sheet "Nama Sheet"`.

## 4. Deploy ke VPS

Aplikasi berjalan di VPS `43.134.133.21` (sama dengan portofolio & 9router) di
**https://sistem-diet.arcand.my.id**, di luar panel Hestia: Nginx (vhost manual) → uvicorn (Supervisor) → SQLite.

- Instalasi pertama: ikuti [deploy/RUNBOOK.md](deploy/RUNBOOK.md) (bisa dijalankan agent Hermes).
- Update kode dari laptop: `.\deploy\deploy.ps1` (database & `.env` di server tidak ditimpa, DB di-backup otomatis).

## 5. Install di HP

- **Android (Chrome):** buka subdomain → menu ⋮ → *Install app / Tambahkan ke layar utama*.
- **iPhone (Safari):** buka subdomain → tombol Share → *Add to Home Screen*.

## Catatan

- Kalau makanan tidak ada di database ahli gizi, nilainya memakai perkiraan AI dan diberi label **"perkiraan AI"**.
- Porsi dari foto hanya perkiraan. Cek dan sesuaikan gram sebelum disimpan.
- Backup: cukup salin file `data/diet.db`.
