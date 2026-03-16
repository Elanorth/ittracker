@echo off
chcp 65001 >nul
echo ══════════════════════════════════════
echo   IT Tracker - Deploy Script
echo ══════════════════════════════════════

:: 1. GitHub'a push
echo.
echo [1/3] GitHub'a push ediliyor...
cd /d "C:\Users\levent.can\Projects\ittracker"
git push github main
if %errorlevel% neq 0 (
    echo HATA: GitHub push basarisiz!
    pause
    exit /b 1
)
echo OK: GitHub push tamamlandi.

:: 2. Sunucuda pull + docker rebuild
echo.
echo [2/3] Sunucuya baglaniliyor... (pull + docker rebuild)
ssh leventcan@10.34.0.62 "cd /home/leventcan/ittracker && git pull origin main && sudo docker compose down && sudo docker compose up -d --build"
if %errorlevel% neq 0 (
    echo HATA: Sunucu deploy basarisiz!
    pause
    exit /b 1
)

:: 3. Durum kontrolu
echo.
echo [3/3] Container durumu kontrol ediliyor...
ssh leventcan@10.34.0.62 "sudo docker compose -f /home/leventcan/ittracker/docker-compose.yml ps"

echo.
echo ══════════════════════════════════════
echo   Deploy tamamlandi!
echo ══════════════════════════════════════
pause
