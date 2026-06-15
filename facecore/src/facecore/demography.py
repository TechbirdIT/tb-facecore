"""Optional emotion + race demography (the ``facecore[demography]`` extra).

The lean core is ONNX/InsightFace only and gives detection, embedding, liveness,
and (free, via buffalo_l's genderage) age + gender. Emotion and race are the one
genuinely-missing piece from deepface — and deepface's models are TensorFlow/Keras,
which the core deliberately avoids.

Rather than blind-vendor preprocessing-sensitive Keras code we couldn't validate,
this module reuses **deepface itself** as an optional backend: correct by
construction, MIT-licensed, and isolated behind the extra so the core stays lean.
Import only triggers the heavy dependency when you actually call it.

    from facecore import demography
    demography.analyze("face.jpg", actions=("emotion", "race"))   # needs the extra
"""

from __future__ import annotations

from facecore.exceptions import FaceCoreError
from facecore.image_io import load_image

VALID_ACTIONS = ("emotion", "race", "age", "gender")

_INSTALL_HINT = (
    "emotion/race demography needs the optional extra — install it with:\n"
    "    pip install 'facecore[demography]'\n"
    "(pulls deepface + TensorFlow/Keras, intentionally kept out of the lean core)."
)


def _deepface():
    try:
        from deepface import DeepFace  # type: ignore[import-untyped]
    except Exception as exc:  # ImportError, or TF load failure
        raise FaceCoreError(_INSTALL_HINT) from exc
    return DeepFace


def _native(obj):
    """Coerce deepface's numpy scalars/arrays into JSON-serializable Python types.

    deepface returns scores as numpy ``float32`` and regions with numpy ints,
    which stdlib ``json.dumps`` cannot serialize. Walk the structure once so the
    library's data contract is plain ``float``/``int``/``str``/``dict``/``list``.
    """
    if isinstance(obj, dict):
        return {k: _native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_native(v) for v in obj]
    if obj.__class__.__module__ == "numpy":
        # ndarray -> nested list (recurse for any numpy scalars inside);
        # scalar (float32/int64/...) -> native via .item()
        if hasattr(obj, "tolist") and getattr(obj, "ndim", 0) > 0:
            return _native(obj.tolist())
        return obj.item()
    return obj


def analyze(
    source: object, actions: tuple[str, ...] = ("emotion", "race")
) -> list[dict]:
    """Per-face demography for ``source`` (path / URL / base64 / bytes / ndarray).

    ``actions`` is any subset of ``("emotion", "race", "age", "gender")``. Returns
    one dict per detected face, e.g.::

        {"facial_area": {...},
         "emotion": "happy", "emotion_scores": {...},
         "race": "white",    "race_scores": {...}}

    Detection/alignment for demography is handled by deepface (its models were
    trained on its own alignment). For age/gender in the lean pipeline, prefer
    ``FaceAnalyzer.analyze`` / ``gender_age`` (free, no TensorFlow).

    Raises ``FaceCoreError`` with an install hint if the extra is not installed.
    """
    unknown = set(actions) - set(VALID_ACTIONS)
    if unknown:
        raise ValueError(f"unknown actions {sorted(unknown)}; valid: {VALID_ACTIONS}")

    deepface = _deepface()
    img = load_image(source)
    results = deepface.analyze(
        img_path=img,
        actions=list(actions),
        enforce_detection=False,
        silent=True,
    )
    if isinstance(results, dict):  # older deepface returned a dict for one face
        results = [results]

    out: list[dict] = []
    for r in results:
        d: dict = {"facial_area": r.get("region")}
        if "emotion" in actions:
            d["emotion"] = r.get("dominant_emotion")
            d["emotion_scores"] = r.get("emotion")
        if "race" in actions:
            d["race"] = r.get("dominant_race")
            d["race_scores"] = r.get("race")
        if "age" in actions:
            d["age"] = r.get("age")
        if "gender" in actions:
            d["gender"] = r.get("dominant_gender")
            d["gender_scores"] = r.get("gender")
        out.append(_native(d))
    return out
