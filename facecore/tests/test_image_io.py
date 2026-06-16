# facecore/tests/test_image_io.py
import base64

import cv2
import numpy as np
import pytest

from facecore.image_io import load_image


def _sample_png_bytes():
    img = (np.random.rand(8, 8, 3) * 255).astype(np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return img, buf.tobytes()


def test_ndarray_passthrough():
    arr = np.zeros((4, 4, 3), np.uint8)
    assert load_image(arr) is arr


def test_ndarray_wrong_shape_rejected():
    with pytest.raises(ValueError):
        load_image(np.zeros((4, 4), np.uint8))


def test_bytes_decode_roundtrip():
    img, raw = _sample_png_bytes()
    out = load_image(raw)
    assert out.shape == img.shape


def test_base64_bare_roundtrip():
    img, raw = _sample_png_bytes()
    b64 = base64.b64encode(raw).decode()
    out = load_image(b64)
    assert out.shape == img.shape


def test_base64_data_uri_roundtrip():
    img, raw = _sample_png_bytes()
    uri = "data:image/png;base64," + base64.b64encode(raw).decode()
    out = load_image(uri)
    assert out.shape == img.shape


def test_file_path_roundtrip(tmp_path):
    img, _ = _sample_png_bytes()
    p = tmp_path / "f.png"
    cv2.imwrite(str(p), img)
    out = load_image(str(p))
    assert out.shape == img.shape


def test_missing_path_raises():
    with pytest.raises(FileNotFoundError):
        load_image("/no/such/file.png")


def test_unsupported_type_raises():
    with pytest.raises(TypeError):
        load_image(12345)  # type: ignore[arg-type]


def test_invalid_base64_raises():
    with pytest.raises(ValueError):
        load_image("data:image/png;base64,@@@not-valid@@@")
