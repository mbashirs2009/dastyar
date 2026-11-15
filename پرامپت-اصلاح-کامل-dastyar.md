# پرامپت کامل اصلاح پروژه «دستیار»

> این فایل یک پرامپت واحد است. همه‌اش را کپی کن و به هوش مصنوعی کدنویس (Cursor / Claude / Copilot و…) بده.
> قبل از اجرا: این پرامپت کد را تغییر می‌دهد؛ روی شاخه جدید (`git checkout -b security-fixes`) اجرا کن و دیتابیس production را بکاپ بگیر.

---

تو یک مهندس ارشد امنیت وب + بک‌اند FastAPI + فرانت‌اند React هستی. پروژه من را کامل اصلاح کن.

## بافت پروژه (تأییدشده با ممیزی زنده)

- **بک‌اند:** Python + FastAPI + uvicorn + SQLite، استقرار روی Render (پلن رایگان)، دامنه `dastyar-grk2.onrender.com`
- **فرانت‌اند:** React 18 + Vite، فارسی RTL، Telegram Mini App
- **احراز هویت:** JWT HS256 در هدر `Authorization: Bearer`، توکن در `localStorage` با کلید `dastyar_token`
- **OAuth:** گوگل و گیت‌هاب در کد هست ولی غیرفعال (`google:false, github:false`)؛ تلگرام هم `bot:false`
- **مدل داده:** کاربر، گفتگو (`Conversation`)، پیام (`Message`)؛ شناسه‌ها integer ترتیبی
- **چت:** SSE / استریم با Pollinations یا OpenRouter (کلید سمت سرور — در باندل کلاینت نبود، خوب)
- **مسیرهای API:** `/auth/register`، `/auth/login`، `/auth/me`، `/auth/logout`، `/auth/providers`، `/auth/google*`، `/auth/github*`، `/auth/telegram/verify`، `/auth/telegram/status`، `/telegram/health`، `/conversations`، `/conversations/{id}/messages`، `/conversations/{id}`، `/chat`، `/profile`، `/health`، `/`
- **چیزی که سالم است و دست نزن (فقط اگر لازم شد بهبود بده):** بررسی مالکیت گفتگوها (IDOR بسته است و 404 می‌دهد)، پیام یکسان ورود برای ایمیل ناموجود/رمز غلط، رد `alg=none`، اعتبارسنجی int روی path، 401 برای APIهای محافظت‌شده، HTTPS و ریدایرکت HTTP، RTL و `lang="fa"`

ممیزی زنده این باگ‌ها را **تأیید کرد**. همه را رفع کن. چیزی را که نمی‌دانی، از کد بخوان و بعد تصمیم بگیر؛ حدس نزن.

---

## بخش ۱ — باگ‌های بحرانی (اول این‌ها)

### ۱. خروج واقعی نیست و توکن ۳۰ روز قابل ابطال نیست
**شواهد:** بعد از `POST /auth/logout` با پاسخ `{"ok":true}`، همان توکن هنوز روی `/auth/me` و `/conversations` کد 200 می‌گیرد. JWT payload: `{"sub":"1","iss":"dastyar","iat":...,"exp":iat+2592000}` یعنی ۳۰ روز. بدون `jti`، بدون جدول نشست، بدون `token_version`. فرانت توکن را در `localStorage` می‌گذارد.
**اقدام:**
1. جدول/مدل `Session` بساز: `id`، `user_id`، `jti` (یکتا)، `token_hash`، `user_agent`، `ip`، `created_at`، `last_used_at`، `expires_at`، `revoked_at`.
2. access token عمر ۱۵ دقیقه + refresh token عمر ۷ روز در کوکی `HttpOnly; Secure; SameSite=Lax; Path=/auth` (نه در localStorage).
3. `POST /auth/logout` نشست جاری را `revoked_at = now` کند و کوکی refresh را پاک کند. بدون توکن معتبر، logout هم 401 بدهد.
4. `POST /auth/refresh` با چرخش refresh token (قبلی باطل، جدید صادر). استفاده مجدد از refresh باطل‌شده = ابطال کل نشست‌های آن کاربر + لاگ هشدار.
5. تغییر رمز و «خروج از همه دستگاه‌ها» همه نشست‌های دیگر را باطل کند.
6. هر درخواست محافظت‌شده، `jti` را در جدول Session چک کند: اگر revoked یا منقضی بود → 401.
7. در فرانت: توکن access فقط در حافظه (متغیر/React state)؛ interceptor در 401 یک‌بار refresh بزند؛ `localStorage.removeItem('dastyar_token')` از همه جا حذف شود. اسکریپت داخل `index.html` که `localStorage.setItem('dastyar_token', token)` می‌کند هم حذف/بازنویسی شود.
8. توکن OAuth دیگر در URL نیاید؛ با کوکی یک‌بارمصرف کد موقت (authorization-code مانند) به صفحه بازگشت بده و بعد کوکی ست کن. اگر مجبوری توکن در URL بمانی، بعد از خواندن با `history.replaceState` پاکش کن و هدر `Referrer-Policy: no-referrer` روی صفحات auth بگذار.

