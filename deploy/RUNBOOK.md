# Runbook: Pasang Sistem Diet di VPS (untuk manusia atau agent Hermes)

Server: VPS Ubuntu 24.04 `43.134.133.21` yang juga menjalankan **HestiaCP** (portofolio `arcand.my.id`),
**Tokosendiri** (vhost manual), dan **9router** (port 20128).

**Tujuan:** aplikasi FastAPI Sistem Diet dilayani di `https://sistem-diet.arcand.my.id` lewat **vhost Nginx manual**
(di luar panel Hestia), proses dijalankan **Supervisor** sebagai user `deploy`, sertifikat **Let's Encrypt**.

```
HP ─HTTPS─> Nginx (milik Hestia) ─┬─ arcand.my.id            → vhost Hestia (portofolio)
                                  ├─ tokosendiri.my.id       → conf.d/tokosendiri.conf
                                  └─ sistem-diet.arcand.my.id → conf.d/sistem-diet.conf
                                                                 → uvicorn 127.0.0.1:8010 (Supervisor, user deploy)
                                                                 → 9router 127.0.0.1:20128
                                                                 → SQLite /var/www/sistem-diet/data/diet.db
```

DNS `arcand.my.id` dikelola di **Domainesia** (nameserver `nsx1/nsx2.domainesia.com`), **tidak** lewat Cloudflare.

---

## ATURAN WAJIB UNTUK AGENT

1. **Jangan ganggu portofolio, Tokosendiri & HestiaCP**: jangan stop/disable layanan apa pun, jangan ubah
   `/usr/local/hestia`, `/etc/nginx/conf.d/domains/`, `/etc/nginx/conf.d/tokosendiri.conf`, atau config Tokosendiri.
2. **Jangan ganggu Hermes dan 9router**: jangan stop/restart/ubah proses atau config-nya. Jangan reboot.
3. **Jangan `apt purge`/`apt autoremove`**, jangan ubah firewall, jangan pasang UFW.
4. **Jangan tampilkan rahasia** (isi `.env`, API key, PIN). Sebutkan path file-nya saja.
5. **Jalankan fase berurutan.** Setelah tiap fase jalankan *Verifikasi*. Jika gagal: **berhenti**, laporkan
   perintah terakhir + 30 baris output terakhir. Jangan improvisasi di luar runbook.
6. Langkah **👤 MANUSIA** tidak bisa dilakukan agent: kirim instruksinya, lalu **tunggu konfirmasi**.
7. Semua perintah sebagai **root**.

---

## Fase 0 — Pemeriksaan awal

```bash
whoami && lsb_release -ds && free -h && df -h / && python3 --version
```

```bash
grep -RhoE 'listen\s+[0-9.]+:443' /etc/nginx/conf.d/domains/ | sort -u; id deploy; systemctl is-active nginx supervisor
```

```bash
ss -ltnp | grep -E ':(8010|20128)\b' || echo "port 8010 & 20128 tidak dipakai"
```

```bash
curl -s -o /dev/null -w "9router lokal: %{http_code}\n" http://127.0.0.1:20128/v1/models
```

```bash
/usr/local/hestia/bin/v-search-domain-owner sistem-diet.arcand.my.id || echo "tidak terdaftar di Hestia"
```

```bash
curl -s -o /dev/null -w "portofolio: %{http_code}\n" https://arcand.my.id/ | tee /root/sistem-diet-portfolio-before.txt; curl -s -o /dev/null -w "tokosendiri: %{http_code}\n" https://tokosendiri.my.id/ | tee -a /root/sistem-diet-portfolio-before.txt
```

**Verifikasi:**
- Ada minimal satu IP listen `:443`, user `deploy` ada, nginx & supervisor `active`, Python ≥ 3.10.
- Port **8010 tidak dipakai** (kalau dipakai → berhenti & laporkan).
- 9router lokal menjawab **200 atau 401** (bukan `000`). Kalau `000`, 9router mungkin hanya listen di IP publik → laporkan.
- `sistem-diet.arcand.my.id` **tidak** terdaftar di Hestia (kalau terdaftar → berhenti & laporkan).

---

## Fase 1 — DNS & upload (👤 MANUSIA)

> 👤 **MANUSIA:**
> 1. Login **Domainesia** → domain `arcand.my.id` → **Kelola DNS / DNS Management** → tambah record:
>    - Type **A**, Name/Host **`sistem-diet`**, Value **`43.134.133.21`**, TTL 3600 (atau default).
> 2. Dari laptop, di folder `D:\Projek\diet-scan` (PowerShell):
>    ```
>    .\deploy\deploy.ps1 -First
>    ```
>    Ini mengupload `sistem-diet.zip`, `.env`, dan database (sudah berisi TKPI) ke `/home/ubuntu/`.
>
> Tunggu konfirmasi.

