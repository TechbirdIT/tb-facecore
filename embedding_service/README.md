# embedding_service — FastAPI Embedding Microservice

FastAPI service that exposes face embedding computation via HTTP. The decoupling boundary between Frappe (which never imports InsightFace) and the AI stack.

## Overview

Single endpoint: `POST /embed`
- Input: image file (jpg, png)
- Output: 512-d embedding + detector score + liveness score + model version

Frappe calls this during enrollment. Edge clients call it to validate enrollment images (for future multi-shot support).

## Installation

```bash
pip install -e ".[dev]"
```

## Running (development)

```bash
# Start the service on http://localhost:8080
uvicorn embedding_service.app:app --reload --host 127.0.0.1 --port 8080
```

Health check: `curl http://localhost:8080/health`

## API

### POST /embed

**Request:**
- File: multipart/form-data with `file` parameter (image bytes)
- Header: `X-Secret: <shared-secret>` (v1: not enforced; prod: required)

**Response:**
```json
{
  "embedding": [0.123, -0.456, ...],  // 512 floats
  "det_score": 0.95,
  "liveness_score": 0.78,
  "model_version": "buffalo_l"
}
```

**Errors:**
- `400 Bad Request` — no face / multiple faces / low det_score / invalid image
- `422 Unprocessable Entity` — malformed multipart
- `401 Unauthorized` — missing/invalid secret (prod)

**Example:**
```bash
curl -F "file=@photo.jpg" http://localhost:8080/embed
```

## Testing

```bash
pytest tests/
```

## Security (Production)

- Enforce `X-Secret` header validation
- Run behind a reverse proxy (nginx) with SSL/TLS
- Restrict to private network only
- Rate-limit (e.g., 100 req/min)
- Log all requests for audit trail

## Configuration

See `main.py` for env var overrides (coming in phase 2):
- `EMBEDDING_SERVICE_SECRET` — shared secret for auth
- `EMBEDDING_SERVICE_LOG_LEVEL` — logging level
- `EMBEDDING_SERVICE_DEVICE` — "cpu" or "cuda"

## Performance

- Single face, CPU (Mac): ~200–400ms
- Single face, GPU (Linux): ~50–100ms
- Cold start: ~2s (model load on first request)

Keep warm by scheduling a health-check job in Frappe.

## References

See facecore README.
