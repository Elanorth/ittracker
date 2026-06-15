# Otomatik DB + Config Yedek — Kurulum

## Genel Bakış

| | |
|---|---|
| **DB tipi** | PostgreSQL (Level 2 — C sonrası). Eski `.db.gz` SQLite yedekler rotation süresi boyunca kalır. |
| **Sıklık** | Her gece 03:00 (cron) |
| **Format** | `db_YYYYMMDD_HHMMSS.sql.gz` — `pg_dump --clean --if-exists --no-owner` |
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
SMB_DOMAIN="INVENTIST"
SMB_USER="ittrackerbackup"
SMB_PASS="<paroleyi-buraya-yaz>"
EOF
chmod 600 ~/.ittracker-backup-creds
```

> **NAS AD-joined ortamda:** Mevcut INVENTIST.LOCAL domain'inde `ittrackerbackup` kullanicisi AD'de tanimli. NAS bu kullaniciya `INVENTIST\ittrackerbackup` syntax'iyla ulasir (SMB_DOMAIN bos kalirsa fail).

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
# Haftalik docker bakimi + disk alarmi (Pazar 04:00):
0 4 * * 0 /home/leventcan/ittracker/scripts/docker-maintenance.sh
```

> **Docker bakimi neden gerekli:** GHCR'a gecisten sonra her deploy yeni image
> katmani + build cache birakir. Birikim disk'i doldurursa Postgres "No space
> left" ile crash eder (2026-06-14'te yasandi, site 2 gun down). Script 7 gun+
> eski kullanilmayan image/cache'i temizler ve disk %85'i asarsa admin'e mail
> atar. Log: `/srv/it_tracker/backups/auto/docker-maintenance.log`.

### 6. Mail test (opsiyonel)
```bash
./scripts/backup-mail.py "Test" "Yedek mail testi"
```

## Restore Kullanimi

**Hedef daima staging'tir** (script prod'a yazmaz):
```bash
./scripts/restore-from-backup.sh list                              # mevcut yedekleri gor
./scripts/restore-from-backup.sh local /srv/.../daily/db_x.sql.gz  # lokal yedek
./scripts/restore-from-backup.sh nas daily db_20260605_030001.sql.gz
./scripts/restore-from-backup.sh nas monthly db_202605.sql.gz
```

Restore süreci (`.sql.gz` için):
1. Mevcut staging Postgres'in dump'ı `/tmp/staging_rollback_*.sql`'e alınır (rollback noktası)
2. `gunzip -c` ile dosya `psql`'e pipe edilir (`--clean --if-exists` ile mevcut tablolar DROP edilir)
3. Web container restart

Eski `.db.gz` (SQLite dönemi) yedekler doğrudan restore edilemez — script `pgloader` ile manuel taşıma adımlarını yazdırır.

Prod restore icin manuel (sessiz saatlerde, downtime kabul):
```bash
docker compose -f /home/leventcan/ittracker/docker-compose.yml stop web

# Rollback noktası al
docker exec ittracker-db-1 pg_dump -U ittracker -d ittracker \
  --clean --if-exists --no-owner > /tmp/prod_rollback_$(date +%s).sql

# Yedekten restore
gunzip -c /srv/it_tracker/backups/auto/daily/db_X.sql.gz | \
  docker exec -i ittracker-db-1 psql -U ittracker -d ittracker

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
| pg_dump hatasi | `docker ps \| grep ittracker-db-1` (container ayakta + healthy mi), `.env`'de POSTGRES_USER/DB doğru mu |
| Mail gitmiyor | `python3 /home/leventcan/ittracker/scripts/backup-mail.py "test" "test"` ile elle test |
| Disk dolu | `du -sh /srv/it_tracker/backups/auto/` — rotation calisiyor mu (30+/365+ gun otomatik silinmeli) |
| Restore sonrası app baglanamiyor | DATABASE_URL'in postgres'e işaret ettiğinden emin ol, web container restart, alembic_version kontrol |
