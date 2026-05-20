# Seviye 2 — Profesyonel Deploy Roadmap

Önerilen sıra (risk artan): **E → D → F → A → B → C**

Her madde için **3-state PR akışı** kullanılacak: feature branch → develop (staging dogrula) → main (prod onay sonrasi).

---

## E. Otomatik DB Yedek (yarım gün) ⭐⭐⭐ — Önce yapılsın

**Neden ilk:** Sonraki migration/Postgres adımlarında geri dönüş güvencesi. Şu an her deploy'da manuel `sudo cp` var; aylar geçtikçe disk doluyor.

**Yapılacaklar:**
1. **Sunucuda cron job** (`/etc/cron.d/ittracker-backup`):
   - Her gece 03:00: `it_tracker.db` → `/srv/it_tracker/backups/db/YYYYMMDD_HHMMSS.db.gz`
   - Eski yedekleri rotate: 7 günlük yerel + 30 günlük aylık snapshot
2. **Offsite (Backblaze B2)** — ~$1/ay, S3-uyumlu API:
   - `rclone` ile günlük snapshot upload
   - 90 gün retention
3. **Restore drill script** — `scripts/restore-from-backup.sh STAGING <date>` ile yedek staging'e geri yükle, smoke test

**Test stratejisi:** Staging DB'sini bilerek boz → restore script çalıştır → veri geri geldi mi.

**Risk:** Düşük. Mevcut prod'u etkilemez.

---

## D. Sentry / Glitchtip — Error Tracking (yarım gün) ⭐⭐⭐

**Neden ikinci:** Sonraki refactor'larda (Alembic, Postgres) hata yakalamak için altyapı önce kurulsun.

**Yapılacaklar:**
1. **Sentry hesabı** — ücretsiz developer tier (5K event/ay yeterli, IT Tracker küçük) veya **Glitchtip** (self-hosted, ücretsiz)
2. `sentry-sdk[flask]` → requirements.txt
3. `app.py` initialization (DSN env var ile)
4. **Tag'ler:** environment (staging/prod), release (git SHA), user (oturum açan)
5. **Filtreleme:** 401/403 (normal auth fail) ignore; OperationalError (DB busy retry) ignore
6. **Alert rules:** 5dk içinde 5+ aynı hata → email (zaten SMTP var)

**Test stratejisi:** Staging'de bilerek 500 fırlat (örn. `/api/test-error` debug endpoint) → Sentry'de görünüyor mu, e-posta geldi mi.

**Risk:** Çok düşük. Tek SDK ekleme.

---

## F. Pre-commit Hooks (1-2 saat) ⭐⭐ — Hızlı kazanç

**Yapılacaklar:**
1. `.pre-commit-config.yaml`:
   - `ruff` — Python lint/format
   - `trailing-whitespace`, `end-of-file-fixer`
   - `detect-secrets` veya `gitleaks` — sızıntı taraması
   - `check-yaml` workflow'lar için
2. `pip install pre-commit && pre-commit install` (sadece kontribütör Mac/dev makinelerinde)
3. CI'da da çalışsın (ci.yml'a `pre-commit run --all-files` adımı)

**Risk:** Çok düşük. Sadece kod kalite kontrolü.

---

## A. GHCR — Image Registry (yarım gün) ⭐⭐⭐ — Deploy Hız

**Mevcut sorun:** Her deploy'da sunucu image'i sıfırdan build ediyor (3-5 dk + CPU yükü).

**Çözüm:**
1. CI'da `docker buildx` ile image build edip GHCR'a push: `ghcr.io/elanorth/ittracker:<sha>` + `:main` + `:develop`
2. Deploy workflow'unda: `docker compose pull && docker compose up -d` (build yok)
3. Multi-arch build sonradan (gerekirse) — sunucu x86_64 olduğu için şimdi sadece amd64
4. Cache: GitHub Actions cache + GHCR layer reuse → CI build'i ~30sn'ye düşer

**Yan kazanç:** Image versiyonlama — istediğin SHA'ya `docker run` ile dön (rollback).