### ۲. Swagger و OpenAPI در production باز است
**شواهد:** `GET /docs`، `/redoc`، `/openapi.json` همه 200 می‌دهند و کل ۱۹ مسیر + اسکیماها را لو می‌دهند.
**اقدام:** در production:
```python
app = FastAPI(..., docs_url=None, redoc_url=None, openapi_url=None)
```
یا فقط وقتی `settings.ENV == "dev"` فعال باشند. `/health` باید JSON بدهد (الان HTML برمی‌گرداند — روتینگ catch-all را درست کن تا مسیرهای API را نبلعد).

### ۳. هیچ محدودیت نرخی روی ورود/ثبت‌نام نیست + هر login ۲.۵ ثانیه CPU می‌گیرد
**شواهد:** ۶ تلاش رمز غلط پشت‌سرهم همه 401 بدون قفل. زمان هر تلاش ~۲.۵ ثانیه. این هم brute-force را ممکن می‌کند هم DoS (هر درخواست ۲.۵ ثانیه CPU روی نمونه رایگان Render).
**اقدام:**
1. با `slowapi` یا middleware خودت + Redis/جدول دیتابیس (نه حافظه پروسه):
   - ورود: ۵ تلاش در ۱۵ دقیقه به ازای هر ایمیل + ۱۰ به ازای هر IP
   - ثبت‌نام: ۵ در ساعت به ازای هر IP
   - OTP/تلگرام: ۵ تلاش برای هر کد
2. پاسخ 429 با `Retry-After` و پیام فارسی ثابت.
3. زمان پاسخ ورود را به زیر ۴۰۰ms برسان: پارامترهای هش را برای نمونه رایگان تنظیم کن (bcrypt cost=12 یا argon2id با memory کمتر ولی نه آن‌قدری که ۲.۵ ثانیه شود). اگر دلیل کندی هش است، cost را پایین بیاور؛ اگر دلیل کندی چیز دیگر است (شبکه/DB)، همان را درست کن. هدف: p95 ورود < 500ms روی Render.
4. برای کاربر ناموجود هم همان کار هش را انجام بده (dummy hash) تا زمان یکسان بماند — الان زمان‌ها نزدیک‌اند، حفظ کن.

### ۴. سیاست رمز عبور وجود ندارد
**شواهد:** ثبت‌نام با رمز `123456` موفق بود (HTTP 201).
**اقدام:**
- حداقل ۱۲ کاراکتر، حداکثر ۱۲۸.
- رد رمزهایی که برابر ایمیل/نام هستند.
- بررسی در برابر فهرست رمزهای لو‌رفته (HIBP k-anonymity یا فهرست محلی top-10k).
- پیام فارسی روشن: «رمز عبور باید حداقل ۱۲ کاراکتر باشد.»
- الگوریتم هش: Argon2id (توصیه) یا bcrypt cost ≥ 12. MD5/SHA خام ممنوع. مقایسه constant-time.
- **مسیر تغییر رمز و بازیابی رمز اضافه کن** — الان اصلاً وجود ندارد (`/auth/change-password`، `/auth/forgot-password`، `/auth/reset-password` 405 می‌دهند):
  - تغییر رمز: رمز فعلی الزامی + ابطال نشست‌های دیگر.
  - بازیابی: توکن `secrets.token_urlsafe(32)`، فقط هش SHA-256 در دیتابیس، انقضای ۴۵ دقیقه، یک‌بارمصرف، پاسخ همیشه یکسان (افشای وجود ایمیل ممنوع)، ایمیل «رمز تغییر کرد» + لینک قفل اضطراری.
- تأیید ایمیل در ثبت‌نام اضافه کن (لینک یک‌بارمصرف ۲۴ ساعته)؛ تا تأیید نشده، ورود محدود باشد.

