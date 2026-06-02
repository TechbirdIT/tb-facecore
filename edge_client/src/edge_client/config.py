"""Load and validate edge client YAML config."""

from __future__ import annotations

from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class EdgeConfig:
    frappe_url: str
    site: str
    api_key: str
    api_secret: str
    edge_id: str
    camera_index: int
    sync_interval: int
    threshold: float
    liveness_threshold: float
    min_det_score: float
    debounce_minutes: int
    db_path: str


def load_config(path: str) -> EdgeConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return EdgeConfig(
        frappe_url=raw["frappe"]["url"],
        site=raw["frappe"]["site"],
        api_key=raw["frappe"]["api_key"],
        api_secret=raw["frappe"]["api_secret"],
        edge_id=raw["edge"]["id"],
        camera_index=raw["edge"]["camera_index"],
        sync_interval=raw["edge"]["sync_interval"],
        threshold=raw["matching"]["threshold"],
        liveness_threshold=raw["matching"]["liveness_threshold"],
        min_det_score=raw["matching"]["min_det_score"],
        debounce_minutes=raw["matching"]["debounce_minutes"],
        db_path=raw["offline"]["db_path"],
    )
