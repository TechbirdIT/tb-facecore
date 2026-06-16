# tb-facecore

Facial recognition biometric attendance for Frappe HRMS v16. Employees check in by looking at a camera — no cards, no PINs. Attendance records are created automatically via Frappe's native shift and auto-attendance pipeline.

This repository contains the AI/edge stack. The companion Frappe app lives at [TechbirdIT/tb-face_attendance](https://github.com/TechbirdIT/tb-face_attendance).

## How it works

HR uploads an employee photo in Frappe. The face is embedded as a 512-dimensional vector and stored against the employee record; an approval workflow gates which profiles sync to devices. Edge devices (kiosks, IP cameras) run a continuous recognition loop — when a face matches, a recognition event (with similarity and liveness scores) is posted to the `face_attendance` app, which creates the Employee Checkin server-side and keeps a full audit trail. Devices heartbeat on every sync tick; a scheduled job flags devices that go quiet. Frappe's shift engine derives IN/OUT and creates Attendance documents hourly.

```
                    ┌──────────────────────────┐
   HR uploads photo │  FRAPPE + face_attendance│
        ──────────► │  Face Profile + workflow │──► POST /embed
                    │  Device registry, events │
                    │  Sync API + Settings     │
                    └──────────────────────────┘
                          ▲          ▲
       post_event +       │          │ pull approved
       heartbeat REST     │          │ embeddings
                    ┌─────┴──────────┴───────┐    ┌──────────────────┐
                    │  edge_client (venv)    │    │ embedding_service │
                    │  camera → facecore     │    │ FastAPI           │
                    │  → NumPy match         │    │ POST /embed       │
                    │  → debounce → event    │    └──────────────────┘
                    └────────────────────────┘
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
| `embedding_service` | FastAPI microservice wrapping facecore. Called by Frappe at enrollment. Keeps InsightFace out of the bench. |
| `edge_client` | Edge device app. Multi-camera capture → IoU tracker → liveness gate → NumPy cosine match → debounce → post recognition event (optionally tagged with age/gender). Heartbeat per sync tick. SQLite offline queue. Ships an operator console (`edge-console`) with Start/Stop, live annotated feeds, config editing, and on-demand emotion/race analysis. |
| [`tb-face_attendance`](https://github.com/TechbirdIT/tb-face_attendance) | Frappe app (v16, separate repo). Face profiles + approval workflow, edge device registry, recognition event audit trail, sync/event/heartbeat APIs, health jobs, role fixtures, employee self-service portal (`/face`) with webcam register, status, and rate-limited self-test. |

## Stack

| Concern | Choice |
|---------|--------|
| Detection + embedding | InsightFace `buffalo_l` (SCRFD + ArcFace r50) |
| Liveness | Silent-Face MiniFASNet (passive, no user interaction) |
| Matching | NumPy cosine similarity (sub-ms, no vector DB needed) |
| Runtime | ONNX Runtime — CPU on dev, CUDA-switchable on prod |
| Python | 3.11 for AI stack |
| Camera | OpenCV — webcam and RTSP/IP cameras (Hikvision, Dahua/CP Plus, S.vision, any ONVIF; see `edge_client/README.md`) |
| Offline queue | SQLite — durable across edge restarts |

## Repository layout

```
tb-facecore/
├── facecore/                   # AI engine (shared lib)
│   ├── src/facecore/
│   └── pyproject.toml
├── embedding_service/          # FastAPI enrollment service
│   ├── src/embedding_service/
│   └── pyproject.toml
├── edge_client/                # Edge device client
│   ├── src/edge_client/
│   ├── config.example.yaml
│   └── pyproject.toml
├── docs/
│   ├── design/architecture.md  # Full architecture & design decisions
│   └── how-to.md               # Complete setup & operations guide
└── models/                     # Downloaded AI models (gitignored, ~310MB)
```

## Setup

Full walkthrough — prerequisites, models, embedding service, Frappe configuration,
enrollment, edge client (webcam and RTSP/IP cameras), local RTSP test rig,
troubleshooting, and production deployment — lives in
**[docs/how-to.md](docs/how-to.md)**.

Quickstart (AI stack only):

```bash
git clone https://github.com/TechbirdIT/tb-facecore
cd tb-facecore

python3.11 -m venv venv
source venv/bin/activate

pip install -e facecore/
pip install -e embedding_service/
pip install -e edge_client/
```

Then follow [docs/how-to.md](docs/how-to.md) from section 4 (models) onward.

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
# facecore
cd facecore && pytest

# embedding_service
cd embedding_service && pytest

# edge_client
cd edge_client && pytest
```

## Compatibility

| App | Version |
|-----|---------|
| Frappe | v16 |
| ERPNext | v16 |
| HRMS | v16 |

## License

MIT