**Test stratejisi:** Staging'e push, image GHCR'da görünür, sunucu pull edip up eder, çalışır mı.

**Risk:** Orta. docker-compose.yml + docker-compose.staging.yml'da `build:` → `image:` geçişi. Geri alınabilir.

---

## B. Alembic — Schema Migration (1 gün) ⭐⭐⭐

**Mevcut sorun:** `init_db()` içinde idempotent SQL (CREATE TABLE IF NOT EXISTS, vs.). v5.0 gibi büyük migration'lar `printf` ile inline yapıldı — kırılgan.

**Yapılacaklar:**
1. `pip install alembic flask-migrate`
2. `flask db init` → migrations/ klasörü
3. **İlk baseline migration:** mevcut DB şemasını autogenerate
4. `init_db()` içindeki manuel CREATE'leri kaldır; sadece seed data (admin kullanıcısı) kalır
5. v5.0 migration'ı (idempotent SQL) → ayrı Alembic revision
6. Deploy workflow'una `flask db upgrade` adımı (DB güncelleme)
7. `instance/it_tracker.db` yapısını korumak için: önce baseline'a stamp et, sonra upgrade

**Test stratejisi:**
- Staging'de prod yedek restore et
- `flask db upgrade head` → veri kaybı yok mu
- Yeni revision ekle, downgrade test et

**Risk:** Yüksek. DB değişikliği. **MUTLAKA E adımı (otomatik yedek) önce.**

---

## C. PostgreSQL Geçişi (1 gün) ⭐⭐

**Neden:** SQLite tek-yazıcı kilit sorunları (Werkzeug dev server'da, prod'da Gunicorn ile multi-worker'a geçince hemen patlar). Concurrent test yazılamıyor şu an.

**Yapılacaklar:**
1. **Postgres container ekle** docker-compose.yml + staging.yml'a (volume: `pgdata`)
2. `requirements.txt`: `psycopg2-binary`
3. `.env`: `DATABASE_URL=postgresql://ittracker:***@db:5432/ittracker`
4. **Migration script:** SQLite → Postgres (`pgloader` veya manuel dump+restore)
5. Alembic ile şema check (driver-agnostic SQL kullanılmalı — `printf` Postgres'te yok, `lpad()` lazım)
6. Staging'de önce dene, prod'a geç

**Test stratejisi:** Staging'i Postgres'e geçir, 1 hafta paralel çalıştır, smoke + manual UAT.

**Risk:** Yüksek. **MUTLAKA B (Alembic) sonra. SQLite ile rollback yedek yolu açık tut.**

---

## G. Multi-stage Dockerfile (2 saat) ⭐ — Opsiyonel

**Mevcut:** 492 MB image (Python base + sistem deps + venv + kod).

**İyileştirme:** Multi-stage build:
- Stage 1: deps build (gcc, libffi-dev vs. ile)
- Stage 2: runtime (sadece compiled wheels + minimum lib)
- Tahmin: ~150-200 MB

**Risk:** Düşük. CI build süresi az artar, deploy hızlanır (image küçülür).

---

## Tahminî Toplam Süre & Sıra

| Adım | Süre | Kümülatif | Bağımlılık |
|---|---|---|---|
| E. Yedek | 0.5g | 0.5g | — |
| D. Sentry | 0.5g | 1g | — |
| F. Pre-commit | 0.25g | 1.25g | — |
| A. GHCR | 0.5g | 1.75g | F (CI hızı için) |
| B. Alembic | 1g | 2.75g | E (DB yedek) |
| C. Postgres | 1g | 3.75g | B (migration için) |
| G. Multi-stage | 0.25g | 4g | A (image baz) |

**~4 iş günü.** Her madde ayrı PR + staging doğrulama + prod onay.

---

## Önerilen Bugünkü İlk Adım

**E** (otomatik yedek) — herhangi bir kod değişikliği gerektirmiyor, sadece sunucuda cron + rclone setup + 1 restore drill script. Geri kalan her şeyin altında güvenlik ağı.
