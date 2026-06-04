"""Per-frame recognition core and the OpenCV capture loop."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version

from edge_client.sync import flush_queue, sync_faces

try:
    _APP_VERSION = version("edge-client")
except PackageNotFoundError:  # editable/dev install
    _APP_VERSION = "dev"

logger = logging.getLogger(__name__)


def process_frame(
    frame, analyzer, matcher, debouncer, client, store, cfg, now: datetime
) -> None:
    """Handle one frame: detect → liveness → match → debounce → event/enqueue."""
    for face in analyzer.analyze(frame):
        if face.liveness_score < cfg.liveness_threshold:
            logger.debug("liveness %.2f below threshold; skipping", face.liveness_score)
            continue
        result = matcher.match(face.embedding, threshold=cfg.threshold)
        if result is None:
            continue
        device_id, score = result
        if not debouncer.allow(device_id, now):
            logger.debug("debounced %s", device_id)
            continue
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        try:
            client.post_event(
                cfg.edge_id, device_id, timestamp, score, face.liveness_score
            )
            logger.info("event posted for %s (score %.3f)", device_id, score)
        except Exception:
            logger.warning("event post failed for %s; enqueueing offline", device_id)
            store.enqueue_event(device_id, timestamp, score, face.liveness_score)


def run_capture(
    analyzer, client, store, cfg, model_version: str
) -> None:  # pragma: no cover
    """OpenCV read loop. Thin I/O glue around process_frame + periodic sync/flush."""
    import cv2

    from edge_client.debounce import Debouncer

    debouncer = Debouncer(cfg.debounce_minutes)
    matcher = sync_faces(client, store, model_version)
    last_sync = time.monotonic()
    cap = cv2.VideoCapture(cfg.camera_index)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                logger.warning("camera read failed; retrying")
                time.sleep(1.0)
                if not cap.isOpened():
                    cap.open(cfg.camera_index)
                continue
            process_frame(
                frame,
                analyzer,
                matcher,
                debouncer,
                client,
                store,
                cfg,
                now=datetime.now(),
            )
            if time.monotonic() - last_sync >= cfg.sync_interval:
                matcher = sync_faces(client, store, model_version)
                flush_queue(client, store, cfg.edge_id)
                try:
                    client.heartbeat(cfg.edge_id, _APP_VERSION)
                except Exception:
                    logger.debug("heartbeat failed; will retry next tick")
                last_sync = time.monotonic()
    finally:
        cap.release()
