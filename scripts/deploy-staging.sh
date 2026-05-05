#!/usr/bin/env bash
# Staging deploy — Mac/Linux'tan calistir
# Kullanim: ./scripts/deploy-staging.sh [branch]
#   branch parametresi verilmezse "develop" varsayilir
set -euo pipefail

BRANCH="${1:-develop}"
SERVER="leventcan@10.34.0.62"
REMOTE_DIR="/home/leventcan/ittracker-staging"

echo "==> Staging deploy: branch=$BRANCH server=$SERVER"

# 1. Local branch kontrolu
LOCAL_BRANCH="$(git branch --show-current)"
if [[ "$LOCAL_BRANCH" != "$BRANCH" ]]; then
  echo "UYARI: lokal branch=$LOCAL_BRANCH, deploy edilecek=$BRANCH"
  read -rp "Devam edilsin mi? [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || exit 1
fi

# 2. Local degisiklikler commit edilmis mi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "HATA: commit edilmemis degisiklikler var. Once commit/stash yap."
  git status --short
  exit 1
fi

# 3. Remote branch'i push (zaten push edilmis olabilir)
echo "==> Push: origin/$BRANCH"
git push origin "$BRANCH"

# 4. Sunucuda guncelle + rebuild
echo "==> Sunucuda pull + rebuild..."
ssh -i ~/.ssh/id_ed25519 "$SERVER" bash <<EOF
set -euo pipefail
cd "$REMOTE_DIR"
echo "Branch: \$(git branch --show-current)"
git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
docker compose -p ittracker-staging -f docker-compose.staging.yml up -d --build
docker compose -p ittracker-staging -f docker-compose.staging.yml ps
EOF

# 5. Smoke test
echo "==> Smoke test..."
sleep 5
HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" https://staging.ittracker.inventist.com.tr/login || echo "000")
if [[ "$HTTP_CODE" == "200" ]]; then
  echo "OK: staging.ittracker.inventist.com.tr/login = 200"
else
  echo "UYARI: smoke test http_code=$HTTP_CODE — manuel kontrol et"
  exit 1
fi

echo "==> Deploy tamamlandi."
