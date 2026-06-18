# FaceCore — Explainer Video (Remotion)

A ~72-second, 1080p motion-graphics explainer for the FaceCore face-attendance platform,
built with [Remotion](https://www.remotion.dev) (React → MP4). It mirrors the pitch deck
(`../index.html`): intro → the problem → the end-to-end flow → dual-engine architecture →
capabilities → closing CTA.

## Prerequisites
- Node 18+ (built & tested on Node 25)
- `npm install` (pulls Remotion + a headless Chromium shell on first render)

## Commands
```bash
npm install            # once

npm run studio         # live editor at http://localhost:3000 — scrub & tweak scenes
npm run render         # → out/facecore.mp4  (H.264, 1920×1080, 30fps)
npm run still          # → out/poster.png   (a single poster frame)
```

Render a different format/quality:
```bash
npx remotion render FaceCore out/facecore.webm --codec=vp8        # web-optimized
npx remotion render FaceCore out/facecore.mp4  --codec=h264 --crf=18   # higher quality
```

## Structure
| File | Role |
|------|------|
| `src/index.ts` | Registers the Remotion root |
| `src/Root.tsx` | Declares the `FaceCore` composition (1920×1080, 30fps) |
| `src/FaceCore.tsx` | All scenes + timing + theme in one file |
| `remotion.config.ts` | Render defaults (image format, concurrency, overwrite) |

## Editing
- **Timing** — each scene's length lives in the `D` map at the top of `FaceCore.tsx`;
  offsets and `TOTAL_FRAMES` are derived automatically.
- **Copy** — the `FLOW_STEPS`, `RIBBON`, `FEATURES` arrays drive the on-screen text.
- **Palette** — `EMERALD` / `VIOLET` / `INK` / `MIST` constants, matching the deck.
- **Fonts** — Space Grotesk (display), Plus Jakarta Sans (body), JetBrains Mono — via
  `@remotion/google-fonts` (closest Google-hosted match to the deck's Clash Display).

## Adding narration / music
There's no audio track yet. To add one:
```tsx
import { Audio, staticFile } from "remotion";
// inside <FaceCore>:  <Audio src={staticFile("voiceover.mp3")} />
```
Drop the file in a `public/` folder and re-render. (A 72s scratch VO script can be
generated from the deck's section copy.)

> `node_modules/` and `out/` are gitignored — only the source is version-controlled.
> Re-render locally to regenerate `out/facecore.mp4`.
