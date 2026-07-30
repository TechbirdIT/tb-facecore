#!/usr/bin/env bash
# Start the facecore embedding service (POST /embed) for Perch face check-in.
# Perch's backend (tb_appe) calls this at Appe Settings -> embedding_service_url
# (default http://127.0.0.1:8080). Auth is off by default (localhost only); set
# EMBEDDING_SERVICE_SECRET to require the X-Secret header.
#
# Dev: run this, or add to the appe-bench Procfile so `bench start` launches it:
#   embedding_service: /home/coldfire/projects/tb-facecore-stack/run_embedding_service.sh
set -euo pipefail
cd "$(dirname "$0")"
HOST="${EMBEDDING_SERVICE_HOST:-127.0.0.1}"
PORT="${EMBEDDING_SERVICE_PORT:-8080}"
exec .venv/bin/python -m uvicorn embedding_service.app:app --host "$HOST" --port "$PORT"
