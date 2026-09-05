"""Entry point: wire the device, the stack, the photo library, and the HTTP face."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

import aiohttp
from aiohttp import web

from framed import __version__, config
from framed.api import build_app
from framed.compositor import Compositor
from framed.layers import Layer, LayerStack
from framed.photos import PhotoLibrary
from framed.pixoo import Pixoo
from framed.sources.icloud import SharedAlbum

log = logging.getLogger("framed")


async def serve(cfg: config.Config) -> None:
    async with aiohttp.ClientSession() as session:
        pixoo = Pixoo(
            cfg.pixoo.host,
            session,
            min_interval=cfg.pixoo.min_interval,
            frame_interval=cfg.pixoo.frame_interval,
            max_brightness=cfg.pixoo.max_brightness,
            max_frames=cfg.pixoo.max_frames,
            reset_every=cfg.pixoo.reset_every,
            timeout=cfg.pixoo.timeout,
        )
        album = (
            SharedAlbum(session, cfg.photos.album, min_width=cfg.photos.min_width)
            if cfg.photos.album
            else None
        )
        photos = PhotoLibrary(
            cfg.data_dir / "photos",
            album,
            shuffle=cfg.photos.shuffle,
            saturation=cfg.photos.saturation,
            contrast=cfg.photos.contrast,
        )
        stack = LayerStack()
        for spec in cfg.layers:
            stack.upsert(Layer(str(spec["id"]), int(spec.get("priority", 0)), spec["content"]))
        compositor = Compositor(cfg, pixoo, stack, photos, session)
        tasks = [
            asyncio.create_task(compositor.run(), name="compositor"),
            asyncio.create_task(compositor.watchdog(), name="watchdog"),
            asyncio.create_task(compositor.photo_refresh_loop(), name="photos"),
        ]
        runner = web.AppRunner(build_app(compositor, cfg.token or ""))
        await runner.setup()
        site = web.TCPSite(runner, cfg.listen_host, cfg.listen_port)
        await site.start()
        log.info(
            "framed %s listening on %s:%d, device %s",
            __version__,
            cfg.listen_host,
            cfg.listen_port,
            cfg.pixoo.host,
        )
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await runner.cleanup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="framed", description="Pixoo-64 scene server")
    parser.add_argument("--config", default=os.environ.get("FRAMED_CONFIG"))
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = config.load(args.config)
    if not cfg.token:
        print(
            "a bearer token is required: set FRAMED_TOKEN or `token` in the config", file=sys.stderr
        )
        return 2
    try:
        asyncio.run(serve(cfg))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
