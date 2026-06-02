# Face Recognition Attendance for Frappe HRMS

Production-ready facial recognition biometric attendance system integrated into Frappe HRMS v16+.

Heavy AI is decoupled from the Frappe bench. The architecture supports single-host POC (v1 on your Mac) and scales to many edge locations reporting to a central Frappe server without refactoring.

## Architecture

```
                    ┌─────────────────────────┐
   HR uploads photo │   FRAPPE (site1.local)  │
        ──────────► │  face_attendance app    │──┐ POST /embed (enrollment only)
                    │  • Employee Face Profile │  │
                    │  • sync API + settings  │  │
                    └─────────────────────────┘  ▼
                          ▲  ▲              ┌──────────────────────┐
        checkin REST API  │  │ pull         │ embedding_service     │
   (add_log_based_on_...) │  │ embeddings   │ FastAPI + facecore     │
                          │  │              └──────────────────────┘
                    ┌─────┴──┴───────────────┐
                    │  EDGE CLIENT (venv)     │
                    │  facecore in-process    │
                    │  camera→live→embed→     │
                    │  match(NumPy)→debounce  │
                    └─────────────────────────┘
```

- **`facecore`**: shared pure AI lib (InsightFace SCRFD + ArcFace + MiniFASNet liveness). No Frappe, no camera, no web. Typed, unit-testable.
- **`embedding_service`**: FastAPI. `POST /embed` — image → 512-d embedding + scores. The decoupling boundary.
- **`face_attendance`**: Frappe app (v16+). DocTypes, enrollment, sync API, settings. Calls embedding_service over HTTP. Zero InsightFace import.
- **`edge_client`**: venv app. Camera → liveness → match (NumPy cosine) → debounce → post check-in. Offline-resilient SQLite queue.

## Stack

- **Detect + embed**: InsightFace `buffalo_l` (SCRFD + ArcFace r50 → 512-d L2-normalized)
- **Liveness**: Silent-Face MiniFASNet (passive, no interaction)
- **Runtime**: ONNX Runtime. CPU on Mac; CUDA-capable on prod Linux
- **Python**: AI stack on 3.11 (insightface/onnxruntime wheels). Frappe app on bench's 3.14.
- **Capture**: OpenCV (Mac webcam now, RTSP/IP cameras later)
- **Offline queue**: SQLite on edge (durable across restarts)

## Design Document

See [`docs/design/architecture.md`](docs/design/architecture.md) for the full design spec. Includes:
- Locked architectural decisions
- Component responsibilities & data flows
- Frappe integration details (verified against installed v16)
- Security & permissions model
- Testing strategy
- Build phases

## Layout

```
facerecog/
├── facecore/                       # shared AI lib (src layout)
│   ├── pyproject.toml
│   ├── src/facecore/
│   ├── tests/
│   └── README.md
├── embedding_service/              # FastAPI app
│   ├── pyproject.toml
│   ├── src/embedding_service/
│   ├── tests/
│   └── README.md
├── edge_client/                    # edge device app
│   ├── pyproject.toml
│   ├── src/edge_client/
│   ├── tests/
│   ├── config.example.yaml
│   └── README.md
├── docs/
│   └── superpowers/specs/
│       └── 2026-06-02-facerecog-hrms-design.md
├── models/                         # downloaded AI models (.gitignored)
├── .gitignore
├── CLAUDE.md                       # project guidelines
├── LICENSE
└── README.md                       (this file)

frappe-bench/apps/face_attendance/  # Frappe app (created via `bench new-app`)
├── face_attendance/
│   ├── hooks.py
│   ├── fixtures/
│   │   ├── role.json              # "Face Edge Device" role
│   │   └── custom_docperm.json    # grants on Employee Checkin
│   ├── modules/
│   │   └── Face Attendance/
│   │       ├── doctype/
│   │       │   ├── Employee Face Profile/
│   │       │   └── Face Recognition Settings/
│   │       └── api.py             # get_face_data + helpers
│   └── tests/
└── README.md
```

