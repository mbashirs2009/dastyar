#!/usr/bin/env bash
# گرفتن آخرین نسخه از گیت‌هاب
set -e
cd "$(dirname "$0")"
git pull --rebase
python3 -c "import fastapi" 2>/dev/null || python3 -m pip install -r backend/requirements.txt
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install --no-audit --no-fund)
fi
echo "✓ به‌روز شد — سرورها را ری‌استارت کن"
