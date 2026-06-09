"""Auto-download for the MiniFASNet liveness model.

buffalo_l (detection + embedding) auto-downloads via InsightFace on first use,
but the MiniFASNet anti-spoof model does not ship with any package. Rather than
require a manual export step (the old how-to §4), fetch a pinned, pre-converted
ONNX on first use — mirroring how buffalo_l appears automatically.

Source: yakhyo/face-anti-spoofing release assets. This is a faithful ONNX export
of the upstream Silent-Face ``2.7_80x80_MiniFASNetV2.pth`` and matches exactly
what ``liveness.py`` expects: raw 0-255 BGR NCHW 80x80 input, 3-class output with
index 1 = live. The file is pinned by SHA-256 so a tampered or truncated download
fails loudly instead of producing silent garbage liveness scores.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path

# Pinned MiniFASNetV2 ONNX (2.7_80x80). Verified: raw 0-255 BGR input, softmax
# index 1 = real/live. If you bump the URL, update the checksum to match.
_MODEL_URL = (
    "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/"
    "MiniFASNetV2.onnx"
)
_MODEL_SHA256 = "b32929adc2d9c34b9486f8c4c7bc97c1b69bc0ea9befefc380e4faae4e463907"
_MODEL_BYTES = 1743581

# Canonical on-disk location: <repo>/models/minifasnet.onnx. Defined here (rather
# than imported from analyzer) so `python -m facecore.model_download` has no import
# cycle through analyzer.
DEFAULT_LIVENESS_PATH = Path(__file__).resolve().parents[3] / "models" / "minifasnet.onnx"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_liveness_model(dest: str | Path) -> Path:
    """Return ``dest``, downloading the pinned MiniFASNet ONNX if it is absent.

    A pre-existing file is trusted as-is (it may be a custom or hand-exported
    model) and returned untouched. A freshly downloaded file is verified against
    the pinned SHA-256 and only then moved into place; a mismatch removes the
    temp file and raises, so a bad download never lands at ``dest``.
    """
    dest = Path(dest)
    if dest.exists():
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"[facecore] liveness model missing; downloading {_MODEL_URL}")

    fd, tmp_name = tempfile.mkstemp(suffix=".onnx", dir=str(dest.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        urllib.request.urlretrieve(_MODEL_URL, tmp)  # noqa: S310 (trusted, pinned URL)
        digest = _sha256(tmp)
        if digest != _MODEL_SHA256:
            raise RuntimeError(
                "MiniFASNet download failed integrity check: "
                f"expected sha256 {_MODEL_SHA256}, got {digest}"
            )
        os.replace(tmp, dest)  # atomic on the same filesystem
    finally:
        if tmp.exists():
            tmp.unlink()

    print(f"[facecore] liveness model ready at {dest} ({dest.stat().st_size} bytes)")
    return dest


if __name__ == "__main__":  # `python -m facecore.model_download` for explicit setup
    ensure_liveness_model(DEFAULT_LIVENESS_PATH)
