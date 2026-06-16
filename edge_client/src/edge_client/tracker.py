"""Lightweight, dependency-free IoU tracker for the recognition loop.

Detection runs every frame (cheap); embedding + matching are the expensive,
repetitive steps we want to avoid. This tracker assigns a stable id to each face
across frames by greedy IoU association, so the loop can recognize a face *once
per track* and then just follow it — instead of re-embedding every frame.

Deliberately tiny and pure (no numpy/scipy/supervision): an edge box stays slim.
ByteTrack-grade association (Kalman + appearance) is overkill for a handful of
faces at a kiosk; IoU on consecutive frames is enough and trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


def iou(a: list[float], b: list[float]) -> float:
    """Intersection-over-union of two [x1, y1, x2, y2] boxes."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0.0 else 0.0


@dataclass
class Track:
    """One tracked face. Identity is resolved lazily and cached here."""

    id: int
    bbox: list[float]
    # Recognition state, filled by the capture loop (not the tracker):
    identity: tuple[str, float] | None = None  # (attendance_device_id, similarity)
    first_attempt: datetime | None = None        # when this track first tried to recognize
    last_verified: datetime | None = None       # when embed+match last ran
    last_liveness: float = 0.0
    spoof: bool = False                          # last liveness check failed
    misses: int = 0                              # consecutive frames unmatched
    age: int = 0                                 # frames seen
    logged_debounce: bool = False                # debounce already logged once
    # Demographics (buffalo_l genderage), cached per track when enabled. Named
    # est_* so they don't clash with `age` above (which counts frames seen).
    est_age: int | None = None
    est_gender: str | None = None


@dataclass
class Tracker:
    """Greedy IoU tracker. Stateful across frames.

    ``update(boxes)`` matches the current detections to existing tracks, spawns
    tracks for new faces, ages out tracks that have been unmatched for more than
    ``max_misses`` frames, and returns the ``(Track, box_index)`` pairs visible
    this frame so the caller can act on each with its persistent Track.
    """

    iou_threshold: float = 0.3
    max_misses: int = 15
    _next_id: int = 1
    _tracks: dict[int, Track] = field(default_factory=dict)

    def update(self, boxes: list[list[float]]) -> list[tuple[Track, int]]:
        tracks = list(self._tracks.values())
        # Candidate (iou, track, box_index) pairs above threshold, best first.
        pairs = sorted(
            (
                (iou(t.bbox, boxes[j]), t, j)
                for t in tracks
                for j in range(len(boxes))
                if iou(t.bbox, boxes[j]) >= self.iou_threshold
            ),
            key=lambda p: p[0],
            reverse=True,
        )
        used_tracks: set[int] = set()
        used_boxes: set[int] = set()
        visible: list[tuple[Track, int]] = []

        for _, track, j in pairs:  # greedy: highest-IoU assignments win
            if track.id in used_tracks or j in used_boxes:
                continue
            used_tracks.add(track.id)
            used_boxes.add(j)
            track.bbox = boxes[j]
            track.misses = 0
            track.age += 1
            visible.append((track, j))

        for j in range(len(boxes)):  # unmatched detections → new tracks
            if j in used_boxes:
                continue
            track = Track(id=self._next_id, bbox=boxes[j], age=1)
            self._next_id += 1
            self._tracks[track.id] = track
            visible.append((track, j))

        for track in tracks:  # unmatched existing tracks age out
            if track.id not in used_tracks:
                track.misses += 1
                if track.misses > self.max_misses:
                    del self._tracks[track.id]

        return visible

    @property
    def active(self) -> int:
        return len(self._tracks)
