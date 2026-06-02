"""facecore — pure face detection, embedding, and liveness engine."""

__version__ = "0.1.0"

from facecore.analyzer import MODEL_VERSION, FaceAnalyzer
from facecore.exceptions import (
    FaceCoreError,
    LowQualityError,
    MultipleFacesError,
    NoFaceError,
)
from facecore.models import DetectedFace

__all__ = [
    "FaceAnalyzer",
    "DetectedFace",
    "MODEL_VERSION",
    "FaceCoreError",
    "NoFaceError",
    "MultipleFacesError",
    "LowQualityError",
]
