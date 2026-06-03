# facecore/tests/test_analyze_file.py
import cv2
import numpy as np
import pytest

from facecore.analyzer import FaceAnalyzer


def _analyzer_recording():
    captured = {}

    def fake_analyze(image):
        captured["shape"] = image.shape
        return ["sentinel"]

    a = FaceAnalyzer.__new__(FaceAnalyzer)
    a.analyze = fake_analyze  # type: ignore[method-assign]
    return a, captured


def test_analyze_image_file_reads_and_delegates(tmp_path):
    img_path = tmp_path / "x.png"
    cv2.imwrite(str(img_path), np.zeros((20, 20, 3), dtype=np.uint8))
    a, captured = _analyzer_recording()
    out = a.analyze_image_file(str(img_path))
    assert out == ["sentinel"]
    assert captured["shape"] == (20, 20, 3)


def test_analyze_image_file_missing_raises():
    a, _ = _analyzer_recording()
    with pytest.raises(FileNotFoundError):
        a.analyze_image_file("/no/such/file.jpg")
