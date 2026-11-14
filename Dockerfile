# ---------- فرانت‌اند ----------
FROM node:20-slim AS web
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- بک‌اند + سرو static ----------
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    APP_HOST=0.0.0.0

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=web /fe/dist ./frontend/dist

EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
