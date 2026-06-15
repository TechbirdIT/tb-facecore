"""Camera frame source: USB webcam index or RTSP/IP stream URL."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_BACKOFF_START = 1.0
_BACKOFF_CAP = 30.0
# Low-latency RTSP: don't accumulate an input buffer (fflags;nobuffer), don't
# hold frames for RTP reordering (reorder_queue_size;0), and no demux delay
# (max_delay;0). These cut the bulk of OpenCV/FFmpeg's steady-state RTSP latency
# so the console preview tracks real time instead of trailing ~1s behind.
_LOW_LATENCY_OPTS = "fflags;nobuffer|reorder_queue_size;0|max_delay;0"
_DEFAULT_RTSP_OPTIONS = f"rtsp_transport;tcp|{_LOW_LATENCY_OPTS}"


def is_rtsp(source: int | str) -> bool:
    """True for RTSP stream URLs (vs a USB webcam index or a file path)."""
    return isinstance(source, str) and source.startswith("rtsp")


def build_ffmpeg_options(
    transport: str = "tcp",
    timeout_seconds: float = 0.0,
    override: str | None = None,
    low_latency: bool = True,
) -> str:
    """Build the OPENCV_FFMPEG_CAPTURE_OPTIONS value for an RTSP stream.

    ``transport`` selects rtsp_transport (tcp is correct for almost all cameras;
    udp only on a clean LAN, but lower latency). ``timeout_seconds`` maps to
    FFmpeg's ``stimeout`` (socket I/O timeout, in microseconds) so a dead or
    unreachable camera makes ``read()``/open fail and trip the reconnect backoff
    instead of blocking the capture thread forever. ``low_latency`` adds the
    nobuffer / no-reorder flags that keep the live preview close to real time.
    ``override`` short-circuits to a verbatim options string for FFmpeg builds
    that spell these keys differently (e.g. newer FFmpeg uses ``timeout`` rather
    than ``stimeout``).
    """
    if override:
        return override
    parts = [f"rtsp_transport;{transport}"]
    if low_latency:
        parts.append(_LOW_LATENCY_OPTS)
    if timeout_seconds and timeout_seconds > 0:
        parts.append(f"stimeout;{int(timeout_seconds * 1_000_000)}")
    return "|".join(parts)


def _mask_source(source: int | str) -> str:
    """Redact credentials in an rtsp://user:pass@host URL for safe logging."""
    if is_rtsp(source) and "@" in source:
        scheme, rest = source.split("://", 1)
        if "@" in rest:
            return f"{scheme}://***@{rest.split('@', 1)[1]}"
    return str(source)


def _apply_ffmpeg_options(source: int | str, options: str | None) -> None:
    """Set FFmpeg capture options for RTSP before OpenCV builds the capture.

    The env var is only read at VideoCapture construction, so set it first.
    setdefault keeps any operator override (exported in the environment) intact.
    """
    if is_rtsp(source):
        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS", options or _DEFAULT_RTSP_OPTIONS
        )


class FrameSource:
    """Threaded grabber keeping only the latest frame, with backoff reconnect.

    Decouples camera FPS from inference FPS: without this, RTSP frames queue
    in the FFmpeg buffer while inference runs and lag grows unbounded.
    ``read()`` consumes the latest frame; ``None`` means nothing new yet.
    """

    def __init__(
        self,
        source: int | str,
        open_fn: Callable[[int | str], Any] | None = None,
        *,
        ffmpeg_options: str | None = None,
    ):
        _apply_ffmpeg_options(source, ffmpeg_options)
        _open_fn: Callable[[int | str], Any]
        if open_fn is None:  # pragma: no cover - real cv2 only outside tests
            import cv2

            def _open_fn(s: int | str) -> Any:
                # Pin the FFmpeg backend for URL streams; let OpenCV pick the
                # native backend (V4L2/AVFoundation/DSHOW) for webcam indices.
                if isinstance(s, str):
                    cap = cv2.VideoCapture(s, cv2.CAP_FFMPEG)
                else:
                    cap = cv2.VideoCapture(s)
                # Keep at most one decoded frame queued so read() returns the
                # freshest frame, not one from the back of a buffer (latency).
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:  # pragma: no cover - backend may not support it
                    pass
                return cap
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
            _mask_source(self._source),
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
