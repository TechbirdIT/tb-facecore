# facecore/tests/test_integration.py
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.integration
def test_same_person_high_similarity(analyzer):
    f1 = analyzer.analyze_image_file(str(FIX / "same_person_1.jpg"))
    f2 = analyzer.analyze_image_file(str(FIX / "same_person_2.jpg"))
    assert len(f1) == 1 and len(f2) == 1
    sim = analyzer.cosine_similarity(f1[0].embedding, f2[0].embedding)
    assert sim > 0.45


@pytest.mark.integration
def test_different_person_low_similarity(analyzer):
    f1 = analyzer.analyze_image_file(str(FIX / "same_person_1.jpg"))
    f2 = analyzer.analyze_image_file(str(FIX / "different_person.jpg"))
    sim = analyzer.cosine_similarity(f1[0].embedding, f2[0].embedding)
    assert sim < 0.45


@pytest.mark.integration
def test_printed_photo_low_liveness(analyzer):
    faces = analyzer.analyze_image_file(str(FIX / "printed_photo.jpg"))
    assert len(faces) >= 1
    assert faces[0].liveness_score < 0.5
