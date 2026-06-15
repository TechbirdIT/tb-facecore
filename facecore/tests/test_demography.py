# facecore/tests/test_demography.py
import importlib.util

import numpy as np
import pytest

from facecore import demography
from facecore.exceptions import FaceCoreError

_HAS_DEEPFACE = importlib.util.find_spec("deepface") is not None


def test_native_coerces_numpy_to_json_safe_types():
    # deepface returns numpy scalars/arrays; _native must make them JSON-safe
    import json

    raw = {
        "facial_area": {"x": np.int64(10), "left_eye": np.array([1, 2])},
        "emotion": "happy",
        "emotion_scores": {"happy": np.float32(99.5), "sad": np.float32(0.5)},
        "age": np.int64(33),
    }
    out = demography._native(raw)
    json.dumps(out)  # must not raise
    assert isinstance(out["age"], int)
    assert all(isinstance(v, float) for v in out["emotion_scores"].values())
    assert isinstance(out["facial_area"]["x"], int)
    assert out["facial_area"]["left_eye"] == [1, 2]


def test_unknown_action_rejected_before_backend():
    # validation happens before the (heavy) deepface import, so this is cheap
    with pytest.raises(ValueError):
        demography.analyze(np.zeros((4, 4, 3), np.uint8), actions=("emotion", "bogus"))


@pytest.mark.skipif(_HAS_DEEPFACE, reason="deepface installed; missing-extra path N/A")
def test_missing_extra_raises_with_install_hint():
    with pytest.raises(FaceCoreError) as exc:
        demography.analyze(np.zeros((4, 4, 3), np.uint8), actions=("emotion",))
    assert "facecore[demography]" in str(exc.value)


@pytest.mark.skipif(_HAS_DEEPFACE, reason="deepface installed; missing-extra path N/A")
def test_warmup_without_extra_raises_install_hint():
    with pytest.raises(FaceCoreError) as exc:
        demography.warmup(actions=("emotion",))
    assert "facecore[demography]" in str(exc.value)


@pytest.mark.skipif(not _HAS_DEEPFACE, reason="needs the facecore[demography] extra")
def test_warmup_builds_models_so_next_call_is_fast():
    # warmup pre-builds the models; it must complete without raising
    demography.warmup(actions=("emotion", "race"))


@pytest.mark.skipif(not _HAS_DEEPFACE, reason="needs the facecore[demography] extra")
def test_emotion_race_on_real_face():
    # only runs where the optional extra is installed
    from facecore import load_image

    img = load_image(
        "https://raw.githubusercontent.com/opencv/opencv/master/samples/data/lena.jpg"
    )
    res = demography.analyze(img, actions=("emotion", "race"))
    assert len(res) >= 1
    assert res[0]["emotion"] is not None
    assert res[0]["race"] is not None
