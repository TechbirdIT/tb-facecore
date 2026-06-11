# Face Attendance — Session Status & Continuation Plan

Working handoff so the conversation can be compacted and resumed. Last updated 2026-06-11.

---

## 0. TL;DR — where we are
A facial-recognition attendance system across two repos is well underway:
- **Server side (`tb-face_attendance` Frappe app)** — presence-session hours model is **built, tested, committed, and pushed**.
- **Edge side (`tb-facecore` repo)** — recognition engine + tracking + multi-camera are **built and committed locally**, but **NOT pushed** (no write access to `tb-facecore` yet).
- A **seeded Edge Console UI prototype** and a **real RTSP→HLS live-video preview** exist (uncommitted).
- Current open task: **"make the UI real"** (wire real video/events/controls into the console).

---

## 1. Repos, branches, push status
| Repo | Path | Branch | Remote | Pushed? |
|---|---|---|---|---|
| Frappe app | `/home/coldfire/projects/tb-face-bench/apps/face_attendance` | `martin-local` | `TechbirdIT/tb-face_attendance` (`upstream`) | ✅ **yes** |
| Edge/AI stack | `/home/coldfire/projects/tb-facecore-stack` | `martin-local` | `TechbirdIT/tb-facecore` (`origin`) | ❌ **no write access** |

> When `tb-facecore` write access lands: `cd tb-facecore-stack && git push -u origin martin-local`.

---

## 2. What's done

### Edge repo `tb-facecore` (`martin-local`, committed, NOT pushed)
- `7061992` feat(facecore): auto-download MiniFASNet liveness model (pinned SHA-256, from yakhyo release; matches liveness.py raw-0-255 / index-1 convention).
- `8c020d2` feat(edge_client): production-harden RTSP (socket timeout, FFmpeg backend, credential masking, config knobs).
- `050ede6` docs: roboflow/supervision integration analysis (deferred to later phase).
- `73ff479` feat(facecore): split `detect()` / `embed()` / `liveness()` out of `analyze()` (detect every frame, embed once per track). Parity vs analyze = cosine 1.0.
- `756118b` feat(edge_client): IoU tracker, recognize once per track (`tracker.py`).
- `38a14a5` fix: don't freeze unidentified tracks for reverify_seconds (fast acquisition).
- `944b141` fix: log "debounced" once per track.
- `79a0bcb` feat: two-phase acquisition backoff (fast lock-on for real faces; lingering unknowns stop embedding every frame).
- `7fc546e` docs: presence-sessions design (plain English, for non-technical reviewers).
- **UNCOMMITTED (Step 5 + UI):**
  - Multi-camera-in-one-config (threaded, shared models): `config.py` (`cameras`, `sighting_interval_seconds`), `capture.py` (`resolve_cameras`, threaded `run_capture`, `_camera_loop`), `store.py` (event_queue `edge_id` + migration), `sync.py` (per-item edge_id flush), `config.example.yaml`, tests. Validated offline (11 checks).
  - `edge_client/ui/face-edge-console.html` — seeded/simulated Edge Console prototype (React inline Babel; Start/Stop, live grid, recent events, config form). Renders cleanly (verified); interactions are standard React.
  - `edge_client/ui/face-edge-live.html` — REAL RTSP→HLS video preview (hls.js) in the tile chrome + demo overlay.
  - `edge_client/ui/rtsp-bridge.sh` — ffmpeg RTSP→HLS bridge + static server; self-healing (`-timeout 8000000` + retry loop).

### Frappe app `tb-face_attendance` (`martin-local`, committed + PUSHED)
- `d00bc20` feat: presence sessions — `Area` + `Presence Session` doctypes, `presence.py` sessioniser (on Face Recognition Event after_insert) + `close_stale_sessions` scheduled job (every minute), `Face Edge Device.area` link, `session_gap_minutes` setting (12), `event_retention_days` default 0 = keep forever (+ retention.py fix), tests. Verified live on bench.
- `b2fb914` feat: per-employee cross-camera check-in cooldown (server-side enforcement of `punch_debounce_minutes`; events always kept, only HR check-in debounced). Verified live.
- `ed15684` feat: **Presence Hours** Script Report (hours per employee per area per day; from/to/employee/area filters; Duration display; "In Progress" flag). Verified live → HR-EMP-00001 / Floor 2 / 10m.

---

## 3. Environment & credentials (this machine)
- **Bench:** `/home/coldfire/projects/tb-face-bench`, site **`tbface.local`**, web port **8002**. Apps: frappe, erpnext, hrms, face_attendance (v16).
- **Bench is NOT running right now** (was stopped). Start with `cd tb-face-bench && bench start`. (System redis on 6379 is separate; bench uses 11002/13002 cache/queue, 9002 socketio.)
- **Edge AI stack:** `/home/coldfire/projects/tb-facecore-stack`, venv at `./venv` (Python 3.11). Models auto-download (buffalo_l + MiniFASNet).
- **Embedding service:** FastAPI on `127.0.0.1:8080` (enrollment only; NOT in the recognition hot path).
- **Edge service user:** `edge-001@tbface.local`, role *Face Edge Device*. API key/secret: `b3131f4b9033d51` : `830d1b34f0d2115`. Device record **edge-001** → Area **Floor 2**.
- **Self-serve employee:** user `martinmwangi5747@gmail.com` / temp pw `FaceServe@2026`; Employee **HR-EMP-00001** (Martin Mwangi), `attendance_device_id=HR-EMP-00001`, face enrolled + Approved.
- **Settings:** `session_gap_minutes=12`, `event_retention_days=0` (keep forever), `punch_debounce_minutes=2`.
- **Camera:** phone IP-cam at **`rtsp://192.168.1.68:8554`** (H.264 1080×1920 portrait + AAC). Drops when phone screen locks / app backgrounds.
- **Tooling present:** ffmpeg 7.1.1, ffprobe, vlc. No go2rtc/mediamtx. (So RTSP→browser uses **HLS via ffmpeg**.)
- **bashrc aliases:** `face-embed` (embedding service :8080), `face-edge` (edge client `--config edge_client/config.yaml --debug`).

