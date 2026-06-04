#!/usr/bin/env bash
# IT Tracker — Otomatik DB + Config Yedek (PostgreSQL)
# Calistirma: cron (gece 03:00) tarafindan
# Lokal: 30 gun gunluk + 12 ay aylik snapshot (.sql.gz)
# NAS: aynisi SMB uzerinden
# Hata: admin@inventist.com.tr'ye mail (Python smtplib + .env)
#
# Not (Level 2 - C sonrasi): Prod artik PostgreSQL kullaniyor.
# Eski .db.gz (SQLite) yedekler /srv/it_tracker/backups/auto/ altinda kalir
# (rotation suresi boyunca silinene kadar). Yeni yedekler .sql.gz (pg_dump).
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

DB_CONTAINER="ittracker-db-1"
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

# === 1. PostgreSQL pg_dump (custom format compatible with pg_restore) ===
# Postgres credentials'i .env'den oku (SADECE bu satirlari grep et — full source
# riskli, SMTP_PASS gibi alanlar bash'in ozel kabul ettigi karakterler icerebilir).
POSTGRES_USER=$(grep -E '^POSTGRES_USER=' "$PROD_DIR/.env" | head -1 | cut -d= -f2-)
POSTGRES_DB=$(grep -E '^POSTGRES_DB=' "$PROD_DIR/.env" | head -1 | cut -d= -f2-)
[ -z "$POSTGRES_USER" ] && notify_failure "POSTGRES_USER .env'de tanimli degil"
[ -z "$POSTGRES_DB" ] && notify_failure "POSTGRES_DB .env'de tanimli degil"

# pg_dump options:
#   --clean      restore sirasinda once DROP yapsin
#   --if-exists  DROP IF EXISTS (tablo yoksa hata vermesin)
#   --no-owner   ownership SQL'i ekleme (farkli kullanici ile restore icin)
TMP_SNAP="/tmp/ittracker_snap_${DATE_TS}.sql"
docker exec "$DB_CONTAINER" pg_dump \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --clean --if-exists --no-owner \
    > "$TMP_SNAP" \
  || notify_failure "pg_dump basarisiz"

LOCAL_GZ="$LOCAL_DAILY/db_${DATE_TS}.sql.gz"
gzip -9 -c "$TMP_SNAP" > "$LOCAL_GZ"
rm -f "$TMP_SNAP"
DB_SIZE=$(stat -c %s "$LOCAL_GZ")
echo "Lokal yedek: $LOCAL_GZ ($DB_SIZE byte)"

# === 2. Aylik snapshot (her ayin 1'inde) ===
if [ "$IS_MONTHLY" = "yes" ]; then
  MONTHLY_GZ="$LOCAL_MONTHLY/db_${MONTH_TAG}.sql.gz"
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
SMB_DOMAIN="${SMB_DOMAIN:-}"  # AD ortaminda gerekli; calisma grubu icin bos birak

upload_smb() {
  local local_path="$1"
  local remote_name="$2"
  local subdir="$3"  # daily veya monthly
  local user_arg
  if [ -n "$SMB_DOMAIN" ]; then
    user_arg="${SMB_DOMAIN}\\${SMB_USER}"
  else
    user_arg="$SMB_USER"
  fi
  smbclient "//${SMB_HOST}/${SMB_SHARE}" "$SMB_PASS" -U "$user_arg" -c \
    "prompt OFF; cd \"${SMB_REMOTE_DIR}\"; mkdir ${subdir} 2>/dev/null; cd ${subdir}; put \"$local_path\" \"$remote_name\"" \
    2>&1 | grep -vE "^(Domain=|Anonymous|prompt|mkdir|Can't mkdir|NT_STATUS_OBJECT_NAME_COLLISION)" || true
}

upload_smb "$LOCAL_GZ" "db_${DATE_TS}.sql.gz" "daily"
echo "NAS daily yukleme: db_${DATE_TS}.sql.gz"

if [ "$IS_MONTHLY" = "yes" ]; then
  upload_smb "$LOCAL_MONTHLY/db_${MONTH_TAG}.sql.gz" "db_${MONTH_TAG}.sql.gz" "monthly"
  echo "NAS monthly DB yukleme: db_${MONTH_TAG}.sql.gz"
  if [ -f "$LOCAL_MONTHLY/configs_${MONTH_TAG}.tar.gz" ]; then
    upload_smb "$LOCAL_MONTHLY/configs_${MONTH_TAG}.tar.gz" "configs_${MONTH_TAG}.tar.gz" "monthly"
    echo "NAS monthly config yukleme: configs_${MONTH_TAG}.tar.gz"
  fi
fi

# === 4. Lokal rotation (30 gun gunluk, 12 ay aylik) ===
# Hem yeni .sql.gz hem eski .db.gz (SQLite donemi) yedekleri rotate et
find "$LOCAL_DAILY" \( -name "db_*.sql.gz" -o -name "db_*.db.gz" \) -mtime +30 -delete \
  && echo "Lokal daily rotation: 30+ gun silindi"
find "$LOCAL_MONTHLY" \( -name "db_*.sql.gz" -o -name "db_*.db.gz" \) -mtime +365 -delete \
  && echo "Lokal monthly DB rotation: 365+ gun silindi"
find "$LOCAL_MONTHLY" -name "configs_*.tar.gz" -mtime +365 -delete \
  && echo "Lokal monthly config rotation: 365+ gun silindi"

echo "===== $(date -Iseconds) backup OK ====="
