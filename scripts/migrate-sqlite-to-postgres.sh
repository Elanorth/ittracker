#!/usr/bin/env bash
# IT Tracker — SQLite'tan PostgreSQL'e veri taşıma (tek seferlik)
#
# Kullanım:
#   ./scripts/migrate-sqlite-to-postgres.sh staging
#   ./scripts/migrate-sqlite-to-postgres.sh prod
#
# Ön koşullar:
#   - docker-compose'da `db` servisi ayakta (postgres:16-alpine)
#   - Sunucudaki SQLite DB: instance/it_tracker.db (prod) veya instance/staging.db (staging)
#   - .env veya .env.staging içinde POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB tanımlı
#
# Süreç:
#   1. App container'ı durdur (DB lock'u serbest kalsın)
#   2. SQLite snapshot al
#   3. pgloader ile Postgres'e veri kopyala (Docker container'da)
#   4. App container'ı RestartPolicy ile yeniden başlat
#   5. Smoke test
#
# Manuel sonraki adım: .env(.staging)'de DATABASE_URL'i postgresql://'e çevirip
# `docker compose restart web` çalıştırın.

set -euo pipefail

ENV_NAME="${1:-}"
if [ -z "$ENV_NAME" ]; then
    echo "Kullanım: $0 staging|prod"
    exit 1
fi

case "$ENV_NAME" in
    staging)
        PROJECT="ittracker-staging"
        COMPOSE_FILE="docker-compose.staging.yml"
        ENV_FILE=".env.staging"
        DIR="/home/leventcan/ittracker-staging"
        SQLITE_NAME="staging.db"
        WEB_CONTAINER="ittracker-staging-web"
        DB_CONTAINER="ittracker-staging-db"
        NETWORK="ittracker-staging_default"
        ;;
    prod)
        PROJECT="ittracker"
        COMPOSE_FILE="docker-compose.yml"
        ENV_FILE=".env"
        DIR="/home/leventcan/ittracker"
        SQLITE_NAME="it_tracker.db"
        WEB_CONTAINER="ittracker-web-1"
        DB_CONTAINER="ittracker-db-1"
        NETWORK="ittracker_default"
        ;;
    *)
        echo "Bilinmeyen ortam: $ENV_NAME (staging veya prod olmalı)"
        exit 1
        ;;
esac

cd "$DIR"

# .env'den SADECE Postgres credentials'ı extract et.
# Tüm .env'i source etmek riskli — SMTP_PASS gibi alanlar bash'in özel kabul ettiği
# karakterler (örn. ')', '(') içerebilir ve "syntax error" verir.
POSTGRES_USER=$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -1 | cut -d= -f2-)
POSTGRES_PASSWORD=$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2-)
POSTGRES_DB=$(grep -E '^POSTGRES_DB=' "$ENV_FILE" | head -1 | cut -d= -f2-)
[ -z "${POSTGRES_USER:-}" ] && { echo "HATA: $ENV_FILE icinde POSTGRES_USER tanimli degil"; exit 1; }
[ -z "${POSTGRES_PASSWORD:-}" ] && { echo "HATA: $ENV_FILE icinde POSTGRES_PASSWORD tanimli degil"; exit 1; }
[ -z "${POSTGRES_DB:-}" ] && { echo "HATA: $ENV_FILE icinde POSTGRES_DB tanimli degil"; exit 1; }

SQLITE_PATH="$DIR/instance/$SQLITE_NAME"
[ ! -f "$SQLITE_PATH" ] && { echo "HATA: SQLite dosyası yok: $SQLITE_PATH"; exit 2; }

echo "=== $(date) Migration başlıyor: $ENV_NAME ==="
echo "  Kaynak SQLite : $SQLITE_PATH"
echo "  Hedef Postgres: $POSTGRES_USER@$DB_CONTAINER/$POSTGRES_DB"

# 1) Yedek snapshot — /tmp/'ye al (instance/ klasörü prod'da root:root sahipliğinde
#    olabilir ve leventcan oraya yazamaz). /tmp her zaman yazılabilir, rollback için
#    yeterli; ayrıca otomatik nightly backup nasıl olsa zaten var.
STAMP=$(date +%Y%m%d_%H%M%S)
SNAPSHOT="/tmp/${SQLITE_NAME%.db}_pre_pg_migration_${STAMP}.db"
cp "$SQLITE_PATH" "$SNAPSHOT" 2>/dev/null || sudo -n cp "$SQLITE_PATH" "$SNAPSHOT"
sudo -n chown "$(id -u):$(id -g)" "$SNAPSHOT" 2>/dev/null || true
echo "✓ Snapshot: $SNAPSHOT"

