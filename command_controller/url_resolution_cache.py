"""In-memory cache with TTL and LRU eviction for URL resolutions."""

from __future__ import annotations

from dataclasses import dataclass
import time
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from command_controller.url_resolver import URLResolutionResult


@dataclass
class CacheEntry:
    """Cache entry with timestamp for TTL expiration."""

    result: URLResolutionResult
    timestamp: float


class URLResolutionCache:
    """In-memory cache with TTL and LRU eviction for URL resolutions."""

    def __init__(self, ttl_secs: int = 900, max_size: int = 100) -> None:
        """Initialize cache with TTL and max size.

        Args:
            ttl_secs: Time-to-live in seconds (default: 15 minutes)
            max_size: Maximum number of entries (default: 100, LRU eviction)
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._ttl = ttl_secs
        self._max_size = max_size

    def get(self, query: str) -> URLResolutionResult | None:
        """Retrieve cached result if not expired.

        Args:
            query: Search query (cache key)

        Returns:
            URLResolutionResult if found and not expired, None otherwise
        """
        entry = self._cache.get(query)
        if entry is None:
            return None

        # Check expiration
        age = time.time() - entry.timestamp
        if age > self._ttl:
            # Expired, remove from cache
            del self._cache[query]
            return None

        # Move to end (mark as recently used)
        self._cache.move_to_end(query)
        return entry.result

    def put(self, query: str, result: URLResolutionResult) -> None:
        """Store result with timestamp and LRU eviction.

        Args:
            query: Search query (cache key)
            result: URLResolutionResult to cache
        """
        # Proactively clean up expired entries before adding (performance optimization)
        self._prune_expired()

        # If already exists, update and move to end
        if query in self._cache:
            self._cache[query] = CacheEntry(result=result, timestamp=time.time())
            self._cache.move_to_end(query)
            return

        # Check if we need to evict oldest entry
        if len(self._cache) >= self._max_size:
            # Remove least recently used (first item)
            self._cache.popitem(last=False)

        # Add new entry at end (most recently used)
        self._cache[query] = CacheEntry(result=result, timestamp=time.time())

    def _prune_expired(self) -> None:
        """Remove all expired entries from cache.

        This is called on put() to batch-cleanup expired entries,
        reducing overhead compared to checking on every get().
        """
        now = time.time()
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if (now - entry.timestamp) > self._ttl
        ]
        for key in expired_keys:
            del self._cache[key]

    def clear(self) -> None:
        """Invalidate all cached entries."""
        self._cache.clear()

    def size(self) -> int:
        """Return number of cached entries (includes expired entries)."""
        return len(self._cache)
