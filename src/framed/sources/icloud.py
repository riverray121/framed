"""Read-only client for a public iCloud Shared Album.

Apple serves public shared albums from ``https://pNN-sharedstreams.icloud.com``,
where the partition NN is encoded in the album token. Two unauthenticated calls
are enough: ``webstream`` lists photos with their derivative checksums, and
``webasseturls`` resolves checksums to download URLs. A ``330`` answer carries the
correct host for the album in ``X-Apple-MMe-Host``; the client follows it once.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import aiohttp

log = logging.getLogger(__name__)

_BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


class ICloudError(Exception):
    pass


@dataclass(frozen=True)
class Photo:
    guid: str
    checksum: str
    width: int
    height: int
    caption: str = ""


def album_token(url_or_token: str) -> str:
    value = url_or_token.strip()
    if "#" in value:
        value = value.rsplit("#", 1)[1]
    value = value.rstrip("/").rsplit("/", 1)[-1]
    if not value or value[0] not in "AB":
        raise ICloudError(f"not a shared album token: {value!r}")
    return value


def partition(token: str) -> int:
    if token[0] == "A":
        return _BASE62.index(token[1])
    return _BASE62.index(token[1]) * 62 + _BASE62.index(token[2])


def base_url(token: str, host: str | None = None) -> str:
    host = host or f"p{partition(token):02d}-sharedstreams.icloud.com"
    return f"https://{host}/{token}/sharedstreams/"


def pick_derivative(derivatives: dict, min_width: int) -> tuple[str, int, int] | None:
    """The smallest derivative at least ``min_width`` wide, else the largest available."""
    candidates = []
    for value in derivatives.values():
        try:
            candidates.append((int(value["width"]), int(value["height"]), value["checksum"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not candidates:
        return None
    big_enough = [c for c in candidates if c[0] >= min_width]
    w, h, checksum = min(big_enough) if big_enough else max(candidates)
    return checksum, w, h


class SharedAlbum:
    def __init__(self, session: aiohttp.ClientSession, album: str, *, min_width: int = 256) -> None:
        self.session = session
        self.token = album_token(album)
        self.min_width = min_width
        self._base = base_url(self.token)
        self.name: str | None = None

    async def _post(self, path: str, payload: dict) -> dict:
        for _attempt in range(2):
            async with self.session.post(
                self._base + path, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 330:
                    data = await resp.json(content_type=None)
                    host = data.get("X-Apple-MMe-Host")
                    if not host:
                        raise ICloudError("redirect without host")
                    self._base = base_url(self.token, host)
                    continue
                if resp.status != 200:
                    raise ICloudError(f"{path}: HTTP {resp.status}")
                return await resp.json(content_type=None)
        raise ICloudError("too many redirects")

    async def list_photos(self) -> list[Photo]:
        data = await self._post("webstream", {"streamCtag": None})
        self.name = data.get("streamName")
        photos = []
        for item in data.get("photos", []):
            if item.get("mediaAssetType") == "video":
                continue
            picked = pick_derivative(item.get("derivatives", {}), self.min_width)
            if not picked:
                continue
            checksum, w, h = picked
            photos.append(Photo(item["photoGuid"], checksum, w, h, item.get("caption") or ""))
        return photos

    async def asset_urls(self, photos: list[Photo]) -> dict[str, str]:
        """Map checksum to a download URL. Apple caps the guid list per call."""
        urls: dict[str, str] = {}
        guids = [p.guid for p in photos]
        for i in range(0, len(guids), 25):
            data = await self._post("webasseturls", {"photoGuids": guids[i : i + 25]})
            for checksum, item in data.get("items", {}).items():
                urls[checksum] = f"https://{item['url_location']}{item['url_path']}"
            if i + 25 < len(guids):
                await asyncio.sleep(0.5)
        return urls

    async def download(self, url: str) -> bytes:
        async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                raise ICloudError(f"download: HTTP {resp.status}")
            return await resp.read()
