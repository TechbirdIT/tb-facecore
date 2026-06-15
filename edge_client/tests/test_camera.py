# edge_client/tests/test_camera.py
import os

from edge_client.camera import (
    _BACKOFF_CAP,
    _BACKOFF_START,
    _DEFAULT_RTSP_OPTIONS,
    _LOW_LATENCY_OPTS,
    FrameSource,
    _mask_source,
    build_ffmpeg_options,
    is_rtsp,
)


class FakeCap:
    """Scripted capture: each item is a frame (success) or None (read failure)."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.released = False

    def read(self):
        if not self.frames:
            return False, None
        f = self.frames.pop(0)
        return (f is not None), f

    def release(self):
        self.released = True


class ForeverCap:
    def read(self):
        return True, "frame"

    def release(self):
        pass


def _source(caps, source=0, ffmpeg_options=None):
    """FrameSource over a scripted sequence of capture objects; no sleeping."""
    it = iter(caps)
    src = FrameSource(
        source, open_fn=lambda s: next(it), ffmpeg_options=ffmpeg_options
    )
    src._sleep = lambda seconds: None  # don't wait in unit tests
    return src


def test_step_stores_frame_and_read_consumes_it():
    src = _source([FakeCap(["f1"])])
    src._step()
    assert src.read() == "f1"
    assert src.read() is None  # consumed


def test_read_none_before_first_frame():
    src = _source([FakeCap([])])
    assert src.read() is None


def test_reconnects_with_new_capture_after_failure():
    bad = FakeCap([None])
    good = FakeCap(["f2"])
    src = _source([bad, bad, good])
    # open_fn calls: __init__ consumes first 'bad'; each failed _step reopens
    src._step()  # read fails → release + reopen (consumes second 'bad')
    assert bad.released is True
    src._step()  # second cap also fails → reopen to good
    src._step()  # good cap delivers
    assert src.read() == "f2"


def test_backoff_doubles_and_caps():
    always_bad = [
        FakeCap([None, None, None, None, None, None, None]) for _ in range(10)
    ]
    src = _source(always_bad)
    delays = []
    src._sleep = lambda seconds: delays.append(seconds)
    for _ in range(7):
        src._step()
    assert delays[0] == _BACKOFF_START
    assert delays[1] == _BACKOFF_START * 2
    assert max(delays) <= _BACKOFF_CAP
    assert delays[-1] == _BACKOFF_CAP


def test_backoff_resets_after_success():
    src = _source([FakeCap([None]), FakeCap(["f", None]), FakeCap([])])
    delays = []
    src._sleep = lambda seconds: delays.append(seconds)
    src._step()  # fail → backoff 1→2
    src._step()  # success → reset
    src._step()  # fail again → should sleep _BACKOFF_START, not 2
    assert delays == [_BACKOFF_START, _BACKOFF_START]


def test_rtsp_source_forces_tcp_transport(monkeypatch):
    monkeypatch.delenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", raising=False)
    _source([FakeCap([])], source="rtsp://cam.local:554/stream")
    assert os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] == _DEFAULT_RTSP_OPTIONS


def test_int_source_does_not_touch_ffmpeg_env(monkeypatch):
    monkeypatch.delenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", raising=False)
    _source([FakeCap([])], source=0)
    assert "OPENCV_FFMPEG_CAPTURE_OPTIONS" not in os.environ


def test_existing_ffmpeg_env_not_overwritten(monkeypatch):
    monkeypatch.setenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;udp")
    _source([FakeCap([])], source="rtsp://cam.local:554/stream")
    assert os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] == "rtsp_transport;udp"


def test_start_and_release_thread_lifecycle():
    src = FrameSource(0, open_fn=lambda s: ForeverCap())
    src.start()
    src.release()
    assert not src._thread.is_alive()


def test_release_without_start_is_safe():
    src = _source([FakeCap([])])
    src.release()  # must not raise


def test_step_does_not_reopen_when_stopping():
    bad = FakeCap([None])
    reopened = []

    def factory(s):
        if not factory.first_done:
            factory.first_done = True
            return bad
        cap = FakeCap([])
        reopened.append(cap)
        return cap

    factory.first_done = False
    src = FrameSource(0, open_fn=factory)
    src._sleep = lambda seconds: None
    src._stop.set()
    src._step()
    assert reopened == []
    assert bad.released is True


def test_release_only_releases_cap_when_thread_stopped():
    cap = FakeCap([])
    src = FrameSource(0, open_fn=lambda s: cap)
    src.release()  # never started → caller owns cap
    assert cap.released is True


# --- RTSP options / helpers ---


def test_is_rtsp():
    assert is_rtsp("rtsp://cam.local:554/stream") is True
    assert is_rtsp("rtsps://cam.local/stream") is True  # startswith("rtsp")
    assert is_rtsp(0) is False
    assert is_rtsp("/dev/video0") is False


def test_build_ffmpeg_options_default_tcp_no_timeout():
    assert build_ffmpeg_options() == f"rtsp_transport;tcp|{_LOW_LATENCY_OPTS}"


def test_build_ffmpeg_options_with_timeout_microseconds():
    # 10s -> 10_000_000 microseconds for FFmpeg stimeout
    assert (
        build_ffmpeg_options("tcp", 10.0)
        == f"rtsp_transport;tcp|{_LOW_LATENCY_OPTS}|stimeout;10000000"
    )


def test_build_ffmpeg_options_udp_transport():
    assert build_ffmpeg_options("udp", 0) == f"rtsp_transport;udp|{_LOW_LATENCY_OPTS}"


def test_build_ffmpeg_options_low_latency_can_be_disabled():
    assert build_ffmpeg_options("tcp", 0, low_latency=False) == "rtsp_transport;tcp"


def test_build_ffmpeg_options_override_wins_verbatim():
    raw = "rtsp_transport;tcp|timeout;5000000"
    assert build_ffmpeg_options("udp", 99, override=raw) == raw


def test_frame_source_applies_custom_ffmpeg_options(monkeypatch):
    monkeypatch.delenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", raising=False)
    opts = "rtsp_transport;tcp|stimeout;10000000"
    _source([FakeCap([])], source="rtsp://cam.local:554/stream", ffmpeg_options=opts)
    assert os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] == opts


def test_frame_source_ffmpeg_options_ignored_for_webcam(monkeypatch):
    monkeypatch.delenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", raising=False)
    _source([FakeCap([])], source=0, ffmpeg_options="rtsp_transport;udp")
    assert "OPENCV_FFMPEG_CAPTURE_OPTIONS" not in os.environ


def test_mask_source_redacts_rtsp_credentials():
    masked = _mask_source("rtsp://admin:hunter2@192.168.1.64:554/Streaming/Channels/102")
    assert masked == "rtsp://***@192.168.1.64:554/Streaming/Channels/102"
    assert "hunter2" not in masked


def test_mask_source_passthrough_when_no_credentials():
    assert _mask_source("rtsp://cam.local:554/stream") == "rtsp://cam.local:554/stream"
    assert _mask_source(0) == "0"
