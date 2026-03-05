@echo off
chcp 65001 >nul
title IT Tracker v2.0
cd /d "%~dp0"

echo.
echo  ==========================================
echo   IT GOREV TAKIP SISTEMI v2.0
echo  ==========================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo  venv bulunamadi, kuruluyor...
    python -m venv venv
    if errorlevel 1 (
        echo  HATA: Python bulunamadi.
        pause
        exit /b 1
    )
    echo  Paketler yukleniyor...
    venv\Scripts\pip install -r requirements.txt --quiet
    echo  Kurulum tamamlandi.
    echo.
)

echo  Baslatiliyor: http://localhost:5000
echo  Durdurmak icin Ctrl+C basin.
echo.

venv\Scripts\python app.py
pause
