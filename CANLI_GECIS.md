# Canlıya Geçiş Kontrol Listesi

## 1. `.env` Dosyası (Sunucuda)

| Değişken | Localhost | **Canlı** |
|---|---|---|
| `O365_REDIRECT_URI` | `http://localhost:5000/auth/callback` | `https://ittracker.inventist.com.tr/auth/callback` |
| `BACKUP_DIR` | *(varsayılan)* | `/srv/it_tracker/backups` |
| `DATABASE_URL` | `sqlite:///it_tracker.db` | PostgreSQL bağlantısı *(opsiyonel)* |

## 2. Azure Portal

**App Registrations → `38b6928b-75b5-4139-83ec-a0ec72c1644f` → Authentication → Redirect URIs**

Şunu ekle:
```
https://ittracker.inventist.com.tr/auth/callback
```

## 3. Docker ile Başlatma

```bash
docker-compose up --build -d
```

## 4. Kontrol

- [ ] `https://ittracker.inventist.com.tr` açılıyor mu?
- [ ] O365 ile giriş çalışıyor mu?
- [ ] Config backup klasörü `/srv/it_tracker/backups` var mı? (`mkdir -p /srv/it_tracker/backups`)


Nasıl Çalışır:
window.location.hostname üzerinden domain otomatik algılanır
assospharma veya assos içeren domain → Assos mavi teması
inventist içeren domain → Inventist yeşil/tan teması
Diğer domainler (localhost dahil) → Varsayılan teal teması
Logo alt yazısı da domain'e göre dinamik değişir
V2'ye Dönmek İçin:
cp templates/app_v2_backup.html templates/app.html