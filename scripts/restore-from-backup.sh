#!/usr/bin/env bash
# IT Tracker — Yedekten geri yukleme (manuel, PostgreSQL)
# Kullanim:
#   ./restore-from-backup.sh list                  → mevcut yedekleri listele
#   ./restore-from-backup.sh local <gz_path>       → lokal yedegi staging'e yukle
#   ./restore-from-backup.sh nas daily <filename>  → NAS daily klasorunden geri yukle
#   ./restore-from-backup.sh nas monthly <filename> → NAS monthly klasorunden geri yukle
#
# Dosya formati: .sql.gz (PostgreSQL pg_dump) — Level 2 - C sonrasi
#                .db.gz   (eski SQLite donemi) — artik dogrudan restore edilemiyor
#                                                 (manuel yontem icin docs/backup-setup.md)
#
# DIKKAT: Hedef her zaman staging'tir (asla prod degil). Prod restore icin manuel ssh + psql.
set -euo pipefail

LOCAL_BACKUP_DIR="/srv/it_tracker/backups/auto"
SMB_HOST="10.34.0.61"
SMB_SHARE="Inventist_IT"
SMB_REMOTE_DIR="Ittracker DB"
SMB_CREDS="/home/leventcan/.ittracker-backup-creds"
STAGING_DIR="/home/leventcan/ittracker-staging"

# Staging Postgres bilgileri (.env.staging'den okunur)
STAGING_DB_CONTAINER="ittracker-staging-db"
STAGING_WEB_CONTAINER="ittracker-staging-web"

ACTION="${1:-}"
ARG2="${2:-}"
ARG3="${3:-}"

# Staging .env'den Postgres credentials oku (SADECE POSTGRES_* satirlari, full source riskli)
_load_staging_pg() {
  STAGING_PG_USER=$(grep -E '^POSTGRES_USER=' "$STAGING_DIR/.env.staging" 2>/dev/null | head -1 | cut -d= -f2-)
  STAGING_PG_DB=$(grep -E '^POSTGRES_DB=' "$STAGING_DIR/.env.staging" 2>/dev/null | head -1 | cut -d= -f2-)
  if [ -z "${STAGING_PG_USER:-}" ] || [ -z "${STAGING_PG_DB:-}" ]; then
    echo "HATA: $STAGING_DIR/.env.staging icinde POSTGRES_USER veya POSTGRES_DB tanimli degil"
    exit 1
  fi
}

# Tek bir gz dosyasini Postgres'e restore et
_restore_to_postgres() {
  local gz_path="$1"
  local ext="${gz_path##*.}"  # son uzanti (gz icin yetersiz, base check edelim)
  local base_ext="${gz_path%.gz}"
  base_ext="${base_ext##*.}"  # .sql.gz icin "sql", .db.gz icin "db"

  case "$base_ext" in
    sql)
      _load_staging_pg
      echo "Yedek formati: PostgreSQL (.sql.gz)"
      echo "Hedef: $STAGING_DB_CONTAINER / $STAGING_PG_DB"
      read -rp "Onayliyor musunuz? [yes/HAYIR]: " ans
      [ "$ans" = "yes" ] || { echo "iptal"; return 0; }

      # Mevcut DB'yi yedekle (rollback icin)
      ROLLBACK="/tmp/staging_rollback_$(date +%s).sql"
      docker exec "$STAGING_DB_CONTAINER" pg_dump -U "$STAGING_PG_USER" -d "$STAGING_PG_DB" --clean --if-exists --no-owner > "$ROLLBACK" \
        && echo "Rollback noktasi: $ROLLBACK" \
        || { echo "UYARI: rollback dump'i alinamadi (devam ediliyor)"; }

      # Restore — sql.gz icindeki SQL'i psql'e pipe et
      gunzip -c "$gz_path" | docker exec -i "$STAGING_DB_CONTAINER" psql -U "$STAGING_PG_USER" -d "$STAGING_PG_DB" \
        > /tmp/restore.log 2>&1
      echo "Restore tamamlandi. Son 10 satir log:"
      tail -10 /tmp/restore.log

      # Web restart
      docker compose -p ittracker-staging -f "$STAGING_DIR/docker-compose.staging.yml" restart web
      echo "OK: staging restore tamamlandi (Postgres)"
      ;;

    db)
      echo "Yedek formati: SQLite (.db.gz) — Level 2 - C cutover'dan onceki donem."
      echo ""
      echo "Staging artik PostgreSQL kullaniyor. SQLite yedegini dogrudan restore edemeyiz."
      echo "Manuel yontem:"
      echo "  1) gunzip -c '$gz_path' > /tmp/legacy.db"
      echo "  2) pgloader uygulamasi ile SQLite -> Postgres taşi (bkz: scripts/migrate-sqlite-to-postgres.sh)"
      echo "  3) docker run --rm --network ittracker-staging_default \\"
      echo "       -v /tmp/legacy.db:/tmp/source.db:ro dimitri/pgloader:latest \\"
      echo "       pgloader --with 'include drop' sqlite:///tmp/source.db \\"
      echo "       postgresql://$STAGING_PG_USER:\$PASS@$STAGING_DB_CONTAINER:5432/$STAGING_PG_DB"
      return 0
      ;;

    *)
      echo "Bilinmeyen yedek formati: $gz_path"
      echo "Beklenen: .sql.gz veya .db.gz"
      exit 1
      ;;
  esac
}

