# How-To: Zero to Running Face Attendance

Complete walkthrough for getting the tb-facecore stack up and running — from a bare
machine to a production edge device recognizing faces against an RTSP camera and
creating attendance in Frappe HRMS.

Audience: developers and deployers. No prior knowledge of this project assumed;
basic command-line comfort is.

Sections 1–8 get a webcam-based dev setup running end-to-end. Sections 9–10 cover
IP/RTSP cameras (real and simulated). Sections 11–13 cover verification,
troubleshooting, and production deployment.

---

## 1. System overview

Two repositories, three processes:

| Piece | What | Where | Port |
|---|---|---|---|
| Frappe bench + [`tb-face_attendance`](https://github.com/TechbirdIT/tb-face_attendance) | DocTypes, sync/event/heartbeat APIs, approval workflow, employee portal (`/face`) | `~/frappe-bench`, site e.g. `site1.localhost` | 8000 |
| `ai_service` (this repo) | FastAPI wrapper around facecore; called by Frappe at enrollment to turn a photo into a 512-d vector | AI venv | 8080 |
| `edge_client` (this repo) | Runs on the edge device: camera → detect → liveness → match → post recognition event | AI venv, one per device | — |

```
                    ┌──────────────────────────┐
   HR uploads photo │  FRAPPE + face_attendance│
        ──────────► │  Face Profile + workflow │──► POST /embed (port 8080)
                    │  Device registry, events │
                    │  Sync API + Settings     │
                    └──────────────────────────┘
                          ▲          ▲
       post_event +       │          │ pull approved
       heartbeat REST     │          │ embeddings
                    ┌─────┴──────────┴───────┐    ┌──────────────────┐
                    │  edge_client (venv)    │    │ ai_service        │
                    │  camera → facecore     │    │ FastAPI           │
                    │  → NumPy match         │    │ POST /embed       │
                    │  → debounce → event    │    └──────────────────┘
                    └────────────────────────┘
```

Data flow, end to end:

1. Employee enrolls (photo via HR Desk or the `/face` self-service portal).
2. Frappe posts the photo to the AI service; the 512-d ArcFace vector is
   stored on the **Employee Face Profile**.
3. An HR Manager approves the profile (**Face Profile Approval** workflow).
   Only **Approved** profiles sync to devices.
4. The edge client pulls approved embeddings every `sync_interval` seconds and
   matches camera faces locally (NumPy cosine — no per-frame network hop).
5. On a match that passes the liveness gate and debounce window, the edge posts a
   **Face Recognition Event**; the server creates the **Employee Checkin**.
6. Frappe's native auto-attendance job converts checkins into **Attendance**
   documents hourly.

Two distinct secrets — don't mix them up:

- **AI service secret** (`EMBEDDING_SERVICE_SECRET` env var) — shared
  between Frappe and the AI service. Set in **Face Recognition Settings**.
- **Edge API key + secret** — Frappe API credentials for the edge client's user
  (role **Face Edge Device**). Go in the edge `config.yaml`.

## 2. Prerequisites

- **Python 3.11** for the AI stack (InsightFace/ONNX pin; newer may not work).
- **Frappe bench v16** with ERPNext v16 + HRMS v16, and the
  [`tb-face_attendance`](https://github.com/TechbirdIT/tb-face_attendance) app:

  ```bash
  cd ~/frappe-bench
  bench get-app https://github.com/TechbirdIT/tb-face_attendance
  bench --site site1.localhost install-app face_attendance
  bench --site site1.localhost migrate
  ```

- A camera: built-in/USB webcam for dev, or any RTSP-capable IP/CCTV camera for
  deployment (section 9). No camera at all also works — simulate one (section 10).
- ~1 GB disk for models and dependencies.

## 3. Install the AI stack

**Quick install (one command):**

```bash
git clone --recurse-submodules https://github.com/TechbirdIT/tb-facecore
cd tb-facecore
./install.sh            # venv + all three packages + generated .env secret
                        # --dev adds test tooling; --with-sidecar brings up DeepFace
```

Then `make run` starts the service on :8080. The script prints the generated
`AI_SERVICE_SECRET` to paste into Frappe (step 6). Manual steps below if you prefer:

```bash
git clone --recurse-submodules https://github.com/TechbirdIT/tb-facecore
cd tb-facecore

python3.11 -m venv venv
source venv/bin/activate

pip install -e facecore/
pip install -e ai_service/
pip install -e edge_client/
```

Verify:

```bash
python -c "import facecore, ai_service, edge_client; print('ok')"
```

## 4. Download models (once, ~310 MB)

**buffalo_l** (SCRFD detector + ArcFace r50 embedder) auto-downloads to
`~/.insightface/models` on first use:

```bash
python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l').prepare(ctx_id=-1)"
```

(`ctx_id=-1` = CPU. Use `ctx_id=0` on a CUDA machine.)

**MiniFASNet** (passive liveness / anti-spoofing) also auto-downloads. A pinned,
pre-converted ONNX (Silent-Face `2.7_80x80_MiniFASNetV2`, verified by SHA-256) is
fetched to `<repo>/models/minifasnet.onnx` the first time the analyzer starts. To
prefetch it explicitly during setup:

```bash
python -m facecore.model_download
```

`models/` is gitignored — each machine downloads its own copy on first use. To use
a custom liveness model instead, drop your own `minifasnet.onnx` at that path
(a pre-existing file is never overwritten); it must take a raw 0-255 BGR `1x3x80x80`
NCHW input and output 3 classes with index 1 = live.

## 5. Start the AI service

```bash
cd tb-facecore && source venv/bin/activate
export EMBEDDING_SERVICE_SECRET=<choose-a-secret>   # must match Face Recognition Settings (step 6)
uvicorn ai_service.app:app --host 127.0.0.1 --port 8080
```

Smoke-test:

```bash
curl http://127.0.0.1:8080/health    # {"status":"ok",...}
```

API surface (one endpoint):

- `POST /embed` — multipart `file` (jpg/png) + `X-Secret` header → 512-d
  embedding, `det_score`, `liveness_score`, `model_version`.
- `400` — no face / multiple faces / low detector score / invalid image.
- `401` — missing or wrong secret.

Performance: ~200–400 ms per image on CPU, ~2 s cold start (model load on first
request). A 10-minute Frappe health job pings `/health` and keeps it warm.

Bind to `127.0.0.1` (or a private interface) — only Frappe needs to reach it.

## 6. Configure Frappe

All in Desk on the Frappe site:

1. **Face Recognition Settings** (single DocType):
   - `embedding_service_url` = `http://localhost:8080`
   - `embedding_service_secret` = the value from step 5
   - keep default thresholds.
2. Create an **API user** for the edge fleet: assign the **"Face Edge Device"**
   role, generate **API key + secret** (User → Settings → API Access). These go
   in the edge `config.yaml` (step 8).
3. On each employee record, set a unique **Attendance Device ID**
   (e.g. `EMP-001`). Recognition events carry this ID.
4. **Shift Type**: enable **Auto Attendance**, set **Process Attendance After** =
   today, assign employees to the shift (Shift Assignment or default shift).
5. Create one **Face Edge Device** record per physical device. **Device ID must
   match `edge.id`** in that device's config — events and heartbeats from
   unregistered devices are rejected.

Security model: the Face Edge Device role can only call the three whitelisted
edge endpoints (`get_face_data`, `post_event`, `heartbeat`). Employee Checkins
are created server-side — the edge role never writes them directly.

## 7. Enroll a face

Two paths:

**Self-service** — employees with a linked User account (Employee role +
`Employee.user_id`) open `http://<site>/face`:
Register → webcam capture → Submit for Approval. They can re-capture while the
profile is Draft/Rejected, track status, and run a webcam self-test once
Approved (rate-limited 5/min).

**HR-managed** — HR → **Employee Face Profile** → New → link employee → upload a
clear front-facing photo → Save. On save, Frappe posts the image to the
AI service and stores the vector. Failures (service down, no/multiple
faces, low quality, blank Attendance Device ID) block the save with a message.

Either way, an HR Manager then approves via the **Face Profile Approval**
workflow. Only **Approved** profiles sync to devices.

> **Enroll from the camera that will do the recognizing.** Cross-device photos
> (phone photo vs. webcam recognition) cost ~0.1 cosine similarity — enough to
> push a genuine match under the threshold.

## 8. Run the edge client (webcam)

```bash
cd tb-facecore && source venv/bin/activate
cp edge_client/config.example.yaml config.yaml
```

Every key:

```yaml
frappe:
  url: "http://localhost:8000"     # bench URL
  site: "site1.localhost"          # site name
  api_key: "key_xxxx"              # from step 6.2
  api_secret: "secret_xxxx"

edge:
  id: "edge-001"        # MUST match a Face Edge Device record's Device ID
  camera_source: 0      # webcam index (0 = built-in) — or RTSP URL, see section 9
  sync_interval: 300    # seconds between embedding pulls / heartbeats / queue flushes

matching:
  threshold: 0.45           # cosine similarity [0..1]; raise = stricter
  liveness_threshold: 0.6   # MiniFASNet spoof gate; raise = stricter
  min_det_score: 0.5        # SCRFD detector confidence floor
  debounce_minutes: 2       # suppress repeat events per employee within N minutes

offline:
  db_path: "/var/lib/edge_client/queue.sqlite"   # offline event queue (durable)
```

`config.*.yaml` is gitignored — configs carry real API credentials. Keep it that way.

Run:

```bash
python -m edge_client.main --config config.yaml --debug
```

Startup sequence: load config → sync embeddings from Frappe (`get_face_data`) →
open camera → loop. Each loop iteration: capture frame → detect → liveness gate
→ cosine match → debounce → POST recognition event. Each sync tick: refresh
embeddings, flush the offline queue, heartbeat.

Logging is stderr-only — INFO by default, DEBUG with `--debug`. At DEBUG you'll
see per-frame matcher scores and the reason every frame was skipped (no face,
below threshold, liveness fail, debounced) — leave it on until the device is
proven, then drop to INFO.

Offline resilience: if Frappe is unreachable, events queue in local SQLite with
their original timestamps. The queue flushes on each sync tick — it stops at the
first connection failure and drops items the server rejects with 4xx. A unique
event index server-side makes queue drains idempotent. The queue survives
process restarts.

## 9. Edge client with an RTSP / IP camera

Set `edge.camera_source` to the camera's RTSP URL (a string) instead of a webcam
index. Any RTSP-capable camera works — effectively every CCTV/IP camera sold
today (ONVIF Profile S devices are RTSP underneath).

| Vendor | RTSP URL pattern |
|---|---|
| Hikvision (and OEM rebrands) | `rtsp://user:pass@<ip>:554/Streaming/Channels/102` |
| Dahua / CP Plus | `rtsp://user:pass@<ip>:554/cam/realmonitor?channel=1&subtype=1` |
| S.vision | `rtsp://<ip>/ch1_0.264` |
| Uniview | `rtsp://user:pass@<ip>:554/unicast/c1/s1/live` |
| Anything else | Camera web UI, or the [iSpy camera database](https://www.ispyconnect.com/cameras) |

Validate the URL before touching the edge client:

```bash
ffprobe "rtsp://user:pass@<ip>:554/Streaming/Channels/102"
# or open it in VLC: Media → Open Network Stream
```

### Use the sub-stream

Every dual-stream camera exposes a high-res main stream and a low-res sub-stream
(`102`, `subtype=1`, `s1` in the URLs above). **Use the sub-stream.** Face
detection doesn't need 4 MP; decoding the main stream burns CPU the inference
loop needs.

### Transport: TCP, forced

RTSP can run over UDP or TCP. UDP drops packets on congested networks and
crashes the FFmpeg decoder mid-stream. The edge client forces TCP by setting

```
OPENCV_FFMPEG_CAPTURE_OPTIONS=rtsp_transport;tcp
```

before the capture is constructed — automatically, whenever `camera_source`
starts with `rtsp`. It uses `setdefault`, so if you export that env var yourself
(e.g. to test UDP), your value wins.

### How the stream is consumed

A dedicated grabber thread reads the stream and keeps **only the latest frame**;
the inference loop consumes it when ready. Without this, RTSP frames queue in
the FFmpeg buffer while inference runs and the recognition lag grows without
bound. Practical effect: recognition always operates on a near-live frame, even
though inference (~150–300 ms/frame on CPU) is slower than the camera (15–30 fps).

### Reconnect behavior

On stream drop the client logs a warning and reconnects with exponential backoff
(1 s → 2 s → 4 s … capped at 30 s), resetting to 1 s after the first good frame.
No operator action needed for camera reboots, switch flaps, or brief outages.
Recognition events queue offline as usual if Frappe is also unreachable.

### Network tips

- Wired Ethernet beats Wi-Fi for stream stability, every time.
- Put cameras and edge devices on the same L2 segment / VLAN where possible.
- If the camera supports it, cap the sub-stream at ~15 fps — the edge can't use
  more, and it halves the bandwidth.

## 10. RTSP test rig (no camera hardware)

Simulate an IP camera locally with [mediamtx](https://github.com/bluenviron/mediamtx)
(RTSP server) + ffmpeg (publisher). Useful for dev, CI, and reproducing stream
failures on demand.

```bash
brew install mediamtx ffmpeg   # macOS; both are in apt/dnf on Linux too
```

**1. Start the RTSP server.** mediamtx rejects unconfigured paths by default and
Homebrew ships no config, so give it a minimal allow-all one:

```bash
printf 'paths:\n  all_others:\n' > /tmp/mediamtx-test.yml
mediamtx /tmp/mediamtx-test.yml
```

> mediamtx writes `auto.key` / `auto.crt` (MoQ TLS certs) into its working
> directory. Delete them when done — they are not gitignored by extension.

**2. Publish a stream.** Synthetic test pattern (no hardware at all):

```bash
ffmpeg -re -f lavfi -i testsrc=size=640x480:rate=15 \
  -c:v libx264 -preset ultrafast -tune zerolatency \
  -rtsp_transport tcp -f rtsp rtsp://127.0.0.1:8554/test
```

`-rtsp_transport tcp` on the **publisher** is required — mediamtx responds 400
to the default transport negotiation otherwise.

Or publish a real webcam over RTSP (macOS; run in a user terminal so the camera
TCC permission prompt can appear — faces will actually match):

```bash
ffmpeg -f avfoundation -framerate 30 -i "0" \
  -c:v libx264 -preset ultrafast -tune zerolatency \
  -rtsp_transport tcp -f rtsp rtsp://127.0.0.1:8554/cam
```

**3. Point the edge client at it:**

```yaml
edge:
  camera_source: "rtsp://127.0.0.1:8554/cam"
```

**4. Verify the transport.** The mediamtx log prints each reader session's
transport — look for `with TCP` on the edge client's session. That's the
definitive check that the forced-TCP env var took effect. (Careful: a VLC
viewer on the same stream defaults to UDP and shows up as a *separate* session —
a classic red herring.)

To test reconnect/backoff: kill the ffmpeg publisher mid-run, watch the edge
client log `camera read failed … reconnecting in Ns` with doubling delays, then
restart ffmpeg and watch it recover.

## 11. Verify end-to-end

With everything running, stand in front of the camera:

1. **Edge log** (`--debug`): match line with similarity + liveness scores,
   then `event posted`.
2. **Frappe**: a new **Face Recognition Event** (device, scores, timestamp) with
   a linked **Employee Checkin** — created instantly, server-side.
3. **Attendance**: produced by Frappe's native
   `process_auto_attendance_for_all_shifts`, which runs on the **hourly**
   scheduler. Expect the Attendance document up to ~1 h after check-in. Force it:

   ```bash
   cd ~/frappe-bench
   bench --site site1.localhost execute hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts
   ```

4. **Device health**: the device heartbeats every sync tick. An hourly job marks
   Active devices **Unreachable** when the last heartbeat is older than **Device
   Stale Threshold** (Face Recognition Settings, default 15 min); the next
   heartbeat revives them. Query per-device status, last-seen, and today's event
   count via `face_attendance.api.get_device_status`.

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Webcam won't open (`camera read failed` immediately, index source) | Wrong index, or another app holds the camera; on macOS, missing TCC camera permission | Try index 1/2; close other apps; run from a user terminal (not a daemon) so the permission prompt appears |
| RTSP stream won't open | Bad URL/credentials, camera unreachable, or port 554 blocked | Validate with `ffprobe`/VLC first (section 9); ping the camera; check the URL against the vendor table |
| Stream opens, then stutters/dies under load | UDP transport (forced-TCP override set?), Wi-Fi, or main-stream overload | Confirm `with TCP` in server logs; switch to sub-stream; use wired Ethernet |
| Face visible but never matches | Profile not Approved; embeddings not synced yet; enrollment photo from a different device | Approve the profile; wait one `sync_interval` or restart the client; re-enroll from the recognizing camera |
| Similarity hovers just under `threshold` (e.g. 0.38–0.44 vs 0.45) | Cross-device enrollment (~0.1 penalty), poor lighting, oblique angle | Re-enroll from the same camera; improve lighting; as a last resort lower `threshold` slightly — never below ~0.35 |
| Match found but event not posted, log shows liveness skip | `liveness_score` under `liveness_threshold` — glare, backlight, low light, or an actual spoof | Fix lighting first; only then consider lowering `liveness_threshold` |
| Enrollment save fails in Frappe | AI service down/unreachable, secret mismatch, or photo rejected (no/multiple faces, low quality) | `curl :8080/health`; compare `EMBEDDING_SERVICE_SECRET` with Face Recognition Settings; use a clear single-face photo |
| Edge gets `401` from Frappe | Wrong API key/secret, or user lacks the Face Edge Device role | Regenerate API credentials; check role assignment |
| Edge events/heartbeats rejected (`403`/validation) | No **Face Edge Device** record with Device ID = `edge.id` | Create/fix the device record (step 6.5) |
| Device shows **Unreachable** in Frappe | Edge process down, or network partition longer than the stale threshold | Check the edge process/logs; any successful heartbeat revives the device |
| Offline queue keeps growing | Frappe persistently unreachable from the edge | Fix connectivity; the queue drains automatically on the next successful sync tick (idempotent server-side) |
| Attendance missing despite checkins | Auto-attendance not configured, or hourly job hasn't run yet | Check Shift Type auto-attendance settings (step 6.4); force the job (section 11) |

Threshold tuning, in one paragraph: `threshold` (default 0.45) trades false
accepts against false rejects — raise it if strangers match, lower it (not below
~0.35) if genuine users are rejected *after* fixing enrollment and lighting.
`liveness_threshold` (default 0.6) gates spoofs; lighting fixes beat threshold
changes. `debounce_minutes` (default 2) only suppresses duplicate events —
it never affects matching.

## 13. Production deployment

### Process supervision (systemd)

AI service (on the bench host):

```ini
# /etc/systemd/system/ai-service.service
[Unit]
Description=Face AI service
After=network.target

[Service]
User=frappe
WorkingDirectory=/opt/tb-facecore
Environment=EMBEDDING_SERVICE_SECRET=<secret>
ExecStart=/opt/tb-facecore/venv/bin/uvicorn ai_service.app:app --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Edge client (on each edge device):

```ini
# /etc/systemd/system/edge-client.service
[Unit]
Description=Face attendance edge client
After=network-online.target

[Service]
User=edge
WorkingDirectory=/opt/tb-facecore
ExecStart=/opt/tb-facecore/venv/bin/python -m edge_client.main --config /etc/edge_client/config.yaml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now ai-service edge-client
journalctl -u edge-client -f      # logs are stderr → journal
```

Make sure `offline.db_path`'s directory exists and is writable by the service
user (`/var/lib/edge_client/`).

### Hardening checklist

- AI service: bind to `127.0.0.1` or a private interface; it needs to be
  reachable by Frappe only. Put nginx + TLS in front if it must cross hosts.
- One **Face Edge Device** record and one unique `edge.id` per physical device.
- Keep `config.yaml` permissions tight (`chmod 600`) — it holds API credentials.
- Edge → Frappe over HTTPS in production (`frappe.url`).

### Monitoring

- **Device liveness**: Frappe-side, free — heartbeats + the hourly stale-device
  job (section 11.4). Alert on devices flipping to Unreachable.
- **Offline queue depth**: check the SQLite queue file on each edge; alert if
  it exceeds ~10k pending events (means Frappe has been unreachable for a while).
- **AI service**: the 10-minute Frappe health job logs when `/health`
  is unreachable.

### Model upgrades

If the embedding model ever changes, stored vectors are no longer comparable
with new ones. Run the **"Face Profiles Needing Reenrollment"** report (HR
module) — it lists profiles whose `model_version` differs from the current
service — and re-enroll those employees.

## Capacity

Single-edge-device reference numbers. **TBD entries must be measured before first
customer demo** (use the RTSP test rig in this guide + `rtk proxy time` on a
known-length event burst).

| Metric | Value | How measured |
|---|---|---|
| Recognition throughput | TBD fps sustained | edge_client, 1 RTSP stream, M-series MBP CPU |
| Enrolled profiles per edge | TBD | sync + in-memory match table size |
| Event burst drain | TBD events/min | offline queue flush against local bench |

## References

- Architecture & design decisions: [`docs/design/architecture.md`](design/architecture.md)
- DeepFace analytics sidecar (Docker stack, `/analyze` endpoint): [`docs/deepface-sidecar.md`](deepface-sidecar.md)
- Package internals: [`facecore/README.md`](../facecore/README.md),
  [`ai_service/README.md`](../ai_service/README.md),
  [`edge_client/README.md`](../edge_client/README.md)
- Frappe app: [TechbirdIT/tb-face_attendance](https://github.com/TechbirdIT/tb-face_attendance)
