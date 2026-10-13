#!/usr/bin/env bash
# Deploy rutin (update kode). Jalankan sebagai root setelah zip baru diupload:
#   sudo bash /var/www/sistem-diet/deploy/server/deploy.sh
#
# .env dan data/diet.db TIDAK ikut di zip, jadi data kalian aman.
set -euo pipefail

APP_DIR="/var/www/sistem-diet"
ZIP="${1:-/home/ubuntu/sistem-diet.zip}"
PORT="8010"

[ -f "$ZIP" ] || { echo "GAGAL: $ZIP tidak ada"; exit 1; }

echo "==> Backup database"
mkdir -p "$APP_DIR/data/backups"
if [ -f "$APP_DIR/data/diet.db" ]; then
    BACKUP="$APP_DIR/data/backups/diet-$(date +%Y%m%d-%H%M%S).db"
    cp "$APP_DIR/data/diet.db" "$BACKUP" && echo "    $BACKUP"
fi
# simpan 10 backup terakhir
ls -1t "$APP_DIR"/data/backups/diet-*.db 2>/dev/null | tail -n +11 | xargs -r rm -f

echo "==> Ekstrak kode baru"
unzip -o -q "$ZIP" -d "$APP_DIR"
rm -f "$ZIP"
chown -R deploy:deploy "$APP_DIR"

echo "==> Dependency Python"
sudo -u deploy "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> Restart aplikasi"
supervisorctl restart sistem-diet
sleep 2
code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/")
echo "    status lokal: $code"
[ "$code" = "200" ] || { echo "GAGAL: aplikasi tidak merespons. Lihat: tail -n 50 /var/log/sistem-diet.log"; exit 1; }

echo "Deploy selesai."
