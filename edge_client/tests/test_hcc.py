"""Tests for the Hik-Connect for Teams cloud streaming client."""

import pytest

from edge_client import hcc


# ----- source parsing -----
def test_is_hcc_source():
    assert hcc.is_hcc_source("hcc://FY6391441/abc?stream=sub")
    assert not hcc.is_hcc_source("rtsp://user:pass@host/Streaming/Channels/102")
    assert not hcc.is_hcc_source(0)
    assert not hcc.is_hcc_source(None)


def test_parse_hcc_source_defaults():
    src = hcc.parse_hcc_source("hcc://FY6391441/56b25d0f")
    assert src.device_serial == "FY6391441"
    assert src.resource_id == "56b25d0f"
    assert src.stream == "sub" and src.stream_type == 2  # sub-stream for detection
    assert src.protocol == "hls" and src.protocol_code == 2


def test_parse_hcc_source_query():
    src = hcc.parse_hcc_source("hcc://S1/RID?stream=main&protocol=rtmp")
    assert src.stream_type == 1 and src.protocol_code == 3


@pytest.mark.parametrize(
    "bad",
    [
        "hcc://FY6391441",  # no resourceId
        "hcc:///RID",  # no serial
        "hcc://S1/RID?stream=ultra",  # unknown stream
        "hcc://S1/RID?protocol=ezopen",  # protocol we can't open
    ],
)
def test_parse_hcc_source_rejects_bad(bad):
    with pytest.raises(ValueError):
        hcc.parse_hcc_source(bad)


# ----- fake transport -----
class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    """Records POSTs and replays queued responses in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, json, headers, timeout):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResp(self._responses.pop(0))


def _token_resp(area="https://iind.hikcentralconnect.com", exp=10_000_000_000):
    return {"errorCode": "0", "data": {"accessToken": "tok123", "expireTime": exp,
                                       "areaDomain": area}}


def test_live_url_flow_and_request_shape():
    area = "https://iind.hikcentralconnect.com"
    sess = _FakeSession([
        _token_resp(area),
        {"errorCode": "0", "data": {"url": "https://stream.example/x.m3u8"}},
    ])
    client = hcc.HccClient("AK", "SK", session=sess)
    src = hcc.parse_hcc_source("hcc://FY6391441/RID?stream=sub&protocol=hls")
    url = client.live_url(src)

    assert url == "https://stream.example/x.m3u8"
    # token call first, then live/address on the returned areaDomain
    assert sess.calls[0]["url"].endswith("/api/hccgw/platform/v1/token/get")
    assert sess.calls[0]["json"] == {"appKey": "AK", "secretKey": "SK"}
    live = sess.calls[1]
    assert live["url"] == f"{area}/api/hccgw/video/v1/live/address/get"
    assert live["headers"]["Token"] == "tok123"
    assert live["json"] == {
        "deviceSerial": "FY6391441", "resourceId": "RID",
        "protocol": 2, "streamType": 2,
    }
    assert "code" not in live["json"]  # unencrypted device: no code sent


def test_token_is_cached_across_calls():
    sess = _FakeSession([
        _token_resp(),
        {"errorCode": "0", "data": {"url": "u1"}},
        {"errorCode": "0", "data": {"url": "u2"}},
    ])
    client = hcc.HccClient("AK", "SK", session=sess)
    src = hcc.parse_hcc_source("hcc://S/R")
    client.live_url(src)
    client.live_url(src)
    # one token call + two live calls — token not re-fetched
    token_calls = [c for c in sess.calls if c["url"].endswith("token/get")]
    assert len(token_calls) == 1


def test_code_sent_for_encrypted_device():
    sess = _FakeSession([
        _token_resp(),
        {"errorCode": "0", "data": {"url": "u"}},
    ])
    client = hcc.HccClient("AK", "SK", session=sess)
    client.live_url(hcc.parse_hcc_source("hcc://J48129032/R"), code="swami112233")
    assert sess.calls[1]["json"]["code"] == "swami112233"


def test_nonzero_errorcode_raises():
    sess = _FakeSession([
        _token_resp(),
        {"errorCode": "OPEN000503", "message": "Resource does not exist"},
    ])
    client = hcc.HccClient("AK", "SK", session=sess)
    with pytest.raises(hcc.HccError):
        client.live_url(hcc.parse_hcc_source("hcc://S/R"))


def test_missing_credentials_rejected():
    with pytest.raises(ValueError):
        hcc.HccClient("", "SK")


def test_make_open_fn_returns_failed_capture_on_error():
    class _Boom(hcc.HccClient):
        def __init__(self):
            pass

        def live_url(self, src, code=None):
            raise hcc.HccError("nope")

    open_fn = hcc.make_open_fn(_Boom(), hcc.parse_hcc_source("hcc://S/R"))
    cap = open_fn("ignored")
    assert cap.read() == (False, None)  # FrameSource sees a failed read -> backs off
    cap.release()
