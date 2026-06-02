# facecore/tests/test_cosine.py
import numpy as np
from facecore.analyzer import FaceAnalyzer


def _analyzer():
    # __init__ must NOT load models, so this is cheap and offline.
    return FaceAnalyzer.__new__(FaceAnalyzer)


def test_identical_vectors_similarity_is_one():
    a = analyzer = _analyzer()
    v = [1.0, 0.0, 0.0]
    assert abs(FaceAnalyzer.cosine_similarity(a, v, v) - 1.0) < 1e-6


def test_orthogonal_vectors_similarity_is_zero():
    a = _analyzer()
    assert abs(FaceAnalyzer.cosine_similarity(a, [1.0, 0.0], [0.0, 1.0])) < 1e-6


def test_opposite_vectors_similarity_is_minus_one():
    a = _analyzer()
    assert abs(FaceAnalyzer.cosine_similarity(a, [1.0, 0.0], [-1.0, 0.0]) + 1.0) < 1e-6
