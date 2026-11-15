<div dir="rtl" align="center">

# دستیار — Dastyar

دستیار هوش مصنوعی فارسی، سریع و مینیمال — با رابط چت شبیه ChatGPT.

**بدون کلید API کار می‌کند.** کلون کن، اجرا کن، چت کن.

ورود با گوگل / گیت‌هاب / ایمیل · تم دارک و روشن · کدنویسی حرفه‌ای · RTL کامل

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white)](https://vitejs.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-0F62FE.svg)](LICENSE)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/mbashirs2009/dastyar)

</div>

---

## 🚀 سایت عمومی (هر push = deploy خودکار)

یک بار روی Render وصل کن، بعدش هر `save.bat` سایت عمومی را هم به‌روز می‌کند:

1. دکمه‌ی **Deploy to Render** بالا را بزن (یا [render.com/deploy?repo=https://github.com/mbashirs2009/dastyar](https://render.com/deploy?repo=https://github.com/mbashirs2009/dastyar))
2. با گیت‌هاب لاگین کن → **Apply**
3. بعد از build، آدرسی مثل `https://dastyar-xxxx.onrender.com` می‌گیری
4. در Render → Environment این‌ها را بگذار:
   - `FRONTEND_URL` = همان آدرس onrender
   - `BACKEND_URL` = همان آدرس
   - `TELEGRAM_WEBAPP_URL` = همان آدرس (برای Mini App)
   - اختیاری: `OPENROUTER_API_KEY`، `TELEGRAM_BOT_TOKEN`
5. **Manual Deploy** بزن تا env های جدید اعمال شود

از این به بعد هر `save.bat` = deploy خودکار سایت عمومی + ربات تلگرام.

Free plan بعد از ۱۵ دقیقه بی‌کاری می‌خوابد؛ اولین درخواست چند ثانیه طول می‌کشد.

## ✏️ تغییر کد — فقط یک جا

**گیت‌هاب تنها منبع پروژه است.** لپ‌تاپ، گوشی، ربات تلگرام و سایت همه از همین یک ریپو می‌خوانند.

| کار | ویندوز | لینوکس/مک |
|---|---|---|
| ذخیره تغییرات در گیت‌هاب | `save.bat "توضیح"` | `./save.sh "توضیح"` |
| گرفتن آخرین نسخه | `update.bat` | `./update.sh` |

قانون:

1. فقط در کلون محلی ادیت کن (همین پوشه)
2. `save.bat "متن تغییر"`
3. روی هر دستگاه دیگر: `update.bat`
4. سرورها را ری‌استارت کن

روی خود گیت‌هاب هم می‌توانی با مداد ادیت کنی، بعد روی کامپیوتر `update.bat` بزن.

`save.bat` و `update.bat` را دوبار کلیک هم می‌شود اجرا کرد.

## ⚡ اجرای صفر-پیکربندی (هر کاربر)

پیش‌نیاز: [Python 3.11+](https://python.org) و [Node.js 20+](https://nodejs.org)

```powershell
git clone https://github.com/mbashirs2009/dastyar.git
cd dastyar
start.bat          # ویندوز
# یا
bash start.sh      # لینوکس / مک
```

مرورگر باز می‌شود روی `http://localhost:5173` — با ایمیل/رمز وارد شو و چت کن.

**نیازی به کلید OpenRouter نیست.** مدل رایگان پیش‌فرض (Pollinations) بدون کلید جواب می‌دهد و روی اینترنت ایران هم تست شده.

## ✨ امکانات

- **چت زنده (SSE)** — پاسخ‌ها کلمه‌به‌کلمه
- **مدل پیش‌فرض بدون کلید** — Pollinations (سازگار با ایران)
- **اختیاری:** کلید OpenRouter برای سرعت/کیفیت بیشتر
- **ورود چندراهی** — گوگل، گیت‌هاب، یا ایمیل/رمز
- **کدنویسی** — پرامپت سیستمی برنامه‌نویس + هایلایت کد
- **تم** — روشن / دارک / پیش‌فرض سیستم
- **فارسی و RTL** — فونت وزیرمتن
- **پروفایل** — نام، آواتار، تم
- **مینیمال** — یک رنگ تاکیدی `#0F62FE`

## 🧠 مدل — زنجیره‌ی خودکار

| ترتیب | سرویس | کلید لازم؟ | توضیح |
|---|---|---|---|
| ۱ | OpenRouter | بله (اختیاری) | اگر در `.env` کلید بگذاری |
| ۲ | **Pollinations** | **نه** | پیش‌فرض همه‌ی کاربران — ایران‌پسند |
| ۳ | پاسخ نمایشی | نه | فقط اگر اینترنت کامل قطع باشد |

نام برند در اپ همیشه **«دستیار»** است.

اگر OpenRouter روی اینترنت تو فیلتر باشد، خودکار به Pollinations می‌رویم — خطای «ارتباط با مدل برقرار نشد» دیگر برای قطعی OpenRouter نمی‌آید.

## 🧱 تکنولوژی

| لایه | ابزار |
|---|---|
| بک‌اند | FastAPI · SQLite · JWT · OAuth2 · SSE |
| فرانت‌اند | React 18 · Vite · TypeScript · Tailwind CSS |
| مدل پیش‌فرض | Pollinations (`openai`) — بدون کلید |
| مدل اختیاری | OpenRouter · `google/gemini-2.5-flash-lite` |

## 📁 ساختار

```
dastyar/
├── backend/           # FastAPI + SQLite + JWT + OAuth
├── frontend/          # React + Vite + Tailwind (RTL)
├── logo/              # لوگو (SVG + JPG)
├── design/            # توکن‌های طراحی
├── start.bat          # ویندوز
├── start.sh           # لینوکس / مک
└── push-to-github.bat
```

## 🚀 اجرای دستی (اگر start.bat نخواستی)

**بک‌اند:**

```powershell
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

**فرانت‌اند (ترمینال جدید):**

```powershell
cd frontend
npm install
npm run dev
```

- UI: http://localhost:5173
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## 🔑 تنظیمات اختیاری (`backend/.env`)

هیچ چیزی اجباری نیست. اگر خواستی بهترش کنی، `.env.example` را به `.env` کپی کن.

### کلید OpenRouter (اختیاری — سرعت بیشتر)

1. [openrouter.ai/keys](https://openrouter.ai/keys)
2. در `.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=google/gemini-2.5-flash-lite
```

> کلیدت را **در گیت‌هاب نگذار.** فقط در `.env` (که در `.gitignore` است).

### ورود با گوگل (اختیاری)

Redirect URI: `http://localhost:8000/auth/google/callback`

راهنمای کامل: [console.cloud.google.com](https://console.cloud.google.com/apis/credentials)

### ورود با گیت‌هاب (اختیاری)

Callback: `http://localhost:8000/auth/github/callback`

[github.com/settings/developers](https://github.com/settings/developers) → New OAuth App

### JWT

```
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

## 🔌 API خلاصه

| متد | مسیر | توضیح |
|---|---|---|
| POST | `/auth/register` | `{email, password, name}` |
| POST | `/auth/login` | `{email, password}` |
| GET | `/auth/me` | پروفایل (Bearer) |
| GET | `/auth/providers` | `{google:bool, github:bool}` |
| GET | `/conversations` | فهرست گفتگوها |
| POST | `/chat` | `{conversation_id, message}` → SSE |
| PATCH | `/profile` | نام / تم / آواتار |
| GET | `/health` | `{status, model:"دستیار"}` |

## 🧪 عیب‌یابی

<details>
<summary><b>start.bat اجرا نمی‌شود</b></summary>

پایتون/Node در PATH نیست. نسخه‌ی فعلی `start.bat` مسیر AutoClaw را هم چک می‌کند.
CMD را در پوشه‌ی پروژه باز کن و `start.bat` را تایپ کن تا خطا را ببینی.
</details>

<details>
<summary><b>ورود با گوگل برمی‌گردد به لاگین</b></summary>

Redirect URI باید دقیقاً `http://localhost:8000/auth/google/callback` باشد.
پنجره‌ی API را ببین. اگر `token exchange failed` بود، فیلترشکن باید برای کل سیستم روشن باشد.
</details>

<details>
<summary><b>پاسخ‌ها کند است</b></summary>

پیش‌فرض Pollinations است (بدون کلید). اگر سریع‌تر می‌خواهی، کلید OpenRouter بگذار.
مدل رایگان برای شروع کافی است.
</details>

<details>
<summary><b>npm install خطای شبکه</b></summary>

```powershell
npm cache verify
npm install --no-audit --no-fund
```
</details>

## 📱 موبایل (PWA)

بعد از باز کردن سایت در Chrome اندروید: منو → **Add to Home screen**.
آیکون دستیار روی گوشی می‌نشیند و تمام‌صفحه باز می‌شود.

iOS Safari: Share → Add to Home Screen.

## 💬 تلگرام (BotFather + Mini App)

اپ به‌عنوان Mini App داخل تلگرام باز می‌شود و کاربر تلگرام خودکار لاگین می‌شود.

### ۱. ساخت ربات
1. در تلگرام به [@BotFather](https://t.me/BotFather) برو
2. `/newbot` → اسم: `Dastyar` → یوزرنیم: مثلاً `dastyar_ai_bot`
3. توکن را کپی کن (`123456:ABC-...`)

### ۲. اتصال به اپ
در `backend/.env`:

```env
TELEGRAM_BOT_TOKEN=123456:ABC-...
# آدرس HTTPS عمومی (localhost در تلگرام باز نمی‌شود)
# برای تست روی سیستم: ngrok http 5173
TELEGRAM_WEBAPP_URL=https://xxxx.ngrok-free.app
```

بک‌اند را ری‌استارت کن — ربات long-polling روشن می‌شود.

### ۳. دکمه‌ی منو در BotFather
به BotFather:
- `/mybots` → رباتت → **Bot Settings → Menu Button** → آدرس وب‌اپ را بده
- یا **Web App** در ربات با همان URL

### ۴. باز کردن از تلگرام
در چت ربات، دکمه‌ی «🚀 باز کردن دستیار» یا منوی ربات را بزن — سایت داخل تلگرام باز می‌شود و بدون پسورد وارد می‌شوی.

> `api.telegram.org` در ایران فیلتر است؛ پنجره‌ی API باید فیلترشکن داشته باشد. وب‌اپ داخل تلگرام روی گوشی کاربر اجرا می‌شود (تلگرام خودش متصل است).

## 🎨 طراحی

توکن‌ها در `design/tokens.css`:

- جوهر `#161616` · کاغذ `#ffffff` · اکسنت `#0F62FE`
- دارک: اکسنت `#4589FF` (کنتراست ۴.۵:۱)
- بدون گرادیانت، بدون بنفش، بدون شلوغی

## 📄 لایسنس

MIT — آزاد برای استفاده، تغییر و انتشار.

---

<div dir="rtl" align="center">

ساخته‌شده با FastAPI و React · مدل برند **دستیار**

</div>
