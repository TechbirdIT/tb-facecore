"""Operator console control server.

A single process (``edge-console``) that, on one port, serves:
  - the console UI static files (``ui/``),
  - a control API the console's Start/Stop button calls
    (``POST /api/start``, ``POST /api/stop``, ``GET /api/status``),
  - the annotated live preview (``/preview/<camera>.mjpg`` and ``.jpg``).

All same-origin, so the browser console can drive the real engine and show its
real feed without CORS gymnastics or a second server. The recognition engine is
NOT started at boot — it waits for ``POST /api/start`` (the UI button).
"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from edge_client.config import load_config
from edge_client.engine import Engine
from edge_client.preview import serve_jpeg, stream_mjpeg

logger = logging.getLogger(__name__)
MODEL_VERSION = "buffalo_l"

_DEFAULT_UI_DIR = Path(__file__).resolve().parents[2] / "ui"


def _json_default(o):
    """Fallback encoder for stragglers (e.g. numpy scalars) so the API never 500s
    on serialization. The demography contract already returns native types; this
    is belt-and-suspenders for any numpy value that slips through."""
    item = getattr(o, "item", None)
    if callable(item) and o.__class__.__module__ == "numpy":
        return o.item()
    if hasattr(o, "tolist"):  # numpy ndarray
        return o.tolist()
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence per-request logging
        pass

    @property
    def engine(self) -> Engine:
        return self.server.engine  # type: ignore[attr-defined]

    @property
    def ui_dir(self) -> Path:
        return self.server.ui_dir  # type: ignore[attr-defined]

    def _json(self, obj, status=200):
        body = json.dumps(obj, default=_json_default).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0].strip("/")
        if path == "api/start":
            self._json({"ok": True, **self.engine.status(), "state": self.engine.start()})
        elif path == "api/stop":
            self._json({"ok": True, **self.engine.status(), "state": self.engine.stop()})
        elif path == "api/config":
            self._handle_config()
        else:
            self.send_error(404)

    def _handle_config(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"error": "invalid JSON body"}, status=400)
            return
        try:
            state = apply_console_config(self.server.config_path, body, self.engine)
        except Exception as exc:  # noqa: BLE001 - report config failures to the UI
            self._json({"error": f"config apply failed: {exc}"}, status=500)
            return
        self._json({"ok": True, **self.engine.status(), "state": state})

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0].strip("/")

        if path == "api/status":
            self._json(self.engine.status())
            return
        if path == "api/demography":
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(self.path).query)
            cam = (q.get("camera") or [""])[0]
            actions = tuple((q.get("actions") or ["emotion,race"])[0].split(","))
            if not cam:
                self._json({"error": "camera query param required"}, status=400)
                return
            self._json(self.engine.demography(cam, actions=actions))
            return
        if path.startswith("preview/"):
            name = path[len("preview/"):]
            if name.endswith(".mjpg"):
                stream_mjpeg(self, self.engine.hub, name[:-5])
            elif name.endswith(".jpg"):
                serve_jpeg(self, self.engine.hub, name[:-4])
            else:
                self.send_error(404)
            return

        self._serve_static(path or "face-edge-console.html")

    def _serve_static(self, rel: str):
        # resolve under ui_dir, guarding against path traversal
        target = (self.ui_dir / rel).resolve()
        try:
            target.relative_to(self.ui_dir.resolve())
        except ValueError:
            self.send_error(403)
            return
        if not target.is_file():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _coerce_source(src):
    """A webcam index arrives from the UI as the string "0"; cv2 needs an int.
    Leave rtsp:// URLs and device paths as strings."""
    if isinstance(src, str) and src.strip().isdigit():
        return int(src.strip())
    return src


def apply_console_config(config_path: Path, body: dict, engine: Engine) -> str:
    """Merge the console's config into config.yaml on disk, then hot-reload the
    engine. Only the fields the console manages are touched; preview /
    demographics / offline / frappe.site are preserved. Returns the engine state.
    """
    import yaml  # type: ignore[import-untyped]

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    fr = body.get("frappe") or {}
    raw.setdefault("frappe", {})
    for k in ("url", "api_key", "api_secret"):
        if k in fr:
            raw["frappe"][k] = fr[k]

    edge = raw.setdefault("edge", {})
    cams = [c for c in (body.get("cameras") or []) if c.get("id") and c.get("source")]
    if cams:
        edge["cameras"] = [
            {
                "id": c["id"],
                "source": _coerce_source(c["source"]),
                # per-camera on/off switch; default on. Disabled nodes stay in
                # config but the engine won't run them (concurrency management).
                "enabled": c.get("enabled", True) is not False,
            }
            for c in cams
        ]
        # The single id/camera_source fallbacks point at the first ENABLED node
        # so a standalone read still lands on a camera that actually runs.
        first = next((c for c in cams if c.get("enabled", True) is not False), cams[0])
        edge["id"] = first["id"]
        edge["camera_source"] = _coerce_source(first["source"])

    rt = body.get("rtsp") or {}
    if "rtsp_transport" in rt:
        edge["rtsp_transport"] = rt["rtsp_transport"]
    if "rtsp_timeout_seconds" in rt:
        edge["rtsp_timeout_seconds"] = rt["rtsp_timeout_seconds"]
    if "sighting_interval_seconds" in body:
        edge["sighting_interval_seconds"] = body["sighting_interval_seconds"]

    m = body.get("matching") or {}
    raw.setdefault("matching", {})
    for k in ("threshold", "liveness_threshold", "min_det_score"):
        if k in m:
            raw["matching"][k] = m[k]

    tr = body.get("tracking") or {}
    raw.setdefault("tracking", {})
    for k in (
        "iou_threshold", "max_misses", "reverify_seconds",
        "acquire_fast_seconds", "acquire_backoff_seconds",
    ):
        if k in tr:
            raw["tracking"][k] = tr[k]

    with open(config_path, "w") as f:
        yaml.safe_dump(raw, f, sort_keys=False)

    return engine.apply_config(load_config(str(config_path)))


class ControlServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, host, port, engine: Engine, ui_dir: Path, config_path: Path):
        super().__init__((host, port), _Handler)
        self.engine = engine
        self.ui_dir = ui_dir
        self.config_path = config_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Face Edge operator console (UI + control API + live preview)"
    )
    parser.add_argument("--config", required=True, help="Path to YAML config")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--ui-dir", default=str(_DEFAULT_UI_DIR), help="console UI folder")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    cfg = load_config(args.config)
    engine = Engine(cfg, MODEL_VERSION)
    ui_dir = Path(args.ui_dir).resolve()
    server = ControlServer(args.host, args.port, engine, ui_dir, Path(args.config).resolve())

    logger.info("console on http://%s:%d  (UI: %s)", args.host, args.port, ui_dir)
    logger.info("open http://%s:%d/face-edge-console.html", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.shutdown()
        server.shutdown()


if __name__ == "__main__":
    main()
