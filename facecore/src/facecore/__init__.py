"""
Face Recognition Core Engine

Pure AI library for face detection, embedding computation, and passive liveness detection.
No camera, no web, no Frappe — just models and math.
"""

__version__ = "0.1.0"

from facecore.analyzer import FaceAnalyzer
from facecore.models import DetectedFace

__all__ = ["FaceAnalyzer", "DetectedFace"]
