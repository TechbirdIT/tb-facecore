# edge_client/tests/test_frappe_client.py
from unittest.mock import MagicMock, patch

from edge_client.frappe_client import FrappeClient


def _client():
    return FrappeClient("http://localhost:8000", "k", "s")


@patch("edge_client.frappe_client.requests.get")
def test_fetch_face_data_returns_message(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: {"message": [{"attendance_device_id": "D1"}]}
    )
    rows = _client().fetch_face_data(since="2026-01-01 00:00:00")
    assert rows == [{"attendance_device_id": "D1"}]
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["since"] == "2026-01-01 00:00:00"
    assert "token k:s" in kwargs["headers"]["Authorization"]


@patch("edge_client.frappe_client.requests.post")
def test_post_event_sends_payload(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200, json=lambda: {"message": {"status": "created"}}
    )
    _client().post_event("edge-001", "D1", "2026-06-04 09:00:00", 0.83, 0.95)
    _, kwargs = mock_post.call_args
    assert kwargs["data"]["device_id"] == "edge-001"
    assert kwargs["data"]["attendance_device_id"] == "D1"
    assert kwargs["data"]["similarity"] == 0.83
    assert kwargs["data"]["liveness"] == 0.95


@patch("edge_client.frappe_client.requests.post")
def test_post_event_duplicate_is_success(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200, json=lambda: {"message": {"status": "duplicate"}}
    )
    _client().post_event("edge-001", "D1", "2026-06-04 09:00:00", 0.8, 0.9)  # no raise


@patch("edge_client.frappe_client.requests.post")
def test_post_event_raises_rejected_on_4xx(mock_post):
    mock_post.return_value = MagicMock(status_code=417, text="boom")
    import pytest

    from edge_client.frappe_client import CheckinRejectedError
    with pytest.raises(CheckinRejectedError):
        _client().post_event("edge-001", "D1", "2026-06-04 09:00:00", 0.8, 0.9)


@patch("edge_client.frappe_client.requests.post")
def test_post_event_raises_runtime_on_5xx(mock_post):
    mock_post.return_value = MagicMock(status_code=500, text="boom")
    import pytest

    from edge_client.frappe_client import CheckinRejectedError
    with pytest.raises(RuntimeError) as exc:
        _client().post_event("edge-001", "D1", "2026-06-04 09:00:00", 0.8, 0.9)
    assert not isinstance(exc.value, CheckinRejectedError)


@patch("edge_client.frappe_client.requests.post")
def test_heartbeat_best_effort(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    _client().heartbeat("edge-001", "1.0.0")
    _, kwargs = mock_post.call_args
    assert kwargs["data"]["device_id"] == "edge-001"
