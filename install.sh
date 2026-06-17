#!/usr/bin/env bash
#
# One-command setup for the tb-facecore AI stack (facecore + ai_service + edge_client),
# the service the Frappe face_attendance app calls at port 8080.
#
# Re-runnable (idempotent). Creates a venv, installs the packages editable, prepares
# .env with a generated secret, and prints next steps.
#
#   ./install.sh                 # core AI stack
#   ./install.sh --dev           # + dev/test tooling (pytest, ruff, ...)
#   ./install.sh --with-sidecar  # + bring up the DeepFace analytics sidecar (Docker)
#
set -euo pipefail
cd "$(dirname "$0")"

WITH_SIDECAR=0
DEV=0
for arg in "$@"; do
  case "$arg" in
    --with-sidecar) WITH_SIDECAR=1 ;;
    --dev) DEV=1 ;;
    -h|--help) sed -n '3,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

# 1. Find Python >= 3.11
find_python() {
  for c in python3.11 python3 python; do
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null; then
      echo "$c"; return 0
    fi
  done
  return 1
}
PY=$(find_python) || { echo "ERROR: Python 3.11+ is required but was not found." >&2; exit 1; }
echo "==> Using $PY ($("$PY" --version 2>&1))"

# 2. OpenCV needs libGL on Linux (facecore depends on opencv-python)
if [ "$(uname -s)" = "Linux" ] && ! ldconfig -p 2>/dev/null | grep -q 'libGL\.so\.1'; then
  echo "==> NOTE: OpenCV needs libGL. If imports fail, run:"
  echo "         sudo apt-get update && sudo apt-get install -y libgl1 libglib2.0-0"
fi

# 3. venv
if [ ! -d venv ]; then
  echo "==> Creating venv"
  "$PY" -m venv venv
fi
# shellcheck disable=SC1091
. venv/bin/activate
python -m pip install --quiet --upgrade pip

# 4. Editable installs (facecore pulls numpy/opencv/onnxruntime/insightface — first run is slow)
echo "==> Installing facecore, ai_service, edge_client (editable)"
if [ "$DEV" -eq 1 ]; then
  pip install -e facecore -e "ai_service[dev]" -e edge_client
else
  pip install -e facecore -e ai_service -e edge_client
fi

# 5. .env with a generated secret (never committed — see .gitignore)
if [ ! -f .env ]; then
  echo "==> Creating .env with a generated AI_SERVICE_SECRET"
  SECRET=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
  cat > .env <<EOF
# AI service auth secret — MUST match Face Recognition Settings > Embedding Service Secret in Frappe.
AI_SERVICE_SECRET=$SECRET
# ai_service -> deepface sidecar base URL
AI_SERVICE_DEEPFACE_URL=http://localhost:5005/api/v1
EOF
else
  echo "==> .env already exists — leaving it untouched"
fi

# 6. Optional: DeepFace analytics sidecar
if [ "$WITH_SIDECAR" -eq 1 ]; then
  echo "==> Bringing up the DeepFace sidecar (Docker)"
  git submodule update --init vendor/deepface
  [ -f vendor/deepface/docker/.env ] || cp vendor/deepface/docker/.env.example vendor/deepface/docker/.env
  docker compose up -d
fi

# 7. Next steps
SECRET_VAL=$(grep -E '^AI_SERVICE_SECRET=' .env | cut -d= -f2-)
cat <<EOF

==> Done.

Run the AI service:
    make run
    # health check:  curl http://127.0.0.1:8080/health

In the Frappe face_attendance app, set Face Recognition Settings:
    Embedding Service URL    = http://localhost:8080
    Embedding Service Secret = $SECRET_VAL
EOF
