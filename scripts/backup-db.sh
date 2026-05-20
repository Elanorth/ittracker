#!/usr/bin/env bash
# IT Tracker — Otomatik DB + Config Yedek
# Calistirma: cron (gece 03:00) tarafindan
# Lokal: 30 gun gunluk + 12 ay aylik snapshot
# NAS: aynisi SMB uzerinden
# Hata: admin@inventist.com.tr'ye mail (Python smtplib + .env)
set -euo pipefail

# === Konfig ===
PROD_DIR="/home/leventcan/ittracker"
LOCAL_BACKUP_DIR="/srv/it_tracker/backups/auto"
LOCAL_DAILY="$LOCAL_BACKUP_DIR/daily"
LOCAL_MONTHLY="$LOCAL_BACKUP_DIR/monthly"
LOG_FILE="$LOCAL_BACKUP_DIR/backup.log"
NOTIFY_SCRIPT="$PROD_DIR/scripts/backup-mail.py"

SMB_HOST="10.34.0.61"
SMB_SHARE="Inventist_IT"
SMB_REMOTE_DIR="Ittracker DB"
SMB_CREDS="/home/leventcan/.ittracker-backup-creds"

WEB_CONTAINER="ittracker-web-1"
CONFIG_BACKUP_VOLUME="ittracker_backups"

# === Hazirlik ===
mkdir -p "$LOCAL_DAILY" "$LOCAL_MONTHLY"
exec >> "$LOG_FILE" 2>&1

DATE_TS=$(date +%Y%m%d_%H%M%S)
DAY=$(date +%d)
MONTH_TAG=$(date +%Y%m)
IS_MONTHLY=$([ "$DAY" = "01" ] && echo "yes" || echo "no")

echo ""
echo "===== $(date -Iseconds) backup baslangic (monthly=$IS_MONTHLY) ====="

# === Hata yakalama ===
notify_failure() {
  local msg="$1"
  echo "FAIL: $msg"
  if [ -x "$NOTIFY_SCRIPT" ] || [ -f "$NOTIFY_SCRIPT" ]; then
    /usr/bin/python3 "$NOTIFY_SCRIPT" "IT Tracker yedek HATA" "$(date -Iseconds): $msg" || \
      echo "WARN: mail gonderilemedi"
  fi
  exit 1
}
trap 'notify_failure "Script beklenmedik hatayla durdu (line $LINENO)"' ERR

# === 1. SQLite atomik yedek (Python .backup() — WAL-safe) ===
TMP_SNAP="/tmp/ittracker_snap_${DATE_TS}.db"
docker exec "$WEB_CONTAINER" python -c "
import sqlite3, sys
try:
    src = sqlite3.connect('/app/instance/it_tracker.db')
    dst = sqlite3.connect('/tmp/snap.db')
    src.backup(dst)
    dst.close(); src.close()
except Exception as e:
    print('SQLITE_BACKUP_ERROR:', e, file=sys.stderr); sys.exit(2)
" || notify_failure "sqlite backup container'da basarisiz"

docker cp "$WEB_CONTAINER:/tmp/snap.db" "$TMP_SNAP"
docker exec "$WEB_CONTAINER" rm -f /tmp/snap.db

LOCAL_GZ="$LOCAL_DAILY/db_${DATE_TS}.db.gz"
gzip -9 -c "$TMP_SNAP" > "$LOCAL_GZ"
rm -f "$TMP_SNAP"
DB_SIZE=$(stat -c %s "$LOCAL_GZ")
echo "Lokal yedek: $LOCAL_GZ ($DB_SIZE byte)"

# === 2. Aylik snapshot (her ayin 1'inde) ===
if [ "$IS_MONTHLY" = "yes" ]; then
  MONTHLY_GZ="$LOCAL_MONTHLY/db_${MONTH_TAG}.db.gz"
  cp "$LOCAL_GZ" "$MONTHLY_GZ"
  echo "Aylik snapshot: $MONTHLY_GZ"

  # Config dosyalarini da aylik yedekle (tar.gz)
  CONFIGS_TGZ="$LOCAL_MONTHLY/configs_${MONTH_TAG}.tar.gz"
  docker run --rm \
    -v "${CONFIG_BACKUP_VOLUME}:/data:ro" \
    -v "$LOCAL_MONTHLY:/out" \
    alpine \
    sh -c "cd /data && tar czf /out/configs_${MONTH_TAG}.tar.gz . 2>/dev/null || echo 'config volume bos'" \
    || echo "WARN: config tar.gz olusturulamadi"
  if [ -f "$CONFIGS_TGZ" ]; then
    echo "Aylik config yedek: $CONFIGS_TGZ ($(stat -c %s "$CONFIGS_TGZ") byte)"
  fi
fi

# === 3. NAS'a yukle (SMB) ===
if [ ! -f "$SMB_CREDS" ]; then
  notify_failure "SMB credentials dosyasi yok: $SMB_CREDS"
fi
# shellcheck disable=SC1090
. "$SMB_CREDS"
: "${SMB_USER:?}" "${SMB_PASS:?}"

upload_smb() {
  local local_path="$1"
  local remote_name="$2"
  local subdir="$3"  # daily veya monthly
  smbclient "//${SMB_HOST}/${SMB_SHARE}" "$SMB_PASS" -U "$SMB_USER" -c \
    "prompt OFF; cd \"${SMB_REMOTE_DIR}\"; mkdir ${subdir} 2>/dev/null; cd ${subdir}; put \"$local_path\" \"$remote_name\"" \
    2>&1 | grep -vE "^(Domain=|Anonymous|prompt|mkdir|Can't mkdir|NT_STATUS_OBJECT_NAME_COLLISION)" || true
}

upload_smb "$LOCAL_GZ" "db_${DATE_TS}.db.gz" "daily"
echo "NAS daily yukleme: db_${DATE_TS}.db.gz"

if [ "$IS_MONTHLY" = "yes" ]; then
  upload_smb "$LOCAL_MONTHLY/db_${MONTH_TAG}.db.gz" "db_${MONTH_TAG}.db.gz" "monthly"
  echo "NAS monthly DB yukleme: db_${MONTH_TAG}.db.gz"
  if [ -f "$LOCAL_MONTHLY/configs_${MONTH_TAG}.tar.gz" ]; then
    upload_smb "$LOCAL_MONTHLY/configs_${MONTH_TAG}.tar.gz" "configs_${MONTH_TAG}.tar.gz" "monthly"
    echo "NAS monthly config yukleme: configs_${MONTH_TAG}.tar.gz"
  fi
fi

# === 4. Lokal rotation (30 gun gunluk, 12 ay aylik) ===
find "$LOCAL_DAILY" -name "db_*.db.gz" -mtime +30 -delete && echo "Lokal daily rotation: 30+ gun silindi"
find "$LOCAL_MONTHLY" -name "db_*.db.gz" -mtime +365 -delete && echo "Lokal monthly DB rotation: 365+ gun silindi"
find "$LOCAL_MONTHLY" -name "configs_*.tar.gz" -mtime +365 -delete && echo "Lokal monthly config rotation: 365+ gun silindi"

echo "===== $(date -Iseconds) backup OK ====="
