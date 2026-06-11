"""Annotated MJPEG preview for the operator console.

The recognition loop already has the frame, the detections, and the resolved
identities. This module lets it draw those onto the frame and publish them as a
low-latency MJPEG stream the browser console can show in an ``<img>`` tag — so
the operator sees the *real* engine's boxes (e.g. ``HR-EMP-00001``) on the live
video, perfectly aligned (the box is drawn on the same frame), with none of the
segment-buffering lag that HLS adds.

MJPEG over localhost/LAN is sub-second and trivial to display (``<img src>``),
unlike RTSP (browsers can't play it) or HLS (≥1–2s of segment buffering). The
cost is bandwidth (a full JPEG per frame), which is fine for a handful of
preview cameras at a capped frame rate.

Opt-in via the ``preview`` config section; when disabled there is zero overhead.
"""

from __future__ import annotations

import logging
import threading
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


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence per-request logging
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")

    def do_GET(self):  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0].strip("/")
        server: PreviewServer = self.server  # type: ignore[assignment]

        if path in ("", "index.html"):
            cams = "".join(
                f'<p><a href="/{c}.mjpg">{c}</a> '
                f'<img src="/{c}.mjpg" width="320"></p>'
                for c in server.camera_ids()
            )
            body = (
                "<!doctype html><meta charset=utf-8>"
                "<title>Edge previews</title>"
                "<body style='background:#111;color:#ddd;font-family:sans-serif'>"
                f"<h3>Annotated previews</h3>{cams or '<p>no frames yet</p>'}"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.endswith(".jpg"):
            cam = path[:-4]
            jpeg = server.latest(cam)
            if jpeg is None:
                self.send_error(404, "no frame")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self._cors()
            self.send_header("Content-Length", str(len(jpeg)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(jpeg)
            return

        if path.endswith(".mjpg"):
            cam = path[:-5]
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self._cors()
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=frame"
            )
            self.end_headers()
            last = -1
            try:
                while not server.stopped():
                    jpeg, last = server.wait_for(cam, last, timeout=5.0)
                    if jpeg is None:
                        continue
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(
                        f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                    )
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                return  # client navigated away
            return

        self.send_error(404)


class PreviewServer(ThreadingHTTPServer):
    """Threaded MJPEG server holding the latest annotated JPEG per camera."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, host: str = "127.0.0.1", port: int = 9101):
        super().__init__((host, port), _Handler)
        self._frames: dict[str, bytes] = {}
        self._seq: dict[str, int] = {}
        self._cond = threading.Condition()
        self._stopped = False
        self._host, self._port = host, port

    # ----- producer side (recognition loop) -----
    def publish(self, cam_id: str, jpeg: bytes) -> None:
        with self._cond:
            self._frames[cam_id] = jpeg
            self._seq[cam_id] = self._seq.get(cam_id, 0) + 1
            self._cond.notify_all()

    # ----- consumer side (HTTP handlers) -----
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

    def camera_ids(self):
        with self._cond:
            return list(self._frames.keys())

    def stopped(self) -> bool:
        return self._stopped

    # ----- lifecycle -----
    def start(self) -> None:
        threading.Thread(target=self.serve_forever, daemon=True).start()
        logger.info("preview server on http://%s:%d", self._host, self._port)

    def stop(self) -> None:
        self._stopped = True
        with self._cond:
            self._cond.notify_all()
        self.shutdown()
