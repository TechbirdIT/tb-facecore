# Dual-Engine Architecture & the `saurabh-test-dev` Branch

> **Branch status:** `saurabh-test-dev` is an **experimental staging branch**. It is where larger, in-progress changes are built and proven in small, reviewable chunks before they are proposed to `main` via PR. Anyone may pull from it to develop on top, but it is not the source of truth — `main` is. Treat anything here as "proposed, not final."

This document explains the architecture this branch introduces and the work completed so far. For day-to-day operation of the analytics sidecar, see [deepface-sidecar.md](deepface-sidecar.md). For the canonical system design, see [design/architecture.md](design/architecture.md).

---

## The idea: two engines, two jobs

Face AI in this platform now runs on **two separate engines**, each matched to a different job and service-level need. They are deliberately **not** merged into one process.

| | InsightFace (ArcFace) | DeepFace (fork) |
|---|---|---|
| **Lives in** | `ai_service` (in-process) | a Docker **sidecar** stack |
| **Endpoint** | `POST /embed` | `POST /analyze` |
| **Job** | "Who is this, right now?" — real-time recognition for attendance | "What can we learn from this face?" — demographics & analytics |
| **Latency target** | low (edge, sub-second) | relaxed (server, async/batch) |
| **Engine** | ONNX / SCRFD + ArcFace | TensorFlow / DeepFace models |

**Why separate, not combined:** the two have opposite performance profiles (fast-and-light vs heavy-and-slow), incompatible runtimes (ONNX vs TensorFlow loaded in one process fight over memory/CUDA), and embeddings that are **not cross-comparable** (an InsightFace vector and a DeepFace vector describe the same face differently and must never be matched against each other). Keeping them apart lets each scale and fail independently. `ai_service` is the single front door; it routes each request to the right engine.

```
                         ┌─────────────────────────────┐
   HR uploads photo ───► │  FRAPPE + face_attendance   │
                         │  profiles, workflow, events │
                         └──────────────┬──────────────┘
                          /embed        │        /analyze
                  (real-time recog)     │   (demographics, async)
                         ┌──────────────▼──────────────┐
                         │          ai_service          │  ◄── single AI gateway
                         │   FastAPI: /embed /analyze   │
                         └───────┬──────────────┬───────┘
              InsightFace (in-process)          │ HTTP proxy
              SCRFD + ArcFace, fast             ▼
                                    ┌───────────────────────────┐
                                    │   DeepFace sidecar (Docker)│
                                    │  Flask API + Weaviate +    │
                                    │  Postgres + MinIO + UI     │
                                    └───────────────────────────┘
```

---

## What this branch has delivered

### 1. `ai_service` consolidation
The former standalone `embedding_service` was folded into a single unified service, `ai_service`. It is the one HTTP gateway for all face AI: `/health`, `/embed`, `/verify-id` (stub), `/analyze`. This stops package sprawl — one service to deploy, secure, and call, rather than a growing set of per-feature microservices.

### 2. DeepFace analytics sidecar
- The `ekansh-tb/deepface` platform (a full Flask API backed by Weaviate, Postgres, MinIO, plus a Next.js UI) is vendored as a **git submodule** at `vendor/deepface`, pinned to a fixed commit on branch `Develop`.
- A top-level `docker-compose.yml` brings the whole sidecar stack up with one command (Compose v2 `include`).
- `ai_service` reaches it through an async HTTP client (`ai_service/clients/deepface.py`) using `AI_SERVICE_DEEPFACE_URL`.
- `POST /analyze` now forwards an uploaded image to the sidecar and returns demographics (age / gender / emotion / race). It was previously a 501 stub.

### 3. Hardening & CI
- `/analyze` enforces the same `X-Secret` auth gate as `/embed` and rejects non-image uploads.
- GitHub Actions runs pytest on every PR (installs `facecore` + `ai_service`); CodeQL scanning is handled by the repository's default setup.
- Test suite: **23 passing**.

---

## Running it locally

```bash
# 1. Get the sidecar source (private submodule — team access required)
git submodule update --init vendor/deepface       # or clone with --recurse-submodules

# 2. Configure and start the DeepFace sidecar stack
cp vendor/deepface/docker/.env.example vendor/deepface/docker/.env
docker compose up -d

# 3. Run ai_service (separately, via uvicorn) — see docs/how-to.md
```

`ai_service` talks to the sidecar at `http://localhost:5005/api/v1` by default. Full operator detail in [deepface-sidecar.md](deepface-sidecar.md).

---

## Not done yet (deferred to later increments)

- `/register` + `/search` — store faces in Weaviate and do vector similarity search (the VIP / open-space recognition use case).
- Frappe `Vision Task` + `Vision Service Settings` DocTypes — log every inference, configure the sidecar from Frappe.
- Frappe field rename `embedding_service_url` → `ai_service_url` (needs a migration patch).
- Authenticating the `ai_service` → DeepFace hop (the fork ships an auth blueprint; this increment trusts the Compose network).
