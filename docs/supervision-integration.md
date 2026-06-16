# Integrating Roboflow `supervision` with tb-facecore

**Status:** analysis / proposal — not yet implemented
**Scope:** the AI/edge stack (this repo), primarily `edge_client`
**Library:** [`roboflow/supervision`](https://github.com/roboflow/supervision) v0.28.0 (MIT)

---

## 1. What `supervision` is (and is not)

`supervision` is a model-agnostic computer-vision **utility toolkit**. It does not
detect faces, compute embeddings, or do anti-spoofing. It provides plumbing around
*any* detector's output:

- `sv.Detections` — a standard container (xyxy boxes, confidence, class_id, `tracker_id`, arbitrary `data`)
- **Trackers** — `sv.ByteTrack` (motion/IoU association → stable `tracker_id` per object across frames)
- **Zones** — `sv.PolygonZone` (region gating), `sv.LineZone` (directional line crossing counts)
- **Annotators** — `BoxAnnotator`, `LabelAnnotator`, `TraceAnnotator`, etc. (debug/preview overlays)
- **Filtering** — confidence/area filters, NMS, `DetectionsSmoother`
- **Video I/O** — `get_video_frames_generator`, `VideoInfo`, `VideoSink`, `FPSMonitor`

Crucially: ByteTrack is **appearance-blind**. It associates by box motion, not identity.
It complements — never replaces — our ArcFace embedding match and MiniFASNet liveness.

---

## 2. Compatibility

| Concern | tb-facecore | supervision 0.28.0 | Verdict |
|---|---|---|---|
| License | MIT | MIT | ✅ compatible |
| Python | 3.11 | `>=3.9` | ✅ |
| numpy / opencv / requests / pyyaml | already deps | shared | ✅ already present |
| **New transitive deps** | — | `matplotlib`, `scipy`, `pillow`, `defusedxml`, `pydeprecate`, `tqdm` | ⚠️ footprint (§4) |

---

## 3. Integration points

All high-value seams are in **`edge_client`**. `facecore` and `embedding_service`
should stay untouched (see §3.5).

### 3.1 `edge_client/capture.py::process_frame` — the primary seam ★

Today the loop matches **every face in every frame** and relies on a per-device
**time** `Debouncer`:

```python
for face in analyzer.analyze(frame):
    if face.liveness_score < cfg.liveness_threshold: continue
    result = matcher.match(face.embedding, threshold=cfg.threshold)   # runs every frame
    ...
    if not debouncer.allow(device_id, now): continue
```

With tracking, faces get a stable `tracker_id`, so identity is resolved **once per
track** instead of once per frame:

```python
import supervision as sv

# adapter: facecore DetectedFace[] -> sv.Detections
def to_detections(faces):
    if not faces:
        return sv.Detections.empty()
    return sv.Detections(
        xyxy=np.array([f.bbox for f in faces], dtype=float),
        confidence=np.array([f.det_score for f in faces], dtype=float),
        data={"embedding": [f.embedding for f in faces],
              "liveness": np.array([f.liveness_score for f in faces])},
    )

# once, in run_capture:
tracker = sv.ByteTrack()
track_identity: dict[int, tuple[str, float]] = {}   # tracker_id -> (device_id, score)

# per frame:
dets = to_detections(analyzer.analyze(frame))
dets = dets[dets.confidence > cfg.min_det_score]      # filter
dets = dets[dets.data["liveness"] >= cfg.liveness_threshold]
dets = tracker.update_with_detections(dets)           # assigns tracker_id

for i, tid in enumerate(dets.tracker_id):
    if tid not in track_identity:                     # match ONCE per track
        res = matcher.match(dets.data["embedding"][i], threshold=cfg.threshold)
        if res: track_identity[tid] = res
    if tid in track_identity and debouncer.allow(track_identity[tid][0], now):
        device_id, score = track_identity[tid]
        client.post_event(...)
```

**Wins:** matching cost drops from O(faces × frames) to ~O(tracks); clean handling of
several simultaneous faces; far fewer redundant events; debounce becomes "once per
continuous presence" rather than a blind time window.

### 3.2 `edge_client/matcher.py` — identity caching layer
`Matcher` is unchanged. Tracking sits *above* it: map `tracker_id → device_id` after
the first confident match and reuse it for the track's lifetime. **Guard rail:** ByteTrack
can swap IDs under occlusion/crossing, so re-verify the embedding every N seconds (or on
low-confidence frames) before trusting a cached identity — never post on track id alone.

### 3.3 Zones — optional
- `sv.PolygonZone`: only recognize faces inside a painted region (ignore the back of a room / passers-by). Low-risk, useful.
- `sv.LineZone`: count/declare IN vs OUT by crossing direction. **Caution:** the Frappe
  side already derives IN/OUT server-side via the shift engine. Driving log_type from
  LineZone would duplicate/contend with that authority. Treat as a hint at most, or skip.

### 3.4 Annotators + `VideoSink` — debug & ops
`BoxAnnotator` + `LabelAnnotator` (name + similarity + liveness overlay), `TraceAnnotator`
(motion trails), and `VideoSink` to record short clips around events. High value for
field debugging, building a `--preview` mode, or feeding the admin **LiveFeed**. Keep
behind a flag (needs a display / writable disk; pulls `matplotlib`).

### 3.5 `facecore` — do **not** integrate ★
`facecore` is deliberately "pure AI engine — no I/O, no Frappe, no web." Adding
`supervision` (with matplotlib/scipy) there violates that boundary and bloats the shared
lib. If a convenience adapter is wanted, keep `to_detections()` in `edge_client`, or
expose it under an optional extra — never as a core `facecore` dependency.

### 3.6 RTSP test rig (`docs/how-to.md` §9–10)
`sv.get_video_frames_generator` / `VideoInfo` / `FPSMonitor` simplify file/RTSP
*test harnesses*. The production `camera.py::FrameSource` uses threaded live capture and
should stay as-is; supervision's pull-generator suits batch/replay testing, not the live loop.

---

## 4. Consequences & drawbacks

1. **Edge dependency footprint.** `matplotlib` + `scipy` + `pillow` add tens of MB and
   build/runtime weight to an edge image that today is numpy+opencv+onnxruntime. `matplotlib`
   import also adds measurable cold-start latency. → Gate behind an optional extra
   (`pip install -e "edge_client[tracking]"`) so headless deployments can skip it.
2. **opencv-python vs -headless.** Both this project and supervision depend on
   `opencv-python` (full GUI build). On headless kiosks you typically want
   `opencv-python-headless`; mixing both is a known footgun. Pick one consistently and pin it.
3. **0.x API churn.** supervision moves fast and deprecates across minor versions (it ships
   `pydeprecate`). Annotator names and `Detections` semantics have changed historically.
   → **Pin an exact version**; budget for migration on upgrades.
4. **No identity / re-ID.** ByteTrack is motion-based. Track-ID swaps under occlusion or
   crossing paths can mislabel a cached identity. Mitigation (§3.2) is mandatory, which adds
   complexity the current code doesn't have.
5. **Behavioral/semantic change to events.** Moving from time-debounce to track-based gating
   changes when events fire. The existing `Debouncer` is tiny and unit-tested; tracking adds
   cross-frame state that's harder to test deterministically. → Make it **additive** (track gate
   *and* keep the time debounce as a backstop), and add new tests.
