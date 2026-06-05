# edge_client — Edge Device Attendance Client

Client application for edge devices (kiosks, cameras) that:
- Captures frames from local camera (webcam, IP camera, etc.)
- Analyzes faces locally using facecore
- Matches against embeddings pulled from Frappe
- Posts recognition events (with similarity + liveness scores) to the `face_attendance` app — check-ins are created server-side
- Heartbeats on every sync tick so Frappe can flag unreachable devices
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
  camera_source: 0  # webcam index or RTSP URL (legacy camera_index accepted)
  sync_interval: 300  # pull embeddings every 5 min

matching:
  threshold: 0.45  # cosine similarity [0.0, 1.0]
  liveness_threshold: 0.6  # anti-spoof score
```

## IP / CCTV cameras

Set `edge.camera_source` to the camera's RTSP URL (string) instead of a webcam
index. Any RTSP-capable camera works — that covers effectively every CCTV/IP
camera sold today (ONVIF Profile S devices are RTSP underneath).

| Vendor | RTSP URL pattern |
|---|---|
| Hikvision (and OEM rebrands) | `rtsp://user:pass@<ip>:554/Streaming/Channels/102` |
| Dahua / CP Plus | `rtsp://user:pass@<ip>:554/cam/realmonitor?channel=1&subtype=1` |
| S.vision | `rtsp://<ip>/ch1_0.264` |
| Uniview | `rtsp://user:pass@<ip>:554/unicast/c1/s1/live` |
| Anything else | Check the camera web UI / [iSpy camera database](https://www.ispyconnect.com/cameras) |

Tips:

- Prefer the **sub-stream** (`102`, `subtype=1`, `s1`) — lower resolution is
  enough for face detection and saves CPU.
- Transport is forced to **TCP** (`OPENCV_FFMPEG_CAPTURE_OPTIONS=rtsp_transport;tcp`)
  unless you set that env var yourself; UDP drops frames and kills the decoder.
- Wired Ethernet beats Wi-Fi for stream stability.
- On stream drop the client reconnects automatically (1 s → 30 s exponential
  backoff); recognitions queue offline as usual if Frappe is unreachable.

## Running

```bash
python -m edge_client.main --config config.yaml --debug
```

The app will:
1. Load config
2. Sync embeddings from Frappe (`get_face_data`)
3. Open camera
4. Loop: capture frame → detect → liveness gate → match → debounce → POST recognition event
5. Each sync tick: refresh embeddings, flush offline queue, heartbeat
6. Handle errors: camera failure (retry), Frappe down (queue offline), no match (ignore)

## Offline Resilience

If Frappe is unreachable:
- Events are enqueued to local SQLite with original timestamp and scores
- Flush retries on each sync tick; stops at first connection failure, drops 4xx-rejected items
- Survives edge process restart (durable storage)
- Server dedup (unique event index) makes queue drains idempotent

## Debouncing

Suppress repeat events within `debounce_minutes` per `attendance_device_id`:
- Employee scans face at 9:00 AM → event posted, check-in created
- Same employee re-scans at 9:01 AM → ignored (within 2-min window)
- Scan at 9:05 AM → new event (past 2-min window)

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
INFO:      Events posted, sync activity
WARNING:   Camera open failures, low quality
ERROR:     Frappe API failures, queue full
```

Logging is stderr-only — INFO by default, DEBUG with `--debug`.

## Permissions (Frappe)

The edge user needs:
- API key+secret (bound to "Face Edge Device" role)
- A matching **Face Edge Device** record in Frappe (Device ID = `edge.id`)
- Access to `get_face_data`, `post_event`, and `heartbeat` whitelisted methods (role-gated)

Employee Checkins are created server-side from posted events — the role never writes them directly.
See `face_attendance` app fixtures for the role + Custom DocPerm definition.

## Performance

- Frame capture: ~30ms (30 FPS)
- Face analysis: ~100ms (facecore on CPU)
- Match + debounce: <1ms (NumPy cosine)
- Event POST: ~50–100ms (network)

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
- Architecture & design decisions: `../docs/design/architecture.md`
- Setup & operations how-to: `../docs/how-to.md`
