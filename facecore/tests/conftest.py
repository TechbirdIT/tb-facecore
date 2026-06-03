# facecore/tests/conftest.py
import os

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires downloaded models")


@pytest.fixture(scope="session")
def analyzer():
    if os.getenv("FACECORE_RUN_INTEGRATION") != "1":
        pytest.skip("set FACECORE_RUN_INTEGRATION=1 to run model-backed tests")
    from facecore import FaceAnalyzer

    return FaceAnalyzer(device="cpu")