6. **IN/OUT authority.** LineZone overlaps the server-side shift engine (§3.3) — risk of two
   sources of truth. Keep Frappe authoritative.
7. **Liveness unchanged.** supervision contributes nothing to anti-spoofing; MiniFASNet stays
   the only liveness gate.
8. **Supply chain / CI.** More packages to audit and a slower install/CI. License is clean (MIT).

---

## 5. Recommendation (phased, edge-only, optional dependency)

| Phase | Change | Risk | Value |
|---|---|---|---|
| **1** | `sv.ByteTrack` + `tracker_id→identity` cache + confidence/liveness filtering in `process_frame` | Med (event semantics, ID-swap guard) | **High** — less CPU, fewer dup events, multi-face |
| **2** | Annotators + `VideoSink` `--preview`/debug mode | Low | High for ops/debugging |
| **3** | `sv.PolygonZone` recognition region | Low | Situational |
| **—** | `sv.LineZone` IN/OUT, any `facecore` dependency | — | **Avoid** (conflicts with shift engine / purity) |

**Do:** add as `edge_client` **optional extra**, pin the exact version, keep `facecore` clean,
ship the ID-swap re-verification guard and tests with Phase 1.
**Don't:** put it on the hot path of `facecore`, let LineZone fight the shift engine, or mix
full + headless OpenCV.

---

## 6. One-line verdict
`supervision` is a clean, MIT-licensed, **additive** win for the `edge_client` recognition
loop — primarily ByteTrack-driven "match once per track" — provided it's an optional edge
dependency, version-pinned, kept out of `facecore`, and paired with an identity re-verification
guard. It does not replace ArcFace matching or MiniFASNet liveness.
