#!/usr/bin/env bash
# ذخیره در گیت‌هاب — استفاده: ./save.sh "توضیح"
set -e
cd "$(dirname "$0")"
git add -A
if [ -z "$1" ]; then
  git commit -m "update" || echo "چیزی برای ذخیره نبود"
else
  git commit -m "$1"
fi
git push
echo "✓ روی github.com/Bashir1425/dastyar رفت"
