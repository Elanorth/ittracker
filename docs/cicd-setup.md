# CI/CD Setup — GitHub Actions (Seviye 1)

3 workflow + branch korumasi:
- **`ci.yml`** — her PR ve push'ta `pytest` calistirir
- **`deploy-prod.yml`** — `main`'e push'ta prod'a deploy + smoke test
- **`deploy-staging.yml`** — `develop`'a push'ta staging'e deploy + smoke test

`deploy.bat` artik gereksiz — emekli ediyoruz.

---

## Tek Seferlik Kurulum

### 1. SSH Deploy Key (sunucuya tek seferlik)

GitHub Actions runner'inin sunucuya SSH ile baglanmasi icin **ayri** bir key:

```bash
# Lokal Mac'te:
ssh-keygen -t ed25519 -C "github-actions@ittracker" -f ~/.ssh/ittracker_deploy -N ""
ssh-copy-id -i ~/.ssh/ittracker_deploy.pub leventcan@10.34.0.62
```

> Neden ayri key: kisisel key'ini GitHub Secrets'a koymak risk. Deploy key'i sadece bu is icin.

### 2. GitHub Secrets

Repo > **Settings** > **Secrets and variables** > **Actions** > **New repository secret**:

| Secret | Deger |
|---|---|
| `PROD_SSH_KEY` | `cat ~/.ssh/ittracker_deploy` ciktisinin **TAMAMI** (BEGIN/END dahil) |
| `PROD_HOST` | `10.34.0.62` |
| `PROD_USER` | `leventcan` |
| `PROD_DIR` | `/home/leventcan/ittracker` |
| `STAGING_DIR` | `/home/leventcan/ittracker-staging` |

### 3. GitHub Environments (opsiyonel ama onerilir)

Repo > **Settings** > **Environments** > **New environment**:
- `production` — protection rule: **Required reviewers** = 1 (sen). Boylece her prod deploy onay ister.
- `staging` — protection yok, otomatik aksin.

### 4. Branch Protection

Repo > **Settings** > **Branches** > **Add rule**:
- Branch pattern: `main`
- ✅ Require a pull request before merging
- ✅ Require status checks to pass before merging — `test` workflow secilsin
- ❌ Require linear history — **KAPALI** (2026-07 karari; bkz. asagidaki Merge Politikasi)
- ✅ Do not allow bypassing the above settings

`develop` icin daha gevsek — sadece status check yeterli.

### Merge Politikasi (ONEMLI — VERSION cakismasinin kok cozumu)

Iki farkli merge yontemi, iki farkli amac:

| Merge | Yontem | Neden |
|---|---|---|
| **feature → develop** | **Squash and merge** | Temiz, tek-satir gecmis. Feature'in ara commit'leri develop'i kirletmez. |
| **develop → main** (release) | **Create a merge commit** | main ↔ develop ORTAK GECMISI korunur. |

**Neden release'de merge-commit zorunlu:** Release PR'i squash (veya rebase) edilirse
GitHub main'de develop'inkiyle icerik-ayni ama SHA-farkli yeni bir commit olusturur;
ortak gecmis kopar. Sonraki her develop↔main merge'inde merge-base cok eskiye duser ve
`VERSION` gibi iki tarafin da dokundugu dosyalar "ikisi de degisti" diye **phantom
cakisir** (2026-06/07'de tekrar tekrar yasandi). Merge-commit gecmisi birlestirir →
gelecekte cakisma olmaz. Bu yuzden `main`'de "Require linear history" KAPATILDI
(linear-history merge-commit'i engelliyordu).

> Release PR'ini birlestirirken GitHub'da **"Create a merge commit"** sec — "Squash"
> veya "Rebase" KULLANMA.

### 5. `develop` branch'i olustur

```bash
git checkout -b develop main
git push -u origin develop
```

### 6. `deploy.bat` emekli et

```bash
git rm deploy.bat
git commit -m "chore: GitHub Actions deploy aktif, deploy.bat kaldirildi"
```

---

## Akis

```
feature dali  --PR-->  develop  --auto deploy-->  staging
                          |
                          v (smoke test OK)
                        PR
                          |
                          v
                        main  --auto deploy + onay-->  prod
```

### Hotfix
Acil prod fix:
```bash
git checkout -b hotfix/x main
# fix
git commit -am "fix: ..."
git push -u origin hotfix/x
# GitHub'da PR ac -> main'e merge -> otomatik deploy
```

### Manuel deploy (gerekirse)
GitHub > **Actions** > workflow sec > **Run workflow** butonu (`workflow_dispatch`).

---

## Geri Donus / Rollback

Workflow rollback yapmaz — onceki commit'e donmek icin:
```bash
git revert <bozuk-commit-sha>
git push origin main   # otomatik deploy edilir
```

Acil durum (manuel):
```bash
ssh leventcan@10.34.0.62
cd /home/leventcan/ittracker
git reset --hard <onceki-sha>
docker compose up -d --build
```

DB rollback: `instance/it_tracker_backup_YYYYMMDD_HHMMSS.db` her deploy'da olusturulur.

---

## Sonraki Seviye (2)

- **GHCR**: image GitHub'da build edilir, sunucuda sadece `docker pull` (deploy 10sn)
- **Alembic**: schema migration versiyonlu
- **Postgres**: SQLite kilit sorunlarinin sonu
- **Sentry**: prod hatalari otomatik raporlansin
- Bunlar Seviye 1 calistiktan sonra adim adim eklenir.
