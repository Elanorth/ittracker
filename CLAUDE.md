# IT Tracker — Claude Code Guide

## Proje Özeti
IT Görev Takip Sistemi — Flask tabanlı web uygulaması. Çok kullanıcılı, O365 OAuth2 destekli, davet sistemi, Config Backup yönetimi ve PDF rapor çıktısı sunar.

## Teknoloji Yığını
- **Backend:** Python / Flask 3.x, Flask-SQLAlchemy, Flask-Session
- **Veritabanı:** SQLite (geliştirme), PostgreSQL destekli (üretim)
- **Auth:** Session tabanlı + Microsoft O365 OAuth2 (MSAL)
- **E-posta:** SMTP (Office365) + O365 Graph API
- **PDF:** WeasyPrint + ReportLab
- **Konteyner:** Docker + docker-compose
- **Frontend:** Tek sayfa (templates/app.html) — vanilla JS + fetch API

## Dizin Yapısı
```
app.py                       # Flask uygulaması, tüm route'lar
models/
  database.py                # SQLAlchemy modelleri (v5.0+ TaskOccurrence dahil)
services/
  mailer.py                  # SMTP ve O365 e-posta gönderimi
  report.py                  # PDF rapor (WeasyPrint/ReportLab)
  storage.py                 # Config backup dosya kaydetme
  notifier.py                # APScheduler + e-posta digest
templates/
  app.html                   # Ana SPA arayüzü (script yok, app.js'e taşındı)
  login.html / error.html
static/
  app.js                     # SPA client JS (v4.8'den itibaren ~3100 satır)
  sw.js                      # Service worker (her sürümde cache bump)
instance/
  it_tracker.db              # SQLite (gitignore)
.env / .env.staging          # gitignore (.env.example şablon)
docker-compose.yml           # Prod stack
docker-compose.staging.yml   # Staging stack (project: ittracker-staging)
docker-compose.override.yml  # Dev hot-reload mount'ları (lokal kullanım)
.github/workflows/           # ci.yml, deploy-prod.yml, deploy-staging.yml
scripts/
  deploy-staging.sh          # Manuel staging deploy (CI/CD yedeği)
docs/
  staging-setup.md           # Staging kurulum rehberi
  cicd-setup.md              # GitHub Actions kurulum
  v5.0-recurring-tasks-spec.md
```

## Görev Kategorileri
- `routine` — Rutin görevler: aylık TaskCompletion kaydıyla takip edilir
- `project` — Proje görevleri: tamamlanmamışlar her ayda görünür
- `support` — Destek talepleri: aya göre filtrelenir
- `infra` — Altyapı
- `backup` — Config backup görevleri
- `other` — Diğer

## Temel Modeller
- **User**: username, full_name, email, role, firm, is_admin, o365_id, **managed_firms** (v4.9 — IT Müdürü çoklu firma yönetimi, many-to-many `Firm` ile)
- **Task**: title, category, priority (düşük/orta/yüksek), period (Günlük/Haftalık/Aylık/Yıllık/Tek Seferlik), firm, team, deadline, checklist, project_status
- **TaskOccurrence** (v5.0 — eski adı TaskCompletion, alias korundu): rutin görevlerin periyod-aware kanonik kaydı. `period_key` formatları: Günlük "YYYY-MM-DD", Haftalık ISO "YYYY-WNN", Aylık "YYYY-MM", Yıllık "YYYY"
- **ConfigBackup**: göreve bağlı yüklenen config dosyaları
- **user_managed_firms**: v4.9 association tablosu (User ↔ Firm)

## Geliştirme Akışı

**Deploy Mac'te YOKTUR** — tüm deploy staging/prod sunucusuna GitHub Actions ile yapılır:
- **Staging:** https://ittracker-staging.inventist.com.tr (branch: `develop`)
- **Prod:** https://ittracker.inventist.com.tr (branch: `main`, onay gerektirir)

