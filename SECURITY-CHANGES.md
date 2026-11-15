# تغییرات امنیتی دستیار — ca30e24 (لوکال)

این تغییرات روی دسکتاپ کامیت شده‌اند ولی **پوش نشده‌اند** چون حساب گیت‌هاب Bashir1425 suspend شده.

بعد از بازیابی حساب:

```powershell
cd C:\Users\pubgm\Desktop\dastyar
save.bat "security hardening"
# سپس Render → Manual Deploy → Deploy latest commit
```

`init_db` خودش جدول‌های جدید را می‌سازد (sessions, rate_limits, password_resets, email_tokens, audit_log) و ستون `is_verified` را اضافه می‌کند. rollback: `git revert` + حذف دستی جدول‌های جدید اختیاری است.

## چک‌لیست تست دستی (بعد از deploy)

1. ثبت‌نام با رمز `123456` → 422 «رمز عبور باید حداقل ۱۲ کاراکتر باشد.»
2. ثبت‌نام با ایمیل تکراری (حرف بزرگ/فاصله/ارقام فارسی) → پیام مبهم ۲۰۰، نه حساب جدید
3. ۶ ورود غلط پشت‌سرهم → 429 + Retry-After
4. `POST /auth/logout` سپس همان access token روی `/auth/me` → 401
5. استفاده دوباره از refresh باطل‌شده → 401 و ابطال بقیه نشست‌ها
6. کاربر B روی conversations کاربر A → 404 (IDOR همچنان بسته)
7. `GET /docs` و `/openapi.json` در production → 404
8. `GET /health` → JSON `{"status":"ok","model":"دستیار"}`
9. هدرهای امنیتی روی `/` و `/auth/me`؛ `Cache-Control: no-store` روی APIهای احرازهویت‌شده
10. `avatar_url: javascript:alert(1)` → 422
11. `GET /conversations?limit=1000` → 422
12. صفحه اصلی بدون اسکریپت بلاک‌کننده تلگرام؛ LCP هدف < ۳ ثانیه

## مهاجرت دیتابیس

خودکار در start:
- جدول‌های sessions, rate_limits, password_resets, email_tokens, audit_log
- `ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0`
- WAL + foreign_keys روشن

پیشنهاد بعدی: PostgreSQL (Neon/Render Postgres) چون Render free فایل‌سیستم موقت دارد.

## رمز گیت‌هاب

رمزی که در چت فرستادی را بعد از بازیابی حساب **عوض کن**.
