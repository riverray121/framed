"""The HTTP face: bearer-authenticated JSON over aiohttp."""

from __future__ import annotations

import logging
import time

from aiohttp import web

from framed.compositor import CONTENT_TYPES, Compositor
from framed.layers import Layer
from framed.pixoo import PixooError

log = logging.getLogger(__name__)

PUBLIC_PATHS = {"/healthz"}


def build_app(compositor: Compositor, token: str) -> web.Application:
    @web.middleware
    async def auth(request: web.Request, handler):
        if request.path not in PUBLIC_PATHS:
            header = request.headers.get("Authorization", "")
            if header != f"Bearer {token}":
                raise web.HTTPUnauthorized(text="bearer token required")
        try:
            return await handler(request)
        except PixooError as exc:
            return web.json_response({"error": str(exc)}, status=502)
        except (KeyError, ValueError, TypeError) as exc:
            return web.json_response({"error": f"bad request: {exc}"}, status=400)

    async def healthz(_request: web.Request) -> web.Response:
        stale = time.time() - compositor.last_tick > 600
        return web.json_response({"ok": not stale}, status=503 if stale else 200)

    async def status(_request: web.Request) -> web.Response:
        return web.json_response(compositor.status())

    async def list_layers(_request: web.Request) -> web.Response:
        return web.json_response([layer.to_dict() for layer in compositor.stack.all()])

    async def upsert_layer(request: web.Request) -> web.Response:
        body = await request.json()
        content = body["content"]
        if not isinstance(content, dict) or content.get("type") not in CONTENT_TYPES:
            raise ValueError(f"content.type must be one of {CONTENT_TYPES}")
        layer = Layer(
            id=str(body["id"]),
            priority=int(body.get("priority", 50)),
            content=content,
            ttl=float(body["ttl"]) if body.get("ttl") is not None else None,
        )
        cooldown = float(body["cooldown"]) if body.get("cooldown") else None
        accepted = compositor.stack.upsert(layer, cooldown=cooldown)
        if accepted:
            compositor.notify()
        return web.json_response({"accepted": accepted, "layer": layer.to_dict()})

    async def delete_layer(request: web.Request) -> web.Response:
        removed = compositor.stack.remove(request.match_info["id"])
        if removed:
            compositor.notify()
        return web.json_response({"removed": removed})

    async def brightness(request: web.Request) -> web.Response:
        body = await request.json()
        await compositor.pixoo.set_brightness(int(body["level"]))
        return web.json_response({"brightness": compositor.pixoo.state.brightness})

    async def screen(request: web.Request) -> web.Response:
        body = await request.json()
        await compositor.pixoo.set_screen(bool(body["on"]))
        return web.json_response({"screen_on": compositor.pixoo.state.screen_on})

    async def refresh_photos(_request: web.Request) -> web.Response:
        added = await compositor.photos.refresh()
        return web.json_response({"added": added, **compositor.photos.status()})

    app = web.Application(middlewares=[auth])
    app.add_routes(
        [
            web.get("/healthz", healthz),
            web.get("/status", status),
            web.get("/layers", list_layers),
            web.post("/layers", upsert_layer),
            web.delete("/layers/{id}", delete_layer),
            web.post("/brightness", brightness),
            web.post("/screen", screen),
            web.post("/photos/refresh", refresh_photos),
        ]
    )
    return app
