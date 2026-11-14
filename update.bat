@echo off
chcp 65001 >nul
title Dastyar — گرفتن آخرین نسخه
cd /d "%~dp0"

echo.
echo  === به‌روزرسانی از گیت‌هاب (تنها منبع پروژه) ===
echo.

git pull --rebase
if errorlevel 1 (
  echo [خطا] pull نشد. اینترنت / فیلتر گیت‌هاب را چک کن.
  pause
  exit /b 1
)

echo [1/2] وابستگی‌های بک‌اند...
python -c "import fastapi" >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul && python -m pip install -r backend\requirements.txt
)
if exist "C:\Users\pubgm\AppData\Local\Programs\AutoClaw2\resources\vendor\python\python.exe" (
  "C:\Users\pubgm\AppData\Local\Programs\AutoClaw2\resources\vendor\python\python.exe" -c "import fastapi" >nul 2>nul
  if errorlevel 1 "C:\Users\pubgm\AppData\Local\Programs\AutoClaw2\resources\vendor\python\python.exe" -m pip install -r backend\requirements.txt
)

echo [2/2] وابستگی‌های فرانت...
if not exist frontend\node_modules (
  pushd frontend
  call npm install --no-audit --no-fund
  popd
) else (
  echo      node_modules هست — skip
)

echo.
echo  ✓ پروژه به آخرین نسخه رسید.
echo  ✓ پنجره‌های API و UI را ری‌استارت کن (start.bat)
echo.
pause