# 2) Web container'ı durdur (DB lock serbestlesin)
echo "→ Web container durduruluyor..."
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" stop web

# 3) Postgres'in healthy olduğundan emin ol
echo "→ Postgres healthcheck bekleniyor..."
for i in 1 2 3 4 5; do
    if docker exec "$DB_CONTAINER" pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; then
        echo "✓ Postgres hazır"
        break
    fi
    sleep 5
done

# 4) pgloader ile veri taşıma — Docker container içinde
#    SQLite dosyasını volume mount ile sokuyoruz, Postgres'e network üzerinden bağlanıyoruz
PG_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$DB_CONTAINER:5432/$POSTGRES_DB"
echo "→ pgloader ile veri taşınıyor..."
docker run --rm \
    --network "$NETWORK" \
    -v "$SQLITE_PATH:/tmp/source.db:ro" \
    dimitri/pgloader:latest \
    pgloader \
        --with "quote identifiers" \
        --with "include drop" \
        --with "create tables" \
        --with "create indexes" \
        --with "reset sequences" \
        sqlite:///tmp/source.db \
        "$PG_URL"

# 5) Sequence düzeltmesi — KRİTİK
# pgloader `--with "reset sequences"` flag'i her zaman tüm tablolarda çalışmıyor.
# id kolonu DEFAULT'sı NULL kalıyor → SQLAlchemy INSERT'te id=NULL gönderiyor
# → NotNullViolation → tüm transaction rollback (edit/delete dahil).
# Çözüm: her tablo için id_seq oluştur, DEFAULT ata, max(id)+1'den başlat.
echo ""
echo "→ Sequence'ler düzeltiliyor (pgloader bug fix)..."
docker exec -i "$DB_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'PSQL'
BEGIN;
DO $$
DECLARE
    t TEXT;
    max_id BIGINT;
    seq_start BIGINT;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.columns
        WHERE table_schema = 'public' AND column_name = 'id'
          AND column_default IS NULL
        ORDER BY table_name
    LOOP
        EXECUTE format('SELECT COALESCE(MAX(id), 0) FROM %I', t) INTO max_id;
        seq_start := max_id + 1;
        EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %I OWNED BY %I.id',
                       t || '_id_seq', t);
        EXECUTE format('ALTER SEQUENCE %I RESTART WITH %s',
                       t || '_id_seq', seq_start);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN id SET DEFAULT nextval(%L::regclass)',
                       t, t || '_id_seq');
        RAISE NOTICE '% : sequence created (next id = %)', t, seq_start;
    END LOOP;
END $$;
COMMIT;
PSQL

# 6) Postgres'te tablo sayısı doğrulaması
echo ""
echo "=== Postgres tablo sayıları ==="
docker exec "$DB_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT schemaname, relname, n_live_tup AS satir_sayisi
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
"

# 6) Web container'ı tekrar başlat (eski DATABASE_URL ile — kullanıcı henüz değiştirmedi)
echo "→ Web container yeniden başlatılıyor (eski DB ile — sonraki adımda DATABASE_URL'i değiştirin)..."
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d web

echo ""
echo "=== TAMAMLANDI ==="
echo ""
echo "Sonraki manuel adım:"
echo "  1) $ENV_FILE içinde DATABASE_URL'i şuna güncelle:"
echo "       DATABASE_URL=postgresql://$POSTGRES_USER:\$POSTGRES_PASSWORD@db:5432/$POSTGRES_DB"
echo "  2) docker compose -p $PROJECT -f $COMPOSE_FILE --env-file $ENV_FILE up -d web"
echo "  3) Sağlık kontrolü:"
echo "       docker compose -p $PROJECT -f $COMPOSE_FILE exec web flask db current"
echo "       curl -I https://<staging|prod>.inventist.com.tr/login"
echo ""
echo "Rollback gerekirse SQLite snapshot: $SNAPSHOT"
