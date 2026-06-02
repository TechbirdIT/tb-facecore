# frappe-facecore

Facial recognition biometric attendance for Frappe HRMS v16. Employees check in by looking at a camera — no cards, no PINs. Attendance records are created automatically via Frappe's native shift and auto-attendance pipeline.

## How it works

HR uploads an employee photo in Frappe. The face is embedded as a 512-dimensional vector and stored against the employee record. Edge devices (kiosks, IP cameras) run a continuous recognition loop — when a face matches, a check-in is posted to Frappe via the native HRMS API. Frappe's shift engine derives IN/OUT and creates Attendance documents hourly.

```
                    ┌──────────────────────────┐
   HR uploads photo │  FRAPPE + face_attendance│
        ──────────► │  Employee Face Profile   │──► POST /embed
                    │  Sync API + Settings     │
                    └──────────────────────────┘
                          ▲          ▲
              check-in    │          │ pull embeddings
              REST API    │          │
                    ┌─────┴──────────┴───────┐    ┌──────────────────┐
                    │  edge_client (venv)    │    │ embedding_service │
                    │  camera → facecore     │    │ FastAPI           │
                    │  → NumPy match         │    │ POST /embed       │
                    │  → debounce → checkin  │    └──────────────────┘
                    └────────────────────────┘
```

## Components

| Package | Role |
|---------|------|
| `facecore` | Pure AI engine — SCRFD detection + ArcFace 512-d embedding + MiniFASNet liveness. No I/O, no Frappe, no web. |
| `embedding_service` | FastAPI microservice wrapping facecore. Called by Frappe at enrollment. Keeps InsightFace out of the bench. |
| `face_attendance` | Frappe app (v16). Employee Face Profile DocType, sync API, settings, role fixtures. |
| `edge_client` | Edge device app. Camera → liveness gate → NumPy cosine match → debounce → post check-in. SQLite offline queue. |

## Stack

| Concern | Choice |
|---------|--------|
| Detection + embedding | InsightFace `buffalo_l` (SCRFD + ArcFace r50) |
| Liveness | Silent-Face MiniFASNet (passive, no user interaction) |
| Matching | NumPy cosine similarity (sub-ms, no vector DB needed) |
| Runtime | ONNX Runtime — CPU on dev, CUDA-switchable on prod |
| Python | 3.11 for AI stack, 3.14 for Frappe bench |
| Camera | OpenCV — webcam and RTSP/IP cameras |
| Offline queue | SQLite — durable across edge restarts |

## Repository layout

```
frappe-facecore/
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
├── docs/design/
│   └── architecture.md         # Full architecture & design decisions
└── models/                     # Downloaded AI models (gitignored, ~310MB)

frappe-bench/apps/face_attendance/   # Frappe app (bench new-app)
├── hooks.py                         # required_apps, fixtures, scheduler
├── fixtures/                        # Role + Custom DocPerm exports
└── face_attendance/
    └── hr/doctype/
        ├── employee_face_profile/
        └── face_recognition_settings/
```

## Setup

### Requirements

- Frappe bench v16 with ERPNext + HRMS installed
- Python 3.11 (AI stack venv)
- Python 3.14 (Frappe bench, already present)
- macOS webcam or RTSP IP camera

### Install AI stack

```bash
git clone https://github.com/saurabh-awate96/frappe-facecore
cd frappe-facecore

python3.11 -m venv venv
source venv/bin/activate

pip install -e facecore/
pip install -e embedding_service/
pip install -e edge_client/
```

### Install Frappe app

```bash
cd ~/frappe-bench
bench get-app /path/to/frappe-facecore/face_attendance  # or GitHub URL
bench --site site1.localhost install-app face_attendance
bench --site site1.localhost migrate
```

### Download models (once, ~310 MB)

```bash
python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l').prepare(ctx_id=0)"
```

### Start embedding service

```bash
uvicorn embedding_service.app:app --host 127.0.0.1 --port 8080
```

### Configure edge client

```bash
cp edge_client/config.example.yaml config.yaml
# Edit: frappe url, api_key, api_secret, camera_index
```

### Run edge client

```bash
python -m edge_client.main --config config.yaml
```

## Enrollment

1. Open Frappe → HR → Employee → open an employee record
2. Set **Attendance Device ID** (unique string, e.g. `EMP-001`)
3. Open **Employee Face Profile** → link employee → upload clear front-facing photo → save
4. Frappe calls embedding service, stores 512-d vector

## Frappe configuration

1. Open **Shift Type** → enable **Auto Attendance**
2. Set **Process Attendance After** to today
3. Assign employees to a shift
4. Add the **"Face Edge Device"** role to the API user (created via HR → API Access)

## Security

- Edge communicates with Frappe via API key+secret scoped to the **"Face Edge Device"** role
- Role has create+read on Employee Checkin only — no other HR data access
- Sync endpoint (`get_face_data`) gated to Face Edge Device and System Manager roles
- Embeddings are one-way transforms — cannot reconstruct a face image from stored data
- Enrollment photos are stored optionally and can be deleted after embedding

## Testing

```bash
# facecore
cd facecore && pytest

# embedding_service
cd embedding_service && pytest

# face_attendance (requires bench)
bench --site site1.localhost run-tests --app face_attendance

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
