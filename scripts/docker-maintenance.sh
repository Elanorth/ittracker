#!/usr/bin/env bash
# IT Tracker — Haftalık Docker bakımı + disk doluluk alarmı
# Calistirma: cron (Pazar 04:00, gece yedeğinden sonra)
#
# Neden: GHCR'a geçişten sonra her deploy yeni image katmanı + build cache
# bırakıyor. Birikim disk'i doldurursa Postgres "No space left" ile crash eder
# (2026-06-14'te yaşandı — site 2 gün down). Bu script birikimleri temizler ve
# disk eşiği aşılırsa admin'e mail atar.
set -euo pipefail

PROD_DIR="/home/leventcan/ittracker"
NOTIFY_SCRIPT="$PROD_DIR/scripts/backup-mail.py"
LOG_FILE="/srv/it_tracker/backups/auto/docker-maintenance.log"
DISK_THRESHOLD=85   # % — bu eşiği aşarsa uyarı maili

mkdir -p "$(dirname "$LOG_FILE")"
exec >> "$LOG_FILE" 2>&1

echo ""
echo "===== $(date -Iseconds) docker bakım başlangıç ====="

# Temizlik öncesi disk
BEFORE=$(df / --output=pcent 2>/dev/null | tail -1 | tr -dc '0-9')
echo "Disk (önce): %${BEFORE}"

# 1. Kullanılmayan image'lar (7 gün+ eski, çalışan container'ların image'ı korunur)
echo "→ Kullanılmayan image temizliği..."
docker image prune -af --filter "until=168h" 2>&1 | tail -2

# 2. Build cache (7 gün+ eski)
echo "→ Build cache temizliği..."
docker builder prune -af --filter "until=168h" 2>&1 | tail -2

# 3. Dangling volume YOK — veri kaybı riski, dokunma (pgdata vs.)

# Temizlik sonrası disk
AFTER=$(df / --output=pcent 2>/dev/null | tail -1 | tr -dc '0-9')
echo "Disk (sonra): %${AFTER}"

# 4. Disk doluluk alarmı — eşik aşıldıysa mail
if [ "${AFTER:-0}" -ge "$DISK_THRESHOLD" ]; then
  echo "UYARI: Disk %${AFTER} ≥ eşik %${DISK_THRESHOLD} — mail atılıyor"
  if [ -f "$NOTIFY_SCRIPT" ]; then
    /usr/bin/python3 "$NOTIFY_SCRIPT" \
      "IT Tracker disk UYARI (%${AFTER})" \
      "Sunucu disk kullanımı %${AFTER} (eşik %${DISK_THRESHOLD}). Temizlik sonrası hâlâ yüksek. Kontrol gerekli — 'docker system df' ve 'df -h /' bak. Disk dolarsa Postgres crash eder (geçmiş: 2026-06-14)." \
      || echo "WARN: mail gönderilemedi"
  fi
fi

echo "===== $(date -Iseconds) docker bakım OK ====="