case "$ACTION" in
  list)
    echo "=== LOKAL DAILY (son 10) ==="
    ls -lh "$LOCAL_BACKUP_DIR/daily/" 2>/dev/null | tail -10 || echo "yok"
    echo
    echo "=== LOKAL MONTHLY ==="
    ls -lh "$LOCAL_BACKUP_DIR/monthly/" 2>/dev/null || echo "yok"
    echo
    . "$SMB_CREDS"
    SMB_DOMAIN="${SMB_DOMAIN:-}"
    if [ -n "$SMB_DOMAIN" ]; then U="${SMB_DOMAIN}\\${SMB_USER}"; else U="$SMB_USER"; fi
    echo "=== NAS DAILY (son 10) ==="
    smbclient "//${SMB_HOST}/${SMB_SHARE}" "$SMB_PASS" -U "$U" -c "cd \"${SMB_REMOTE_DIR}/daily\"; ls" 2>/dev/null | tail -15 || echo "NAS daily erisilemedi"
    echo
    echo "=== NAS MONTHLY ==="
    smbclient "//${SMB_HOST}/${SMB_SHARE}" "$SMB_PASS" -U "$U" -c "cd \"${SMB_REMOTE_DIR}/monthly\"; ls" 2>/dev/null | tail -20 || echo "NAS monthly erisilemedi"
    ;;

  local)
    [ -z "$ARG2" ] && { echo "kullanim: $0 local <gz_dosya_yolu>"; exit 1; }
    [ ! -f "$ARG2" ] && { echo "Dosya yok: $ARG2"; exit 1; }
    _restore_to_postgres "$ARG2"
    ;;

  nas)
    { [ -z "$ARG2" ] || [ -z "$ARG3" ]; } && { echo "kullanim: $0 nas daily|monthly <filename>"; exit 1; }
    [ "$ARG2" != "daily" ] && [ "$ARG2" != "monthly" ] && { echo "tip: daily|monthly"; exit 1; }
    . "$SMB_CREDS"
    SMB_DOMAIN="${SMB_DOMAIN:-}"
    if [ -n "$SMB_DOMAIN" ]; then U="${SMB_DOMAIN}\\${SMB_USER}"; else U="$SMB_USER"; fi
    TMP="/tmp/restore_${ARG3}"
    smbclient "//${SMB_HOST}/${SMB_SHARE}" "$SMB_PASS" -U "$U" -c "cd \"${SMB_REMOTE_DIR}/${ARG2}\"; get \"$ARG3\" \"$TMP\""
    [ ! -f "$TMP" ] && { echo "indirme basarisiz"; exit 1; }
    echo "Indirildi: $TMP ($(stat -c %s "$TMP") byte)"
    _restore_to_postgres "$TMP"
    rm -f "$TMP"
    ;;

  *)
    echo "Kullanim:"
    echo "  $0 list                          → yedekleri listele (lokal + NAS)"
    echo "  $0 local <gz_path>               → lokal .sql.gz veya .db.gz staging'e yukle"
    echo "  $0 nas daily <filename>          → NAS/daily'den staging'e yukle"
    echo "  $0 nas monthly <filename>        → NAS/monthly'den staging'e yukle"
    exit 2
    ;;
esac
