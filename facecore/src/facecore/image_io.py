"""Flexible image loading: ndarray / path / URL / base64 / bytes → BGR ndarray.

Lets the enrollment service (and tests) hand facecore whatever they have without
each caller re-implementing decode logic. Lean by design — cv2 + numpy + urllib
+ base64 only, no new dependencies. Adapted from serengil/deepface
(``deepface/commons/image_utils.py``, MIT licensed), trimmed to what facecore needs.
"""

from __future__ import annotations

import base64
import binascii
from pathlib import Path
from urllib.request import Request, urlopen

import cv2
import numpy as np

_URL_TIMEOUT = 15


def _decode(buf: bytes) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise ValueError("could not decode image bytes")
    return arr


def _from_base64(data: str) -> np.ndarray:
    # accept full data URIs ("data:image/png;base64,....") or bare base64
    if data.startswith("data:"):
        if "," not in data:
            raise ValueError("malformed data URI")
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64 image") from exc
    return _decode(raw)


def _from_url(url: str) -> np.ndarray:
    req = Request(url, headers={"User-Agent": "facecore/1.0"})
    with urlopen(req, timeout=_URL_TIMEOUT) as resp:  # noqa: S310 - explicit http(s) only
        return _decode(resp.read())


def load_image(source: str | bytes | np.ndarray) -> np.ndarray:
    """Return a BGR (H, W, 3) uint8 array from many input kinds.

    Accepts:
      - a numpy array (returned as-is after a shape check),
      - raw image ``bytes`` (encoded jpg/png/...),
      - a filesystem path,
      - an ``http(s)://`` URL,
      - a base64 string (bare or a ``data:`` URI).

    Raises ValueError/FileNotFoundError on anything unreadable.
    """
    if isinstance(source, np.ndarray):
        if source.ndim != 3 or source.shape[2] != 3:
            raise ValueError("image array must be (H, W, 3) BGR")
        return source
    if isinstance(source, bytes):
        return _decode(source)
    if not isinstance(source, str):
        raise TypeError(f"unsupported image source type: {type(source).__name__}")

    s = source.strip()
    if s.startswith("data:") or s.startswith("data:image"):
        return _from_base64(s)
    if s.startswith("http://") or s.startswith("https://"):
        return _from_url(s)
    p = Path(s)
    if p.is_file():
        img = cv2.imread(str(p))
        if img is None:
            raise ValueError(f"not a readable image: {s}")
        return img
    # last resort: maybe a bare base64 blob
    if len(s) > 64:
        return _from_base64(s)
    raise FileNotFoundError(s)
