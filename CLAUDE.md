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
app.py                  # Flask uygulaması, tüm route'lar
models/
  database.py           # SQLAlchemy modelleri: User, Task, TaskCompletion, ConfigBackup, Firm, Team, Invitation
services/
  mailer.py             # SMTP ve O365 e-posta gönderimi
  report.py             # PDF rapor oluşturma (WeasyPrint/ReportLab)
  storage.py            # Config backup dosya kaydetme
templates/
  app.html              # Ana SPA arayüzü
  login.html / register.html / error.html
instance/
  it_tracker.db         # SQLite veritabanı (gitignore)
.env.example            # Gerekli ortam değişkenleri
docker-compose.yml      # Üretim konfigürasyonu
docker-compose.override.yml  # Dev hot-reload mount'ları
```

## Görev Kategorileri
- `routine` — Rutin görevler: aylık TaskCompletion kaydıyla takip edilir
- `project` — Proje görevleri: tamamlanmamışlar her ayda görünür
- `support` — Destek talepleri: aya göre filtrelenir
- `infra` — Altyapı
- `backup` — Config backup görevleri
- `other` — Diğer

## Temel Modeller
- **User**: username, full_name, email, role, firm, is_admin, o365_id
- **Task**: title, category, priority (düşük/orta/yüksek), period (Günlük/Haftalık/Aylık/Yıllık/Tek Seferlik), firm, team, deadline, checklist, project_status
- **TaskCompletion**: rutin görevlerin aylık tamamlanma kaydı (task_id + year + month unique)
- **ConfigBackup**: göreve bağlı yüklenen config dosyaları

## Geliştirme
```bash
# Venv aktif
source venv/Scripts/activate  # Windows bash
pip install -r requirements.txt
python app.py  # localhost:5000

# Docker ile
docker-compose up --build
```

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
- Rutin görevlerin `is_done` durumu `TaskCompletion` tablosundan hesaplanır, `Task.is_done` flag'inden değil
- Tüm API route'ları `/api/` prefix'i ile başlar
- Admin işlemleri `@admin_required` decorator gerektirir
- Config backup dosyaları `BACKUP_DIR` (varsayılan: `/srv/it_tracker/backups`) altına kaydedilir
