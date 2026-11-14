#!/usr/bin/env bash
# Dastyar launcher — Linux / macOS
set -e
cd "$(dirname "$0")"

echo ""
echo "  === دستیار ==="
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 پیدا نشد. Python 3.11+ نصب کنید."
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] npm پیدا نشد. Node.js 20+ نصب کنید."
  exit 1
fi

if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
  echo "[ok] backend/.env ساخته شد — بدون کلید هم کار می‌کند."
fi

echo "[1/2] بک‌اند..."
python3 -c "import fastapi" 2>/dev/null || python3 -m pip install -r backend/requirements.txt
(
  cd backend
  python3 -m uvicorn main:app --reload --port 8000 &
)

echo "[2/2] فرانت‌اند..."
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install --no-audit --no-fund)
fi
(
  cd frontend
  npm run dev &
)

sleep 5
open http://localhost:5173 2>/dev/null || xdg-open http://localhost:5173 2>/dev/null || true

echo ""
echo "  API:  http://localhost:8000/docs"
echo "  UI:   http://localhost:5173"
echo ""
wait
