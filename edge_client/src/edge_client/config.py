"""Load and validate edge client YAML config."""

from __future__ import annotations

from dataclasses import dataclass

import yaml  # type: ignore[import-untyped]


@dataclass(frozen=True)
class EdgeConfig:
    frappe_url: str
    site: str
    api_key: str
    api_secret: str
    edge_id: str
    camera_source: int | str
    sync_interval: int
    threshold: float
    liveness_threshold: float
    min_det_score: float
    debounce_minutes: int
    db_path: str
    # RTSP-only knobs; ignored for webcam (int) sources. Defaults give a safe
    # TCP + 10s socket timeout so an unreachable camera reconnects rather than
    # hangs. ffmpeg_capture_options, if set, overrides transport/timeout verbatim.
    rtsp_transport: str = "tcp"
    rtsp_timeout_seconds: float = 10.0
    ffmpeg_capture_options: str | None = None
    # Tracking: detection runs every frame; a face is embedded + matched once per
    # track, then re-verified every reverify_seconds to catch IoU id-swaps.
    track_iou_threshold: float = 0.3
    track_max_misses: int = 15
    reverify_seconds: float = 30.0
    # Acquisition: an unidentified track retries every frame for the first
    # acquire_fast_seconds (a real face locks on instantly), then backs off to
    # once per acquire_backoff_seconds so a lingering unknown face stops embedding
    # every frame.
    acquire_fast_seconds: float = 2.0
    acquire_backoff_seconds: float = 1.0


def load_config(path: str) -> EdgeConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return EdgeConfig(
        frappe_url=raw["frappe"]["url"],
        site=raw["frappe"]["site"],
        api_key=raw["frappe"]["api_key"],
        api_secret=raw["frappe"]["api_secret"],
        edge_id=raw["edge"]["id"],
        camera_source=(
            raw["edge"]["camera_source"]
            if "camera_source" in raw["edge"]
            else raw["edge"]["camera_index"]  # legacy key
        ),
        sync_interval=raw["edge"]["sync_interval"],
        threshold=raw["matching"]["threshold"],
        liveness_threshold=raw["matching"]["liveness_threshold"],
        min_det_score=raw["matching"]["min_det_score"],
        debounce_minutes=raw["matching"]["debounce_minutes"],
        db_path=raw["offline"]["db_path"],
        rtsp_transport=raw["edge"].get("rtsp_transport", "tcp"),
        rtsp_timeout_seconds=raw["edge"].get("rtsp_timeout_seconds", 10.0),
        ffmpeg_capture_options=raw["edge"].get("ffmpeg_capture_options"),
        track_iou_threshold=raw.get("tracking", {}).get("iou_threshold", 0.3),
        track_max_misses=raw.get("tracking", {}).get("max_misses", 15),
        reverify_seconds=raw.get("tracking", {}).get("reverify_seconds", 30.0),
        acquire_fast_seconds=raw.get("tracking", {}).get("acquire_fast_seconds", 2.0),
        acquire_backoff_seconds=raw.get("tracking", {}).get(
            "acquire_backoff_seconds", 1.0
        ),
    )