**Verifikasi:**

```bash
getent hosts sistem-diet.arcand.my.id; ls -la /home/ubuntu/sistem-diet.zip /home/ubuntu/sistem-diet.env /home/ubuntu/sistem-diet.db
```

IP harus `43.134.133.21` dan ketiga file ada. Jika DNS belum muncul, tunggu 5–15 menit lalu ulangi
(Let's Encrypt di Fase 2 **gagal** kalau DNS belum mengarah ke server).

---

## Fase 2 — Instalasi

```bash
mkdir -p /var/www/sistem-diet && unzip -o -q /home/ubuntu/sistem-diet.zip -d /var/www/sistem-diet && rm -f /home/ubuntu/sistem-diet.zip
```

```bash
bash /var/www/sistem-diet/deploy/server/setup.sh
```

Script ini: memasang `python3-venv`, `unzip`, `certbot` (hanya install); memindahkan `.env` & database;
mengubah `AI_BASE_URL` ke `127.0.0.1:20128` dan `HTTPS_ONLY=true`; membuat virtualenv; membuat program
Supervisor `sistem-diet`; memasang vhost Nginx; mengambil sertifikat Let's Encrypt; memasang hook reload Nginx
saat sertifikat diperpanjang.

**Verifikasi:**

```bash
supervisorctl status sistem-diet && nginx -t && curl -s -o /dev/null -w "lokal: %{http_code}\n" http://127.0.0.1:8010/ && ls /etc/letsencrypt/live/sistem-diet.arcand.my.id/
```

`RUNNING`, `syntax is ok`, `lokal: 200`, ada `fullchain.pem`. Jika gagal: `tail -n 50 /var/log/sistem-diet.log`.

---

## Fase 3 — Uji akhir

```bash
curl -s -o /dev/null -w "sistem-diet: %{http_code}\n" https://sistem-diet.arcand.my.id/; curl -s -o /dev/null -w "http->https: %{http_code}\n" http://sistem-diet.arcand.my.id/; curl -s https://sistem-diet.arcand.my.id/api/me
```

```bash
cat /root/sistem-diet-portfolio-before.txt; curl -s -o /dev/null -w "portofolio: %{http_code}\n" https://arcand.my.id/; curl -s -o /dev/null -w "tokosendiri: %{http_code}\n" https://tokosendiri.my.id/
```

```bash
sudo -u deploy /var/www/sistem-diet/.venv/bin/python -c "
import asyncio, sys; sys.path.insert(0, '/var/www/sistem-diet')
from app import ai
print(asyncio.run(ai.chat_completion(ai.AI_CHAT_MODEL, [{'role':'user','content':'Balas: OK'}]))[:50])"
```

**Verifikasi:** `sistem-diet: 200`, `http->https: 301`, `/api/me` → `{"detail":"Belum login"}`,
portofolio & tokosendiri **sama seperti Fase 0**, tes AI membalas teks (bukan error). Cek `free -h`.

---

## Fase 4 — Laporan & uji di HP

Kirim ringkasan hasil tiap fase (tanpa rahasia), lalu:

> 👤 **MANUSIA:** Buka `https://sistem-diet.arcand.my.id` di HP → login → isi Profil → coba scan.
> Install: Android (Chrome) menu ⋮ → **Install app**; iPhone (Safari) **Share → Add to Home Screen**.
> Disarankan ganti PIN jadi ≥ 6 digit: edit `USERS` di `/var/www/sistem-diet/.env`, lalu
> `supervisorctl restart sistem-diet`.

---

## Deploy rutin (update kode)

Dari laptop: `.\deploy\deploy.ps1` (upload zip + jalankan `deploy.sh`: backup DB, ekstrak, pip, restart).
`.env` dan database **tidak** ditimpa.

## Perintah berguna

```bash
supervisorctl status sistem-diet          # status
supervisorctl restart sistem-diet         # restart (mis. setelah ubah .env)
tail -f /var/log/sistem-diet.log          # log aplikasi
ls /var/www/sistem-diet/data/backups/     # backup DB otomatis tiap deploy
```

## Rollback (lepas aplikasi, portofolio & Tokosendiri tidak terpengaruh)

```bash
rm -f /etc/nginx/conf.d/sistem-diet.conf && nginx -t && systemctl reload nginx
```

```bash
supervisorctl stop sistem-diet; rm -f /etc/supervisor/conf.d/sistem-diet.conf && supervisorctl reread && supervisorctl update
```
