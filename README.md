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

## Components

| Package | Role |
|---------|------|
| `facecore` | Pure AI engine — SCRFD detection + ArcFace 512-d embedding + MiniFASNet liveness. No I/O, no Frappe, no web. |
| `embedding_service` | FastAPI microservice wrapping facecore. Called by Frappe at enrollment. Keeps InsightFace out of the bench. |
| `edge_client` | Edge device app. Camera → liveness gate → NumPy cosine match → debounce → post recognition event. Heartbeat per sync tick. SQLite offline queue. |
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
│   └── operations.md           # Operator guide
└── models/                     # Downloaded AI models (gitignored, ~310MB)
```

## Setup

### Requirements

- Frappe bench v16 with ERPNext + HRMS and [tb-face_attendance](https://github.com/TechbirdIT/tb-face_attendance) installed
- Python 3.11 (AI stack venv)
- Webcam or RTSP IP camera

### Install AI stack

```bash
git clone https://github.com/TechbirdIT/tb-facecore
cd tb-facecore

python3.11 -m venv venv
source venv/bin/activate

pip install -e facecore/
pip install -e embedding_service/
pip install -e edge_client/
```

### Install Frappe app

```bash
cd ~/frappe-bench
bench get-app https://github.com/TechbirdIT/tb-face_attendance
bench --site site1.localhost install-app face_attendance
bench --site site1.localhost migrate
```

### Download models (once, ~310 MB)

```bash
python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l').prepare(ctx_id=0)"
```

### Start embedding service

```bash
export EMBEDDING_SERVICE_SECRET=<secret>   # must match Face Recognition Settings
uvicorn embedding_service.app:app --host 127.0.0.1 --port 8080
```

### Configure edge client

```bash
cp edge_client/config.example.yaml config.yaml
# Edit: frappe url, api_key, api_secret, camera_source
```

### Run edge client

```bash
python -m edge_client.main --config config.yaml
```

## Enrollment

Two paths:

**Self-service (employee portal at `/face`):** employees with a linked User account capture their face via webcam, submit for approval, track status, and run a webcam self-test once approved.

**HR-managed (Desk):**
1. Open Frappe → HR → Employee → open an employee record
2. Set **Attendance Device ID** (unique string, e.g. `EMP-001`)
3. Open **Employee Face Profile** → link employee → upload clear front-facing photo → save
4. Frappe calls embedding service, stores 512-d vector

Either way, approve the profile (**Face Profile Approval** workflow) — only Approved profiles sync to edge devices. Tip: enroll with a photo from the device that will do the recognizing — phone photos against a webcam cost ~0.1 similarity.

## Frappe configuration

1. Open **Shift Type** → enable **Auto Attendance**
2. Set **Process Attendance After** to today
3. Assign employees to a shift (Shift Assignment or Employee default shift)
4. Add the **"Face Edge Device"** role to the API user (created via HR → API Access)
5. Create a **Face Edge Device** record whose Device ID matches `edge.id` in the client config — events and heartbeats from unregistered devices are rejected

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
