"""Controllable recognition engine.

Wraps the capture loop so it can be started and stopped on demand (from the
operator console's Start/Stop button) instead of running for the lifetime of the
process. Owns the loaded face models, one capture thread per camera, a central
sync/heartbeat tick, a :class:`FrameHub` for the annotated preview, and a ring
of recent recognition events for the console's activity rail.

Models are loaded once on first start and kept across stop/start cycles so
restarting is instant (the slow part is the first model load).
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from importlib.metadata import PackageNotFoundError, version

from edge_client.capture import _camera_loop, resolve_cameras
from edge_client.frappe_client import FrappeClient
from edge_client.preview import FrameHub
from edge_client.store import Store
from edge_client.sync import flush_queue, sync_faces

logger = logging.getLogger(__name__)

try:
    _APP_VERSION = version("edge-client")
except PackageNotFoundError:  # editable/dev install
    _APP_VERSION = "dev"

_LIVE_WINDOW_S = 2.0  # a camera is "live" if it produced a frame within this window


class Engine:
    """Lifecycle-managed recognition engine for one or many cameras."""

    def __init__(self, cfg, model_version: str):
        self.cfg = cfg
        self.model_version = model_version
        self.hub = FrameHub()
        self._state = "stopped"  # stopped | starting | running | stopping
        self._error: str | None = None
        self._lock = threading.Lock()
        self._stop: threading.Event | None = None
        self._threads: list[threading.Thread] = []
        self._analyzer = None  # loaded lazily, kept across restarts
        self._name_map: dict[str, str] = {}
        self._events: collections.deque = collections.deque(maxlen=60)
        self._events_lock = threading.Lock()
        self._cameras = resolve_cameras(cfg)
        # latest raw (un-annotated) frame per camera, for offline demography
        self._raw: dict[str, object] = {}
        # serialize heavy deepface demography calls (TF on CPU) so overlapping
        # Analyze clicks queue instead of contending for cores
        self._demo_lock = threading.Lock()
        self._demo_warmed = False

    # ----- introspection -----
    def status(self) -> dict:
        with self._lock:
            state, error = self._state, self._error
        # Report ALL configured nodes (incl. disabled) with their on/off state,
        # so the console can show every camera and toggle it; only enabled +
        # running ones can be "live".
        specs = getattr(self.cfg, "camera_specs", None)
        if specs is not None:
            rows = [(cid, src, en) for cid, src, en in specs]
        else:
            rows = [(cid, src, True) for cid, src in self._cameras]
        cams = []
        for cam_id, source, enabled in rows:
            fresh = self.hub.freshness(cam_id)
            live = (
                enabled
                and state == "running"
                and fresh is not None
                and fresh < _LIVE_WINDOW_S
            )
            cams.append({
                "id": cam_id,
                "source": _mask(source),
                "enabled": enabled,
                "live": live,
                "last_frame_s": round(fresh, 2) if fresh is not None else None,
            })
        with self._events_lock:
            events = list(self._events)
        return {"state": state, "error": error, "cameras": cams, "events": events}

    # ----- lifecycle -----
    def start(self) -> str:
        with self._lock:
            if self._state in ("starting", "running"):
                return self._state
            self._state, self._error = "starting", None
        threading.Thread(target=self._bring_up, daemon=True).start()
        return "starting"

    def stop(self) -> str:
        with self._lock:
            if self._state in ("stopped", "stopping"):
                return self._state
            self._state = "stopping"
        if self._stop is not None:
            self._stop.set()
        for t in self._threads:
            t.join(timeout=3.0)
        self._threads = []
        with self._lock:
            self._state = "stopped"
        logger.info("engine stopped")
        return "stopped"

    def shutdown(self) -> None:
        self.stop()
        self.hub.close()

    def apply_config(self, cfg) -> str:
        """Swap in a new config and hot-reload cameras.

        If the engine is running it is stopped, re-pointed at the new config's
        cameras/settings, and restarted (models stay loaded, so it's quick).
        Returns the resulting state. This is how the console's Save button takes
        effect without restarting the process.
        """
        with self._lock:
            was_running = self._state in ("starting", "running")
        if was_running:
            self.stop()
        self.cfg = cfg
        self._cameras = resolve_cameras(cfg)
        self._raw.clear()  # old cameras' frames are stale
        if was_running:
            return self.start()
        return self._state

    # ----- internals -----
    def _bring_up(self) -> None:
        try:
            if self._analyzer is None:
                from facecore import FaceAnalyzer

                logger.info("loading face models…")
                self._analyzer = FaceAnalyzer(device="cpu", det_thresh=self.cfg.min_det_score)

            client = FrappeClient(self.cfg.frappe_url, self.cfg.api_key, self.cfg.api_secret)
            store = Store(self.cfg.db_path)
            matcher = sync_faces(client, store, self.model_version)
            self._refresh_name_map(store)

            self._stop = threading.Event()
            shared = {
                "matcher": matcher,
                "preview": self.hub,
                "on_event": self._record_event,
                "raw": self._raw,
            }
            self._threads = [
                threading.Thread(
                    target=_camera_loop,
                    args=(cam_id, src, shared, self._analyzer, client, store, self.cfg, self._stop),
                    daemon=True,
                )
                for cam_id, src in self._cameras
            ]
            for t in self._threads:
                t.start()
            tick = threading.Thread(
                target=self._sync_loop, args=(client, store, shared), daemon=True
            )
            tick.start()
            self._threads.append(tick)

            with self._lock:
                self._state = "running"
            logger.info("engine running: %d camera(s)", len(self._cameras))
            self._warm_demography_async()
        except Exception as exc:  # noqa: BLE001 - surface any startup failure to the UI
            logger.exception("engine failed to start")
            with self._lock:
                self._state, self._error = "stopped", str(exc)

    def _warm_demography_async(self) -> None:
        """Pre-build the deepface emotion/race models in the background so the
        first console Analyze click is fast instead of paying ~6s of cold model
        load. No-op if the optional extra isn't installed or it's already warm.
        """
        if self._demo_warmed:
            return

        def _warm():
            try:
                from facecore import demography as _demography

                with self._demo_lock:
                    if self._demo_warmed:
                        return
                    logger.info("warming demography models…")
                    _demography.warmup()
                    self._demo_warmed = True
                    logger.info("demography models ready")
            except Exception:  # noqa: BLE001 - extra not installed / load failure
                logger.debug("demography warmup skipped", exc_info=True)

        threading.Thread(target=_warm, daemon=True).start()

    def _sync_loop(self, client, store, shared) -> None:
        last_sync = time.monotonic()
        stop = self._stop
        while stop is not None and not stop.is_set():
            stop.wait(0.5)
            if stop.is_set():
                break
            if time.monotonic() - last_sync >= self.cfg.sync_interval:
                shared["matcher"] = sync_faces(client, store, self.model_version)
                self._refresh_name_map(store)
                flush_queue(client, store, self.cfg.edge_id)
                for cam_id, _src in self._cameras:
                    try:
                        client.heartbeat(cam_id, _APP_VERSION)
                    except Exception:
                        logger.debug("heartbeat failed for %s; will retry", cam_id)
                last_sync = time.monotonic()

    def _refresh_name_map(self, store) -> None:
        try:
            self._name_map = {
                r["attendance_device_id"]: r.get("employee_name") or r.get("employee") or r["attendance_device_id"]
                for r in store.all_faces()
                if r.get("attendance_device_id")
            }
        except Exception:
            logger.debug("could not build name map", exc_info=True)

    def _record_event(
        self, edge_id, device_id, timestamp, score, liveness, age=None, gender=None
    ) -> None:
        with self._events_lock:
            self._events.appendleft({
                "name": self._name_map.get(device_id, device_id),
                "device_id": device_id,
                "cam": edge_id,
                "time": timestamp.split(" ")[-1] if " " in timestamp else timestamp,
                "score": round(float(score), 3),
                "liveness": round(float(liveness), 3),
                "age": age,
                "gender": gender,
            })

    def demography(
        self, cam_id: str, actions: tuple[str, ...] = ("emotion", "race")
    ) -> dict:
        """Run offline emotion/race demography on the latest raw frame of ``cam_id``.

        Uses the heavy deepface backend (``facecore[demography]`` extra) — kept
        off the real-time loop on purpose. Returns ``{"camera", "faces"}`` or
        ``{"camera", "error"}`` (e.g. the install hint when the extra is absent),
        so the caller never has to handle exceptions.
        """
        frame = self._raw.get(cam_id)
        if frame is None:
            return {"camera": cam_id, "error": f"no frame available yet for {cam_id}"}
        from facecore import demography as _demography

        try:
            # serialize: the first call builds models (~6s); overlapping clicks
            # would otherwise each spawn a heavy concurrent TF inference
            with self._demo_lock:
                faces = _demography.analyze(frame, actions=actions)
                self._demo_warmed = True
            return {"camera": cam_id, "faces": faces}
        except Exception as exc:  # noqa: BLE001 - surface install hint / failures to UI
            return {"camera": cam_id, "error": str(exc)}


def _mask(source) -> str:
    """Redact credentials in rtsp://user:pass@host for display."""
    s = str(source)
    if s.startswith("rtsp") and "@" in s:
        scheme, rest = s.split("://", 1)
        if "@" in rest:
            return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return s
