@echo off
chcp 65001 >nul
echo ======================================
echo   IT Tracker - Deploy Script
echo ======================================

cd /d "C:\Users\levent.can\Projects\ittracker"

:: --- 0. Branch kontrolu ---
for /f "tokens=*" %%b in ('git branch --show-current') do set CURBRANCH=%%b
if not "%CURBRANCH%"=="main" goto :BRANCH_ERROR

:: --- 0.1 Uncommitted degisiklik var mi ---
git diff --quiet
if errorlevel 1 goto :NEED_COMMIT
git diff --cached --quiet
if errorlevel 1 goto :NEED_COMMIT
goto :DO_PUSH

:NEED_COMMIT
echo.
echo UYARI: Commit edilmemis degisiklikler var.
git status --short
echo.
echo GUVENLIK: Asagidaki dosyalarin commitlenmemesi gerekir.
echo   - .env, *.secret, *_secret.txt, *.pem, *.key
echo   - ms_cer_secret.txt
echo Yukarida bunlardan biri goruluyorsa CTRL+C ile iptal edin.
echo.
set COMMITMSG=
set /p COMMITMSG=Commit mesaji yazin [bos=iptal]:
if "%COMMITMSG%"=="" goto :CANCEL
REM Sadece bilinen kaynak dosyalari ekle (secret'lari kaza ile almamak icin)
git add .gitignore
git add "*.py"
git add "templates/*.html"
git add "static/*.js"
git add "static/*.png"
git add "static/manifest.json"
git add deploy.bat
git add start.bat
git add docker-compose.yml
git add Dockerfile
git add requirements.txt
git add .env.example
git add nginx/
git commit -m "%COMMITMSG%"
if errorlevel 1 goto :COMMIT_ERROR
echo OK: Commit olusturuldu.

:DO_PUSH
echo.
echo [1/5] GitHub push...
git push github main
if errorlevel 1 goto :PUSH_ERROR
echo OK: Push tamamlandi.

echo.
echo [2/5] Sunucuda DB yedegi aliniyor...
ssh -t leventcan@10.34.0.62 "cd /home/leventcan/ittracker && if [ -f instance/it_tracker.db ]; then STAMP=$(date +%%Y%%m%%d_%%H%%M%%S); cp instance/it_tracker.db instance/it_tracker_backup_$STAMP.db && echo Yedek: instance/it_tracker_backup_$STAMP.db; else echo 'UYARI: instance/it_tracker.db bulunamadi'; fi"
if errorlevel 1 goto :BACKUP_ERROR

echo.
echo [3/5] Sunucuda git pull + docker rebuild...
ssh -t leventcan@10.34.0.62 "cd /home/leventcan/ittracker && git pull github main && sudo docker compose down && sudo docker system prune -f && sudo docker compose up -d --build"
if errorlevel 1 goto :DEPLOY_ERROR

echo.
echo [4/5] Web container loglari son 60 satir...
timeout /t 5 /nobreak >nul
ssh -t leventcan@10.34.0.62 "cd /home/leventcan/ittracker && sudo docker compose logs --tail=60 web"

echo.
echo [5/5] Container durumu...
ssh -t leventcan@10.34.0.62 "cd /home/leventcan/ittracker && sudo docker compose ps"

echo.
echo ======================================
echo   Deploy tamamlandi!
echo ======================================
echo.
echo Son kontroller:
echo   1. Tarayicida Ctrl+Shift+R ile hard refresh
echo   2. DevTools - Application - Service Workers - Unregister
echo   3. Logo altinda v4.5 gorunmeli
echo   4. Denetim Kayitlari ve SLA KPI kartlari gelmeli
echo.
pause
goto :EOF

:BRANCH_ERROR
echo HATA: main branch disindasin. Mevcut: %CURBRANCH%
echo Once: git checkout main
pause
exit /b 1

:CANCEL
echo Iptal edildi.
pause
exit /b 1

:COMMIT_ERROR
echo HATA: Commit basarisiz.
pause
exit /b 1

:PUSH_ERROR
echo HATA: GitHub push basarisiz.
pause
exit /b 1

:BACKUP_ERROR
echo HATA: DB yedegi alinamadi.
pause
exit /b 1

:DEPLOY_ERROR
echo HATA: Sunucu deploy basarisiz.
pause
exit /b 1
