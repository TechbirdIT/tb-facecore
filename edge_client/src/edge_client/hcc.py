"""Hik-Connect for Teams (HikCentral Connect) OpenAPI cloud live streaming.

Lets an edge box pull a camera that is **only reachable through the Hik-Connect
cloud** — not on the edge's LAN, and with no VPN or router port-forward. The
cloud relay hands back a short-lived HLS/RTMP/FLV URL that OpenCV/FFmpeg can open
just like an RTSP source, so the rest of the pipeline is unchanged.

Flow (verified live against the India gateway ``iind.hikcentralconnect.com``):

    POST /api/hccgw/platform/v1/token/get   {appKey, secretKey}
        -> { accessToken (~7d), expireTime, areaDomain }     # Token: header
    POST <areaDomain>/api/hccgw/video/v1/live/address/get
        {deviceSerial, resourceId, protocol, streamType[, code]}
        -> { url, expireTime }                               # ~5 min lifetime

Key facts learned the hard way:

* ``resourceId`` is the camera's **logical resource id**, NOT the ``id`` that
  ``resource/v1/devicedetail/get`` returns for a ``cameraChannel`` (that one
  gives "Resource does not exist"). Read the logical id from the Hik-Connect web
  client: open the camera in Video Monitoring and grab the id in the
  ``/hcc/resource/v1/logicalresource/element/camera/<resourceId>/thumbnail``
  request.
* ``protocol``: 1=ezopen (unusable here), 2=HLS, 3=RTMP, 4=FLV. ``streamType``:
  1=main, 2=sub. Use the **sub** stream for detection — lower resolution is
  plenty and saves bandwidth.
* HLS/RTMP/FLV transcodes are **H.264 only**; an H.265 channel errors out.
* If the device has stream encryption ON, pass its 6–12 char verification code
  as ``code``; with encryption OFF no code is needed.
* The returned URL **expires (~5 min)**, so re-resolve on every (re)connect —
  :class:`~edge_client.camera.FrameSource` already reopens on read failure, so
  wiring the resolver into its open path makes refresh automatic.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import requests

logger = logging.getLogger(__name__)

# Regional OpenAPI gateways. token/get works on any of them and returns the
# account's real `areaDomain` (which we then use for every later call), so the
# default below is only a starting point — India here, matching the cameras.
DEFAULT_HOST = "https://iind.hikcentralconnect.com"

# config value -> live/address/get protocol code. ezopen (1) is deliberately
# omitted: it needs Hikvision's SDK to decode and FFmpeg can't open it.
_PROTOCOLS = {"hls": 2, "rtmp": 3, "flv": 4}
# config value -> streamType. "sub" first because it's the detection default.
_STREAMS = {"sub": 2, "main": 1}

_SCHEME = "hcc://"
# Refresh the access token this many seconds before it actually expires, so a
# request never goes out with a token that lapses mid-flight.
_TOKEN_SKEW_S = 120


class HccError(RuntimeError):
    """A Hik-Connect OpenAPI call returned a non-zero errorCode."""


@dataclass(frozen=True)
class HccSource:
    """A camera addressed via the Hik-Connect cloud, parsed from a source URL.

    Wire form (goes in ``cameras[].source`` / the console's source field, with
    NO secrets — credentials live in the separate ``hcc:`` config block)::

        hcc://<deviceSerial>/<resourceId>?stream=sub&protocol=hls

    e.g. ``hcc://FY6391441/56b25d0f608e43ff9c37db989bf384a8?stream=sub``
    """

    device_serial: str
    resource_id: str
    protocol: str = "hls"
    stream: str = "sub"

    @property
    def protocol_code(self) -> int:
        return _PROTOCOLS[self.protocol]

    @property
    def stream_type(self) -> int:
        return _STREAMS[self.stream]


def is_hcc_source(source: object) -> bool:
    """True for an ``hcc://…`` cloud source string."""
    return isinstance(source, str) and source.startswith(_SCHEME)


def parse_hcc_source(source: str) -> HccSource:
    """Parse ``hcc://<serial>/<resourceId>?stream=&protocol=`` into an HccSource.

    Raises ``ValueError`` on a malformed source or an unknown stream/protocol so
    a typo in config fails loudly at startup, not as a silent no-frames camera.
    """
    parts = urlsplit(source)
    serial = parts.netloc
    resource_id = parts.path.lstrip("/")
    if not serial or not resource_id:
        raise ValueError(
            f"bad hcc source {source!r}: expected "
            "hcc://<deviceSerial>/<resourceId>[?stream=sub&protocol=hls]"
        )
    q = parse_qs(parts.query)
    stream = q.get("stream", ["sub"])[0]
    protocol = q.get("protocol", ["hls"])[0]
    if stream not in _STREAMS:
        raise ValueError(f"bad hcc stream {stream!r}; use one of {sorted(_STREAMS)}")
    if protocol not in _PROTOCOLS:
        raise ValueError(
            f"bad hcc protocol {protocol!r}; use one of {sorted(_PROTOCOLS)}"
        )
    return HccSource(serial, resource_id, protocol=protocol, stream=stream)


