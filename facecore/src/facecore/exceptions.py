"""Exception hierarchy for facecore."""


class FaceCoreError(Exception):
    """Base class for all facecore errors."""


class NoFaceError(FaceCoreError):
    """No face detected in the image."""


class MultipleFacesError(FaceCoreError):
    """More than one face detected where exactly one was required."""


class LowQualityError(FaceCoreError):
    """A face was detected but its detector confidence is below threshold."""
