# Face Recognition Attendance for Frappe HRMS — Design Spec

**Date:** 2026-06-02
**Status:** Approved (brainstorming)
**Author:** Saurabh + Claude

---

## 1. Goal

Production-ready facial-recognition biometric attendance integrated into Frappe HRMS,
relying on Frappe's **native** attendance pipeline (no customized attendance logic).
Heavy AI is decoupled from the Frappe bench. v1 runs entirely on a single Mac;
the architecture supports the end goal of many edge locations reporting to a
central Frappe server **without a later refactor**.

### Locked decisions
- **Matching:** in-memory NumPy cosine similarity. No vector DB (Qdrant/Milvus dropped
  as YAGNI at HRMS scale — brute-force over a 512-d matrix is sub-ms up to ~50k faces,
  and each edge only holds its own site's faces).
- **Liveness:** passive single-camera anti-spoof (Silent-Face MiniFASNet). No user interaction.
- **Enrollment:** Frappe-native photo upload; embedding computed by an external service.
- **Frappe never imports InsightFace.** It calls a small embedding microservice over HTTP.
- **Capture:** OpenCV (`cv2.VideoCapture`) — supports Mac webcam now and RTSP/IP cameras later.
- **Offline queue:** SQLite on the edge (durable across restarts).

### Non-goals (v1)
- Multi-shot / averaged enrollment embeddings (documented future extension).
- Real-time attendance dashboards (Frappe's native worker is hourly — see §4).
- GPU acceleration on the Mac (CPU only; CUDA is a prod-edge config switch).
- Active liveness challenges (blink/turn).

---

## 2. Architecture (Approach A)

```
                    ┌─────────────────────────┐
   HR uploads photo │   FRAPPE (site1.local)  │
        ──────────► │  face_attendance app    │
                    │  • Employee Face Profile │──┐ POST /embed (enrollment only)
                    │  • sync API  • settings  │  │
                    └─────────────────────────┘  ▼
                          ▲  ▲              ┌──────────────────────┐
        checkin REST API  │  │ pull         │ embedding_service     │
   (add_log_based_on_...) │  │ embeddings   │ FastAPI + facecore     │
                          │  │              └──────────────────────┘
                    ┌─────┴──┴───────────────┐
                    │  EDGE CLIENT (venv)     │   facecore = shared lib:
                    │  facecore in-process    │     SCRFD detect + ArcFace 512-d
                    │  camera→live→embed→     │     embed + MiniFASNet liveness.
                    │  match(NumPy)→debounce  │     Pure, typed, no Frappe/camera/web.
                    └─────────────────────────┘
```

### Components

| Unit | Location | Imports InsightFace | Responsibility |
|------|----------|:--:|----------------|
| `facecore` | `facerecog/facecore/` | yes | Pure AI engine. `analyze(image) -> list[DetectedFace]`. No I/O. |
| `embedding_service` | `facerecog/embedding_service/` | via facecore | `POST /embed`: image → embedding + scores. Decoupling boundary. |
| `face_attendance` | `frappe-bench/apps/face_attendance/` | **no** | Frappe app: enrollment DocTypes, sync API, settings. HTTP-calls the service. |
| `edge_client` | `facerecog/edge_client/` | via facecore | Camera → liveness → embed → match → debounce → post check-in. Offline-resilient. |

`facecore` is the single shared dependency of `embedding_service` and `edge_client`.

---

## 3. Models & stack

- **Detect + embed:** InsightFace `buffalo_l` pack — SCRFD detector + ArcFace r50 →
  512-dim L2-normalized embedding. Auto-downloads (~300 MB) on first run.
- **Liveness:** Silent-Face MiniFASNet (ONNX) → spoof probability. Passive, CPU-friendly.
  Model files fetched to a local `models/` dir (documented download step).
- **Runtime:** ONNX Runtime. `CPUExecutionProvider` on the Mac;
  `CUDAExecutionProvider` on prod Linux edges (selected via config).
- **Python split:**
  - AI stack (`facecore`, `embedding_service`, `edge_client`): **Python 3.11** venv
    (insightface + onnxruntime have reliable 3.11 wheels; 3.14 does not).
  - `face_attendance`: runs in the bench's Python 3.14 — no AI deps, only `requests`.

---

## 4. Native Frappe integration (verified against installed v16)

All integration points confirmed present in the installed HRMS/ERPNext v16 code:

- **Check-in endpoint:** `hrms.hr.doctype.employee_checkin.employee_checkin.add_log_based_on_employee_field`
  Signature: `(employee_field_value, timestamp, device_id=None, log_type=None,
  skip_auto_attendance=0, employee_fieldname="attendance_device_id", latitude=None, longitude=None)`.
- **Mapping field:** `attendance_device_id` on Employee (ERPNext core).
- **Auto-attendance:** `enable_auto_attendance` flag on Shift Type;
  worker `process_auto_attendance_for_all_shifts`.

**Timing constraint (must be documented for users):** check-ins post **instantly** via the
API, but `process_auto_attendance` runs on the **hourly** (`hourly_long`) scheduler hook,
gated per Shift Type by `process_attendance_after` and `last_sync_of_checkin`. So
`Attendance` documents appear up to ~1h after check-in. This is the accepted cost of
staying native. Acceptable for payroll; not a live dashboard.

**Direction:** the edge **omits `log_type`** so Frappe's native logic derives IN/OUT
from the employee's shift rules.

---

## 5. Frappe data model (`face_attendance`)

### DocType: Employee Face Profile
| Field | Type | Notes |
|-------|------|-------|
| `employee` | Link (Employee), unique | one profile per employee (v1) |
| `embedding` | Long Text | JSON array of 512 floats (L2-normalized) |
| `model_version` | Data | e.g. `buffalo_l` — guards against cross-model mismatch |
| `enrollment_image` | Attach Image | optional retention; deletable |
| `det_score` | Float | detector confidence at enrollment (gated) |
| `liveness_score` | Float | informational only; NOT gated at enrollment (see §5 logic) |
| `enrolled_on` | Datetime | |

`modified` (standard Frappe field) drives incremental sync.

**Naming:** `autoname = "field:employee"` (employee is unique → profile name = employee ID).

**App dependencies:** `required_apps = ["frappe", "erpnext", "hrms"]` in `hooks.py`.
Dependency direction: frappe → erpnext → hrms → face_attendance (no cycles).

### Single DocType: Face Recognition Settings
| Field | Type | Default |
|-------|------|---------|
| `embedding_service_url` | Data | `http://localhost:8080` |
| `embedding_service_secret` | Password | — |
| `match_threshold` | Float | 0.45 (cosine, tune empirically) |
| `liveness_threshold` | Float | 0.60 |
| `min_det_score` | Float | 0.50 |
| `punch_debounce_minutes` | Int | 2 |

### Server logic
- Enrollment runs in the Employee Face Profile **controller `validate()`** (own DocType →
  controller class, never `doc_events`; `validate` is the idiomatic hook for field
  population + `frappe.throw`). Guard with `self.has_value_changed("enrollment_image")` so
  it only re-embeds when the image actually changes.
- If a new `enrollment_image` is attached, read the file bytes and `POST` them to
  `embedding_service /embed`. Validate the response: exactly one face and
  `det_score >= min_det_score`. **Liveness is NOT gated at enrollment** — an uploaded
  enrollment photo is inherently a 2D image and a passive anti-spoof model would reject
  every one. Liveness is enforced only on the live edge path (§6). The service may still
  return `liveness_score`; it is stored as informational only.
  Store the returned embedding + det_score + `model_version`. **Never imports InsightFace.**
  The HTTP call uses a hard timeout (default 10s). On failure: `frappe.log_error(
  frappe.get_traceback(), "face_attendance.enroll")` then `frappe.throw` a generic message
  (log internals, never leak them to the client).
- Validate the linked Employee has a non-blank `attendance_device_id` (core enforces its
  uniqueness; we only guard against blank).
- On failure (service down/timeout, no/multi/low-quality face, blank device id):
  `frappe.throw` a clear message; **no half-saved profile**.

### Model-version drift
`model_version` guards against comparing embeddings produced by different models. The edge
filters synced embeddings to its active model version. When the embedding model changes,
affected Employee Face Profiles are flagged for **re-enrollment** (a report lists profiles
whose `model_version` ≠ the current service version). No automatic re-embedding in v1.

### Sync API
- Whitelisted, GET-only, type-annotated:
  `@frappe.whitelist(methods=["GET"])  def get_face_data(site: str | None = None, since: str | None = None)`.
- **Authorization gate (security-critical):** first line is
  `frappe.only_for(["Face Edge Device", "System Manager"])`. `@frappe.whitelist()` only
  verifies login — without this gate any logged-in user could pull biometric embeddings.
- Returns `[{attendance_device_id, employee, embedding, model_version, modified}]`.
- Incremental: `modified > since`. Filterable by site/branch (each edge pulls only its
  location's faces). v1 returns all. Uses `frappe.get_all` (trusted-service query, justified
  by the explicit role gate above).
- `attendance_device_id` is read from the linked Employee. Employees missing it are
  excluded and surfaced in a validation report (the edge cannot check them in otherwise).

---

## 6. Edge client internals

- **Sync worker:** every `sync_interval`, GET `get_face_data(since=last_sync)` → upsert into
  a local SQLite cache → rebuild a normalized `N×512 float32` matrix + parallel
  `attendance_device_id` array. On sync failure, keep the last-good matrix.
- **Capture loop:** `cv2.VideoCapture(camera_index)` → frame → `facecore.analyze` →
  for each face: liveness gate (`>= liveness_threshold`) → `cosine = matrix @ vec` →
  `argmax` → if `>= match_threshold` → candidate.
- **Debounce:** per `attendance_device_id`, suppress repeat punches within
  `debounce_minutes` (in-memory last-punch map). Prevents native-endpoint check-in flooding.
- **Check-in dispatch:** `POST add_log_based_on_employee_field` with
  `employee_field_value=<attendance_device_id>`, `timestamp=<now ISO>`, `device_id=<edge_id>`,
  **`log_type` omitted**. Auth via Frappe API key/secret.
- **Offline queue (SQLite):** on POST failure → enqueue with the **original timestamp** →
  background flush on reconnect. Enqueue-once to avoid duplicate storms; durable across restarts.
- **Config (YAML/env):** `frappe_url`, `api_key`, `api_secret`, `edge_id`, `site`,
  `camera_index`, `sync_interval`. Thresholds pulled from Frappe Settings at sync.

---

## 7. Data flows

**Enrollment:** HR opens Employee Face Profile → links employee → uploads photo → save →
controller POSTs image bytes to `embedding_service` → validate → store 512-d vector + scores.

**Sync:** edge GETs `get_face_data(since)` → rebuilds local matrix.

**Recognition:** camera → `facecore.analyze` → liveness gate → NumPy match → debounce →
POST check-in → Frappe **Employee Checkin** created → hourly `process_auto_attendance` →
**Attendance** doc.

---

## 8. Security & compliance

- **Edge → Frappe:** Frappe API key+secret bound to a dedicated user with a scoped
  **"Face Edge Device"** role. **Not Administrator, not HR User.**
- **Required permission grant (verified against installed v16):** `Employee Checkin` core
  permissions grant `create` only to System Manager / HR Manager / HR User / Employee. The
  native check-in endpoint runs `doc.insert()` under the **caller's** permissions, so the
  edge user would hit a `PermissionError` without an explicit grant. `face_attendance`
  ships, via **filtered fixtures** in `hooks.py`, both:
  - the **`Role`** "Face Edge Device" — `{"dt": "Role", "filters": [["name", "=", "Face Edge Device"]]}`
  - a **`Custom DocPerm`** granting that role **create + read on Employee Checkin only**
    (least privilege) — `{"dt": "Custom DocPerm", "filters": [["role", "=", "Face Edge Device"]]}`.
    Custom DocPerm is the correct mechanism to add a role's permissions to an existing
    (HRMS) DocType without modifying its core JSON.
- The edge user needs **no `read` on Employee** — the native endpoint looks the employee up
  via `frappe.db.get_values()`, which bypasses permission checks. Least privilege holds.
- The `get_face_data` sync method enforces its own role gate (§5).
- Run `bench --site <site> migrate` after any `hooks.py`/fixture/DocType change.
- **embedding_service:** shared-secret header; bound to localhost (v1) / private network (prod);
  HTTPS in prod.
- **Biometric data:** store only **derived embeddings** (not reversible to a face image).
  Enrollment-photo retention optional/deletable. Consent + retention policy is an
  org-policy line item (flagged, not coded). HTTPS for embeddings in transit (prod).

---

## 9. Error handling

| Condition | Behavior |
|-----------|----------|
| Embedding service down at enrollment | save fails loud; no profile stored |
| No face / multiple faces / low det score | reject enrollment with message |
| Edge camera open fails | log + retry-open with backoff |
| Match below threshold | ignore (no punch) |
| Liveness below threshold (spoof) | log, no punch |
| Frappe unreachable at check-in | enqueue to SQLite; flush on reconnect |
| Sync failure | keep last-good matrix; retry next interval |

---

## 10. Testing strategy

- **facecore:** same-person pair → high cosine; different person → low; printed-photo
  fixture → low liveness. Small committed fixture images.
- **embedding_service:** FastAPI `TestClient` — single/multi/no-face, auth header.
- **face_attendance:** `FrappeTestCase` — enrollment controller (embedding service mocked),
  blank-`attendance_device_id` rejection, sync output shape + incremental `since` filter,
  and a **permission test asserting the "Face Edge Device" user CAN create an Employee
  Checkin** (proves the DocPerm fixture works) but cannot touch unrelated HR data.
- **edge_client:** matcher (synthetic vectors), debounce window, offline-queue flush,
  sync merge logic.
- **E2E on Mac:** enroll a real face via Frappe → run edge client vs webcam → assert an
  Employee Checkin row → `bench --site site1.localhost execute
  hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts` →
  assert an Attendance doc.

---

## 11. Repository layout

```
facerecog/
├── facecore/                       # shared AI lib (src layout, pyproject)
│   ├── pyproject.toml
│   └── src/facecore/
├── embedding_service/              # FastAPI app (depends on facecore)
│   ├── pyproject.toml
│   └── src/embedding_service/
├── edge_client/                    # edge app (depends on facecore)
│   ├── pyproject.toml
│   ├── config.example.yaml
│   └── src/edge_client/
├── docs/superpowers/specs/         # this spec
└── models/                         # downloaded liveness model (gitignored)

frappe-bench/apps/face_attendance/  # Frappe app (created via `bench new-app`)
```

The Frappe app must live under `frappe-bench/apps/` to install; the three AI/edge units
live in this repo. All four are developed together.

---

## 12. Python practices (per python-patterns)

- Type hints on all public signatures; `DetectedFace` as a `@dataclass` / `NamedTuple`.
- EAFP for I/O; specific exceptions with a small custom hierarchy
  (`FaceCoreError`, `EnrollmentError`, `EdgeSyncError`).
- Context managers for camera, DB, and file handles.
- `pyproject.toml` per unit; `ruff` + `mypy` + `pytest` configured.
- No mutable default args; `pathlib` for paths; f-strings; generators for frame streams.

---

## 13. Build phases (input to the implementation plan)

1. `facecore` + tests
2. `embedding_service` + tests
3. `face_attendance` Frappe app: `required_apps`, DocTypes (+ autoname), enrollment
   controller, sync API, "Face Edge Device" role + Custom DocPerm fixture on Employee
   Checkin (create+read), model-version re-enroll report + tests
4. `edge_client` (matcher, sync, capture, debounce, offline queue) + tests
5. E2E on Mac + operator docs (model download, enrollment, edge config, shift setup)
