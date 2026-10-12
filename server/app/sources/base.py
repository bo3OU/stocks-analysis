import logging
from datetime import timedelta
from typing import Any, Callable

from app.cache import Cache, CacheEntry

log = logging.getLogger(__name__)


class SourceError(Exception):
    """An upstream source failed and there was nothing cached to fall back on."""


class NotFound(Exception):
    """The source answered, but has nothing for this key (unknown ticker, no data)."""


class Source:
    """Base for every adapter: one upstream, one cache namespace, one TTL.

    Subclasses implement the fetch and call `cached()`; they never talk to the cache
    directly. That keeps the rate-limit and freshness rules in one place.
    """

    name: str = "source"
    ttl: timedelta = timedelta(hours=12)

    def __init__(self, cache: Cache):
        self.cache = cache

    def cached(self, key: str, fetch: Callable[[], Any], ttl: timedelta | None = None) -> CacheEntry:
        ttl = ttl or self.ttl
        entry = self.cache.get(self.name, key)
        if entry is not None and entry.age() < ttl:
            return entry
        try:
            payload = fetch()
        except NotFound:
            raise
        except Exception as exc:  # network, HTTP or parse errors
            if entry is not None:
                log.warning("%s fetch failed for %s, serving stale cache: %s", self.name, key, exc)
                return entry
            raise SourceError(f"{self.name}: {exc}") from exc
        return self.cache.put(self.name, key, payload)
