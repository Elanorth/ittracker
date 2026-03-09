@echo off
chcp 65001 >nul
title IT Tracker — Dev
cd /d "%~dp0"

echo.
echo  ==========================================
echo   IT TRACKER — Gelistirme Sunucusu
echo   http://localhost:5000
echo  ==========================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo  [*] venv bulunamadi, kuruluyor...
    python -m venv venv
    if errorlevel 1 (
        echo  [!] HATA: Python bulunamadi veya venv olusturulamadi.
        pause
        exit /b 1
    )
    echo  [*] Paketler yukleniyor...
    venv\Scripts\pip install -r requirements.txt --quiet
    echo  [*] Kurulum tamamlandi.
    echo.
)

if not exist ".env" (
    echo  [!] UYARI: .env dosyasi bulunamadi. .env.example'dan olusturun.
    echo.
)

echo  [*] Sunucu baslatiliyor...
echo  [*] Durdurmak icin Ctrl+C basin, sonra bu pencereyi kapatin.
echo.

venv\Scripts\python app.py

echo.
echo  [*] Sunucu durduruldu.
pause
