"""The photo library: a shared album mirrored as pre-rendered 64x64 frames."""

from __future__ import annotations

import io
import logging
import random
import time
from pathlib import Path

from PIL import Image

from framed.render import fit_image
from framed.sources.icloud import SharedAlbum

log = logging.getLogger(__name__)


class PhotoLibrary:
    def __init__(
        self,
        cache_dir: Path,
        album: SharedAlbum | None,
        *,
        shuffle: bool = True,
        saturation: float = 1.15,
        contrast: float = 1.05,
    ) -> None:
        self.cache_dir = cache_dir
        self.album = album
        self.shuffle = shuffle
        self.saturation = saturation
        self.contrast = contrast
        self.last_refresh: float | None = None
        self.last_error: str | None = None
        self._order: list[Path] = []
        self._index = 0
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._reload_order()

    def _reload_order(self) -> None:
        files = sorted(self.cache_dir.glob("*.png"))
        if self.shuffle:
            random.shuffle(files)
        self._order = files
        self._index = 0

    @property
    def count(self) -> int:
        return len(self._order)

    def next(self) -> Image.Image | None:
        """The next frame in rotation, or None when the library is empty."""
        for _ in range(len(self._order)):
            if self._index >= len(self._order):
                self._reload_order()
                if not self._order:
                    return None
            path = self._order[self._index]
            self._index += 1
            try:
                return Image.open(path).convert("RGB")
            except OSError as exc:
                log.warning("dropping unreadable frame %s: %s", path.name, exc)
                path.unlink(missing_ok=True)
        return None

    def render(self, data: bytes) -> Image.Image:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            return fit_image(img, saturation=self.saturation, contrast=self.contrast)

    async def refresh(self) -> int:
        """Mirror the album into the cache. Returns the number of new frames."""
        if self.album is None:
            return 0
        try:
            photos = await self.album.list_photos()
            wanted = {f"{p.guid}-{p.checksum[:12]}": p for p in photos}
            existing = {path.stem for path in self.cache_dir.glob("*.png")}
            missing = {key: p for key, p in wanted.items() if key not in existing}
            added = 0
            if missing:
                urls = await self.album.asset_urls(list(missing.values()))
                for key, photo in missing.items():
                    url = urls.get(photo.checksum)
                    if not url:
                        log.warning("no url for %s", photo.guid)
                        continue
                    frame = self.render(await self.album.download(url))
                    tmp = self.cache_dir / f"{key}.tmp"
                    frame.save(tmp, format="PNG")
                    tmp.replace(self.cache_dir / f"{key}.png")
                    added += 1
            for stale in existing - set(wanted):
                (self.cache_dir / f"{stale}.png").unlink(missing_ok=True)
            if added or existing - set(wanted):
                self._reload_order()
            self.last_refresh = time.time()
            self.last_error = None
            log.info("album %r: %d frames (%d new)", self.album.name, self.count, added)
            return added
        except Exception as exc:  # noqa: BLE001
            self.last_error = repr(exc)
            log.warning("album refresh failed: %r", exc)
            return 0

    def status(self) -> dict:
        return {
            "count": self.count,
            "last_refresh": self.last_refresh,
            "last_error": self.last_error,
            "album": self.album.name if self.album else None,
        }
