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

    Unidentified tracks acquire in two phases so a lingering *unknown* face does
    not burn an embedding every frame forever: aggressive (every frame) for the
    first acquire_fast_seconds so a real face locks on instantly, then backed off
    to once per acquire_backoff_seconds.
    """
    if track.identity is not None:
        return (now - track.last_verified).total_seconds() >= cfg.reverify_seconds
    if track.first_attempt is None:
        return True  # brand-new track: try immediately
    if (now - track.first_attempt).total_seconds() < cfg.acquire_fast_seconds:
        return True  # fast acquisition window
    return (now - track.last_verified).total_seconds() >= cfg.acquire_backoff_seconds


def process_frame(
    frame, analyzer, matcher, tracker, debouncer, client, store, cfg, now: datetime,
    on_event=None,
) -> list:
    """One frame: detect → track → (embed+match once per track / re-verify) →
    debounce → event/enqueue.

    Detection runs every frame (cheap); the expensive embedding + match run only
    for new or due-for-re-verification tracks, not for every face every frame.

    Returns the tracks visible this frame (with their current bbox/identity/
    liveness state) so a caller can render an annotated preview.
    """
    boxes = analyzer.detect(frame)
    visible = tracker.update([b.bbox for b in boxes])
    for track, idx in visible:
        if _needs_recognition(track, cfg, now):
            face = boxes[idx]
            if track.first_attempt is None:
                track.first_attempt = now
            live = analyzer.liveness(frame, face.bbox)
            track.last_verified = now
            track.last_liveness = live
            if live < cfg.liveness_threshold:
                track.spoof = True
                track.identity = None
                logger.debug("track %d liveness %.2f below threshold", track.id, live)
                continue
            track.spoof = False
            if cfg.analyze_demographics:
                # cheap genderage pass, once per recognition cycle (like embed);
                # unknown faces get demographics too, so do it before matching.
                track.est_age, track.est_gender = analyzer.gender_age(frame, face)
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
            if on_event is not None:
                on_event(
                    cfg.edge_id, device_id, timestamp, score, track.last_liveness,
                    age=track.est_age, gender=track.est_gender,
                )
        except Exception:
            logger.warning("event post failed for %s; enqueueing offline", device_id)
            store.enqueue_event(
                device_id, timestamp, score, track.last_liveness, cfg.edge_id
            )

    return [track for track, _idx in visible]


def resolve_cameras(cfg) -> list[tuple[str, object]]:
    """The (camera_id, source) pairs this process should run.

    Multi-camera: cfg.cameras is a list of (id, source). Single-camera (legacy):
    one pair from cfg.edge_id + cfg.camera_source.
    """
    if cfg.cameras:
        return [(cid, src) for cid, src in cfg.cameras]
    return [(cfg.edge_id, cfg.camera_source)]


def _sighting_window_minutes(cfg) -> float:
    """How often (in minutes) the edge posts a sighting per employee — the
    presence-sampling cadence. Server-side punch_debounce gates HR check-ins, so
    this can be finer (seconds) without causing duplicate check-ins."""
    seconds = cfg.sighting_interval_seconds or (cfg.debounce_minutes * 60)
    return seconds / 60.0


def _camera_loop(cam_id, source_spec, shared, analyzer, client, store, cfg, stop):  # pragma: no cover
    """One camera's capture loop: its own FrameSource + Tracker + Debouncer, but
    the analyzer, matcher (via `shared`), client and store are shared across all
    cameras in this process — so the face models load once."""
    from dataclasses import replace

    from edge_client.camera import FrameSource, build_ffmpeg_options
    from edge_client.debounce import Debouncer
    from edge_client.tracker import Tracker

    cam_cfg = replace(cfg, edge_id=cam_id, camera_source=source_spec)
    tracker = Tracker(
        iou_threshold=cfg.track_iou_threshold, max_misses=cfg.track_max_misses
    )
    debouncer = Debouncer(_sighting_window_minutes(cfg))
    ffmpeg_options = build_ffmpeg_options(
        cfg.rtsp_transport, cfg.rtsp_timeout_seconds, cfg.ffmpeg_capture_options
    )
    source = FrameSource(source_spec, ffmpeg_options=ffmpeg_options)
    source.start()

    preview = shared.get("preview")
    preview_period = 1.0 / cfg.preview_fps if (preview and cfg.preview_fps) else 0.0
    last_preview = 0.0
    raw_store = shared.get("raw")  # latest raw frame per camera, for offline demography

    logger.info("camera loop started: %s", cam_id)
    try:
        while not stop.is_set():
            frame = source.read()
            if frame is None:
                time.sleep(0.01)
                continue
            if raw_store is not None:
                raw_store[cam_id] = frame
            tracks = process_frame(
                frame, analyzer, shared["matcher"], tracker, debouncer,
                client, store, cam_cfg, now=datetime.now(),
                on_event=shared.get("on_event"),
            )
            if preview is not None:
                mono = time.monotonic()
                if mono - last_preview >= preview_period:
                    last_preview = mono
                    from edge_client.preview import annotate, encode_jpeg

                    jpeg = encode_jpeg(
                        annotate(frame, tracks),
                        quality=cfg.preview_jpeg_quality, scale=cfg.preview_scale,
                    )
                    if jpeg is not None:
                        preview.publish(cam_id, jpeg)
    finally:
        source.release()


def run_capture(
    analyzer, client, store, cfg, model_version: str
) -> None:  # pragma: no cover
    """Run one capture loop per camera (sharing the analyzer + matcher), plus a
    central sync/heartbeat tick. One camera or many — same path."""
    import threading

    cameras = resolve_cameras(cfg)
    shared = {"matcher": sync_faces(client, store, model_version)}

    preview_server = None
    if cfg.preview_enabled:
        from edge_client.preview import PreviewServer

        preview_server = PreviewServer(cfg.preview_host, cfg.preview_port)
        preview_server.start()
        shared["preview"] = preview_server

    stop = threading.Event()
    threads = [
        threading.Thread(
            target=_camera_loop,
            args=(cam_id, src, shared, analyzer, client, store, cfg, stop),
            daemon=True,
        )
        for cam_id, src in cameras
    ]
    for t in threads:
        t.start()
    logger.info("started %d camera loop(s)", len(threads))

    last_sync = time.monotonic()
    try:
        while True:
            time.sleep(0.5)
            if time.monotonic() - last_sync >= cfg.sync_interval:
                shared["matcher"] = sync_faces(client, store, model_version)
                flush_queue(client, store, cfg.edge_id)
                for cam_id, _src in cameras:
                    try:
                        client.heartbeat(cam_id, _APP_VERSION)
                    except Exception:
                        logger.debug("heartbeat failed for %s; will retry", cam_id)
                last_sync = time.monotonic()
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=2.0)
        if preview_server is not None:
            preview_server.stop()
