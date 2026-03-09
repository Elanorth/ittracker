#!/bin/bash
# Let's Encrypt ilk sertifika kurulum scripti
# Sunucuda bir kez çalıştırılır: bash init-letsencrypt.sh

set -e

DOMAIN="ittracker.assospharma.com"
EMAIL="levent.can@inventist.com.tr"   # Sertifika uyarıları için
STAGING=0                              # Test için 1, üretim için 0

echo ">>> Certbot klasörleri oluşturuluyor..."
mkdir -p ./certbot/conf ./certbot/www

echo ">>> Geçici sertifika oluşturuluyor (nginx başlatmak için)..."
mkdir -p ./certbot/conf/live/$DOMAIN
openssl req -x509 -nodes -newkey rsa:4096 -days 1 \
  -keyout ./certbot/conf/live/$DOMAIN/privkey.pem \
  -out    ./certbot/conf/live/$DOMAIN/fullchain.pem \
  -subj   "/CN=localhost" 2>/dev/null

echo ">>> TLS parametreleri indiriliyor..."
curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf \
  -o ./certbot/conf/options-ssl-nginx.conf
curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/_internal/cli/cli_defaults.py > /dev/null
openssl dhparam -out ./certbot/conf/ssl-dhparams.pem 2048 2>/dev/null

echo ">>> Nginx başlatılıyor..."
docker compose up --force-recreate -d nginx

echo ">>> Geçici sertifika siliniyor..."
rm -rf ./certbot/conf/live

echo ">>> Let's Encrypt'ten gerçek sertifika alınıyor..."
STAGING_FLAG=""
if [ $STAGING = "1" ]; then
  STAGING_FLAG="--staging"
  echo "    (STAGING modu — üretim için STAGING=0 yapın)"
fi

docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  $STAGING_FLAG \
  --email $EMAIL \
  --agree-tos \
  --no-eff-email \
  -d $DOMAIN

echo ">>> Nginx yeniden yükleniyor..."
docker compose exec nginx nginx -s reload

echo ""
echo "✅ SSL kurulumu tamamlandı!"
echo "   https://$DOMAIN adresini test edebilirsiniz."
