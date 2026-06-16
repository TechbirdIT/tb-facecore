# facecore/tests/test_metrics.py

import pytest

from facecore import metrics


def test_cosine_distance_identical_is_zero():
    v = [1.0, 2.0, 3.0]
    assert metrics.cosine_distance(v, v) == pytest.approx(0.0, abs=1e-6)


def test_cosine_distance_orthogonal_is_one():
    assert metrics.cosine_distance([1.0, 0.0], [0.0, 1.0]) == pytest.approx(1.0)


def test_cosine_distance_opposite_is_two():
    assert metrics.cosine_distance([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(2.0)


def test_cosine_distance_zero_vector_safe():
    assert metrics.cosine_distance([0.0, 0.0], [1.0, 0.0]) == 1.0


def test_euclidean_distance():
    assert metrics.euclidean_distance([0.0, 0.0], [3.0, 4.0]) == pytest.approx(5.0)


def test_euclidean_l2_is_scale_invariant():
    # same direction, different magnitude -> ~0 after normalization
    assert metrics.euclidean_l2_distance([2.0, 0.0], [9.0, 0.0]) == pytest.approx(0.0)


def test_angular_distance_bounds():
    assert metrics.angular_distance([1.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)
    assert metrics.angular_distance([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.5)
    assert metrics.angular_distance([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(1.0)


def test_find_distance_dispatch_and_validation():
    assert metrics.find_distance([1.0, 0.0], [0.0, 1.0], "cosine") == pytest.approx(1.0)
    with pytest.raises(ValueError):
        metrics.find_distance([1.0], [1.0], "manhattan")


def test_find_threshold_buffalo_l_and_default():
    assert metrics.find_threshold("buffalo_l", "cosine") == 0.68
    assert metrics.find_threshold("buffalo_l", "euclidean_l2") == 1.13
    # unknown model falls back to generic defaults, not a KeyError
    assert metrics.find_threshold("Nonexistent", "cosine") == 0.40
    with pytest.raises(ValueError):
        metrics.find_threshold("buffalo_l", "bogus")


def test_verify_match_and_nonmatch():
    same = metrics.verify([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
    assert same["verified"] is True and same["distance"] == pytest.approx(0.0)
    diff = metrics.verify([1.0, 0.0], [-1.0, 0.0])  # cosine distance 2.0 > 0.68
    assert diff["verified"] is False
    assert diff["metric"] == "cosine" and diff["model"] == "buffalo_l"


def test_verify_explicit_threshold_overrides():
    res = metrics.verify([1.0, 0.0], [0.0, 1.0], threshold=1.5)  # dist 1.0 <= 1.5
    assert res["verified"] is True and res["threshold"] == 1.5