### ۵. هیچ هدر امنیتی‌ای نیست
**شواهد:** پاسخ صفحه اصلی و API هیچ‌کدام از این‌ها را ندارند: HSTS، CSP، X-Content-Type-Options، X-Frame-Options، Referrer-Policy، Permissions-Policy.
**اقدام:** یک middleware FastAPI بنویس (یا `secure` / Nginx اگر جلوی app هست):
```
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cross-Origin-Opener-Policy: same-origin
Cache-Control: no-store   # برای همه پاسخ‌های /auth و /conversations و /chat و /profile
```
CSP را اول یک هفته با `Content-Security-Policy-Report-Only` اجرا کن، بعد اجباری کن.

### ۶. اسکریپت تلگرام سایت را در ایران از کار می‌اندازد
**شواهد:** در `index.html` این خط، سنکرون و بدون `defer/async` است و در ایران فیلتر می‌شود:
`<script src="https://telegram.org/js/telegram-web-app.js"></script>`
در تست مرورگر، این اسکریپت ۲۱ ثانیه بلاک کرد و React اصلاً mount نشد (`#root` خالی). کاربر ایرانی سایت را «همیشه در حال لود» می‌بیند.
**اقدام:**
1. آن اسکریپت را `async` کن، یا بهتر: فقط وقتی داخل تلگرام هستی لودش کن:
```js
if (window.Telegram?.WebApp || /Telegram/i.test(navigator.userAgent)) {
  const s = document.createElement('script');
  s.src = 'https://telegram.org/js/telegram-web-app.js';
  s.async = true;
  document.head.appendChild(s);
}
```
2. اگر فایل را خودت در `/public` نگه می‌داری هم مشکلی نیست؛ آدرس `telegram.org` را از مسیر بحرانی render حذف کن.
3. فونت وزیرمتن را از Google Fonts حذف و self-host کن (`/fonts/Vazirmatn.woff2` + `font-display: swap` + `preload`). Google Fonts برای کاربر ایرانی ناپایدار است و رندر را کند می‌کند.
4. LCP هدف: زیر ۲.۵ ثانیه در موبایل.

### ۷. SQLite روی Render = پاک شدن همه گفتگوها در هر دیپلوی
**شواهد:** OpenAPI می‌گوید «گفتگوها و پیام‌ها در SQLite». Render پلن رایگان فایل‌سیستم موقت دارد؛ هر ری‌استارت/دیپلوی دیتابیس پاک می‌شود مگر disk دائمی یا دیتابیس بیرونی داشته باشی.
**اقدام (با من تأیید کن کدام مسیر):**
- **گزینه A (پیشنهادی):** مهاجرت به PostgreSQL (Render Postgres یا Neon/Supabase). SQLAlchemy URL را از env بگیر. برای SQLite فقط dev.
- **گزینه B:** Render Persistent Disk mount کن و مسیر db را به آن دیسک ببر + بکاپ روزانه `sqlite3 .backup` به object storage.
- در هر دو حالت: `PRAGMA foreign_keys=ON` اگر SQLite ماندی، WAL فعال، و یک job بکاپ روزانه + تست بازیابی ماهانه.
- همین امروز قبل از هر کس دیگر ثبت‌نام کند این را درست کن — الان دیتای واقعی کاربران در خطر است.

---

## بخش ۲ — باگ‌های مهم (بعد از بحرانی‌ها)

### ۸. نرمال‌سازی ناقص ایمیل (ارقام فارسی/فولویدث حساب تکراری می‌سازد)
**شواهد:** ثبت‌نام با `AUDIT.PROBE.K83M@...` و با فاصله اضافی → 409 (درست). ثبت‌نام با `audit.probe.k８３m@...` (ارقام فولویدث) → **201 حساب جدید**.
**اقدام:** تابع `normalize_email`:
```python
import unicodedata
def normalize_email(raw: str) -> str:
    s = unicodedata.normalize("NFKC", raw or "")
    s = s.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    s = "".join(ch for ch in s if ch not in "\u200c\u200d\u200e\u200f\ufeff")
    return s.strip().lower()
```
همین کار برای موبایل اگر داری. ایندکس یکتا روی ستون نرمال‌شده. در register و login و forgot همه از یک تابع استفاده کن. مهاجرت داده‌های فعلی را هم بنویس.

### ۹. افشای وجود ایمیل در ثبت‌نام
**شواهد:** `{"detail":"این ایمیل قبلاً ثبت شده است. وارد شوید."}` با 409.
**اقدام:** پاسخ همیشه: «اگر این ایمیل معتبر باشد، لینک ورود/تأیید ارسال شد.» با 200. اگر UX فعلی اجازه نمی‌دهد کامل عوض شود، حداقل پیام را مبهم کن و rate limit سخت بگذار. (ورود از قبل پیام یکسان دارد — دست نزن.)

