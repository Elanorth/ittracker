# Otomatik DB + Config Yedek — Kurulum

## Genel Bakış

| | |
|---|---|
| **Sıklık** | Her gece 03:00 (cron) |
| **Lokal** | `/srv/it_tracker/backups/auto/` — 30 gün günlük + 12 ay aylık |
| **NAS** | `smb://10.34.0.61/Inventist_IT/Ittracker DB/{daily,monthly}/` |
| **Config dosyaları** | Her ayın 1'inde dahil (`configs_YYYYMM.tar.gz`) |
| **Hata bildirimi** | `admin@inventist.com.tr` (prod `.env` SMTP credentials) |

## Tek Seferlik Kurulum (sunucuda)

### 1. smbclient kurulumu (sudo gerekir)
```bash
sudo apt update && sudo apt install -y smbclient
```

### 2. SMB credentials dosyasi
```bash
cat > ~/.ittracker-backup-creds <<'EOF'
SMB_USER="ittrackerbackup"
SMB_PASS="<paroleyi-buraya-yaz>"
EOF
chmod 600 ~/.ittracker-backup-creds
```

### 3. Backup script'lerini executable yap
```bash
cd /home/leventcan/ittracker
chmod +x scripts/backup-db.sh scripts/restore-from-backup.sh scripts/backup-mail.py
```

### 4. Test calistirma (cron oncesi)
```bash
./scripts/backup-db.sh
tail -20 /srv/it_tracker/backups/auto/backup.log
ls -la /srv/it_tracker/backups/auto/daily/
# NAS kontrol:
. ~/.ittracker-backup-creds
smbclient "//10.34.0.61/Inventist_IT" "$SMB_PASS" -U "$SMB_USER" -c 'cd "Ittracker DB/daily"; ls'
```

### 5. Cron kaydi (kullanici crontab)
```bash
crontab -e
# Sona ekle:
0 3 * * * /home/leventcan/ittracker/scripts/backup-db.sh
```

### 6. Mail test (opsiyonel)
```bash
./scripts/backup-mail.py "Test" "Yedek mail testi"
```

## Restore Kullanimi

**Hedef daima staging'tir** (script prod'a yazmaz):
```bash
./scripts/restore-from-backup.sh list                          # mevcut yedekleri gor
./scripts/restore-from-backup.sh local /srv/.../daily/db_x.gz  # lokal yedek
./scripts/restore-from-backup.sh nas daily db_20260605_030001.db.gz
./scripts/restore-from-backup.sh nas monthly db_202605.db.gz
```

Prod restore icin manuel:
```bash
sudo systemctl stop docker-ittracker-web 2>/dev/null || \
  docker compose -f /home/leventcan/ittracker/docker-compose.yml stop web
sudo cp /srv/it_tracker/backups/auto/daily/db_X.db.gz /tmp/
sudo gunzip /tmp/db_X.db.gz
sudo mv /tmp/db_X.db /home/leventcan/ittracker/instance/it_tracker.db
sudo chown root:root /home/leventcan/ittracker/instance/it_tracker.db
docker compose -f /home/leventcan/ittracker/docker-compose.yml start web
```

## Dogrulama

Cron calistiktan sonra her sabah:
```bash
tail -30 /srv/it_tracker/backups/auto/backup.log
du -sh /srv/it_tracker/backups/auto/{daily,monthly}
```

Aksaklik olursa `admin@inventist.com.tr`'ye otomatik mail gelir.

## Sorun Cikarsa

| Belirti | Kontrol |
|---|---|
| Cron calismadi | `systemctl status cron`, `journalctl -u cron \| tail` |
| smbclient hatasi | `~/.ittracker-backup-creds` dogru mu, NAS erisilebilir mi (`ping 10.34.0.61`), kullanici izinleri |
| Docker exec hatasi | `docker ps \| grep ittracker-web-1` (container ayakta mi) |
| Mail gitmiyor | `python3 /home/leventcan/ittracker/scripts/backup-mail.py "test" "test"` ile elle test |
| Disk dolu | `du -sh /srv/it_tracker/backups/auto/` — rotation calisiyor mu (30+/365+ gun otomatik silinmeli) |
