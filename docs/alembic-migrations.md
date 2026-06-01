# Alembic Schema Migration

Level 2 Roadmap — B maddesi. DB schema değişiklikleri artık Alembic revision'ları
ile versiyonlanır.

## Genel bakış

| | |
|---|---|
| Migration aracı | Alembic + Flask-Migrate (`flask db <komut>`) |
| Migration klasörü | `migrations/versions/` |
| Baseline | `20260601_baseline_v52.py` (boş — prod zaten bu noktada) |
| Deploy entegrasyonu | Her deploy sonunda `flask db upgrade` çalışır |
| CI test | `init_db()` `db.create_all()` ile schema kurar (Alembic gerekmez) |

## Hibrit yaklaşım — neden?

Mevcut `init_db()` fonksiyonu hem schema oluşturur (`db.create_all()`) hem
idempotent ALTER mantığı içerir hem seed data ekler. Bunu birden Alembic'e
taşımak:
- CI test'leri (`in-memory SQLite`) etkilenir
- Prod DB'de risk yüksek (5 GB veri taşıma)

Bunun yerine:
- **Mevcut DB'ler:** init_db()'in çalışmış olduğu state'i `baseline_v52` olarak
  işaretledik. `flask db upgrade` ilk seferinde baseline'ı stamp'ler, hiçbir
  schema değişikliği yapmaz.
- **Yeni schema değişiklikleri:** Artık Alembic revision'ı olarak gelir.
  `init_db()` içine yeni ALTER eklenmez.
- **CI/test ortamı:** Hala `db.create_all()` ile schema kurar. Alembic
  revision'ları test edilirse `tests/test_migrations.py` benzeri bir test
  yazılabilir (şimdilik gerek yok).

## Yeni migration oluşturma

Bir model değişikliği yaptıktan sonra (`models/database.py` içine kolon
eklediniz vb.), otomatik revision oluştur:

```bash
# Lokal makinede ya da staging container'da:
docker compose exec web flask db migrate -m "task'a tags kolonu ekle"
```

Bu `migrations/versions/<timestamp>_task_a_tags_kolonu_ekle.py` dosyası üretir.
İçeriği inceleyin — autogenerate her zaman doğru değildir:
- Tablo rename yanlış algılanabilir
- Türkçe karakter / collation farkları
- SQLite ALTER limitations (batch mode gerekir, env.py'de aktif)

Sonra:

```bash
# Lokal test:
docker compose exec web flask db upgrade

# Geri al testi:
docker compose exec web flask db downgrade -1
docker compose exec web flask db upgrade
```

PR'a hem `models/database.py` hem `migrations/versions/<dosya>.py`'yi dahil et.
Deploy workflow'u prod'a push sonrası `flask db upgrade` çağırır otomatik.

## CLI komutları

| Komut | Ne yapar |
|---|---|
| `flask db init` | İlk kez — migrations/ klasörünü oluşturur (bizde zaten var) |
| `flask db migrate -m "açıklama"` | Model'den autogenerate revision üretir |
| `flask db upgrade` | En son revision'a yükselt |
| `flask db upgrade <rev>` | Belirli revision'a yükselt |
| `flask db downgrade -1` | Bir revision geri al |
| `flask db history` | Tüm revision listesi |
| `flask db current` | Şu anda hangi revision'dayız |
| `flask db stamp head` | Mevcut DB'yi en son rev olarak işaretle (migration uygulamadan) |

## SQLite batch mode

SQLite ALTER TABLE bazı işlemleri (DROP COLUMN, ALTER COLUMN type) desteklemez.
Alembic bunu **batch mode** ile çözer: yeni tablo oluştur, veri kopyala, eski
tabloyu DROP et, yeni tabloyu rename et.

`env.py`'de `render_as_batch=True` (SQLite için) ayarlandı. Yeni migration
yazarken SQLite kısıtlamalarına dikkat:

```python
# YANLIŞ (SQLite'ta direkt çalışmaz)
op.drop_column("tasks", "old_field")

# DOĞRU (batch mode kullan)
with op.batch_alter_table("tasks") as batch_op:
    batch_op.drop_column("old_field")
```

## Rollback

Bir migration'ı geri almak:

```bash
# Sunucuda (prod):
cd /home/leventcan/ittracker
docker compose exec web flask db downgrade -1
```

Veri kaybı riski olabilir (örn. yeni kolon kaldırılıyorsa). Kritik
production rollback için önce **otomatik DB yedek**'i restore etmek daha güvenli
(bkz: `docs/backup-setup.md` ve `scripts/restore-from-backup.sh`).

## Deploy entegrasyonu

`.github/workflows/deploy-{staging,prod}.yml` içinde:

```yaml
- name: DB migration (Alembic)
  run: docker compose exec -T web flask db upgrade
```

Container `up -d` ile başladıktan sonra healthcheck'i bekler, sonra Alembic
upgrade çalıştırır. Çıkış kodu non-zero ise deploy fail.

## İlk deploy (bu PR)

Bu PR ile birlikte prod ilk kez `flask db upgrade` çalıştırır:
1. `alembic_version` tablosu oluşur
2. `20260601_baseline_v52` revision'ı stamp'lenir
3. Hiçbir schema değişikliği yapılmaz (baseline boş)
4. Container çalışmaya devam eder

Sonraki deploy'larda yeni revision varsa otomatik uygulanır.

## Sorun giderme

| Belirti | Kontrol |
|---|---|
| `Target database is not up to date` | `flask db upgrade` çağrıldı mı, alembic_version tablosu var mı |
| `Can't locate revision identified by '...'` | Migration dosyası eksik. `git pull` veya `flask db stamp head` |
| `Multiple head revisions` | İki PR aynı anda yeni revision eklemiş — branch merge gerekir |
| Production DB locked (SQLite) | Container restart, sonra retry |
| Test'lerde "no such table: alembic_version" | Normal — testler `db.create_all()` kullanır, Alembic devrede değil |
