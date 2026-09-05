import base64
import time

import pytest
from PIL import Image

from framed.pixoo import Pixoo, PixooError, encode_frame


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        return self.payload


class FakeSession:
    def __init__(self, error_code=0):
        self.calls = []
        self.error_code = error_code

    def post(self, url, json=None, timeout=None):
        self.calls.append((time.monotonic(), json))
        return FakeResponse({"error_code": self.error_code})


def test_encode_frame_is_raw_rgb():
    img = Image.new("RGB", (64, 64), (1, 2, 3))
    raw = base64.b64decode(encode_frame(img))
    assert len(raw) == 64 * 64 * 3 and raw[:3] == b"\x01\x02\x03"
    with pytest.raises(ValueError):
        encode_frame(Image.new("RGB", (32, 32)))


async def test_push_resets_id_and_spaces_commands():
    session = FakeSession()
    pixoo = Pixoo("h", session, min_interval=0.05, frame_interval=0.01)
    frames = [Image.new("RGB", (64, 64), (i, 0, 0)) for i in range(3)]
    await pixoo.push(frames, speed_ms=100)
    commands = [c["Command"] for _, c in session.calls]
    assert commands == ["Draw/ResetHttpGifId"] + ["Draw/SendHttpGif"] * 3
    offsets = [c["PicOffset"] for _, c in session.calls[1:]]
    assert offsets == [0, 1, 2]
    assert all(c["PicNum"] == 3 and c["PicWidth"] == 64 for _, c in session.calls[1:])
    assert session.calls[1][0] - session.calls[0][0] >= 0.045
    assert pixoo.state.pushes == 1 and pixoo.state.ok


async def test_reset_every_n_pushes_increments_pic_id():
    session = FakeSession()
    pixoo = Pixoo("h", session, min_interval=0, frame_interval=0, reset_every=2)
    frame = [Image.new("RGB", (64, 64))]
    for _ in range(3):
        await pixoo.push(frame)
    commands = [c["Command"] for _, c in session.calls]
    assert commands == [
        "Draw/ResetHttpGifId",
        "Draw/SendHttpGif",
        "Draw/SendHttpGif",
        "Draw/ResetHttpGifId",
        "Draw/SendHttpGif",
    ]
    assert [c["PicID"] for _, c in session.calls if "PicID" in c] == [1, 2, 1]


async def test_error_code_raises_and_marks_state():
    pixoo = Pixoo("h", FakeSession(error_code=5), min_interval=0)
    with pytest.raises(PixooError):
        await pixoo.set_brightness(500)
    assert not pixoo.state.ok


async def test_brightness_is_capped():
    session = FakeSession()
    pixoo = Pixoo("h", session, min_interval=0, max_brightness=90)
    await pixoo.set_brightness(100)
    assert session.calls[0][1]["Brightness"] == 90


async def test_too_many_frames_rejected():
    pixoo = Pixoo("h", FakeSession(), max_frames=2)
    with pytest.raises(ValueError):
        await pixoo.push([Image.new("RGB", (64, 64))] * 3)
