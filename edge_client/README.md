# edge_client — Edge Device Attendance Client

Client application for edge devices (kiosks, cameras) that:
- Captures frames from local camera (webcam, IP camera, etc.)
- Analyzes faces locally using facecore
- Matches against embeddings pulled from Frappe
- Posts check-ins to the native attendance system
- Handles offline queuing (SQLite) for network resilience

## Overview

Runs continuously on an edge device, consuming frames and making instant match/no-match decisions. Frappe syncs embeddings to each edge, so matching happens locally (no per-frame network hop).

## Installation

```bash
# Create a Python 3.11 venv
python3.11 -m venv venv
source venv/bin/activate

# Install
pip install -e ".[dev]"
```

## Configuration

Copy `config.example.yaml` to `config.yaml` and fill in:

```yaml
frappe:
  url: http://localhost:8000
  site: site1.localhost
  api_key: key_xxx
  api_secret: secret_xxx

edge:
  id: edge-001  # unique per device
  camera_index: 0  # 0 = default webcam; rtsp://... for IP cameras
  sync_interval: 300  # pull embeddings every 5 min

matching:
  threshold: 0.45  # cosine similarity [0.0, 1.0]
  liveness_threshold: 0.6  # anti-spoof score
```

## Running

```bash
python -m edge_client.main --config config.yaml --debug
```

The app will:
1. Load config
2. Sync embeddings from Frappe (`get_face_data`)
3. Open camera
4. Loop: capture frame → detect → liveness gate → match → debounce → POST check-in
5. Handle errors: camera failure (retry), Frappe down (queue offline), no match (ignore)

## Offline Resilience

If Frappe is unreachable:
- Check-ins are enqueued to local SQLite with original timestamp
- Background flush retries on reconnect
- Survives edge process restart (durable storage)
- Prevents duplicate storms (enqueue-once logic)

## Debouncing

Suppress repeat check-ins within `debounce_minutes` per `attendance_device_id`:
- Employee scans face at 9:00 AM → check-in created
- Same employee re-scans at 9:01 AM → ignored (within 2-min window)
- Scan at 9:05 AM → new check-in (past 2-min window)

## Testing

```bash
pytest tests/
```

Tests cover:
- Matcher (synthetic vectors)
- Debounce window
- Offline queue flush
- Sync merge logic
- Config validation

## Logging

```
DEBUG:     Frame analysis, matcher scores
INFO:      Check-ins posted, sync events
WARNING:   Camera open failures, low quality
ERROR:     Frappe API failures, queue full
```

Log file location: see `config.yaml` `logging.file`.

## Permissions (Frappe)

The edge user needs:
- API key+secret (bound to "Face Edge Device" role)
- Create + read on `Employee Checkin`
- Read on `get_face_data` whitelisted method

See `face_attendance` app fixtures for the role + Custom DocPerm definition.

## Performance

- Frame capture: ~30ms (30 FPS)
- Face analysis: ~100ms (facecore on CPU)
- Match + debounce: <1ms (NumPy cosine)
- Check-in POST: ~50–100ms (network)

**Total loop: ~150–300ms** → practical 3–7 FPS recognition rate on a single-camera edge.

## Multi-Camera Setup (Future)

v1 handles one camera per edge. Multi-camera edges (different angles, entrance/exit) planned for phase 2:
- Thread per camera
- Shared embedding cache
- Fused match logic

## Production Deployment

- Use supervisor or systemd to auto-restart on crash
- Monitor `config.sqlite` queue size (alert if > 10k pending)
- Sync embeddings periodically (e.g., hourly via cron)
- Log to a central system (syslog, Datadog, etc.)

## References

- facecore: `../facecore/README.md`
- Frappe integration: `../docs/superpowers/specs/2026-06-02-facerecog-hrms-design.md` § 6, 9
