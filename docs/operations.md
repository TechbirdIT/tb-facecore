# Operations Guide

## 1. Download models (~310 MB, once)

```bash
cd /Users/saurabh/facerecog && source venv/bin/activate
# buffalo_l (SCRFD + ArcFace) — auto-downloads to ~/.insightface/models
python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l').prepare(ctx_id=-1)"
# MiniFASNet liveness ONNX → models/minifasnet.onnx
# Place the Silent-Face MiniFASNet ONNX at: /Users/saurabh/facerecog/models/minifasnet.onnx
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

## 4. Enroll a face

HR → **Employee Face Profile** → New → link employee → upload a clear front-facing photo → Save.
On save the controller posts the image to the embedding service and stores the 512-d vector.
A failure (service down, no/multi/low-quality face, blank device id) blocks the save with a message.

## 5. Run an edge device

```bash
cd /Users/saurabh/facerecog && source venv/bin/activate
cp edge_client/config.example.yaml config.yaml   # fill url/api_key/api_secret/camera_index
python -m edge_client.main --config config.yaml --debug
```

## 6. Attendance timing

Check-ins post instantly as **Employee Checkin** rows. **Attendance** documents are produced by
Frappe's native `process_auto_attendance_for_all_shifts`, which runs on the **hourly** scheduler.
Expect Attendance up to ~1h after check-in. To force it now:

```bash
cd ~/frappe-bench
bench --site site1.localhost execute hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts
```

## 7. Model upgrades

If the embedding model changes, run report **"Face Profiles Needing Reenrollment"**
(HR module) to list profiles whose `model_version` differs, and re-enroll them.
