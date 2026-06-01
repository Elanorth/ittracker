# PostgreSQL Migration

Level 2 Roadmap — C. SQLite → Postgres geçişi. **Yüksek riskli adım**. Mutlaka
önce staging'de doğrulanır, sonra prod'a alınır.

## Neden Postgres?

- **Concurrent yazma:** SQLite tek-yazıcı kilit (write lock). Gunicorn multi-worker
  veya yüksek yük altında "database is locked" hatası.
- **Production ölçek:** SQLite ~100 GB üstünde performans düşer; bizim DB henüz
  küçük ama büyüme planı var.
- **Tooling:** Postgres ekosistemi (pg_dump, replication, monitoring) çok daha
  zengin.

## Strateji

**Hibrit cutover (bu PR):**
1. Compose dosyalarına `db` servisi (postgres:16-alpine) eklendi — **HEMEN ayağa kalkar**, ama app hala SQLite kullanır
2. `requirements.txt` `psycopg2-binary` eklendi (yeni image'de var)
3. `init_db()` v5.0 migration bloğu dialect-aware (printf vs lpad)
4. Migration script: `scripts/migrate-sqlite-to-postgres.sh`
5. Cutover **manuel** (env değişikliği + restart)

Bu yaklaşımın avantajı: PR merge → app davranışı değişmez, sadece altyapı hazır.
Cutover'ı kendi zamanlamanızda yaparsınız.

## Cutover Adımları (Staging)

```bash
ssh leventcan@10.34.0.62
cd /home/leventcan/ittracker-staging

# 1) .env.staging içinde Postgres credentials'ı tanımlı olduğundan emin ol
grep -E '^POSTGRES_' .env.staging
# Yoksa ekle:
cat >> .env.staging <<'EOF'
POSTGRES_DB=ittracker_staging
POSTGRES_USER=ittracker
POSTGRES_PASSWORD=$(openssl rand -base64 24)
EOF

# 2) Yeni image'i çek (db servisi compose'da var artık)
docker compose -p ittracker-staging -f docker-compose.staging.yml --env-file .env.staging pull
docker compose -p ittracker-staging -f docker-compose.staging.yml --env-file .env.staging up -d

# Postgres'in healthy olduğunu doğrula
docker compose -p ittracker-staging -f docker-compose.staging.yml ps

# 3) Veri taşıma script'i (SQLite → Postgres, otomatik snapshot alır)
bash scripts/migrate-sqlite-to-postgres.sh staging

# 4) .env.staging'de DATABASE_URL'i güncelle
sed -i 's|^DATABASE_URL=.*|DATABASE_URL=postgresql://ittracker:'"$POSTGRES_PASSWORD"'@db:5432/ittracker_staging|' .env.staging

# 5) Web container'ı yeniden başlat
docker compose -p ittracker-staging -f docker-compose.staging.yml --env-file .env.staging restart web

# 6) Doğrulama
docker compose -p ittracker-staging -f docker-compose.staging.yml exec web flask db current
# → 20260601_baseline_v52 (head)

# 7) Smoke test
curl -I https://ittracker-staging.inventist.com.tr/login
# → HTTP 200
```

Staging'de **1-2 gün kullanım gözlemlendikten sonra** prod'a aynı adımlar
uygulanır (prod için `prod` argümanı).

## Cutover Adımları (Prod)

Staging başarılı olduktan SONRA:

```bash
ssh leventcan@10.34.0.62
cd /home/leventcan/ittracker

# 1) Otomatik yedek script'inin son çalıştığını doğrula
tail -3 /srv/it_tracker/backups/auto/backup.log
# Son çalışma timestamp'i bugünden olmalı

# 2) Postgres credentials .env'de
cat >> .env <<'EOF'
POSTGRES_DB=ittracker
POSTGRES_USER=ittracker
POSTGRES_PASSWORD=$(openssl rand -base64 24)
EOF

# 3) Compose pull + up (db servisi gelir)
docker compose pull
docker compose up -d

# 4) Veri taşıma — Prod kullanıcı yokken zamanlama (akşam/gece)
bash scripts/migrate-sqlite-to-postgres.sh prod

# 5) DATABASE_URL değiştir
sed -i 's|^DATABASE_URL=.*|DATABASE_URL=postgresql://ittracker:'"$POSTGRES_PASSWORD"'@db:5432/ittracker|' .env

# 6) Restart
docker compose restart web

# 7) Smoke test
curl -I https://ittracker.inventist.com.tr/login
```

**Tahmini downtime: 5-10 dk** (veri taşıma süresine bağlı).

## Rollback

**Eğer cutover sonrası sorun çıkarsa:**

```bash
# DATABASE_URL'i SQLite'a geri çevir
sed -i 's|^DATABASE_URL=.*|DATABASE_URL=sqlite:///it_tracker.db|' .env

# Web restart
docker compose restart web
```

SQLite verisi `instance/it_tracker.db` yerinde duruyor — migration script onu
silmiyor, sadece kopyalıyor. Bu yüzden geri dönüş anında.

Eğer SQLite verisi bozulduysa veya silindiyse:
- Otomatik yedek `/srv/it_tracker/backups/auto/daily/db_YYYYMMDD_*.db.gz` restore et
- Migration script'in oluşturduğu snapshot `instance/{db_name}_pre_pg_migration_*.db`
  kullan

## Sorun giderme

| Belirti | Kontrol |
|---|---|
| `db` container restart loop | `POSTGRES_PASSWORD` set mi, `docker logs ittracker-staging-db` |
| `connection refused` | `db` healthy mi (`pg_isready`), web `depends_on` doğru mu |
| pgloader `permission denied` | SQLite dosyası container'a `:ro` mount edildi, write deniyor olabilir |
| `flask db upgrade` Postgres'te hata | Migration `op.batch_alter_table` SQLite-spesifik kullanmış olabilir |
| Veri eksik | pgloader log'una bak, "skipped" satırı var mı; bazı kolon tipleri için manuel cast gerekebilir |

## SQLAlchemy dialect farkları

Mevcut kod çoğunlukla dialect-agnostic ama dikkat:

- ✅ `db.create_all()` — modeller tip-aware
- ✅ Alembic `render_as_batch=True` — SQLite için aktif, Postgres'te no-op
- ⚠️ `init_db()` v5.0 migration: `printf()` SQLite, `lpad()` Postgres — düzeltildi
- ⚠️ `BOOLEAN DEFAULT 1` (SQLite) vs `BOOLEAN DEFAULT TRUE` (Postgres) — ALTER
  TABLE bloklarında. Postgres'te `1` int olarak görülür, hata vermez ama
  konvensiyon değil. Yeni migration'larda `TRUE/FALSE` kullanın.
- ⚠️ `text("SELECT ...")` raw SQL: tarih/string fonksiyonları farklı

## Sonraki adımlar (bu PR sonrası)

- **Monitoring:** Postgres metrics (connections, slow queries) → Glitchtip alerts
- **Otomatik yedek**: Mevcut `scripts/backup-db.sh` SQLite'a özgü;
  PostgreSQL için `pg_dump` ile yeniden yaz
- **Connection pool**: SQLAlchemy `pool_size`, `pool_pre_ping` tuning
- **Migrations:** Postgres-uyumlu yeni Alembic revision'ları için batch mode
  kullanmaya gerek yok
