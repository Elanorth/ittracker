# Glitchtip — Self-hosted Error Tracking Kurulumu

Sentry protokolü uyumlu, tamamen self-hosted hata izleme.
IT Tracker uygulamasının hata ve exception'larını `errors.inventist.com.tr` adresine iletir.

---

## Mimari

```
ittracker-web → sentry-sdk → Glitchtip (Docker) → Cloudflare Tunnel → errors.inventist.com.tr
```

Glitchtip stack bileşenleri:
- `glitchtip-postgres` — kalıcı veri
- `glitchtip-redis` — kuyruk
- `glitchtip-web` — UI + API (127.0.0.1:8086)
- `glitchtip-worker` — Celery hata işleyici + zamanlanmış görev
- `glitchtip-migrate` — tek seferlik migration (restart: no)

---

## 1. Tek Seferlik Kurulum (Sunucuda)

### 1.1 Env dosyasını oluştur

```bash
cat > /home/leventcan/ittracker/.env.glitchtip <<'EOF'
SECRET_KEY=<rastgele-uzun-string>      # python3 -c "import secrets; print(secrets.token_hex(40))"
DATABASE_URL=postgresql://glitchtip:${POSTGRES_PASSWORD}@glitchtip-postgres/glitchtip
REDIS_URL=redis://glitchtip-redis:6379
CELERY_BROKER_URL=redis://glitchtip-redis:6379
POSTGRES_PASSWORD=<guclu-sifre>
EMAIL_URL=smtp+tls://user:pass@smtp.office365.com:587
DEFAULT_FROM_EMAIL=admin@inventist.com.tr
GLITCHTIP_DOMAIN=https://errors.inventist.com.tr
ENABLE_OPEN_USER_REGISTRATION=False
CELERY_WORKER_AUTOSCALE=1,3
EOF
chmod 600 /home/leventcan/ittracker/.env.glitchtip
```

> **Not:** `${POSTGRES_PASSWORD}` shell expansion çalışması için bu değeri DATABASE_URL içinde literal yazın.

### 1.2 Stack'i başlat ve migrate et

```bash
cd /home/leventcan/ittracker

# Migration önce
docker compose -f docker-compose.glitchtip.yml --env-file .env.glitchtip run --rm glitchtip-migrate

# Sonra servisleri kaldır
docker compose -f docker-compose.glitchtip.yml --env-file .env.glitchtip up -d glitchtip-postgres glitchtip-redis glitchtip-web glitchtip-worker
```

### 1.3 Superuser oluştur

```bash
docker compose -f docker-compose.glitchtip.yml --env-file .env.glitchtip \
  exec glitchtip-web ./manage.py createsuperuser
```

---

## 2. Cloudflare Tunnel Route Ekleme

Cloudflare Zero Trust → Tunnels → `ittracker-prod-tunnel` → Public Hostnames → Add:

| Alan | Değer |
|---|---|
| Subdomain | `errors` |
| Domain | `inventist.com.tr` |
| Service Type | `HTTP` |
| URL | `localhost:8086` |

---

## 3. Glitchtip UI'da Proje Oluşturma

1. `https://errors.inventist.com.tr` → superuser ile giriş
2. **Create Organization** → `Inventist IT`
3. **Create Project** → Platform: `Python → Django/Flask` → Name: `ittracker-prod`
4. Proje oluşturulduktan sonra **DSN** kopyalanır:  
   `https://<key>@errors.inventist.com.tr/<project-id>`

---

## 4. .env'e DSN Ekle

Sunucuda:

```bash
# Prod .env
echo 'GLITCHTIP_DSN=https://KEY@errors.inventist.com.tr/1' >> /home/leventcan/ittracker/.env
echo 'APP_ENV=production' >> /home/leventcan/ittracker/.env
echo 'APP_VERSION=v5.0' >> /home/leventcan/ittracker/.env

# Staging .env (isteğe bağlı — ayrı proje oluşturulursa)
echo 'GLITCHTIP_DSN=' >> /home/leventcan/ittracker/.env.staging
echo 'APP_ENV=staging' >> /home/leventcan/ittracker/.env.staging
```

Sonra uygulamayı yeniden başlat:

```bash
docker compose -p ittracker -f docker-compose.yml --env-file .env restart web
```

---

## 5. Test Hatası Gönderme

```bash
docker compose -p ittracker -f docker-compose.yml exec web \
  python3 -c "
import sentry_sdk
sentry_sdk.init(dsn='$(grep GLITCHTIP_DSN /home/leventcan/ittracker/.env | cut -d= -f2)')
sentry_sdk.capture_message('IT Tracker Glitchtip testi OK')
print('gonderildi')
"
```

Birkaç saniye sonra `https://errors.inventist.com.tr` → Issues'da görünmeli.

---

## Güncelleme

```bash
cd /home/leventcan/ittracker
docker compose -f docker-compose.glitchtip.yml --env-file .env.glitchtip pull
docker compose -f docker-compose.glitchtip.yml --env-file .env.glitchtip \
  run --rm glitchtip-migrate
docker compose -f docker-compose.glitchtip.yml --env-file .env.glitchtip up -d
```

---

## Sorun Giderme

| Belirti | Kontrol |
|---|---|
| 502 Bad Gateway | `docker ps \| grep glitchtip-web` — container ayakta mı? |
| DSN reddediliyor | Proje DSN doğru kopyalandı mı? Cloudflare Tunnel route URL `localhost:8086` mi? |
| Mail gitmiyor | `.env.glitchtip` EMAIL_URL syntaxı: `smtp+tls://user:pass@host:port` |
| Worker durdu | `docker compose ... logs glitchtip-worker` |
| Disk dolu | Glitchtip varsayılan olarak 90 gün olay saklar. Proje ayarlarından kısaltılabilir. |