---

## 4. Currently running background processes
- **RTSP→HLS bridge** for the live preview: `ffmpeg` (rtsp://192.168.1.68:8554 → `edge_client/ui/live/*.ts`) + `python -m http.server 8099` (serving `edge_client/ui/`).
  - View: `http://127.0.0.1:8099/face-edge-live.html`
  - Stop: `pkill -f ffmpeg ; pkill -f "http.server 8099"`

---

## 5. How to run things
```bash
# Frappe bench (server): http://localhost:8002
cd /home/coldfire/projects/tb-face-bench && bench start

# Embedding service (enrollment): http://127.0.0.1:8080
cd /home/coldfire/projects/tb-facecore-stack && source venv/bin/activate
uvicorn embedding_service.app:app --host 127.0.0.1 --port 8080      # or: face-embed

# Edge recognition client
edge-client --config edge_client/config.yaml --debug               # or: face-edge

# Live RTSP preview (phone must be streaming, screen on)
cd /home/coldfire/projects/tb-facecore-stack/edge_client/ui
./rtsp-bridge.sh "rtsp://192.168.1.68:8554"      # then open http://127.0.0.1:8099/face-edge-live.html

# Edge console prototype (seeded): open edge_client/ui/face-edge-console.html in a browser
# Tests (need dev extras): pip install -e "facecore[dev]" -e "edge_client[dev]" && pytest facecore/tests edge_client/tests -q
```

---

## 6. Decisions locked (with the team)
- **No HRMS IN/OUT alternation** for hours — it's unfair when a face briefly leaves frame. Use **presence sessions** instead.
- **Session gap = 12 minutes** (restroom-proof). Long gaps (lunch) are not counted.
- **Retain recognition events as long as possible** (security forensics: who/where/when) — `event_retention_days=0` = never purge.
- **"Present ≠ working"** is a supervisor concern — not modeled.
- **Viewers** of presence/hours: HR Manager + System Manager (employees see their own via `/face`).
- Cameras map to **Areas**; one console process can run **multiple cameras**; server-side **global cooldown** prevents cross-camera double check-ins.

---

## 7. Architecture notes (gotchas that bit us)
- `tb-facecore` is the **AI/edge stack only** (not a Frappe app). The Frappe app is the separate `tb-face_attendance` repo, installed in the bench.
- App package layout: `apps/face_attendance/face_attendance/` is the Python package (hooks.py, presence.py, jobs/, tests/); doctypes/reports live one level deeper under `.../face_attendance/face_attendance/{doctype,report}/`.
- Browsers can't play RTSP → must transcode (HLS via ffmpeg). `-rw_timeout` is invalid in ffmpeg 7.1; use **`-timeout`** (µs) for the RTSP socket timeout.
- Standalone Frappe scripts mis-resolve the bench path; run via `bench --site tbface.local execute <dotted.path>` or `bench console`.
- `pytest` is NOT installed in the edge venv (validated logic via direct execution instead).
- Browser-MCP screenshots time out on **live-video** pages (capture too heavy) — verify those by opening manually.

---

## 8. Next steps / open choices
1. **"Make the UI real"** (current ask) — phased:
   - **Layer A:** real HLS feeds (one bridge per camera) in the *actual* console grid. *(recommended next; no new backend)*
   - **Layer B:** console polls Frappe API for real recognition events / presence (read-only).
   - **Layer C:** add a small **control API** to `edge_client` (start/stop engine, status, read/write `config.yaml`) so Start/Stop and config are real. *(largest)*
   - **User has not yet chosen scope (A only vs full A→C).**
2. **Commit Step 5 + UI files** on edge `martin-local` (waiting on push access for remote).
3. **Push `tb-facecore`** once write access is granted (all commits + Step 5 + UI).
4. **Multi-frame confirmation** before posting — recommended for accuracy at 500 employees / 10-15 cameras (layers on the existing track state).
5. **Optional Step 6:** feed HRMS Attendance from presence sessions (only if payroll integration is needed).

---

## 9. Key files
- Edge: `tb-facecore-stack/edge_client/src/edge_client/{config,capture,tracker,store,sync,camera}.py`, `facecore/src/facecore/{analyzer,model_download}.py`.
- Edge UI: `tb-facecore-stack/edge_client/ui/{face-edge-console.html,face-edge-live.html,rtsp-bridge.sh}`.
- App: `apps/face_attendance/face_attendance/{presence.py, hooks.py, jobs/retention.py}`, doctypes `area`/`presence_session`, report `presence_hours`.
- Docs: `tb-facecore-stack/docs/{presence-and-hours-design.md, supervision-integration.md, this file}`.
