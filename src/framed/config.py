"""Configuration: a YAML file plus a few environment overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class PixooConfig:
    host: str = "pixoo"
    max_brightness: int = 90
    min_interval: float = 1.0
    frame_interval: float = 0.2
    max_frames: int = 40
    reset_every: int = 1
    timeout: float = 8.0
    watchdog: float = 60.0


@dataclass
class PhotosConfig:
    album: str | None = None
    interval: float = 240.0
    refresh: float = 3600.0
    shuffle: bool = True
    saturation: float = 1.15
    contrast: float = 1.05
    min_width: int = 256


@dataclass
class GreetingConfig:
    headline: str = "WELCOME HOME"
    default_color: str = "#4cc9f0"
    colors: dict[str, str] = field(default_factory=dict)


@dataclass
class Config:
    listen_host: str = "0.0.0.0"
    listen_port: int = 8090
    token: str | None = None
    data_dir: Path = Path("./data")
    image_base_url: str | None = None
    pixoo: PixooConfig = field(default_factory=PixooConfig)
    photos: PhotosConfig = field(default_factory=PhotosConfig)
    greeting: GreetingConfig = field(default_factory=GreetingConfig)
    layers: list[dict] = field(default_factory=list)
    brightness: int = 80


DEFAULT_LAYER = {"id": "base", "priority": 0, "content": {"type": "photos"}}


def _section(cls, data: dict | None):
    data = dict(data or {})
    known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
    unknown = set(data) - set(known)
    if unknown:
        raise ValueError(f"unknown {cls.__name__} keys: {sorted(unknown)}")
    return cls(**known)


def load(path: str | Path | None) -> Config:
    raw: dict = {}
    if path:
        with open(path) as fh:
            raw = yaml.safe_load(fh) or {}
    listen = str(raw.get("listen", "0.0.0.0:8090"))
    host, _, port = listen.rpartition(":")
    cfg = Config(
        listen_host=host or "0.0.0.0",
        listen_port=int(port),
        token=os.environ.get("FRAMED_TOKEN") or raw.get("token"),
        data_dir=Path(os.environ.get("FRAMED_DATA_DIR") or raw.get("data_dir", "./data")),
        image_base_url=raw.get("image_base_url"),
        pixoo=_section(PixooConfig, raw.get("pixoo")),
        photos=_section(PhotosConfig, raw.get("photos")),
        greeting=_section(GreetingConfig, raw.get("greeting")),
        layers=list(
            raw.get("layers") or [{"id": "base", "priority": 0, "content": {"type": "photos"}}]
        ),
        brightness=int(raw.get("brightness", 80)),
    )
    if os.environ.get("FRAMED_PIXOO_HOST"):
        cfg.pixoo.host = os.environ["FRAMED_PIXOO_HOST"]
    if os.environ.get("FRAMED_PHOTOS_ALBUM"):
        cfg.photos.album = os.environ["FRAMED_PHOTOS_ALBUM"]
    return cfg