### ۱۰. ذخیره ورودی‌های خطرناک در نام و آواتار
**شواهد:** `name = "Probe<script>alert(1)</script>"` و `avatar_url = "javascript:alert(document.domain)"` هر دو ذخیره شدند (200).
**اقدام:**
- `avatar_url`: فقط `http://` و `https://` مجاز؛ `javascript:` `data:` `vbscript:` رد. طول ≤ 500. اگر آواتار آپلودی اضافه می‌کنی، magic bytes + resize با Pillow + ذخیره بیرون web root.
- `name`: حذف کاراکترهای کنترلی، طول ۱..۸۰، بدون `<` و `>` (یا escape در رندر).
- در فرانت: آواتار را فقط با `img src` بعد از اعتبارسنجی scheme رندر کن؛ هر `dangerouslySetInnerHTML` را فهرست کن و اگر محتوای کاربر/هوش مصنوعی رندر می‌کند، با DOMPurify با فهرست سفید تنگ پاک کن. پیام‌های assistant اگر markdown هستند، `react-markdown + rehype-sanitize` بگذار.

### ۱۱. CORS
**شواهد:** `allow-credentials: true` و `expose-headers: *` روی همه پاسخ‌ها. `http://localhost:5173` در production در allowlist است. origin های ناشناس ACAO نمی‌گیرند (خوب).
**اقدام:** allowlist از env: فقط `https://dastyar-grk2.onrender.com` (و دامنه سفارشی اگر داری). localhost فقط وقتی `ENV=dev`. `allow_credentials=True` لازم نیست چون Bearer استفاده می‌کنی — خاموشش کن. `expose-headers` را به `[X-Request-Id]` محدود کن. `Vary: Origin` بماند.

### ۱۲. صفحه‌بندی نیست
**شواهد:** `GET /conversations` و `/conversations/{id}/messages` بدون `limit`/`offset` در OpenAPI؛ کل آرایه برمی‌گردد.
**اقدام:** `?limit=20&cursor=<id>` با سقف ۱۰۰؛ بیشتر از ۱۰۰ → 422. کلید مرتب‌سازی `updated_at DESC, id DESC`. برای SQLite/Postgres index روی `(user_id, updated_at DESC)`. پاسخ: `{items, next_cursor}`.

### ۱۳. خطاها و 404
**شواهد:** خطای تلگرام: `"ربات تلگرام پیکربندی نشده. BOT_TOKEN را در .env بگذار."` با 501 — مسیر کانفیگ را لو می‌دهد. مسیرهای ناشناخته همه 200 و HTML هستند (soft 404). `/health` HTML می‌دهد نه JSON. `HEAD /` و `HEAD /assets/...` → 405.
**اقدام:**
- پیام تلگرام: «سرویس تلگرام در دسترس نیست.» بدون نام متغیر env.
- exception handler سراسری: production بدون stack و بدون نام جدول/فایل. لاگ کامل سمت سرور با request-id. پاسخ: `{"error":{"code":"...","message":"...","request_id":"..."}}`.
- مسیرهای ناشناخته زیر `/auth`، `/conversations`، `/chat`، `/profile`، `/health` → 404 JSON.
- catch-all SPA فقط برای مسیرهای غیر API.
- `/health` واقعی JSON بدهد: `{"status":"ok"}`.
- `HEAD` را روی استاتیک و `/` فعال کن (uvicorn/StaticFiles).
- هدر `X-Request-Id` در پاسخ + در لاگ.
- `app.disable` معادل: هدرهای `Server` و نسخه را مخفی کن (`Server: cloudflare` می‌ماند، اشکالی ندارد؛ `x-render-origin-server: uvicorn` را حذف کن اگر می‌شود).

### ۱۴. MFA و عملیات حساس
برای تغییر ایمیل/رمز و حذف حساب، رمز فعلی الزامی شود. TOTP اختیاری (pyotp) با QR و کد بازیابی. جدول `audit_log` فقط-append: ورود موفق/ناموفق، قفل، تغییر رمز/ایمیل، حذف گفتگو. ایمیل اعلان برای ورود از دستگاه جدید.

---

## بخش ۳ — فرانت‌اند (React)

