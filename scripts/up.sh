#!/usr/bin/env bash
#
# Bring up the whole stack and VERIFY it is healthy — one command.
#   1. DeepFace sidecar (Docker) + wait until its API actually responds
#   2. ai_service (uvicorn :8080) + wait until /health responds
#   3. Confirm ai_service reports the sidecar as reachable
# Prints a clear PASS/FAIL with the next action on any failure.
#
set -euo pipefail
cd "$(dirname "$0")/.."

AI_PORT="${AI_PORT:-8080}"
RUN_DIR=".run"
PID_FILE="$RUN_DIR/ai_service.pid"
mkdir -p "$RUN_DIR"

red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }

fail() { red "❌ $1"; [ -n "${2:-}" ] && echo "   → $2"; exit 1; }

# Poll an HTTP endpoint until it returns 200, or time out.
wait_http() {
  local url=$1 name=$2 timeout=${3:-120} i=0
  echo "==> waiting for $name ($url) ..."
  while [ "$i" -lt "$timeout" ]; do
    if [ "$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null)" = "200" ]; then
      green "✅ $name is up"; return 0
    fi
    sleep 2; i=$((i + 2))
  done
  return 1
}

# 0. Preconditions
[ -d venv ] || fail "venv missing." "run ./install.sh first"
docker info >/dev/null 2>&1 || fail "Docker daemon not reachable." "start Docker (or: colima start)"
git submodule status vendor/deepface 2>/dev/null | grep -q '^-' && \
  fail "deepface submodule not initialised." "git submodule update --init vendor/deepface"

# 1. Sidecar config — ensure .env exists and Weaviate does NOT clash with ai_service on :8080
SIDE_ENV="vendor/deepface/docker/.env"
[ -f "$SIDE_ENV" ] || cp vendor/deepface/docker/.env.example "$SIDE_ENV"
if grep -qE '^WEAVIATE_PORT=8080([^0-9]|$)' "$SIDE_ENV"; then
  sed -i.bak -E 's/^(WEAVIATE_PORT=)8080/\18081/' "$SIDE_ENV" && rm -f "$SIDE_ENV.bak"
  echo "==> remapped Weaviate host port 8080 -> 8081 (avoids clash with ai_service)"
fi

# 2. Bring up the sidecar (build on first run; weights persist in a named volume)
echo "==> starting DeepFace sidecar (docker compose up -d --build) ..."
docker compose up -d --build deepface
wait_http "http://localhost:5005/api/v1/" "deepface API" 240 \
  || fail "deepface API never responded." "docker compose logs deepface"

# 2b. Warm the demographics models. DeepFace lazy-loads TF models on the first
# /analyze of a fresh container (cold start can take minutes). Pay that cost
# here, once, with a clear message — so the first real user call is fast.
SAMPLE="venv/lib/python3.11/site-packages/insightface/data/images/Tom_Hanks_54745.png"
if [ -f "$SAMPLE" ]; then
  echo "==> warming DeepFace models (one-time per container; can take a few minutes) ..."
  if curl -s --max-time 600 -o /dev/null -F "img=@$SAMPLE" \
       "http://localhost:5005/api/v1/analyze"; then
    green "✅ models warm"
  else
    red "⚠ warm-up call did not complete; first /analyze may be slow (not fatal)"
  fi
fi

# 3. ai_service
if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$AI_PORT/health" 2>/dev/null)" = "200" ]; then
  echo "==> ai_service already running on :$AI_PORT"
else
  echo "==> starting ai_service on :$AI_PORT ..."
  nohup bash -c "set -a; [ -f ./.env ] && . ./.env; set +a; exec venv/bin/uvicorn ai_service.app:app --host 127.0.0.1 --port $AI_PORT" \
    > "$RUN_DIR/ai_service.log" 2>&1 &
  echo $! > "$PID_FILE"
  wait_http "http://127.0.0.1:$AI_PORT/health" "ai_service" 60 \
    || fail "ai_service did not become healthy." "tail $RUN_DIR/ai_service.log"
fi

# 4. Confirm ai_service can actually reach the sidecar
DEEPFACE_STATE=$(curl -s "http://127.0.0.1:$AI_PORT/health" | grep -o '"deepface":"[a-z]*"' || true)
echo
if echo "$DEEPFACE_STATE" | grep -q '"deepface":"up"'; then
  green "✅ All systems up — ai_service (:$AI_PORT) reaches the deepface sidecar."
  echo "   Next: 'make verify' to push a real face through, or point Frappe at http://localhost:$AI_PORT"
else
  fail "ai_service is up but reports the sidecar as DOWN ($DEEPFACE_STATE)." \
       "check AI_SERVICE_DEEPFACE_URL in .env and 'docker compose logs deepface'"
fi
