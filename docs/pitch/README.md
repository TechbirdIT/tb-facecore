# FaceCore — Visual Product Overview / Pitch Deck

`index.html` is a **single, self-contained** product overview of the FaceCore face-attendance
platform (the `tb-facecore` AI/edge stack + the `tb_face_attendance` Frappe app). It is built
to be shared with stakeholders and prospective clients as a pitch, while staying technically
accurate — every claim is drawn from this repo's own docs (`design/architecture.md`,
`dual-engine-architecture.md`, `presence-and-hours-design.md`, the competitor benchmark, and
the engineering backlog in `SESSION-STATUS.md`).

## What it covers
- **How it works** — animated five-step flow: Enroll → Approve → Sync → Recognise → Check-in
- **Capabilities** — sub-second edge recognition, passive liveness, fair presence-hours,
  cross-camera cooldown, device fleet health, employee portal, privacy-by-design, audit trail + offline queue
- **Dual-engine architecture** — Frappe · `ai_service` (`/embed`) · `edge_client` · DeepFace sidecar (`/analyze`)
- **Use cases**, the competitive wedge, **installation runbook**, and the **roadmap (coming soon)**

## Explainer video
A ~72s motion-graphics version of this deck (Remotion → MP4) lives in [`video/`](video/).
Run `npm install && npm run render` there to produce `video/out/facecore.mp4` (1080p, 30fps).
The rendered MP4 is gitignored — re-render locally.

## Viewing it
It's a static file — no build step, no network dependency beyond CDN fonts/Tailwind.

```bash
# just open it
open docs/pitch/index.html            # macOS
xdg-open docs/pitch/index.html        # Linux

# or serve it (nicer for sharing on a LAN)
python -m http.server -d docs/pitch 8090   # → http://localhost:8090
```

## Notes
- Self-contained HTML/CSS/JS. Fonts (Clash Display, Plus Jakarta Sans) and Tailwind load from
  CDN; everything else — diagrams, animation, the flow stepper — is inline.
- Designed mobile-first; collapses to a single column below 768px.
- To export a PDF for email, open in Chrome → Print → Save as PDF (A4/Letter, background graphics on).

## Roadmap accuracy
The "Coming soon" section reflects work that is **proposed/in-flight**, not shipped:
Weaviate vector search (`/register`, `/search`), the real-time Edge Console + control API,
Roboflow `supervision` (zones / line-crossing), Frappe `Vision Task` DocTypes, payroll hours from
presence sessions, adaptive multi-shot enrollment, and a GPU/CUDA edge switch. Keep this in sync
with `docs/dual-engine-architecture.md` ("Not done yet") and `docs/SESSION-STATUS.md` ("Next steps").