1. توکن از localStorage به حافظه + refresh کوکی (بخاطرات ۱).
2. اسکریپت تلگرام async/شرطی و فونت self-host (بخاطرات ۶).
3. چهار حالت برای هر صفحه داده: loading (skeleton)، error (پیام فارسی + تلاش مجدد + request_id)، empty (راهنمای «اولین گفتگو را بساز»)، success.
4. فرم‌ها: اعتبارسنجی با zod مشترک با بک‌اند؛ خطا کنار فیلد؛ `autocomplete` درست (`email`, `current-password`, `new-password`)؛ `inputmode` مناسب؛ دکمه ارسال در حین ارسال disable.
5. خطای 401 → انتقال به `/login` با `returnTo` و پیام «نشست شما منقضی شد».
6. دسترس‌پذیری: `:focus-visible`، contrast ≥ 4.5، label واقعی، کیبورد، `prefers-reduced-motion`، هدف لمسی 44px.
7. عنوان صفحه‌ها درست؛ `<html lang="fa" dir="rtl">` حفظ شود.
8. هیچ توکنی در URL نماند (بخاطرات ۱).

---

## بخش ۴ — پیکربندی و استقرار

1. `.env` در Git نیست؟ تأیید کن. `.env.example` فقط نام متغیرها. اگر تاریخچه Git راز دارد، بچرخان و با `git filter-repo` پاک کن.
2. متغیرهای الزامی: `JWT_SECRET` (≥ ۵۶ کاراکتر تصادفی، نه کلمه)، `DATABASE_URL`، `ENV=production`، `ALLOWED_ORIGINS`. اگر `JWT_SECRET` ضعیف یا پیش‌فرض است، **همین امروز عوض کن** (همه توکن‌ها باطل می‌شوند — خوب است).
3. `uvicorn --workers 2` اگر حافظه اجازه می‌دهد؛ SQLite با چند ورکر مشکل قفل دارد — دلیل دیگر برای Postgres.
4. `docs_url=None` در production.
5. CI: `ruff`، `pytest`، `npm audit`/`pip-audit`، gitleaks. بیلد روی آسیب‌پذیری high بشکند.
6. لاگ JSON ساختاریافته؛ رمز/توکن/ایمیل ماسک؛ Sentry با scrubbing.
7. robots.txt: `/auth`, `/conversations`, `/chat`, `/profile`, `/docs` disallow.
8. `security.txt` در `/.well-known/security.txt`.

---

## بخش ۵ — ترتیب اجرا (همین ترتیب پیش برو)

1. بکاپ + شاخه جدید + `JWT_SECRET` جدید + بستن Swagger در production
2. Persistent disk یا Postgres برای SQLite (فوری‌ترین ریسک از دست رفتن داده)
3. حذف اسکریپت بلاک‌کننده تلگرام + self-host فونت
4. logout واقعی + refresh token + حذف localStorage
5. rate limit + سیاست رمز + بازیابی/تغییر رمز
6. هدرهای امنیتی + CSP report-only
7. نرمال‌سازی ایمیل + پیام مبهم ثبت‌نام
8. اعتبارسنجی avatar/name + DOMPurify
9. صفحه‌بندی + ایندکس
10. هندلر خطا + 404 API + `/health` JSON
11. MFA اختیاری + audit log
12. CI و تست‌ها

---

## بخش ۶ — تست‌هایی که باید بعد از اصلاح سبز شوند (بنویسشان)

1. ثبت‌نام با رمز `123456` → 422.
2. ثبت‌نام با ایمیل تکراری (حرف بزرگ/فاصله/ارقام فارسی) → پیام یکسان مبهم، نه حساب جدید.
3. ۶ ورود غلط پشت‌سرهم → 429.
4. `POST /auth/logout` سپس همان access token روی `/auth/me` → 401.
5. refresh token استفاده‌شده دوباره → 401 و ابطال بقیه نشست‌ها.
6. کاربر B روی `GET/PATCH/DELETE /conversations/{id کاربر A}` → 404. (این الان درست است؛ نسل	next نشکن.)
7. `GET /docs` و `/openapi.json` در production → 404.
8. `GET /health` → JSON `{"status":"ok"}`.
9. هدرهای امنیتی روی `/` و `/auth/me` حاضرند؛ `Cache-Control: no-store` روی APIهای احرازهویت‌شده.
10. `avatar_url: javascript:alert(1)` → 422.
11. `GET /conversations?limit=1000` → 422.
12. صفحه اصلی بدون اسکریپت بلاک‌کننده تلگرام در کمتر از ۳ ثانیه interactive شود (تست با throttle).
13. `pip-audit` و `npm audit` بدون high/critical.

هیچ رفتار موجود دیگری را که در «چیزی که سالم است» نوشتم تغییر نده. بازسازی UI نکن. مهاجرت‌های دیتابیس را بنویس و قابل rollback کن.

در پایان: فهرست تغییرات + دستور اجرای مهاجرت + چک‌لیست تست دستی ۱۲ موردی بالا را به من بده.