## Getting Started (v1 — POC on Mac)

### Prerequisites
- Frappe bench v16+ already running locally (✅ you have this)
- Python 3.11 & 3.14 (✅ installed)
- OpenCV, ONNX Runtime (installed via pip in venv)
- Webcam on your Mac

### Build Order

1. **`facecore`**: Pure AI engine + tests
2. **`embedding_service`**: FastAPI wrapper + tests
3. **`face_attendance`**: Frappe app + tests
4. **`edge_client`**: Edge loop + tests
5. **E2E**: Enroll real face → recognize via edge → Frappe check-in → Attendance doc

### First Run

```bash
# Download models (once, ~300MB)
python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l')"

# Enroll an employee
# (open Frappe → Employee → create Face Profile → upload photo)

# Run edge client
python -m edge_client.main --config config.yaml

# Open webcam → recognize face → see Employee Checkin created
# After ~1h, Frappe's hourly scheduler generates Attendance doc
```

## Security

- **Edge → Frappe**: API key+secret bound to scoped "Face Edge Device" role (create+read on Employee Checkin only).
- **Biometric data**: Store only derived embeddings (not reversible to face). Photos optional/deletable.
- **HTTPS in production** (localhost/private net for v1).
- **Sync endpoint gated**: `frappe.only_for(["Face Edge Device", "System Manager"])`

See spec §8 for full security model.

## Permissions & Compliance

Enrollment, attendance, and biometric retention are organizational policy decisions — flagged but not automated in v1. Consider:
- Consent forms & retention period
- Who can enroll employees (HR only? Self-serve?)
- Who can view face data (HR manager? System admin? Audit trail?)
- Deletion-on-termination workflow

## Testing

- **Unit**: facecore (face matching, liveness), embedding_service (API), edge_client (debounce, offline queue)
- **Integration**: face_attendance (enrollment, sync, permissions)
- **E2E on Mac**: enroll real face → edge recognizes → Frappe check-in → Attendance

All tests use fixtures (small committed images for same-person/different/spoofed detection).

## Implementation Plan

See [`docs/design/`](docs/design/) for architecture and the detailed implementation plan.

## Version Compatibility

- **Frappe**: v16+ (v15 possible with minor hooks adjustments)
- **ERPNext**: v16+ (used only for Employee, Attendance DocTypes — no customizations)
- **HRMS**: v16+

## Development

### Local Setup

```bash
# Clone this repo
git clone <repo>
cd facerecog

# Create venv for AI stack (Python 3.11)
python3.11 -m venv venv
source venv/bin/activate

# Install all dev dependencies
pip install -e ".[dev]"  # from project's pyproject.toml (TBD)
```

### Code Style

- **Type hints** on all public signatures
- **Black** for formatting (88 char line)
- **Ruff** for linting
- **Mypy** for type checking
- **Pytest** for testing

```bash
make format   # black + isort
make lint     # ruff + mypy
make test     # pytest
```

(Makefiles TBD — see build phase docs)

## Known Limitations & Future Work

- **v1 scope**: single embedding per employee; multi-shot enrollment (average vectors) is phase 2
- **Real-time dashboards**: not supported (Frappe's auto-attendance runs hourly)
- **GPU**: v1 CPU only; CUDA support is a config flag for prod edges
- **Multi-site**: architecture ready; v1 enroll happens on one Frappe site

## License

(TBD — recommend MIT for open-source internal use, or proprietary if not shared)

## Authors

- Saurabh (product & architecture)
- Claude (brainstorming & design validation)

## Next Steps

1. **Approval**: User reviews this README & project structure
2. **Implementation Plan**: Brainstorming → writing-plans skill → detailed step-by-step
3. **Scaffold code**: Generate pyproject.toml, __init__.py, test fixtures
4. **Build phase 1**: facecore + tests

---

*Design finalized 2026-06-02. Validated against installed Frappe v16 code.*
