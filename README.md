# tb-facecore

Facial recognition biometric attendance for Frappe HRMS v16. Employees check in by looking at a camera — no cards, no PINs. Attendance records are created automatically via Frappe's native shift and auto-attendance pipeline.

This repository contains the AI/edge stack. The companion Frappe app lives at [TechbirdIT/tb-face_attendance](https://github.com/TechbirdIT/tb-face_attendance).

The system runs a **dual-engine architecture**: InsightFace for fast real-time recognition on the edge, and a DeepFace analytics sidecar (Docker) for server-side analysis (`/analyze` demographics). The two engines are deliberately separate — see [docs/dual-engine-architecture.md](docs/dual-engine-architecture.md).

> 🎞️ **Looking for the big picture?** Open the **[visual product overview / pitch deck](docs/pitch/index.html)** — a single self-contained page that walks through the end-to-end flow, features, architecture, use cases, install steps and roadmap (built for sharing with stakeholders and clients). See [docs/pitch/README.md](docs/pitch/README.md).

## How it works

HR uploads an employee photo in Frappe. The face is embedded as a 512-dimensional vector and stored against the employee record; an approval workflow gates which profiles sync to devices. Edge devices (kiosks, IP cameras) run a continuous recognition loop — when a face matches, a recognition event (with similarity and liveness scores) is posted to the `face_attendance` app, which creates the Employee Checkin server-side and keeps a full audit trail. Devices heartbeat on every sync tick; a scheduled job flags devices that go quiet. Frappe's shift engine derives IN/OUT and creates Attendance documents hourly.

```
                    ┌──────────────────────────┐
   HR uploads photo │  FRAPPE + face_attendance│
        ──────────► │  Face Profile + workflow │──► POST /embed, /analyze
                    │  Device registry, events │
                    │  Sync API + Settings     │
                    └──────────────────────────┘
                          ▲          ▲
       post_event +       │          │ pull approved
       heartbeat REST     │          │ embeddings
                    ┌─────┴──────────┴───────┐    ┌────────────────────────┐
                    │  edge_client (venv)    │    │ ai_service (FastAPI)    │
                    │  camera → facecore     │    │ /health /embed         │
                    │  → NumPy match         │    │ /analyze /verify-id    │
                    │  → debounce → event    │    └───────────┬────────────┘
                    └────────────────────────┘                │ proxy /analyze
                                                               ▼
                                                  ┌──────────────────────────┐
                                                  │ DeepFace sidecar (Docker) │
                                                  │ API + Weaviate + Postgres │
                                                  │ + MinIO  (analytics)      │
                                                  └──────────────────────────┘
```

Operators drive the edge from a single-port web console (`edge-console`): a
Start/Stop button, live annotated feeds from every camera, in-browser config
editing (hot-reloaded into the running engine), and on-demand emotion/race
analysis. Recognition events can be tagged with age and gender for free; emotion
and race are an optional, offline-only add-on.

## Components

| Package | Role |
|---------|------|
| `facecore` | Pure AI engine — SCRFD detection + ArcFace 512-d embedding + MiniFASNet liveness, plus free age/gender, distance metrics + thresholds, and image loaders / aligned crops. No I/O, no Frappe, no web. Optional `[demography]` extra adds emotion/race. |
| `ai_service` | FastAPI microservice wrapping facecore. Called by Frappe at enrollment and for AI inference (ID verification, analytics). Keeps InsightFace/DeepFace out of the bench. `POST /analyze` proxies to the DeepFace analytics sidecar (see [docs/deepface-sidecar.md](docs/deepface-sidecar.md)). |
| `edge_client` | Edge device app. Multi-camera capture → IoU tracker → liveness gate → NumPy cosine match → debounce → post recognition event (optionally tagged with age/gender). Heartbeat per sync tick. SQLite offline queue. Ships an operator console (`edge-console`) with Start/Stop, live annotated feeds, config editing, and on-demand emotion/race analysis. |
| [`tb-face_attendance`](https://github.com/TechbirdIT/tb-face_attendance) | Frappe app (v16, separate repo). Face profiles + approval workflow, edge device registry, recognition event audit trail, sync/event/heartbeat APIs, health jobs, role fixtures, employee self-service portal (`/face`) with webcam register, status, and rate-limited self-test. |

## Stack

| Concern | Choice |
|---------|--------|
| Detection + embedding | InsightFace `buffalo_l` (SCRFD + ArcFace r50) |
| Liveness | Silent-Face MiniFASNet (passive, no user interaction) |
| Matching | NumPy cosine similarity (sub-ms, no vector DB needed) |
| Runtime | ONNX Runtime — CPU on dev, CUDA-switchable on prod |
| Analytics | DeepFace fork as a Docker sidecar (Flask API + Weaviate + Postgres + MinIO) — emotion/age/gender/race, server-side |
| Ports | Frappe 8000 · ai_service 8080 · deepface API 5005 · Weaviate 8081 · MinIO 9000/9001 · Postgres 5432 |
| Python | 3.11 for AI stack |
| Camera | OpenCV — webcam and RTSP/IP cameras (Hikvision, Dahua/CP Plus, S.vision, any ONVIF; see `edge_client/README.md`) |
| Offline queue | SQLite — durable across edge restarts |

## Repository layout

```
tb-facecore/
├── facecore/                       # AI engine (shared lib): SCRFD + ArcFace + liveness
│   ├── src/facecore/
│   └── pyproject.toml              # optional [demography] extra (DeepFace/TF)
├── ai_service/                     # FastAPI gateway: /health /embed /analyze /verify-id
│   ├── src/ai_service/
│   ├── tests/
│   └── pyproject.toml              # [dev] extra: pytest, ruff, mypy
├── edge_client/                    # Edge client + operator console (edge-console)
│   ├── src/edge_client/
│   ├── config.example.yaml
│   └── pyproject.toml
├── docs/
│   ├── design/architecture.md          # Full architecture & design decisions
│   ├── how-to.md                       # Complete setup & operations guide
│   ├── dual-engine-architecture.md     # InsightFace edge + DeepFace sidecar
│   └── deepface-sidecar.md             # DeepFace analytics sidecar setup
├── scripts/                        # up.sh / verify.sh / down.sh (one-click bring-up)
├── vendor/deepface/                # DeepFace fork (git submodule, private)
├── docker-compose.yml              # Sidecar stack (Compose v2 include + weights volume)
├── install.sh                      # venv + editable installs + generated .env
├── Makefile                        # install / up / verify / down / test
├── .github/workflows/ci.yml        # pytest + ruff + mypy
└── models/                         # Downloaded AI models (gitignored, ~310MB)
```

## Setup

Full walkthrough — prerequisites, models, AI service, Frappe configuration,
enrollment, edge client (webcam and RTSP/IP cameras), local RTSP test rig,
troubleshooting, and production deployment — lives in
**[docs/how-to.md](docs/how-to.md)**.

Quickstart:

```bash
git clone --recurse-submodules https://github.com/TechbirdIT/tb-facecore
cd tb-facecore

./install.sh        # venv + facecore/ai_service/edge_client + generated .env secret
make up             # start sidecar + ai_service, warm models, verify health (prints ✅/❌)
make verify         # push a real face through /analyze and confirm demographics
```

`make up` prints the generated `AI_SERVICE_SECRET` to paste into Frappe. To run just the
AI service without the analytics sidecar, use `make run`. Full walkthrough — models, Frappe
configuration, enrollment, edge client (webcam/RTSP), production — in
[docs/how-to.md](docs/how-to.md). The DeepFace sidecar requires access to the private
`ekansh-tb/deepface` submodule; see [docs/deepface-sidecar.md](docs/deepface-sidecar.md).

## Security

- Edge communicates with Frappe via API key+secret scoped to the **"Face Edge Device"** role
- Edge posts recognition events; Employee Checkins are created server-side — the role cannot write checkins directly
- All edge endpoints (`get_face_data`, `post_event`, `heartbeat`) gated to Face Edge Device and System Manager roles
- Only **Approved** face profiles sync to devices; the raw embedding field is permlevel-restricted in Desk
- Every recognition is audited as a **Face Recognition Event** (scores, device, linked checkin); duplicates are rejected by a unique index
- Embeddings are one-way transforms — cannot reconstruct a face image from stored data
- Enrollment photos are stored optionally and can be deleted after embedding

## Testing

```bash
make test                                  # ai_service suite (pytest)

# full ai_service gate, exactly as CI runs it:
cd ai_service && ruff check . && mypy src && pytest

# other packages
cd facecore && pytest
cd edge_client && pytest
```

CI (`.github/workflows/ci.yml`) runs ruff, mypy, and pytest on every PR; CodeQL scans via the repository's default setup.

## Compatibility

| App | Version |
|-----|---------|
| Frappe | v16 |
| ERPNext | v16 |
| HRMS | v16 |

## License

MIT