**Yerel test opsiyonu (2026-07):** Mac'te artık pytest lokal koşulabiliyor. Sistem Python 3.9'a dokunmadan `uv` ile standalone CPython 3.12 (prod/CI ile aynı sürüm) + proje `.venv` kuruldu. Kullanım:
```bash
export PATH="$HOME/.local/bin:$PATH"      # uv PATH
.venv/bin/python -m pytest -q             # tüm paket (~3 dk, 335 test)
.venv/bin/python -m pytest tests/test_x.py -q   # tek dosya
```
`.venv` gitignore'da. Kurulum yoksa: `uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt`. Deploy yine staging→prod akışıyla; yerel test yalnızca push öncesi hızlı doğrulama içindir.

```bash
# Yeni feature
git checkout -b feature/x develop
# kod degisikligi
git commit -am "feat: ..."
git push -u origin feature/x
# GitHub UI'da PR ac, develop'a merge → otomatik staging deploy

# Staging smoke test sonrasi prod'a tasima:
# develop → main PR ac, merge → GitHub Actions test + onay (Elanorth) + deploy

# Manuel staging deploy (CI/CD yedek yolu, develop branch icin):
./scripts/deploy-staging.sh
```

Detay: [docs/cicd-setup.md](docs/cicd-setup.md), [docs/staging-setup.md](docs/staging-setup.md)

## Ortam Değişkenleri (.env)
| Değişken | Açıklama |
|---|---|
| SECRET_KEY | Flask oturum anahtarı |
| ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD | İlk admin oluşturma |
| DATABASE_URL | SQLite veya PostgreSQL bağlantısı |
| BACKUP_DIR | Config dosyaları klasörü |
| SMTP_HOST/PORT/USER/PASS | E-posta gönderimi |
| O365_CLIENT_ID/SECRET/TENANT_ID | OAuth2 (isteğe bağlı) |

## Önemli Notlar
- Admin ilk çalıştırmada ADMIN_PASSWORD yoksa `RuntimeError` fırlatır
- Rutin görevlerin tamamlanma durumu `TaskOccurrence` (eski adı TaskCompletion) tablosundan hesaplanır, `Task.is_done` flag'inden değil. v5.0'dan itibaren `period_key` periyod-aware (Günlük/Haftalık/Aylık/Yıllık)
- **Boş firma semantiği:** `User.firm` için "boş" daima `""` (string), asla `None`. `@validates('firm')` decorator None→"" coerce eder. Kontroller `not user.firm` veya `user.firm == ""` ile yapılmalı, `is None` ile değil.
- **`it_director` çoklu firma (v4.9):** Yetki kontrolü için `me.has_firm_scope(target.firm)` kullan; yeni director oluşturulunca `after_insert` event'i kendi firma'sını otomatik `managed_firms`'a ekler.
- **Türkçe slug:** `_slugify_tr(name)` helper Türkçe karakterleri ASCII'ye eşler ('İnventist' → 'inventist'). Saf `.lower()` U+0307 hayalet karakter bırakır — direkt kullanma.
- **API auth:** `login_required` `request.path.startswith('/api/')` veya `Accept: application/json` veya `Content-Type: application/json` ile JSON 401 döner; diğer durumlarda `/login`'e 302.
- Tüm API route'ları `/api/` prefix'i ile başlar
- Admin işlemleri `@admin_required` decorator gerektirir
- Config backup dosyaları `BACKUP_DIR` (varsayılan: `/srv/it_tracker/backups`) altına kaydedilir
- **Test:** GitHub Actions CI'da otomatik çalışır (her push + PR, Python 3.12). Mac'te de lokal koşulabilir (`.venv/bin/python -m pytest`, bkz. Geliştirme Akışı → Yerel test opsiyonu). 335+ test, `requirements-dev.txt` (pytest, flask, cov, bs4, freezegun, responses). `tests/conftest.py` `db` fixture her test sonrası `init_db()` ile seed datayı yeniden kurar. NOT: `models/database.py` `from datetime import UTC` kullanır → Python 3.11+ şart (sistem 3.9 ile çalışmaz).
- **Deploy:** Tüm deploy GitHub Actions üzerinden. `deploy.bat` emekli. Detay: [docs/cicd-setup.md](docs/cicd-setup.md).
