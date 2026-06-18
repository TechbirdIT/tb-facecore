# FaceCore — Voiceover Script (≈72s)

Timecodes match the scene cuts in `src/FaceCore.tsx` (30fps). Pacing target is a calm,
confident product-marketing read (~150 wpm). Trim/expand to land each line inside its window.

| Time | Scene | Narration |
|------|-------|-----------|
| 0:00–0:04 | Intro | "Attendance that recognises faces — not badges." |
| 0:04–0:12 | Problem | "Cards get shared. Punches get faked. And naive in-out logic turns a quick step away from the camera into unfair hours." |
| 0:12–0:39 | Flow | "FaceCore fixes it end-to-end. An employee self-registers a photo — which becomes an irreversible face vector, then the image is discarded. HR approves it. Only approved profiles sync to the cameras. At the edge, faces are matched in milliseconds, with passive liveness blocking photo and video spoofs. A signed event is posted, and a check-in is created — server-side." |
| 0:39–0:51 | Architecture | "Under the hood, two engines do two jobs. A fast edge engine answers 'who is this, right now'. A separate analytics sidecar handles the heavy lifting. Frappe never touches the AI — it just calls one secure gateway." |
| 0:51–1:03 | Features | "Sub-second recognition. Passive liveness. Fair presence-hours. Cross-camera de-duplication. Fleet health. Privacy by design — and a full, offline-capable audit trail. All feeding Frappe HRMS natively." |
| 1:03–1:13 | Outro | "On the cameras you already own. On servers you fully control. FaceCore — put a face to every check-in." |

## Producing the audio
1. Generate or record `voiceover.mp3` (any TTS — ElevenLabs / Azure / macOS `say` — or a human read).
   Quick scratch track on macOS:
   ```bash
   say -v Daniel -o voiceover.aiff -f voiceover-lines.txt && ffmpeg -i voiceover.aiff voiceover.mp3
   ```
2. Drop it at `video/public/voiceover.mp3`.
3. Uncomment the `<Audio>` block in `src/FaceCore.tsx` (search for `VOICEOVER`).
4. `npm run render` — Remotion muxes the audio onto the MP4 automatically.

> Keep the MP3 ≤ ~73s. If it runs long, either tighten the read or bump the per-scene
> durations in the `D` map so the visuals breathe to match the narration.
