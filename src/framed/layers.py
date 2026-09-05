"""The layer stack: what is on screen is the highest-priority live layer."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Layer:
    id: str
    priority: int
    content: dict
    ttl: float | None = None
    created: float = field(default_factory=time.time)
    version: int = 0

    @property
    def expires_at(self) -> float | None:
        return None if self.ttl is None else self.created + self.ttl

    def expired(self, now: float | None = None) -> bool:
        exp = self.expires_at
        return exp is not None and (now or time.time()) >= exp

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "priority": self.priority,
            "content": self.content,
            "ttl": self.ttl,
            "expires_at": self.expires_at,
            "created": self.created,
        }


class LayerStack:
    def __init__(self) -> None:
        self._layers: dict[str, Layer] = {}
        self._last_shown: dict[str, float] = {}
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def upsert(self, layer: Layer, cooldown: float | None = None) -> bool:
        """Add or replace a layer. Returns False when ``cooldown`` seconds have not
        passed since the same id was last put on screen."""
        if cooldown:
            last = self._last_shown.get(layer.id)
            if last is not None and time.time() - last < cooldown:
                return False
        self._version += 1
        layer.version = self._version
        self._layers[layer.id] = layer
        return True

    def remove(self, layer_id: str) -> bool:
        if layer_id in self._layers:
            del self._layers[layer_id]
            self._version += 1
            return True
        return False

    def mark_shown(self, layer_id: str) -> None:
        self._last_shown[layer_id] = time.time()

    def purge(self, now: float | None = None) -> list[Layer]:
        now = now or time.time()
        gone = [layer for layer in self._layers.values() if layer.expired(now)]
        for layer in gone:
            del self._layers[layer.id]
        if gone:
            self._version += 1
        return gone

    def top(self) -> Layer | None:
        self.purge()
        if not self._layers:
            return None
        return max(self._layers.values(), key=lambda layer: (layer.priority, layer.version))

    def next_expiry(self) -> float | None:
        expiries = [layer.expires_at for layer in self._layers.values() if layer.ttl is not None]
        return min(expiries) if expiries else None

    def all(self) -> list[Layer]:
        self.purge()
        return sorted(self._layers.values(), key=lambda layer: -layer.priority)
