"""Small in-process TTL cache for expensive runtime calls.

This intentionally stays simple because Render instances are ephemeral and may
run multiple workers. It still helps a lot with repeated page loads inside one
worker by avoiding duplicate upstream GraphQL and price requests.
"""

from __future__ import annotations

import time
from threading import RLock
from typing import Callable, Generic, Hashable, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self) -> None:
        self._lock = RLock()
        self._store: dict[Hashable, tuple[float, T]] = {}

    def get_or_set(self, key: Hashable, ttl_seconds: float, factory: Callable[[], T]) -> T:
        now = time.time()
        with self._lock:
            cached = self._store.get(key)
            if cached is not None:
                expires_at, value = cached
                if expires_at > now:
                    return value

        value = factory()
        with self._lock:
            self._store[key] = (now + max(0.0, float(ttl_seconds)), value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
