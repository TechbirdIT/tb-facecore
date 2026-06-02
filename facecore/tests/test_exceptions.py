# facecore/tests/test_exceptions.py
import pytest
from facecore.exceptions import (
    FaceCoreError,
    NoFaceError,
    MultipleFacesError,
    LowQualityError,
)


def test_subclasses_are_facecore_errors():
    for exc in (NoFaceError, MultipleFacesError, LowQualityError):
        assert issubclass(exc, FaceCoreError)


def test_raisable_with_message():
    with pytest.raises(FaceCoreError, match="boom"):
        raise NoFaceError("boom")
