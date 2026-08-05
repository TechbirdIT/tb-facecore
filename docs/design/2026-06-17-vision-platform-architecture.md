# Vision Platform Architecture

**Status:** Proposed · **Date:** 2026-06-17 · **Supersedes:** none (extends [`architecture.md`](architecture.md))

This document defines the target architecture for evolving tb-facecore from a
single-purpose **face-attendance** stack into a modular, multi-tenant **computer-vision
platform**: a shared vision core (camera + CCTV discovery, biometrics, face recognition,
object detection, image analysis) with separately installable, customer-facing use-case
modules (HRMS attendance, ERPNext invoice/item detection, hotel minibar detection, and
future client-specific use cases), offered as SaaS.

It records the current state, the recommended production architecture, a phased roadmap,
and the risks — grounded in the existing code/docs and in current (2025–26) research. Where
a claim depends on external research, a source is cited inline.

---

## 1. Where we are today

Two repositories, two natures:

| | `tb_face_attendance` | `tb-facecore` (this repo) |
|---|---|---|
| Nature | A real Frappe v16 **app** | A standalone **Python AI/edge stack** (not a Frappe app) |
| Contents | DocTypes, approval workflow, sync/event/heartbeat REST APIs, role fixtures, `/face` frappe-ui SPA | `facecore` (pure engine) · `embedding_service` (FastAPI) · `edge_client` (edge app + operator console) |
| Runtime | In-bench, Python 3.14 | Separate venv, Python 3.11 (InsightFace/ONNX pin) |
| Role | System of record + control plane | Inference + camera capture + recognition loop |

The two are deliberately decoupled — Frappe never imports InsightFace; it calls the
embedding microservice over HTTP. The operator console in `edge_client` is a vanilla
`ThreadingHTTPServer` + static HTML + MJPEG, **not** frappe-ui.

### Strengths to build on

- Clean four-unit decoupling; `facecore`'s `detect() / embed() / liveness()` split is the
  right shape (detect every frame, embed once per track).
- `edge_client` infrastructure is **task-neutral and the most valuable reusable asset**:
  `FrameSource` (RTSP/webcam + exponential reconnect), IoU `Tracker`, `Store` (SQLite
  queue), `Engine` lifecycle/threads, `FrameHub`/MJPEG preview, `FrappeClient`, hot-reload.

### Structural blockers to a multi-task platform

1. **InsightFace is hardwired into `FaceAnalyzer`** (reaches into `self._app.det_model`,
   `models["recognition"]`, `models["genderage"]`). No `Detector`/`Embedder`/`Backend`
   interface; `MODEL_VERSION` is a module constant. *Biggest blocker.*
2. **Face-only data contract** (`DetectedFace`: embedding/liveness/age/gender) — no generic
   `Detection { bbox, score, class, landmarks?, embedding?, attributes{} }`.
3. **Hardcoded pipeline** — `capture.py::process_frame` wires capture→track→liveness→match
   →debounce→post imperatively; stages are not pluggable.

### Production gaps (fix before scaling)

- **Accuracy is never validated** — integration-test `fixtures/` is empty; no CI guard on
  recognition/liveness correctness.
- **Edge console control API is unauthenticated** with `Access-Control-Allow-Origin: *` and
  reads/writes **plaintext Frappe + RTSP credentials** over HTTP.
- **SQLite event queue is unbounded, no WAL**; `flush_queue` has no backoff — a long Frappe
  outage can exhaust edge disk.
- **Embedding service runs sync CPU inference on the async event loop** (no
  `run_in_threadpool`) → serializes under load.
- **No camera discovery** — every camera is a hand-typed RTSP URL in `config.yaml`.

### Two assumptions that must be corrected

