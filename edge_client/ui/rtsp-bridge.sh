#!/usr/bin/env bash
# RTSP -> HLS bridge for the Face Edge "live preview" UI.
#
# Browsers can't play RTSP directly, so this transcodes the camera stream to
# HLS (segmented MP4/TS) that the live UI plays via hls.js. It also serves the
# ui/ folder over http://127.0.0.1:8099 so you can just open the page.
#
# Usage:
#   ./rtsp-bridge.sh "rtsp://user:pass@192.168.1.68:1935" [tcp|udp]
# Then open:  http://127.0.0.1:8099/face-edge-live.html
#
# Ctrl-C stops the transcode. (The static server keeps running in the
# background; stop it with:  pkill -f "http.server 8099")
set -euo pipefail

URL="${1:?usage: rtsp-bridge.sh <rtsp-url> [tcp|udp]}"
TRANSPORT="${2:-tcp}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/live"
PORT=8099

mkdir -p "$OUT"
rm -f "$OUT"/*.ts "$OUT"/*.m3u8 2>/dev/null || true

# Static server for the ui/ folder (only if not already up on this port).
if ! ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  ( cd "$HERE" && python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 & )
  echo "[bridge] serving $HERE on http://127.0.0.1:$PORT"
fi

echo "[bridge] open:  http://127.0.0.1:$PORT/face-edge-live.html"
echo "[bridge] transcoding (transport=$TRANSPORT) — Ctrl-C to stop"
echo

# Transcode to browser-friendly H.264, downscaled to <=960 wide to keep CPU
# sane, ~15 fps, low-latency HLS.
#
# LATENCY: the killer is keyframe/segment alignment. ffmpeg can only cut a
# segment on a keyframe, so the GOP (-g) MUST match the segment length
# (-hls_time) — otherwise 1s segments silently become 2s segments and the
# player buffers ~3 of them (~6s lag, which is what we hit). Here: 0.5s
# segments, keyframe every 0.5s (g = fps*0.5 ≈ 8), tiny 4-segment playlist.
# Combined with the player's lowLatencyMode + catch-up playback this lands
# ~1–1.5s glass-to-glass.
#
# -fflags nobuffer / -flags low_delay / -probesize / -analyzeduration trim the
# input-side buffering ffmpeg does before it emits the first frame.
#
# Retry loop + -timeout (µs) make it self-heal: if the camera drops (phone
# screen locks, app backgrounds), ffmpeg exits within a few seconds instead of
# hanging, and we reconnect automatically when it comes back.
while :; do
  ffmpeg -nostdin -loglevel warning \
    -fflags nobuffer -flags low_delay -probesize 500000 -analyzeduration 0 \
    -rtsp_transport "$TRANSPORT" -timeout 8000000 -i "$URL" \
    -an \
    -c:v libx264 -preset ultrafast -tune zerolatency -profile:v baseline -pix_fmt yuv420p \
    -vf "scale='min(960,iw)':-2" -r 15 -g 8 -keyint_min 8 -sc_threshold 0 \
    -f hls -hls_time 0.5 -hls_list_size 4 \
    -hls_flags delete_segments+append_list+omit_endlist+independent_segments \
    "$OUT/stream.m3u8" || true
  echo "[bridge] stream ended (camera unreachable?) — retrying in 2s…"
  sleep 2
done
