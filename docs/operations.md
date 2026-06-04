# Operations Guide

## 1. Download models (~310 MB, once)

```bash
cd /Users/saurabh/facerecog && source venv/bin/activate
# buffalo_l (SCRFD + ArcFace) — auto-downloads to ~/.insightface/models
python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l').prepare(ctx_id=-1)"
# MiniFASNet liveness ONNX → models/minifasnet.onnx
# Source: Silent-Face Anti-Spoofing (https://github.com/minivision-ai/Silent-Face-Anti-Spoofing),
# export the MiniFASNet checkpoint to ONNX and place at: <repo>/models/minifasnet.onnx
```

## 2. Start the embedding service

```bash
cd /Users/saurabh/facerecog && source venv/bin/activate
export EMBEDDING_SERVICE_SECRET=change-me   # match Face Recognition Settings
uvicorn embedding_service.app:app --host 127.0.0.1 --port 8080
curl http://127.0.0.1:8080/health   # {"status":"ok",...}
```

## 3. Configure Frappe

1. **Face Recognition Settings** (single): set `embedding_service_url=http://localhost:8080`,
   `embedding_service_secret` to match step 2, keep default thresholds.
2. Create an **API user**, assign the **"Face Edge Device"** role, generate **API key + secret**.
3. On each employee, set a unique **Attendance Device ID**.
4. **Shift Type** → enable **Auto Attendance**, set **Process Attendance After** = today,
   assign employees to the shift.
5. Create a **Face Edge Device** record per device; **Device ID** must match `edge.id`
   in the client config. Unregistered devices get their events/heartbeats rejected.

## 4. Enroll a face

**Self-service:** employees with a linked User (Employee role + `Employee.user_id`) open
`http://<site>/face` → Register → webcam capture → Submit for Approval. They can re-capture
while Draft/Rejected, track status, and run a webcam self-test once Approved (rate-limited 5/min).

**HR-managed:** HR → **Employee Face Profile** → New → link employee → upload a clear
front-facing photo → Save. On save the controller posts the image to the embedding service and
stores the 512-d vector. A failure (service down, no/multi/low-quality face, blank device id)
blocks the save with a message.

Then approve the profile via the **Face Profile Approval** workflow (HR Manager approves).
Only **Approved** profiles are synced to edge devices. Enroll with a photo from the device
that does the recognizing — cross-device photos (phone vs webcam) lose ~0.1 similarity.

## 5. Run an edge device

```bash
cd /Users/saurabh/facerecog && source venv/bin/activate
cp edge_client/config.example.yaml config.yaml   # fill url/api_key/api_secret/camera_source
python -m edge_client.main --config config.yaml --debug
```

For IP/CCTV cameras set `edge.camera_source` to the RTSP URL (sub-stream
preferred) — see `edge_client/README.md` for per-vendor URL patterns.

## 6. Attendance timing

Each recognition posts a **Face Recognition Event** (device, scores, timestamp); the server
creates the **Employee Checkin** from it instantly and links the two. **Attendance** documents are produced by
Frappe's native `process_auto_attendance_for_all_shifts`, which runs on the **hourly** scheduler.
Expect Attendance up to ~1h after check-in. To force it now:

```bash
cd ~/frappe-bench
bench --site site1.localhost execute hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts
```

## 7. Device health

Devices heartbeat on every sync tick (default 60 s). An hourly job marks Active devices
**Unreachable** when the heartbeat is older than **Device Stale Threshold** (Face Recognition
Settings, default 15 min); the next heartbeat revives them. HR can query
`face_attendance.api.get_device_status` for per-device status, last-seen, and today's event
count. A 10-min job pings the embedding service `/health` and logs when it is unreachable.

## 8. Model upgrades

If the embedding model changes, run report **"Face Profiles Needing Reenrollment"**
(HR module) to list profiles whose `model_version` differs, and re-enroll them.
