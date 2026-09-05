"""HTTP driver for the Divoom Pixoo-64.

The device exposes one endpoint, ``POST /post``, taking ``{"Command": ...}`` JSON.
Everything here is serialized through one lock with a minimum spacing between
commands, because the firmware drops or garbles commands that arrive back to back,
and it stops responding after a few hundred frame pushes unless the GIF id is reset.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field

import aiohttp
from PIL import Image

log = logging.getLogger(__name__)

SIZE = 64
CHANNEL_FACES = 0
CHANNEL_CLOUD = 1
CHANNEL_VISUALIZER = 2
CHANNEL_CUSTOM = 3


class PixooError(Exception):
    """The device answered with a non-zero error code."""


@dataclass
class PixooState:
    ok: bool = False
    last_ok: float | None = None
    last_error: str | None = None
    pushes: int = 0
    brightness: int | None = None
    screen_on: bool | None = None
    conf: dict = field(default_factory=dict)


class Pixoo:
    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        *,
        min_interval: float = 1.0,
        frame_interval: float = 0.2,
        max_brightness: int = 90,
        max_frames: int = 40,
        reset_every: int = 1,
        timeout: float = 8.0,
    ) -> None:
        self.url = f"http://{host}/post"
        self.session = session
        self.min_interval = min_interval
        self.frame_interval = frame_interval
        self.max_brightness = max_brightness
        self.max_frames = max_frames
        self.reset_every = max(1, reset_every)
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.state = PixooState()
        self._lock = asyncio.Lock()
        self._last_write = 0.0
        self._pic_id = 0

    async def _send(self, command: str, spacing: float, **params) -> dict:
        """Send one command, holding the lock for the caller-specified spacing."""
        wait = self._last_write + spacing - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        body = {"Command": command, **params}
        try:
            async with self.session.post(self.url, json=body, timeout=self.timeout) as resp:
                data = await resp.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError, ValueError) as exc:
            self.state.ok = False
            self.state.last_error = f"{command}: {exc!r}"
            raise PixooError(self.state.last_error) from exc
        finally:
            self._last_write = time.monotonic()
        code = data.get("error_code", 0)
        if code != 0:
            self.state.ok = False
            self.state.last_error = f"{command}: error_code {code}"
            raise PixooError(self.state.last_error)
        self.state.ok = True
        self.state.last_ok = time.time()
        self.state.last_error = None
        return data

    async def command(self, command: str, **params) -> dict:
        async with self._lock:
            return await self._send(command, self.min_interval, **params)

    async def probe(self) -> dict:
        """Read the device configuration. Raises PixooError when the device is unreachable."""
        conf = await self.command("Channel/GetAllConf")
        self.state.conf = conf
        return conf

    async def set_brightness(self, level: int) -> None:
        level = max(0, min(int(level), self.max_brightness))
        await self.command("Channel/SetBrightness", Brightness=level)
        self.state.brightness = level

    async def set_screen(self, on: bool) -> None:
        await self.command("Channel/OnOffScreen", OnOff=1 if on else 0)
        self.state.screen_on = on

    async def show_clock(self, clock_id: int) -> None:
        await self.command("Channel/SetIndex", SelectIndex=CHANNEL_FACES)
        await self.command("Channel/SetClockSelectId", ClockId=int(clock_id))

    async def show_channel(self, index: int) -> None:
        await self.command("Channel/SetIndex", SelectIndex=int(index))

    async def push(self, frames: list[Image.Image], speed_ms: int = 100) -> None:
        """Push one still image or a short animation. The device loops animations itself."""
        if not frames:
            raise ValueError("no frames")
        if len(frames) > self.max_frames:
            raise ValueError(f"{len(frames)} frames exceeds the device limit of {self.max_frames}")
        async with self._lock:
            if self._pic_id == 0 or self.state.pushes % self.reset_every == 0:
                await self._send("Draw/ResetHttpGifId", self.min_interval)
                self._pic_id = 0
            self._pic_id += 1
            for offset, frame in enumerate(frames):
                spacing = self.min_interval if offset == 0 else self.frame_interval
                await self._send(
                    "Draw/SendHttpGif",
                    spacing,
                    PicNum=len(frames),
                    PicWidth=SIZE,
                    PicOffset=offset,
                    PicID=self._pic_id,
                    PicSpeed=int(speed_ms),
                    PicData=encode_frame(frame),
                )
            self.state.pushes += 1


def encode_frame(image: Image.Image) -> str:
    """Base64 of the raw RGB bytes, row-major, exactly 64x64."""
    if image.size != (SIZE, SIZE):
        raise ValueError(f"frame must be {SIZE}x{SIZE}, got {image.size}")
    return base64.b64encode(image.convert("RGB").tobytes()).decode("ascii")