class HccClient:
    """Thin, thread-safe client for the Hik-Connect for Teams streaming API.

    Caches the access token (refreshing before expiry) and pins subsequent calls
    to the ``areaDomain`` the token response advertises. One instance can be
    shared across camera threads.
    """

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        host: str = DEFAULT_HOST,
        *,
        timeout: float = 20.0,
        session: requests.Session | None = None,
    ):
        if not app_key or not app_secret:
            raise ValueError("hcc app_key and app_secret are required")
        self._app_key = app_key
        self._app_secret = app_secret
        self._host = host.rstrip("/")
        self._timeout = timeout
        self._session = session or requests.Session()
        self._lock = threading.Lock()
        self._token: str | None = None
        self._area_domain = self._host
        self._token_exp = 0.0  # epoch seconds when the cached token expires

    # ----- low-level -----
    def _post(self, base: str, path: str, body: dict, *, token: str | None) -> dict:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Token"] = token
        resp = self._session.post(
            f"{base}{path}", json=body, headers=headers, timeout=self._timeout
        )
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("errorCode", "0")) != "0":
            raise HccError(
                f"{path} -> {data.get('errorCode')}: {data.get('message', data)}"
            )
        return data.get("data", {})

    def _ensure_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_exp - _TOKEN_SKEW_S:
                return self._token
            data = self._post(
                self._host,
                "/api/hccgw/platform/v1/token/get",
                {"appKey": self._app_key, "secretKey": self._app_secret},
                token=None,
            )
            self._token = data["accessToken"]
            self._area_domain = (data.get("areaDomain") or self._host).rstrip("/")
            # expireTime is epoch *seconds* in the responses observed.
            self._token_exp = float(data.get("expireTime", time.time() + 3600))
            logger.info("hcc: token acquired, area=%s", self._area_domain)
            return self._token

    # ----- public -----
    def live_url(self, src: HccSource, code: str | None = None) -> str:
        """Resolve a fresh, short-lived stream URL for ``src``.

        ``code`` is the device verification code, required only when the device
        has stream encryption enabled. Raises :class:`HccError` on an API error
        (e.g. wrong resourceId, H.265 channel, or a channel disabled by the
        service plan), which the caller's reconnect/backoff then retries.
        """
        token = self._ensure_token()
        body: dict[str, object] = {
            "deviceSerial": src.device_serial,
            "resourceId": src.resource_id,
            "protocol": src.protocol_code,
            "streamType": src.stream_type,
        }
        if code:
            body["code"] = code
        data = self._post(
            self._area_domain,
            "/api/hccgw/video/v1/live/address/get",
            body,
            token=token,
        )
        url = data.get("url")
        if not url:
            raise HccError(f"live/address/get returned no url: {data}")
        return url


class _FailedCapture:
    """Stand-in capture whose ``read()`` always fails.

    Returned when URL resolution errors (network blip, token refresh, a channel
    momentarily unavailable) so :class:`~edge_client.camera.FrameSource` treats
    it as a normal read failure and backs off + reopens — which re-resolves a
    fresh URL — instead of the capture thread dying on an exception.
    """

    def read(self):  # noqa: D401 - cv2.VideoCapture-compatible
        return False, None

    def release(self):
        pass


def make_open_fn(client: HccClient, src: HccSource, code: str | None = None):
    """Build a FrameSource ``open_fn`` that resolves a FRESH cloud URL each call.

    Because the URLs expire (~5 min) and FrameSource reopens on read failure,
    resolving inside the opener makes URL refresh automatic with no extra logic.
    """

    def _open(_source_ignored):
        import cv2

        try:
            url = client.live_url(src, code=code)
        except Exception as exc:  # noqa: BLE001 - any error -> retry via backoff
            logger.warning("hcc: live url resolution failed (%s); will retry", exc)
            return _FailedCapture()
        logger.info(
            "hcc: opening %s stream for %s/%s",
            src.protocol,
            src.device_serial,
            src.resource_id,
        )
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:  # pragma: no cover - backend may not support it
            pass
        return cap

    return _open


def cli_main(argv: list[str] | None = None) -> None:
    """`edge-hcc-url`: resolve and print a cloud stream URL (for testing).

    Reads credentials from the edge config so you never paste secrets on the
    command line, e.g.::

        edge-hcc-url --config config.yaml \
            --source "hcc://FY6391441/56b25d0f608e43ff9c37db989bf384a8?stream=sub"

    Pipe the printed URL to a player to eyeball the feed: ``ffplay "$(...)"``.
    """
    import argparse

    from edge_client.config import load_config

    p = argparse.ArgumentParser(description="Resolve a Hik-Connect cloud stream URL")
    p.add_argument("--config", required=True, help="Path to the edge YAML config")
    p.add_argument(
        "--source",
        required=True,
        help="hcc://<deviceSerial>/<resourceId>?stream=sub&protocol=hls",
    )
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    if not (cfg.hcc_app_key and cfg.hcc_app_secret):
        p.error("config is missing hcc.app_key / hcc.app_secret")
    src = parse_hcc_source(args.source)
    code = dict(cfg.hcc_device_codes or ()).get(src.device_serial)
    client = HccClient(cfg.hcc_app_key, cfg.hcc_app_secret, cfg.hcc_host)
    print(client.live_url(src, code=code))


if __name__ == "__main__":  # pragma: no cover
    cli_main()
