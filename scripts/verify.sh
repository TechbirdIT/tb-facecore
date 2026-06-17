#!/usr/bin/env bash
#
# Smoke test: push a real face through ai_service /analyze and confirm
# demographics come back. Proves the full edge→gateway→sidecar path.
#   IMG=/path/to/face.jpg ./scripts/verify.sh   (defaults to a bundled sample)
#
set -euo pipefail
cd "$(dirname "$0")/.."

AI_PORT="${AI_PORT:-8080}"
IMG="${IMG:-venv/lib/python3.11/site-packages/insightface/data/images/Tom_Hanks_54745.png}"

red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }

[ -f "$IMG" ] || { red "❌ no test image."; echo "   → pass one: IMG=/path/to/face.jpg make verify"; exit 1; }

SECRET=$(grep -E '^AI_SERVICE_SECRET=' .env 2>/dev/null | cut -d= -f2- || true)
HDR=(); [ -n "$SECRET" ] && HDR=(-H "X-Secret: $SECRET")

echo "==> POST $IMG -> http://127.0.0.1:$AI_PORT/analyze  (first call may download models, be patient)"
BODY=$(curl -s --max-time 300 "${HDR[@]}" -F "file=@$IMG" "http://127.0.0.1:$AI_PORT/analyze")

if echo "$BODY" | grep -q '"age"'; then
  green "✅ Smoke test passed — demographics returned:"
  echo "$BODY" | grep -oE '"age":[0-9]+|"dominant_gender":"[^"]*"|"dominant_emotion":"[^"]*"|"dominant_race":"[^"]*"'
else
  red "❌ Smoke test failed. Response:"
  echo "$BODY" | head -c 600
  exit 1
fi
