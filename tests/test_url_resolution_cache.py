"""Tests for URLResolutionCache (TTL, LRU eviction, pruning)."""

import time
from unittest.mock import Mock

import pytest

from command_controller.url_resolution_cache import URLResolutionCache


# Mock URLResolutionResult for testing
class MockResolutionResult:
    """Mock URLResolutionResult for testing."""

    def __init__(self, url: str, status: str = "ok"):
        self.resolved_url = url
        self.status = status
        self.search_query = "test"
        self.candidates_found = 1
        self.selected_reason = "test_match"
        self.elapsed_ms = 100
        self.error_message = None


class TestURLResolutionCache:
    """Test suite for URLResolutionCache."""

    def test_cache_miss_returns_none(self):
        """Test that cache returns None for non-existent keys."""
        cache = URLResolutionCache(ttl_secs=900)
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_hit_returns_result(self):
        """Test that cache returns stored result on hit."""
        cache = URLResolutionCache(ttl_secs=900)
        mock_result = MockResolutionResult("https://example.com")

        cache.put("test_query", mock_result)
        retrieved = cache.get("test_query")

        assert retrieved is not None
        assert retrieved.resolved_url == "https://example.com"
        assert retrieved.status == "ok"

    def test_cache_size_tracking(self):
        """Test that cache size is tracked correctly."""
        cache = URLResolutionCache(ttl_secs=900)
        assert cache.size() == 0

        cache.put("query1", MockResolutionResult("https://example1.com"))
        assert cache.size() == 1

        cache.put("query2", MockResolutionResult("https://example2.com"))
        assert cache.size() == 2

    def test_cache_clear(self):
        """Test that clear() removes all entries."""
        cache = URLResolutionCache(ttl_secs=900)
        cache.put("query1", MockResolutionResult("https://example1.com"))
        cache.put("query2", MockResolutionResult("https://example2.com"))

        assert cache.size() == 2
        cache.clear()
        assert cache.size() == 0
        assert cache.get("query1") is None

    def test_ttl_expiration_on_get(self):
        """Test that expired entries are removed on get()."""
        cache = URLResolutionCache(ttl_secs=1)  # 1 second TTL
        cache.put("query", MockResolutionResult("https://example.com"))

        # Should be present immediately
        assert cache.get("query") is not None
        assert cache.size() == 1

        # Wait for expiration
        time.sleep(1.1)

        # Should be gone after TTL
        assert cache.get("query") is None
        assert cache.size() == 0

    def test_lru_eviction_on_max_size(self):
        """Test that LRU eviction works when max_size is exceeded."""
        cache = URLResolutionCache(ttl_secs=900, max_size=3)

        # Add 3 entries (at capacity)
        cache.put("query1", MockResolutionResult("https://example1.com"))
        cache.put("query2", MockResolutionResult("https://example2.com"))
        cache.put("query3", MockResolutionResult("https://example3.com"))

        assert cache.size() == 3
        assert cache.get("query1") is not None

        # Add 4th entry - should evict query1 (least recently used)
        cache.put("query4", MockResolutionResult("https://example4.com"))

        assert cache.size() == 3
        assert cache.get("query1") is None  # Evicted
        assert cache.get("query2") is not None
        assert cache.get("query3") is not None
        assert cache.get("query4") is not None

    def test_lru_eviction_with_access_pattern(self):
        """Test that accessing entries updates LRU order."""
        cache = URLResolutionCache(ttl_secs=900, max_size=3)

        cache.put("query1", MockResolutionResult("https://example1.com"))
        cache.put("query2", MockResolutionResult("https://example2.com"))
        cache.put("query3", MockResolutionResult("https://example3.com"))

        # Access query1 to make it most recently used
        cache.get("query1")

        # Add query4 - should evict query2 (now least recently used)
        cache.put("query4", MockResolutionResult("https://example4.com"))

        assert cache.get("query1") is not None  # Not evicted
        assert cache.get("query2") is None  # Evicted
        assert cache.get("query3") is not None
        assert cache.get("query4") is not None

    def test_update_existing_entry(self):
        """Test that updating existing entry preserves LRU order."""
        cache = URLResolutionCache(ttl_secs=900, max_size=3)

        cache.put("query1", MockResolutionResult("https://example1.com"))
        cache.put("query2", MockResolutionResult("https://example2.com"))

        # Update query1 with new result
        cache.put("query1", MockResolutionResult("https://updated.com"))

        result = cache.get("query1")
        assert result is not None
        assert result.resolved_url == "https://updated.com"
        assert cache.size() == 2  # Size unchanged

    def test_proactive_expiration_on_put(self):
        """Test that expired entries are pruned on put()."""
        cache = URLResolutionCache(ttl_secs=1, max_size=10)

        # Add entries that will expire
        cache.put("query1", MockResolutionResult("https://example1.com"))
        cache.put("query2", MockResolutionResult("https://example2.com"))

        assert cache.size() == 2

        # Wait for expiration
        time.sleep(1.1)

        # Add new entry - should trigger pruning of expired entries
        cache.put("query3", MockResolutionResult("https://example3.com"))

        # Cache should only contain query3 (expired entries pruned)
        assert cache.size() == 1
        assert cache.get("query1") is None
        assert cache.get("query2") is None
        assert cache.get("query3") is not None

    def test_mixed_expiration_and_lru(self):
        """Test that both expiration and LRU work together."""
        cache = URLResolutionCache(ttl_secs=2, max_size=3)

        # Add 2 entries
        cache.put("query1", MockResolutionResult("https://example1.com"))
        cache.put("query2", MockResolutionResult("https://example2.com"))

        # Wait for them to expire
        time.sleep(2.1)

        # Add 3 new entries (should trigger pruning first, then LRU)
        cache.put("query3", MockResolutionResult("https://example3.com"))
        cache.put("query4", MockResolutionResult("https://example4.com"))
        cache.put("query5", MockResolutionResult("https://example5.com"))

        # Only new entries should be present
        assert cache.size() == 3
        assert cache.get("query1") is None
        assert cache.get("query2") is None
        assert cache.get("query3") is not None
        assert cache.get("query4") is not None
        assert cache.get("query5") is not None

    def test_cache_handles_failed_resolutions(self):
        """Test that cache stores failed resolutions to avoid retries."""
        cache = URLResolutionCache(ttl_secs=900)
        failed_result = MockResolutionResult(None, status="failed")
        failed_result.error_message = "Navigation timeout"

        cache.put("bad_query", failed_result)
        retrieved = cache.get("bad_query")

        assert retrieved is not None
        assert retrieved.status == "failed"
        assert retrieved.resolved_url is None

    def test_zero_ttl_effectively_disables_caching(self):
        """Test that TTL=0 causes immediate expiration."""
        cache = URLResolutionCache(ttl_secs=0)
        cache.put("query", MockResolutionResult("https://example.com"))

        # Should expire immediately on get()
        # Note: This is implementation-specific; age check uses > not >=
        # So TTL=0 should expire on next get() call
        time.sleep(0.01)  # Tiny delay to ensure age > 0
        assert cache.get("query") is None

    def test_large_cache_performance(self):
        """Test that cache handles large number of entries efficiently."""
        cache = URLResolutionCache(ttl_secs=900, max_size=1000)

        # Add 1000 entries
        for i in range(1000):
            cache.put(f"query{i}", MockResolutionResult(f"https://example{i}.com"))

        assert cache.size() == 1000

        # Add one more - should evict oldest
        cache.put("query1000", MockResolutionResult("https://example1000.com"))

        assert cache.size() == 1000
        assert cache.get("query0") is None  # First entry evicted
        assert cache.get("query999") is not None  # Last entry still present