- 🔴 **"Embeddings are one-way / cannot reconstruct a face" is false.** Current research
  reconstructs faces from embeddings at **95.69% re-match** against ArcFace
  ([Idiap, 2024](https://arxiv.org/abs/2411.03960)) and in **~100 queries** against
  commercial APIs ([IEEE S&P 2024, via BiometricUpdate](https://www.biometricupdate.com/202505/alarming-gains-in-face-reconstruction-from-biometric-templates-made-by-researchers)).
  Treat stored embeddings as **recoverable biometric data** — still regulated, must be
  encrypted/consented/deletable. Do not market them as anonymized.
- 🔴 **Licensing traps for commercial SaaS.** InsightFace *code* is MIT but the **`buffalo_l`
  pretrained models are non-commercial research only**
  ([deepinsight/insightface](https://github.com/deepinsight/insightface)). And **Ultralytics
  YOLO (v8/v11) is AGPL-3.0** — SaaS/API use triggers copyleft on the *entire* derivative
  work, fine-tuned weights included ([ultralytics.com/license](https://www.ultralytics.com/license)).
  Both need commercial licensing or a swap to permissive alternatives (see §3.5).

---

## 2. Target topology (three-tier hybrid)

```
┌─ TENANT LAN — on-prem agent box (1+ per site) ─────────────────┐
│  Camera discovery (ONVIF / WS-Discovery, UDP 3702 multicast)   │
│  RTSP ingest → media bridge (go2rtc-style)                     │
│  Edge inference: vision-core pipeline (detect → track → task)  │
│  SQLite durable queue · OUTBOUND-ONLY to cloud (through NAT)    │
└──────────────┬─────────────────────────────────────────────────┘
   metadata / events / clips (HTTPS, outbound)    WebRTC/HLS live view
               ▼
┌─ CLOUD CONTROL PLANE ──────────────────────────────────────────┐
│  Frappe (site-per-tenant) = orchestration + system of record    │
│   • DocTypes (agents, devices, events, results), workflow, portals
│   • enqueue(queue="long") → inference · webhooks · usage metering
│  Heavy / cross-camera inference tier: Triton/DeepStream on GPU   │
│   (MIG-partitioned, shared across tenants)                      │
└─────────────────────────────────────────────────────────────────┘
```

### Why this shape

- **An on-prem agent is non-negotiable** for CCTV discovery and RTSP ingest:
  - A **browser cannot scan a LAN** — JS/WASM has no raw UDP socket API, so it cannot send a
    WS-Discovery multicast Probe; mixed-content and Chrome's Local Network Access prompt
    (launching ~Chrome 142) block private-IP access anyway
    ([Chrome LNA](https://developer.chrome.com/blog/local-network-access),
    [why no raw UDP](https://www.computerenhance.com/p/no-really-why-cant-we-have-raw-udp)).
  - The **cloud cannot reach private cameras** — RFC1918 ranges aren't routable and sit
    behind NAT; ONVIF even returns the camera's private IP in `XAddrs`
    ([RFC1918](https://www.techtarget.com/whatis/definition/RFC-1918)).
  - The standard solution (Frigate/go2rtc, Scrypted) is a LAN agent that runs WS-Discovery
    locally, calls ONVIF `GetStreamUri`, pulls RTSP, and reports **outbound** to the cloud
    ([Frigate cameras](https://docs.frigate.video/configuration/cameras/),
    [ONVIF GetStreamUri](https://support.avigilon.com/s/article/how-to-get-the-rtsp-stream-for-an-onvif-camera-to-use-in-a-3rd-party-player)).
- **Edge-first inference controls cost and latency.** Streaming raw RTSP to the cloud is the
  cost killer — a 1080p H.264 stream is ~2.5–5 Mbps and managed cloud video ingest bills per
  GB in+out+stored ([AWS KVS pricing](https://aws.amazon.com/kinesis/video-streams/pricing/));
  edge-first deployments cut WAN traffic up to ~80% by sending only metadata/alerts/clips
  ([API4AI](https://medium.com/@API4AI/cloud-vs-edge-finding-the-sweet-spot-for-vision-dc33669aed45)).
  Run first-pass inference on the agent; reserve the cloud GPU tier for cross-camera and
  heavy models. The same box does discovery **and** inference.
- **Browser live view:** RTSP cannot play natively in a browser
  ([Ant Media](https://antmedia.io/rtsp-explained-what-is-rtsp-how-it-works/)); bridge
  **RTSP → WebRTC** (<500 ms) or HLS, with the substream feeding inference
  ([Wowza](https://www.wowza.com/blog/rtsp-to-webrtc-ip-camera-streaming-for-real-time-surveillance)).

---

## 3. Design

### 3.1 The "vision-core" refactor

Generalize `facecore` from a face engine into a vision core — evolution, not rewrite, since
the detect/embed split already fits.

1. **Backend protocols + registry:** `Detector`, `Embedder`, `Classifier`, `LivenessModel`
   interfaces with a registry. InsightFace becomes *one* face backend; object-detection
   backends (RF-DETR / YOLOX) plug in alongside. Move `MODEL_VERSION` to a backend property.
2. **Generic `Detection` contract** replacing `DetectedFace`; face fields become a typed
   attribute set; object/item detections reuse the same type.
3. **Pluggable pipeline:** turn `process_frame` into a configured stage list
   (`Stage.process(frame, tracks) -> tracks`) with a registry. Examples:
   - Face attendance: `[detect_faces, track, liveness, embed_match, debounce, post_event]`
   - Minibar: `[detect_objects, track, count_by_zone, post_consumption]`
   - Invoice items: `[detect_objects, classify, post_line_items]`
4. **Keep `facecore` pure.** Supervision/ByteTrack live as an `edge_client` optional extra,
   not a core dependency — consistent with [`supervision-integration.md`](../supervision-integration.md).

### 3.2 Module model — separate Frappe apps

Mirror Frappe's own `frappe → erpnext → hrms` pattern. A **`tb_vision_core`** app
(agent/device registry, camera management, generic Detection/Result DocTypes, inference
orchestration, tenant + consent/retention settings) plus thin use-case apps declaring
`required_apps`:

- `tb_face_attendance` (exists) → `tb_vision_core` + `hrms`
- `tb_invoice_vision` → `tb_vision_core` + `erpnext` (item/stock detection)
- `tb_minibar_vision` → `tb_vision_core` (+ hotel/POS app)

A Frappe app is a standalone package; one app installs on many sites and one site hosts many
apps, so optional features ship as **separate apps installed per site**
([Frappe apps](https://docs.frappe.io/framework/user/en/basics/apps)). Trade-off to manage:
the **last-installed app has highest override priority**
([install order](https://discuss.frappe.io/t/order-of-apps-to-be-installed/93885)) — modules
must not override the same DocType/method. (Alternative: one app + feature flags avoids
override conflicts but ships all code everywhere; separate apps are recommended here because
true per-customer installability is the goal.)

On the edge, mirror this: a vision-core runtime + per-use-case **task plugins** (pip extras)
selected by the agent's config.

### 3.3 Multi-tenant / SaaS

- **Tenant = Frappe site = isolated database** — silo-at-the-data-layer natively
  (DNS-multitenant on one bench; Frappe Cloud's model)
  ([Frappe multitenancy](https://docs.frappe.io/framework/user/en/bench/guides/setup-multitenancy)).
  Ideal for isolating each tenant's biometric embeddings; add **per-tenant encryption keys**
  for cryptographic separation and audit evidence. Group tenants into benches to manage
  silo's ops overhead.
- **Use a "bridge" model** ([AWS SaaS Lens](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/bridge-model.html)):
  silo the regulated/biometric data store, **pool the GPU inference tier** via **NVIDIA MIG**
  (hardware isolation + QoS, up to 7 instances/GPU on A100/H100) served by **Triton**
  ([ScaleOps](https://scaleops.com/blog/kubernetes-gpu-sharing/)). Avoid GPU time-slicing for
  tenant isolation (no fault/memory isolation).
- **Metering:** per-camera-stream is the industry precedent (AWS Panorama charges
  $8.33/cam/month; CV SaaS lists $199–$2,500/cam/yr)
  ([Panorama pricing](https://aws.amazon.com/panorama/pricing/)).

### 3.4 Edge vs cloud decision rule

Run inference at the **edge** when you need sub-200 ms latency, have >20 cameras, face spotty
connectivity, or have privacy-critical use; use **cloud** only for small/low-complexity
deployments; use **hybrid** for everything in between
([Fora Soft](https://www.forasoft.com/blog/article/edge-ai-vs-cloud-ai-video-surveillance) —
vendor estimates, treat latency/cost figures as order-of-magnitude). Reference designs: AWS
Panorama, Azure Live Video Analytics, and the open-source **Frigate + go2rtc** pattern
(low-res detect substream feeds inference; high-res copied for record/view)
([Frigate live](https://docs.frigate.video/configuration/live/)).

### 3.5 Object-detection stack (license-clean for closed SaaS)

- **Use:** RF-DETR core (≤Large, Apache-2.0), YOLOX (Apache), D-FINE (Apache), RT-DETR
  (Apache), RTMDet (MIT); **ByteTrack / BoT-SORT** (MIT — vet ReID sub-deps); **Supervision**
  (MIT, model-agnostic annotators/zones/tracking); serve via **Triton + ONNX/TensorRT**, or
  **DeepStream** for GPU RTSP pipelines
  ([best detectors](https://blog.roboflow.com/best-object-detection-models/),
  [supervision](https://github.com/roboflow/supervision)).
- **Avoid (or buy a commercial license):** Ultralytics YOLO v8/v11, YOLOv9/v10/YOLO-World
  (copyleft), original DeepSORT (GPL), RF-DETR XL/2XL (proprietary), and **InsightFace
  pretrained models** (non-commercial) ([model licenses](https://roboflow.com/model-licenses/yolov10)).
- **Face + object in one pipeline:** run a general detector for objects/persons in parallel
  with the face stack (detector → ArcFace embedding → similarity match), unify via
  Triton/DeepStream, maintain IDs with ByteTrack, annotate/zone with Supervision.

### 3.6 Frappe as the control plane (integration patterns)

- **Outbound to AI services:** `frappe.make_post_request(url, data=..., headers=...)` (token
  via headers); persist results with `frappe.get_doc(...).insert()`.
- **Offload long calls:** `frappe.enqueue(method, queue="long", timeout=..., enqueue_after_commit=True)`
  — default short/default timeout is 300 s; put inference on `queue="long"`
  ([background jobs](https://docs.frappe.io/framework/user/en/api/background_jobs)).
- **Webhooks both ways:** inbound via `@frappe.whitelist(allow_guest=True)` (then HMAC-verify);
  outbound via the no-code Webhook DocType with a Webhook Secret
  (`X-Frappe-Webhook-Signature`, HMAC-SHA256)
  ([webhooks](https://docs.frappe.io/framework/v14/user/en/guides/integration/webhooks)).
- **Auth:** API Key + Secret per User → `Authorization: token <key>:<secret>`.
- **Real-time progress:** `frappe.publish_realtime()` over socket.io + Redis; rooms are
  namespaced per site ([realtime](https://docs.frappe.io/framework/user/en/api/realtime)).
- **Recommended pattern:** a "Job/Result" DocType captures the request →
  `frappe.enqueue(queue="long")` calls the inference microservice → result stored on the
  DocType → progress via `publish_realtime`; async services call back an HMAC-verified
  `@frappe.whitelist(allow_guest=True)` endpoint to update the record.

### 3.7 Security & compliance (biometrics)

- Store **protected embeddings, not raw images** — but treat them as **recoverable**;
  consider **cancelable biometrics** (revocable transforms / template protection), encrypt at
  rest + in transit, prefer **edge/on-device matching** to shrink central-breach blast radius.
- **GDPR:** face identification = Article 9 special-category data → explicit consent + a
  **mandatory DPIA** ([Art. 9](https://gdpr-info.eu/art-9-gdpr/)). **BIPA** (Illinois):
  written consent before collection, private right of action ($1k–$5k/violation; $650M
  Facebook precedent). **India DPDP Rules 2025** (notified 13 Nov 2025): free/specific/
  informed consent, 72 h breach notice, erasure-on-request, penalties up to ₹250 cr; biometrics
  ride the general consent framework ([DPDP guide](https://www.seclore.com/fundamentals/dpdp-rules-2025-compliance-guide/)).
  Bake consent + retention + deletion into `tb_vision_core`.

---

## 4. Implementation roadmap

| Phase | Goal | Key work | Exit criterion |
|---|---|---|---|
| **0 — Harden** | Stop the bleeding | Auth on edge console; secrets out of plaintext (env/keyring); WAL + bounded queue + backoff; threadpool-offload the embedding service; **real test fixtures + accuracy CI**; correct the "irreversible embeddings" claim | Existing face-attendance is secure and CI-guarded |
| **1 — Vision-core refactor** | Generalize without breaking | Backend protocols + registry; generic `Detection`; pluggable pipeline; InsightFace becomes a backend; `facecore` stays pure | `tb_face_attendance` runs unchanged on the new core |
| **2 — On-prem agent** | CCTV discovery + edge inference | ONVIF/WS-Discovery service; `GetStreamUri` → RTSP; outbound registration to Frappe; go2rtc-style WebRTC live view; agent config selects task plugins | Plug in a camera → it auto-registers in Frappe |
| **3 — `tb_vision_core` + control plane** | Orchestration & multi-tenant | Agent/device registry, generic Result DocTypes, `enqueue` → inference, HMAC webhooks, site-per-tenant, per-tenant keys, Triton+MIG inference tier | One cloud serves N tenant sites; metering live |
| **4 — First new module** | Prove the module model | `tb_minibar_vision` *or* `tb_invoice_vision` as a separate app + edge task plugin (RF-DETR/YOLOX + zones) | A non-face use case ships end-to-end |
| **5 — SaaS productization** | Scale & sell | Onboarding, billing/metering, measured capacity numbers, compliance packaging (DPIA/consent templates), per-tenant model isolation | Self-serve tenant onboarding |

---

## 5. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| InsightFace `buffalo_l` non-commercial license | High | Commercial face SDK or own-trained/permissive ArcFace before monetizing |
| Embeddings are recoverable biometric data | High | Template protection, encryption, consent, edge matching; fix the marketing claim |
| GDPR/BIPA/DPDP exposure on biometrics | High | DPIA, explicit consent, retention/erasure in `tb_vision_core` |
| Ultralytics/GPL licensing in object detection | Med-High | Use Apache/MIT detectors + trackers only |
| Accuracy unverified (empty test fixtures) | Med-High | Accuracy CI in Phase 0 |
| Multi-app override-priority conflicts | Med | Modules must not override the same DocType/method; integration tests |
| Edge cost/latency assumptions unmeasured | Med | Measure real fps/throughput before customer demos (already flagged TBD in how-to) |
| Silo scaling/ops overhead at high tenant counts | Med | Group tenants into benches; automate provisioning |

---

## 6. Open decisions (owner input needed)

1. **Face model strategy** — commercial face SDK vs self-trained/permissive ArcFace (gates
   monetization; Phase 0/1).
2. **First non-face module** — minibar vs invoice item detection (Phase 4).
3. **Tenancy packing** — one bench many sites vs bench-per-tenant grouping (Phase 3).

---

## References

Inline links above point to primary sources. Key categories: edge/cloud trade-offs and
streaming (AWS KVS, Frigate, NVIDIA DeepStream); ONVIF/WS-Discovery and browser/NAT limits
(OASIS WS-Discovery, Chrome LNA, RFC1918); multi-tenant SaaS (AWS SaaS Lens, Frappe
multitenancy, NVIDIA MIG/Triton); biometric security/compliance (Idiap & IEEE template
inversion, GDPR Art. 9, BIPA, India DPDP Rules 2025); object-detection licensing (Ultralytics,
Roboflow model-licenses, InsightFace).
