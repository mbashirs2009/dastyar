@echo off
chcp 65001 >nul
title Dastyar — ذخیره در گیت‌هاب
cd /d "%~dp0"

echo.
echo  === ذخیره تغییرات در گیت‌هاب (تنها منبع پروژه) ===
echo.

git status --porcelain >nul 2>nul
if errorlevel 1 (
  echo [خطا] این پوشه مخزن گیت نیست.
  pause
  exit /b 1
)

git add -A

set "MSG="
if not "%~1"=="" set "MSG=%~1"
if not defined MSG (
  set /p MSG=توضیح تغییر (Enter): 
)
if not defined MSG set "MSG=update"

git commit -m "%MSG%"
if errorlevel 1 (
  echo [ok] تغییری برای ذخیره نبود.
) else (
  echo [ok] commit شد.
)

git push
if errorlevel 1 (
  echo.
  echo [خطا] پوش نشد. اگر ریپو را تازه ساختی، یک بار این را بزن:
  echo   git push -u origin main
  pause
  exit /b 1
)

echo.
echo  ✓ روی https://github.com/Bashir1425/dastyar رفت.
echo  ✓ هر ماشین دیگری با update.bat همین را می‌گیرد.
echo.
pause
