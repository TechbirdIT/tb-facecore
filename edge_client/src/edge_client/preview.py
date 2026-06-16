"""Annotated MJPEG preview for the operator console.

The recognition loop already has the frame, the detections, and the resolved
identities. This module lets it draw those onto the frame and publish them as a
low-latency MJPEG stream the browser console can show in an ``<img>`` tag — so
the operator sees the *real* engine's boxes (e.g. ``HR-EMP-00001``) on the live
video, perfectly aligned (the box is drawn on the same frame), with none of the
segment-buffering lag that HLS adds.

A :class:`FrameHub` is the shared in-memory buffer (latest annotated JPEG per
camera + a monotonic timestamp for liveness). Two HTTP front-ends serve it:
:class:`PreviewServer` (standalone ``edge-client`` run) and the control server's
handler (``edge-console`` run) — both via the streaming helpers here.
"""

from __future__ import annotations

import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)

# BGR colours (OpenCV) keyed by track state.
_GREEN = (120, 220, 0)
_AMBER = (40, 180, 240)
_RED = (60, 60, 235)
_GRAY = (180, 180, 180)


def annotate(frame, tracks):
    """Return a copy of ``frame`` with a labelled box per visible track.

    ``tracks`` is the list of Track objects visible this frame. Colour encodes
    state: green = recognised + live, red = spoof (liveness failed), amber =
    live but unrecognised, gray = still acquiring.
    """
    import cv2

    img = frame.copy()
    for t in tracks:
        x1, y1, x2, y2 = (int(v) for v in t.bbox)
        if t.spoof:
            color, label = _RED, f"SPOOF {t.last_liveness:.2f}"
        elif t.identity is not None:
            device_id, score = t.identity
            color = _GREEN
            label = f"{device_id}  {score:.2f} / live {t.last_liveness:.2f}"
        elif t.first_attempt is not None:
            color, label = _AMBER, "unknown"
        else:
            color, label = _GRAY, "…"

        # demographics suffix (when enabled + computed): e.g. "  M~33"
        age = getattr(t, "est_age", None)
        gender = getattr(t, "est_gender", None)
        if age is not None or gender is not None:
            g = {"male": "M", "female": "F"}.get(gender or "", "?")
            label += f"  {g}~{age}" if age is not None else f"  {g}"

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        # label chip above the box (or below if it would clip the top edge)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        ly = y1 - 8 if y1 - 8 - th > 0 else y2 + th + 8
        cv2.rectangle(img, (x1, ly - th - 6), (x1 + tw + 10, ly + 4), color, -1)
        cv2.putText(
            img, label, (x1 + 5, ly),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1, cv2.LINE_AA,
        )
    return img


def encode_jpeg(frame, quality: int = 70, scale: float = 1.0):
    """JPEG-encode a (optionally downscaled) frame; returns bytes or None."""
    import cv2

    if scale and scale != 1.0:
        frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    return buf.tobytes() if ok else None


class FrameHub:
    """Thread-safe latest-frame buffer per camera, with liveness timestamps."""

    def __init__(self) -> None:
        self._frames: dict[str, bytes] = {}
        self._seq: dict[str, int] = {}
        self._ts: dict[str, float] = {}
        self._cond = threading.Condition()
        self._closed = False

    def publish(self, cam_id: str, jpeg: bytes) -> None:
        with self._cond:
            self._frames[cam_id] = jpeg
            self._seq[cam_id] = self._seq.get(cam_id, 0) + 1
            self._ts[cam_id] = time.monotonic()
            self._cond.notify_all()

    def latest(self, cam_id: str) -> bytes | None:
        with self._cond:
            return self._frames.get(cam_id)

    def wait_for(self, cam_id: str, last_seq: int, timeout: float):
        """Block until a newer frame than ``last_seq`` exists; return (jpeg, seq)."""
        with self._cond:
            if self._seq.get(cam_id, 0) <= last_seq:
                self._cond.wait(timeout)
            seq = self._seq.get(cam_id, 0)
            if seq <= last_seq:
                return None, last_seq
            return self._frames.get(cam_id), seq

    def freshness(self, cam_id: str) -> float | None:
        """Seconds since the last frame for ``cam_id``, or None if never seen."""
        with self._cond:
            ts = self._ts.get(cam_id)
        return None if ts is None else (time.monotonic() - ts)

    def camera_ids(self):
        with self._cond:
            return list(self._frames.keys())

    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True
        with self._cond:
            self._cond.notify_all()


# ---- MJPEG streaming helpers (shared by both HTTP front-ends) ----

def stream_mjpeg(handler: BaseHTTPRequestHandler, hub: FrameHub, cam_id: str) -> None:
    """Stream ``cam_id`` as multipart/x-mixed-replace MJPEG until the client
    disconnects or the hub closes."""
    handler.send_response(200)
    handler.send_header("Age", "0")
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
    handler.end_headers()
    last = -1
    try:
        while not hub.closed():
            jpeg, last = hub.wait_for(cam_id, last, timeout=5.0)
            if jpeg is None:
                continue
            handler.wfile.write(b"--frame\r\n")
            handler.wfile.write(b"Content-Type: image/jpeg\r\n")
            handler.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
            handler.wfile.write(jpeg)
            handler.wfile.write(b"\r\n")
    except (BrokenPipeError, ConnectionResetError):
        return  # client navigated away


def serve_jpeg(handler: BaseHTTPRequestHandler, hub: FrameHub, cam_id: str) -> None:
    """Serve the single latest JPEG for ``cam_id`` (404 if none yet)."""
    jpeg = hub.latest(cam_id)
    if jpeg is None:
        handler.send_error(404, "no frame")
        return
    handler.send_response(200)
    handler.send_header("Content-Type", "image/jpeg")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(jpeg)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(jpeg)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence per-request logging
        pass

    def do_GET(self):  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0].strip("/")
        server: PreviewServer = self.server  # type: ignore[assignment]
        hub = server.hub

        if path in ("", "index.html"):
            cams = "".join(
                f'<p><a href="/{c}.mjpg">{c}</a> '
                f'<img src="/{c}.mjpg" width="320"></p>'
                for c in hub.camera_ids()
            )
            body = (
                "<!doctype html><meta charset=utf-8>"
                "<title>Edge previews</title>"
                "<body style='background:#111;color:#ddd;font-family:sans-serif'>"
                f"<h3>Annotated previews</h3>{cams or '<p>no frames yet</p>'}"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.endswith(".jpg"):
            serve_jpeg(self, hub, path[:-4])
            return
        if path.endswith(".mjpg"):
            stream_mjpeg(self, hub, path[:-5])
            return

        self.send_error(404)


class PreviewServer(ThreadingHTTPServer):
    """Threaded MJPEG server (standalone ``edge-client`` run)."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, host: str = "127.0.0.1", port: int = 9101):
        super().__init__((host, port), _Handler)
        self.hub = FrameHub()
        self._host, self._port = host, port

    def publish(self, cam_id: str, jpeg: bytes) -> None:
        self.hub.publish(cam_id, jpeg)

    def start(self) -> None:
        threading.Thread(target=self.serve_forever, daemon=True).start()
        logger.info("preview server on http://%s:%d", self._host, self._port)

    def stop(self) -> None:
        self.hub.close()
        self.shutdown()
