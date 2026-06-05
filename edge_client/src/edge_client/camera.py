"""Camera frame source: USB webcam index or RTSP/IP stream URL."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Any, cast

logger = logging.getLogger(__name__)

_BACKOFF_START = 1.0
_BACKOFF_CAP = 30.0


def _ensure_tcp_transport(source: int | str) -> None:
    """Force TCP for RTSP before OpenCV builds the FFmpeg capture.

    UDP drops packets on congested networks and crashes the decoder. The env
    var is only read at VideoCapture construction, so set it first. setdefault
    keeps any operator override intact.
    """
    if isinstance(source, str) and source.startswith("rtsp"):
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")


class FrameSource:
    """Threaded grabber keeping only the latest frame, with backoff reconnect.

    Decouples camera FPS from inference FPS: without this, RTSP frames queue
    in the FFmpeg buffer while inference runs and lag grows unbounded.
    ``read()`` consumes the latest frame; ``None`` means nothing new yet.
    """

    def __init__(
        self, source: int | str, open_fn: Callable[[int | str], Any] | None = None
    ):
        _ensure_tcp_transport(source)
        _open_fn: Callable[[int | str], Any]
        if open_fn is None:  # pragma: no cover - real cv2 only outside tests
            import cv2

            _open_fn = cast(Callable[[int | str], Any], cv2.VideoCapture)
        else:
            _open_fn = open_fn
        self._source = source
        self._open_fn = _open_fn
        self._lock = threading.Lock()
        self._latest = None
        self._stop = threading.Event()
        self._backoff = _BACKOFF_START
        self._cap = _open_fn(source)
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _step(self) -> None:
        """One read-or-reconnect iteration. Extracted for deterministic tests."""
        ok, frame = self._cap.read()
        if ok:
            with self._lock:
                self._latest = frame
            self._backoff = _BACKOFF_START
            return
        logger.warning(
            "camera read failed (%s); reconnecting in %.0fs",
            self._source,
            self._backoff,
        )
        self._cap.release()
        self._sleep(self._backoff)
        if self._stop.is_set():
            return  # shutting down; don't reopen
        self._backoff = min(self._backoff * 2, _BACKOFF_CAP)
        self._cap = self._open_fn(self._source)

    def _sleep(self, seconds: float) -> None:
        self._stop.wait(seconds)

    def _run(self) -> None:  # pragma: no cover - thread glue around _step
        while not self._stop.is_set():
            self._step()

    def read(self) -> Any:
        """Return and consume the latest frame, or None if nothing new."""
        with self._lock:
            frame, self._latest = self._latest, None
            return frame

    def release(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._thread.is_alive():  # pragma: no cover - blocked in cap.read()
            # A dead-socket cap.read() can block past the join timeout. The
            # daemon thread owns the cap; it dies with the process.
            logger.warning("frame source thread did not stop; leaving capture open")
            return
        self._cap.release()
