#!/usr/bin/env bash
# Instalasi pertama Sistem Diet di VPS (Ubuntu 24.04 + HestiaCP). Jalankan sebagai root:
#   bash /var/www/sistem-diet/deploy/server/setup.sh
#
# Opsional: LE_EMAIL=email@kamu.com untuk notifikasi Let's Encrypt.
# Aman dijalankan ulang (idempotent). Tidak menyentuh konfigurasi Hestia.
set -euo pipefail

DOMAIN="sistem-diet.arcand.my.id"
APP_DIR="/var/www/sistem-diet"
PORT="8010"
UPLOAD_DIR="/home/ubuntu"
NGINX_CONF="/etc/nginx/conf.d/sistem-diet.conf"
TEMPLATE="$APP_DIR/deploy/server/nginx-sistem-diet.conf"

echo "==> Paket yang dibutuhkan (hanya install, tidak menghapus apa pun)"
apt-get install -y -q python3-venv unzip certbot >/dev/null

echo "==> User & folder"
id deploy >/dev/null
mkdir -p "$APP_DIR/data" /var/www/letsencrypt

# .env & database diupload terpisah dari laptop (deploy.ps1 -First)
if [ ! -f "$APP_DIR/.env" ]; then
    [ -f "$UPLOAD_DIR/sistem-diet.env" ] || { echo "GAGAL: $UPLOAD_DIR/sistem-diet.env tidak ada"; exit 1; }
    mv "$UPLOAD_DIR/sistem-diet.env" "$APP_DIR/.env"
fi
if [ ! -f "$APP_DIR/data/diet.db" ] && [ -f "$UPLOAD_DIR/sistem-diet.db" ]; then
    mv "$UPLOAD_DIR/sistem-diet.db" "$APP_DIR/data/diet.db"
fi

echo "==> Sesuaikan .env untuk server"
# 9router ada di VPS yang sama: panggil lewat localhost (lebih cepat, tidak lewat internet)
sed -i -E 's#^AI_BASE_URL=https?://43\.134\.133\.21(:[0-9]+)?#AI_BASE_URL=http://127.0.0.1\1#' "$APP_DIR/.env"
grep -q '^HTTPS_ONLY=' "$APP_DIR/.env" && sed -i 's/^HTTPS_ONLY=.*/HTTPS_ONLY=true/' "$APP_DIR/.env" || echo "HTTPS_ONLY=true" >> "$APP_DIR/.env"

chown -R deploy:deploy "$APP_DIR"
chmod 600 "$APP_DIR/.env"

echo "==> Virtualenv & dependency Python"
[ -x "$APP_DIR/.venv/bin/python" ] || sudo -u deploy python3 -m venv "$APP_DIR/.venv"
sudo -u deploy "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
sudo -u deploy "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> Supervisor (proses aplikasi)"
cat > /etc/supervisor/conf.d/sistem-diet.conf <<EOF
[program:sistem-diet]
directory=$APP_DIR
command=$APP_DIR/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $PORT --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1 --timeout-graceful-shutdown 55
user=deploy
autostart=true
autorestart=true
# Beri waktu scan yang sedang berjalan untuk selesai saat restart/deploy
stopwaitsecs=60
stopasgroup=true
killasgroup=true
redirect_stderr=true
stdout_logfile=/var/log/sistem-diet.log
stdout_logfile_maxbytes=5MB
stdout_logfile_backups=3
EOF
supervisorctl reread >/dev/null
supervisorctl update
supervisorctl restart sistem-diet

echo "==> Vhost Nginx"
LISTEN_IP=$(grep -RhoE 'listen\s+[0-9.]+:443' /etc/nginx/conf.d/domains/ | grep -oE '[0-9.]+' | sort -u | head -n1)
[ -n "$LISTEN_IP" ] || { echo "GAGAL: IP listen Nginx Hestia tidak ditemukan"; exit 1; }
echo "    IP listen: $LISTEN_IP"

render() {
    sed -e "s/__LISTEN_IP__/$LISTEN_IP/g" -e "s/__DOMAIN__/$DOMAIN/g" -e "s/__PORT__/$PORT/g" "$TEMPLATE"
}

if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "==> Sertifikat belum ada: pasang vhost HTTP saja dulu untuk validasi Let's Encrypt"
    render | sed '/# __HTTPS_START__/,/# __HTTPS_END__/d' > "$NGINX_CONF"
    nginx -t
    systemctl reload nginx

    if [ -n "${LE_EMAIL:-}" ]; then EMAIL_ARGS=(--email "$LE_EMAIL"); else EMAIL_ARGS=(--register-unsafely-without-email); fi
    certbot certonly --webroot -w /var/www/letsencrypt -d "$DOMAIN" --agree-tos --non-interactive "${EMAIL_ARGS[@]}"
fi

render > "$NGINX_CONF"
nginx -t
systemctl reload nginx

# Reload Nginx otomatis setiap sertifikat diperpanjang (certbot.timer jalan 2x sehari)
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
printf '#!/bin/sh\nsystemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

echo "Setup selesai: https://$DOMAIN"
