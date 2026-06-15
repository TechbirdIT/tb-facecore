"""facecore — pure face detection, embedding, and liveness engine."""

__version__ = "0.1.0"

from facecore.analyzer import MODEL_VERSION, FaceAnalyzer
from facecore.exceptions import (
    FaceCoreError,
    LowQualityError,
    MultipleFacesError,
    NoFaceError,
)
from facecore.image_io import load_image
from facecore.metrics import find_distance, find_threshold
from facecore.metrics import verify as verify_embeddings
from facecore.models import DetectedFace, FaceBox

__all__ = [
    "FaceAnalyzer",
    "DetectedFace",
    "FaceBox",
    "MODEL_VERSION",
    "load_image",
    "find_distance",
    "find_threshold",
    "verify_embeddings",
    "FaceCoreError",
    "NoFaceError",
    "MultipleFacesError",
    "LowQualityError",
]
