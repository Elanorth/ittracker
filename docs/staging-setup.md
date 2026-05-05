# Staging Ortami — Kurulum Rehberi

Staging ortami prod ile **ayni sunucuda** ama **tam izole** calisir.

| | Prod | Staging |
|---|---|---|
| Domain | `ittracker.inventist.com.tr` | `ittracker-staging.inventist.com.tr` |
| Dizin | `/home/leventcan/ittracker` | `/home/leventcan/ittracker-staging` |
| Branch | `main` | `develop` |
| Compose project | `ittracker` | `ittracker-staging` |
| Cloudflare Tunnel | mevcut | **yeni token gerekli** |
| DB | `instance/it_tracker.db` | `instance/staging.db` |
| Backups | `/srv/it_tracker/backups` | `/srv/it_tracker/backups-staging` |

## Tek Seferlik Kurulum

### 1. `develop` branch olustur (lokalden)
```bash
git checkout -b develop main
git push -u origin develop
```

### 2. Cloudflare Tunnel — yeni hostname (Dashboard'dan)

Cloudflare Zero Trust > **Networks** > **Tunnels**:
- Yeni tunnel: **`ittracker-staging`** olustur
- Token'i kopyala (sonra `.env.staging`'e gidecek)
- **Public hostname** ekle:
  - Subdomain: `ittracker-staging`
  - Domain: `inventist.com.tr`
  - Service: `HTTP` `ittracker-staging-nginx:80`

### 3. Sunucuda staging klasorunu hazirla
```bash
ssh leventcan@10.34.0.62
cd /home/leventcan
git clone https://github.com/Elanorth/ittracker.git ittracker-staging
cd ittracker-staging
git checkout develop
cp .env.staging.example .env.staging
nano .env.staging   # SECRET_KEY, ADMIN_PASSWORD, CLOUDFLARE_TUNNEL_TOKEN_STAGING doldur

# Backup klasoru
sudo mkdir -p /srv/it_tracker/backups-staging
sudo chown leventcan:leventcan /srv/it_tracker/backups-staging
```

### 4. Azure App Registration (O365 kullanilacaksa)

`38b6928b-75b5-4139-83ec-a0ec72c1644f` > Authentication > Redirect URIs:
```
https://ittracker-staging.inventist.com.tr/auth/callback
```

### 5. Ilk baslatma
```bash
cd /home/leventcan/ittracker-staging
docker compose -p ittracker-staging -f docker-compose.staging.yml up -d --build
docker compose -p ittracker-staging -f docker-compose.staging.yml logs -f web   # log izle
```

### 6. Dogrulama
```bash
curl -I https://ittracker-staging.inventist.com.tr/login   # 200 beklenir
```

---

## Gunluk Deploy (lokalden)

```bash
git checkout develop
# ... kod degisiklikleri ...
git commit -am "feat: ..."
./scripts/deploy-staging.sh
```

Script: branch kontrol, push, sunucuda pull + rebuild, smoke test.

---

## Prod'a Tasima Akisi

```
develop  --(test edildi staging'de)-->  main  --(deploy.bat / GitHub Actions)-->  prod
```

1. Staging'de smoke test yap
2. `git checkout main && git merge --no-ff develop`
3. Prod deploy (Seviye 1 sonrasi: GitHub Actions otomatik)

---

## Sorun Cikarsa

| Belirti | Kontrol |
|---|---|
| 502 staging'de | `docker compose -p ittracker-staging logs web` |
| Tunnel baglanmiyor | `docker logs ittracker-staging-cloudflared` — token yanlis olabilir |
| O365 redirect hatasi | Azure'da `staging.*` redirect URI eklenmemis |
| Disk dolu | `docker system prune -a` (dikkat: kullanilmayan image siler) |
| DB bozuldu | `rm instance/staging.db` + container restart (init_db yeniden seed eder) |

## Prod'dan Staging'e Veri Kopyalama (manuel)

Staging gercekci veriyle test etmek istersen:
```bash
ssh leventcan@10.34.0.62
sudo cp /home/leventcan/ittracker/instance/it_tracker.db \
        /home/leventcan/ittracker-staging/instance/staging.db
sudo chown leventcan:leventcan /home/leventcan/ittracker-staging/instance/staging.db
docker compose -p ittracker-staging restart web
```

**DIKKAT:** Bu kullanici e-postalari + sifreli oturumlar dahil her seyi kopyalar. Anonimlestirme istiyorsan ayri script lazim.
