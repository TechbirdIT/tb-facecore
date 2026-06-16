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
    # Multi-camera: when set, this process runs one capture loop per camera,
    # sharing the loaded face models. Each entry is (camera_id, source). When
    # None, the single edge_id + camera_source above is used.
    cameras: tuple | None = None
    # How often a present employee is recorded as a sighting (presence sampling).
    # Server-side punch_debounce gates HR check-ins, so this can be fine.
    sighting_interval_seconds: float = 60.0
    # Annotated MJPEG preview for the operator console. Opt-in; zero overhead off.
    # When on, the recognition loop draws real boxes/identities and serves them at
    # http://<host>:<port>/<camera_id>.mjpg (sub-second, browser-displayable).
    preview_enabled: bool = False
    preview_host: str = "127.0.0.1"
    preview_port: int = 9101
    preview_fps: float = 12.0
    preview_scale: float = 0.75
    preview_jpeg_quality: int = 70
    # Estimate age + gender per track (buffalo_l genderage, a few ms). Off by
    # default; the operator console enables it so the live boxes show age/gender.
    # Emotion/race are NOT here — they run offline via /api/demography.
    analyze_demographics: bool = False


def _resolve_edge_id(edge: dict, cameras: tuple | None) -> str:
    if "id" in edge:
        return edge["id"]
    if cameras:
        return cameras[0][0]
    return edge["id"]  # raise KeyError: id required when no cameras list


def _resolve_camera_source(edge: dict, cameras: tuple | None):
    # explicit membership checks: camera_source may legitimately be 0 (webcam)
    if "camera_source" in edge:
        return edge["camera_source"]
    if "camera_index" in edge:  # legacy key
        return edge["camera_index"]
    if cameras:
        return cameras[0][1]
    return edge["camera_source"]  # raise KeyError: required when no cameras list


def load_config(path: str) -> EdgeConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    edge = raw["edge"]
    raw_cams = edge.get("cameras")
    cameras = (
        tuple((c["id"], c["source"]) for c in raw_cams) if raw_cams else None
    )
    return EdgeConfig(
        frappe_url=raw["frappe"]["url"],
        site=raw["frappe"]["site"],
        api_key=raw["frappe"]["api_key"],
        api_secret=raw["frappe"]["api_secret"],
        edge_id=_resolve_edge_id(edge, cameras),
        camera_source=_resolve_camera_source(edge, cameras),
        cameras=cameras,
        sync_interval=raw["edge"]["sync_interval"],
        threshold=raw["matching"]["threshold"],
        liveness_threshold=raw["matching"]["liveness_threshold"],
        min_det_score=raw["matching"]["min_det_score"],
        debounce_minutes=raw["matching"]["debounce_minutes"],
        db_path=raw["offline"]["db_path"],
        rtsp_transport=raw["edge"].get("rtsp_transport", "tcp"),
        rtsp_timeout_seconds=raw["edge"].get("rtsp_timeout_seconds", 10.0),
        ffmpeg_capture_options=raw["edge"].get("ffmpeg_capture_options"),
        sighting_interval_seconds=raw["edge"].get("sighting_interval_seconds", 60.0),
        preview_enabled=raw.get("preview", {}).get("enabled", False),
        preview_host=raw.get("preview", {}).get("host", "127.0.0.1"),
        preview_port=raw.get("preview", {}).get("port", 9101),
        preview_fps=raw.get("preview", {}).get("fps", 12.0),
        preview_scale=raw.get("preview", {}).get("scale", 0.75),
        preview_jpeg_quality=raw.get("preview", {}).get("jpeg_quality", 70),
        analyze_demographics=raw.get("demographics", {}).get("enabled", False),
        track_iou_threshold=raw.get("tracking", {}).get("iou_threshold", 0.3),
        track_max_misses=raw.get("tracking", {}).get("max_misses", 15),
        reverify_seconds=raw.get("tracking", {}).get("reverify_seconds", 30.0),
        acquire_fast_seconds=raw.get("tracking", {}).get("acquire_fast_seconds", 2.0),
        acquire_backoff_seconds=raw.get("tracking", {}).get(
            "acquire_backoff_seconds", 1.0
        ),
    )
