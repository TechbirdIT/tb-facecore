#!/usr/bin/env bash
#
# Stop everything started by scripts/up.sh: ai_service + the DeepFace sidecar.
# Model weights persist in the named volume, so the next `make up` is fast.
#
set -euo pipefail
cd "$(dirname "$0")/.."

PID_FILE=".run/ai_service.pid"
if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if kill "$PID" 2>/dev/null; then echo "==> stopped ai_service (pid $PID)"; fi
  rm -f "$PID_FILE"
fi

echo "==> stopping DeepFace sidecar (docker compose down) ..."
docker compose down

echo "✅ stack stopped (model weights kept in the deepface_weights volume)"
