"""Per-frame recognition core and the capture loop."""

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


def _needs_recognition(track, cfg, now: datetime) -> bool:
    """Retry until a track is identified, then re-verify only periodically.

    Acquisition must be fast: a not-yet-identified track — new, or whose last
    attempt failed liveness/match (a poorly framed first glimpse, score 0.12) —
    is retried EVERY frame until it locks on. Stamping last_verified on a failed
    attempt (as before) froze an unrecognized face for reverify_seconds, which is
    why it took so long to pick up a face.

    Once identified, switch to the slow cadence: re-embed every reverify_seconds
    to guard against IoU id-swaps (tracking is appearance-blind), without paying
    the embedding cost every frame.
    """
    if track.identity is None:
        return True
    return (now - track.last_verified).total_seconds() >= cfg.reverify_seconds


def process_frame(
    frame, analyzer, matcher, tracker, debouncer, client, store, cfg, now: datetime
) -> None:
    """One frame: detect → track → (embed+match once per track / re-verify) →
    debounce → event/enqueue.

    Detection runs every frame (cheap); the expensive embedding + match run only
    for new or due-for-re-verification tracks, not for every face every frame.
    """
    boxes = analyzer.detect(frame)
    for track, idx in tracker.update([b.bbox for b in boxes]):
        if _needs_recognition(track, cfg, now):
            face = boxes[idx]
            live = analyzer.liveness(frame, face.bbox)
            track.last_verified = now
            track.last_liveness = live
            if live < cfg.liveness_threshold:
                track.spoof = True
                track.identity = None
                logger.debug("track %d liveness %.2f below threshold", track.id, live)
                continue
            track.spoof = False
            track.identity = matcher.match(analyzer.embed(frame, face), cfg.threshold)

        if track.identity is None:
            continue
        device_id, score = track.identity
        if not debouncer.allow(device_id, now):
            if not track.logged_debounce:  # log once per track, not every frame
                logger.debug("debounced %s (track %d)", device_id, track.id)
                track.logged_debounce = True
            continue
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        try:
            client.post_event(
                cfg.edge_id, device_id, timestamp, score, track.last_liveness
            )
            track.logged_debounce = False  # allow one debounce log after this post
            logger.info(
                "event posted for %s (score %.3f, track %d)", device_id, score, track.id
            )
        except Exception:
            logger.warning("event post failed for %s; enqueueing offline", device_id)
            store.enqueue_event(device_id, timestamp, score, track.last_liveness)


def run_capture(
    analyzer, client, store, cfg, model_version: str
) -> None:  # pragma: no cover
    """Capture loop. Thin I/O glue around FrameSource + process_frame + sync."""
    from edge_client.camera import FrameSource, build_ffmpeg_options
    from edge_client.debounce import Debouncer
    from edge_client.tracker import Tracker

    debouncer = Debouncer(cfg.debounce_minutes)
    tracker = Tracker(
        iou_threshold=cfg.track_iou_threshold, max_misses=cfg.track_max_misses
    )
    matcher = sync_faces(client, store, model_version)
    last_sync = time.monotonic()
    ffmpeg_options = build_ffmpeg_options(
        cfg.rtsp_transport, cfg.rtsp_timeout_seconds, cfg.ffmpeg_capture_options
    )
    source = FrameSource(cfg.camera_source, ffmpeg_options=ffmpeg_options)
    source.start()
    try:
        while True:
            frame = source.read()
            if frame is None:
                time.sleep(0.01)  # nothing new; don't spin
            else:
                process_frame(
                    frame,
                    analyzer,
                    matcher,
                    tracker,
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
        source.release()
