"""The loop that keeps the panel showing the top layer."""

from __future__ import annotations

import asyncio
import io
import logging
import time

import aiohttp
from PIL import Image

from framed.config import Config
from framed.layers import Layer, LayerStack
from framed.photos import PhotoLibrary
from framed.pixoo import Pixoo, PixooError
from framed.render import blank, fit_image, greeting_frames, parse_color, text_frame

log = logging.getLogger(__name__)

CONTENT_TYPES = ("photos", "image", "greeting", "text", "color", "clock", "channel")


class Compositor:
    def __init__(
        self,
        cfg: Config,
        pixoo: Pixoo,
        stack: LayerStack,
        photos: PhotoLibrary,
        session: aiohttp.ClientSession,
    ) -> None:
        self.cfg = cfg
        self.pixoo = pixoo
        self.stack = stack
        self.photos = photos
        self.session = session
        self.showing: tuple[str, int] | None = None
        self.showing_since: float | None = None
        self.last_tick: float = time.time()
        self._event = asyncio.Event()
        self._next_photo_at = 0.0
        self._device_was_ok: bool | None = None

    def notify(self) -> None:
        self._event.set()

    def invalidate(self) -> None:
        """Force a redraw of the current top layer on the next tick."""
        self.showing = None
        self.notify()

    async def run(self) -> None:
        await self._apply_device_settings()
        while True:
            try:
                await self._tick()
            except PixooError as exc:
                log.warning("device: %s", exc)
            except Exception:  # noqa: BLE001
                log.exception("compositor tick failed")
            self.last_tick = time.time()
            timeout = self._wait_time()
            try:
                await asyncio.wait_for(self._event.wait(), timeout)
            except TimeoutError:
                pass
            self._event.clear()

    async def _apply_device_settings(self) -> None:
        try:
            await self.pixoo.set_brightness(
                self.pixoo.state.brightness
                if self.pixoo.state.brightness is not None
                else self.cfg.brightness
            )
            if self.pixoo.state.screen_on is not None:
                await self.pixoo.set_screen(self.pixoo.state.screen_on)
        except PixooError as exc:
            log.warning("device settings not applied: %s", exc)

    def _wait_time(self) -> float:
        now = time.time()
        candidates = [self.cfg.pixoo.watchdog]
        exp = self.stack.next_expiry()
        if exp is not None:
            candidates.append(exp - now)
        top = self.stack.top()
        if top and top.content.get("type") == "photos":
            candidates.append(self._next_photo_at - now)
        return max(0.05, min(candidates))

    async def _tick(self) -> None:
        top = self.stack.top()
        now = time.time()
        if top is None:
            if self.showing is not None:
                await self.pixoo.push([blank()])
                self.showing = None
            return
        key = (top.id, top.version)
        if key != self.showing:
            ok = await self._show(top)
            if not ok:
                self.stack.remove(top.id)
                self.notify()
                return
            self.showing = key
            self.showing_since = now
            self.stack.mark_shown(top.id)
            self._next_photo_at = now + self.cfg.photos.interval
        elif top.content.get("type") == "photos" and now >= self._next_photo_at:
            await self._show_photo()
            self._next_photo_at = now + self.cfg.photos.interval

    async def _show(self, layer: Layer) -> bool:
        content = layer.content
        kind = content.get("type")
        log.info("showing %s (%s, priority %d)", layer.id, kind, layer.priority)
        try:
            if kind == "photos":
                await self._show_photo()
            elif kind == "image":
                image = await self._fetch_image(content["url"])
                await self.pixoo.push([fit_image(image)])
            elif kind == "greeting":
                name = str(content.get("name", "")).strip() or "FRIEND"
                color = parse_color(
                    content.get("color")
                    or self.cfg.greeting.colors.get(name)
                    or self.cfg.greeting.colors.get(name.lower())
                    or self.cfg.greeting.default_color
                )
                frames = greeting_frames(name.upper(), color, headline=self.cfg.greeting.headline)
                await self.pixoo.push(frames, speed_ms=int(content.get("speed", 120)))
            elif kind == "text":
                lines = content.get("lines") or str(content.get("text", "")).split("\n")
                frame = text_frame(
                    [str(line) for line in lines],
                    parse_color(content.get("color")),
                    parse_color(content.get("background"), (0, 0, 0)),
                )
                await self.pixoo.push([frame])
            elif kind == "color":
                await self.pixoo.push([blank(parse_color(content.get("color")))])
            elif kind == "clock":
                await self.pixoo.show_clock(int(content.get("id", 0)))
            elif kind == "channel":
                await self.pixoo.show_channel(int(content.get("index", 0)))
            else:
                log.warning("layer %s has unknown type %r", layer.id, kind)
                return False
        except PixooError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("layer %s cannot be rendered: %r", layer.id, exc)
            return False
        return True

    async def _show_photo(self) -> None:
        frame = self.photos.next()
        if frame is None:
            frame = text_frame(["NO", "PHOTOS", "YET"], (120, 120, 120))
        await self.pixoo.push([frame])

    async def _fetch_image(self, url: str) -> Image.Image:
        if url.startswith("/"):
            if not self.cfg.image_base_url:
                raise ValueError("relative image url without image_base_url configured")
            url = self.cfg.image_base_url.rstrip("/") + url
        async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                raise ValueError(f"image fetch: HTTP {resp.status}")
            data = await resp.read()
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            return img.convert("RGB")

    async def watchdog(self) -> None:
        """Probe the device; after it comes back (power cycle, reboot) restore the screen."""
        while True:
            try:
                await self.pixoo.probe()
            except PixooError as exc:
                log.warning("watchdog: %s", exc)
            ok = self.pixoo.state.ok
            if ok and self._device_was_ok is False:
                log.info("device reachable, restoring display")
                await self._apply_device_settings()
                self.invalidate()
            self._device_was_ok = ok
            await asyncio.sleep(self.cfg.pixoo.watchdog)

    async def photo_refresh_loop(self) -> None:
        while True:
            added = await self.photos.refresh()
            if added and self.showing and self.showing[0] == self._photos_layer_id():
                self._next_photo_at = 0
                self.notify()
            await asyncio.sleep(self.cfg.photos.refresh)

    def _photos_layer_id(self) -> str | None:
        for layer in self.stack.all():
            if layer.content.get("type") == "photos":
                return layer.id
        return None

    def status(self) -> dict:
        state = self.pixoo.state
        return {
            "device": {
                "ok": state.ok,
                "last_ok": state.last_ok,
                "last_error": state.last_error,
                "pushes": state.pushes,
                "brightness": state.brightness,
                "screen_on": state.screen_on,
            },
            "showing": self.showing[0] if self.showing else None,
            "showing_since": self.showing_since,
            "layers": [layer.to_dict() for layer in self.stack.all()],
            "photos": self.photos.status(),
            "last_tick": self.last_tick,
        }
