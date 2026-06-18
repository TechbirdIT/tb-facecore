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

## Narration
The video ships **with voiceover by default** — one clip per scene in `public/vo/scene_*.mp3`,
placed at each scene's start in `src/FaceCore.tsx`. The clips were synthesized locally with the
macOS `say` engine (voice: Samantha) from [`voiceover-script.md`](voiceover-script.md), then
encoded to MP3 with ffmpeg. Scene durations in the `D` map are paced to match the clip lengths.

Regenerate the voiceover (e.g. to swap voices or edit copy):
```bash
# edit the lines, then re-synthesize a scene:
say -v Samantha -r 172 -o public/vo/scene_3.aiff "your new line…"
ffmpeg -y -i public/vo/scene_3.aiff -ar 44100 -ac 1 -b:a 128k public/vo/scene_3.mp3
rm public/vo/scene_3.aiff
# if a clip gets longer than its scene, bump that scene in the `D` map, then `npm run render`.
```
To use a higher-quality voice (ElevenLabs / Azure / a human read), just replace the
`public/vo/scene_*.mp3` files — keep the same filenames and the wiring is unchanged.
For background music, add another `<Audio src={staticFile("music.mp3")} volume={0.15} />`
at the top level of `<FaceCore>`.

> `node_modules/` and `out/` are gitignored — only the source is version-controlled.
> Re-render locally to regenerate `out/facecore.mp4`.
