# GHCR Image Registry

Level 2 Roadmap — A maddesi. Docker image'leri GitHub Container Registry'de saklanır,
sunucuda her deploy'da sıfırdan build edilmez.

## Önceki davranış vs. yeni

| | Önce | Sonra |
|---|---|---|
| Build yapan | Sunucu (her deploy'da) | CI (her push'ta tek sefer) |
| Süre | 3–5 dk | ~30–45 sn (image pull) |
| CPU yükü | Prod sunucuda | GitHub'ın runner'larında |
| Rollback | `git revert` + deploy | Direkt SHA'lı tag ile pull |

## Image etiketleri

Her develop ya da main push'unda iki tag pushlanır:

| Tag | Hedef | Kullanım |
|---|---|---|
| `ghcr.io/elanorth/ittracker:develop` | son develop build | staging deploy |
| `ghcr.io/elanorth/ittracker:develop-<sha>` | spesifik commit | rollback / debug |
| `ghcr.io/elanorth/ittracker:main` | son main build | prod deploy |
| `ghcr.io/elanorth/ittracker:main-<sha>` | spesifik commit | rollback / debug |

## CI/CD akışı (deploy-staging.yml örnek)

```
push to develop
   ↓
[test]   ← pytest + pre-commit
   ↓
[build]  ← ubuntu-latest, docker buildx, push GHCR (cache-from/to: gha)
   ↓
[deploy] ← self-hosted runner, docker compose pull + up -d
```

`build` job'u GitHub Actions cache (`type=gha`) ile katmanları yeniden kullanır.
İlk build ~3–5 dk, sonrakiler ~30–60 sn.

## Rollback

Önceki SHA'lı tag'e geri dön:

```bash
# Prod sunucuda
cd /home/leventcan/ittracker
IMAGE=ghcr.io/elanorth/ittracker:main-<önceki_sha> docker compose up -d
```

`IMAGE` env var docker-compose.yml'de `${IMAGE:-...}` syntax'ı ile pickup edilir;
override edilmezse default `:main` etiketini kullanır.

## Manuel test (geliştirici makinesi)

GHCR private (default). Çekmek için login lazım:

```bash
# Kişisel token (read:packages scope'lu) ile:
echo $GH_PAT | docker login ghcr.io -u <github_username> --password-stdin

# Sonra pull:
docker pull ghcr.io/elanorth/ittracker:develop
```

## Lokal dev

`docker-compose.yml` hem `image:` hem `build:` taşır. Lokalde `docker compose up`
çağrılırsa Docker önce `ghcr.io/elanorth/ittracker:main` pull eder; bulamazsa
`build: .` ile yereldeki Dockerfile'dan build eder.

`docker-compose.override.yml` bind mount'larla hot-reload sağlar — bu lokal-only,
prod/staging compose dosyalarında yok.

## Self-hosted runner

Deploy job'u prod sunucusundaki self-hosted runner'da çalışır. Her job çalıştığında:

```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_ACTOR --password-stdin
```

Sonraki `docker compose pull` bu auth'u kullanır. Token job sonrası invalidate edilir.

## Maliyet ve kotalar

GHCR public/private:
- Public packages: ücretsiz, sınırsız
- Private packages: ücretsiz tier 500 MB depolama + 1 GB/ay transfer
- Bizim image ~492 MB → kuotada dikkatli olalım. Eski SHA'lı tag'leri 30+ gün sonra
  manuel veya otomatik retention politikası ile temizlemek mantıklı (sonraki iteration).

## Sorun giderme

| Belirti | Kontrol |
|---|---|
| `denied: unauthorized` (deploy log) | `docker login ghcr.io` adımı atlanmış / token expire (job re-run) |
| `manifest unknown` | Build job'u henüz tag'i push etmemiş; deploy `needs: build` doğru mu? |
| Eski versiyon hala canlıda | `docker compose pull` sonrası `up -d` yapıldı mı? Container restart olmadıysa eski image kullanır |
| Disk dolu (sunucu) | `docker image prune -af --filter "until=720h"` (30+ gün eski image'leri temizle) |
