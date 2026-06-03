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
def test_post_checkin_omits_log_type(mock_post):
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"message": {}})
    _client().post_checkin("D1", "2026-01-01 09:00:00", "edge-001")
    _, kwargs = mock_post.call_args
    assert "log_type" not in kwargs["data"]
    assert kwargs["data"]["employee_field_value"] == "D1"
    assert kwargs["data"]["timestamp"] == "2026-01-01 09:00:00"
    assert kwargs["data"]["device_id"] == "edge-001"


@patch("edge_client.frappe_client.requests.post")
def test_post_checkin_raises_on_error(mock_post):
    mock_post.return_value = MagicMock(status_code=417, text="boom")
    import pytest
    with pytest.raises(RuntimeError):
        _client().post_checkin("D1", "2026-01-01 09:00:00", "edge-001")
