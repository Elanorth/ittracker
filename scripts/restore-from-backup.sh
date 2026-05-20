#!/usr/bin/env bash
# IT Tracker — Yedekten geri yukleme (manuel)
# Kullanim:
#   ./restore-from-backup.sh list                  → mevcut yedekleri listele
#   ./restore-from-backup.sh local <gz_path>       → lokal .db.gz dosyasini staging'e yukle
#   ./restore-from-backup.sh nas daily <filename>  → NAS daily klasorunden geri yukle
#   ./restore-from-backup.sh nas monthly <filename> → NAS monthly klasorunden geri yukle
#
# DIKKAT: Hedef her zaman staging'tir (asla prod degil). Prod restore icin manuel ssh + cp.
set -euo pipefail

LOCAL_BACKUP_DIR="/srv/it_tracker/backups/auto"
SMB_HOST="10.34.0.61"
SMB_SHARE="Inventist_IT"
SMB_REMOTE_DIR="Ittracker DB"
SMB_CREDS="/home/leventcan/.ittracker-backup-creds"
STAGING_DIR="/home/leventcan/ittracker-staging"
STAGING_DB="$STAGING_DIR/instance/staging.db"

ACTION="${1:-}"
ARG2="${2:-}"
ARG3="${3:-}"

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
    echo "Hedef: $STAGING_DB"
    read -rp "Onayliyor musunuz? [yes/HAYIR]: " ans
    [ "$ans" = "yes" ] || { echo "iptal"; exit 0; }
    mkdir -p "$(dirname "$STAGING_DB")"
    [ -f "$STAGING_DB" ] && cp "$STAGING_DB" "${STAGING_DB}.before-restore-$(date +%s)"
    gunzip -c "$ARG2" > "$STAGING_DB"
    docker compose -p ittracker-staging -f "$STAGING_DIR/docker-compose.staging.yml" restart web
    echo "OK: staging restore tamamlandi"
    ;;

  nas)
    [ -z "$ARG2" ] || [ -z "$ARG3" ] && { echo "kullanim: $0 nas daily|monthly <filename>"; exit 1; }
    [ "$ARG2" != "daily" ] && [ "$ARG2" != "monthly" ] && { echo "tip: daily|monthly"; exit 1; }
    . "$SMB_CREDS"
    SMB_DOMAIN="${SMB_DOMAIN:-}"
    if [ -n "$SMB_DOMAIN" ]; then U="${SMB_DOMAIN}\\${SMB_USER}"; else U="$SMB_USER"; fi
    TMP="/tmp/restore_${ARG3}"
    smbclient "//${SMB_HOST}/${SMB_SHARE}" "$SMB_PASS" -U "$U" -c "cd \"${SMB_REMOTE_DIR}/${ARG2}\"; get \"$ARG3\" \"$TMP\""
    [ ! -f "$TMP" ] && { echo "indirme basarisiz"; exit 1; }
    echo "Indirildi: $TMP ($(stat -c %s "$TMP") byte)"
    echo "Hedef: $STAGING_DB"
    read -rp "Onayliyor musunuz? [yes/HAYIR]: " ans
    [ "$ans" = "yes" ] || { rm -f "$TMP"; echo "iptal"; exit 0; }
    [ -f "$STAGING_DB" ] && cp "$STAGING_DB" "${STAGING_DB}.before-restore-$(date +%s)"
    gunzip -c "$TMP" > "$STAGING_DB"
    rm -f "$TMP"
    docker compose -p ittracker-staging -f "$STAGING_DIR/docker-compose.staging.yml" restart web
    echo "OK: staging restore tamamlandi"
    ;;

  *)
    echo "Kullanim:"
    echo "  $0 list                          → yedekleri listele (lokal + NAS)"
    echo "  $0 local <gz_path>               → lokal .db.gz'i staging'e yukle"
    echo "  $0 nas daily <filename>          → NAS/daily'den staging'e yukle"
    echo "  $0 nas monthly <filename>        → NAS/monthly'den staging'e yukle"
    exit 2
    ;;
esac
