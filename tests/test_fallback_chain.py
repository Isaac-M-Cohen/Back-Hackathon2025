"""Tests for FallbackChain (resolution, search, homepage fallbacks)."""

from unittest.mock import Mock, MagicMock

import pytest

from command_controller.fallback_chain import FallbackChain, FallbackResult
from command_controller.url_resolver import URLResolutionResult


class TestFallbackChain:
    """Test suite for FallbackChain."""

    def _create_mock_resolver(self, resolution_result):
        """Create a mock URLResolver that returns the given result."""
        resolver = Mock()
        resolver.resolve = Mock(return_value=resolution_result)
        return resolver

    def test_direct_resolution_success(self):
        """Test successful resolution on first attempt."""
        # Mock successful resolution
        resolution = URLResolutionResult(
            status="ok",
            resolved_url="https://www.youtube.com/results?search_query=cats",
            search_query="youtube cats",
            candidates_found=10,
            selected_reason="text_match",
            elapsed_ms=500,
        )
        resolver = self._create_mock_resolver(resolution)

        chain = FallbackChain(resolver)
        result = chain.execute("youtube cats")

        assert result.status == "ok"
        assert result.final_url == "https://www.youtube.com/results?search_query=cats"
        assert result.fallback_used == "resolution"
        assert "resolution" in result.attempts_made
        assert result.resolution_details is not None

    def test_search_fallback_triggered(self):
        """Test search fallback when resolution fails."""
        # Mock failed resolution
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="unknown site xyz",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
            error_message="No matching links found",
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {"enable_search_fallback": True}
        chain = FallbackChain(resolver, settings)
        result = chain.execute("unknown site xyz")

        assert result.status == "ok"
        assert "duckduckgo.com" in result.final_url
        assert "unknown+site+xyz" in result.final_url  # URL-encoded
        assert result.fallback_used == "search"
        assert "resolution" in result.attempts_made
        assert "search" in result.attempts_made

    def test_homepage_fallback_triggered(self):
        """Test homepage fallback when resolution and search fail."""
        # Mock failed resolution
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="youtube",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
            error_message="No matching links found",
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {
            "enable_search_fallback": False,  # Skip search
            "enable_homepage_fallback": True,
        }
        chain = FallbackChain(resolver, settings)
        result = chain.execute("youtube")

        assert result.status == "ok"
        assert result.final_url == "https://www.youtube.com"
        assert result.fallback_used == "homepage"
        assert "resolution" in result.attempts_made
        assert "homepage" in result.attempts_made

    def test_all_fallbacks_disabled_fails(self):
        """Test that disabling all fallbacks results in failure."""
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="test",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
            error_message="Failed",
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {
            "enable_search_fallback": False,
            "enable_homepage_fallback": False,
        }
        chain = FallbackChain(resolver, settings)
        result = chain.execute("test")

        assert result.status == "all_failed"
        assert result.final_url is None
        assert result.fallback_used == "none"
        assert result.error_message == "All fallback attempts exhausted"

    def test_search_fallback_url_encoding(self):
        """Test that search queries are properly URL-encoded."""
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="test query with spaces",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {"enable_search_fallback": True}
        chain = FallbackChain(resolver, settings)
        result = chain.execute("test query with spaces")

        assert result.status == "ok"
        assert "test+query+with+spaces" in result.final_url
        # Should not contain raw spaces
        assert " " not in result.final_url.split("?")[1]

    def test_search_fallback_special_characters(self):
        """Test that special characters are properly escaped in search."""
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query='test&query="value"',
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {"enable_search_fallback": True}
        chain = FallbackChain(resolver, settings)
        result = chain.execute('test&query="value"')

        assert result.status == "ok"
        # Special characters should be encoded
        assert "&" not in result.final_url.split("?")[1] or "%26" in result.final_url

    def test_custom_search_engine(self):
        """Test using custom search engine URL."""
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="test",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {
            "enable_search_fallback": True,
            "search_engine_url": "https://google.com/search?q={query}",
        }
        chain = FallbackChain(resolver, settings)
        result = chain.execute("test")

        assert result.status == "ok"
        assert "google.com" in result.final_url
        assert "q=test" in result.final_url

    def test_domain_extraction_youtube(self):
        """Test homepage fallback for YouTube."""
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="youtube",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {
            "enable_search_fallback": False,
            "enable_homepage_fallback": True,
        }
        chain = FallbackChain(resolver, settings)
        result = chain.execute("youtube")

        assert result.status == "ok"
        assert result.final_url == "https://www.youtube.com"

    def test_domain_extraction_gmail(self):
        """Test homepage fallback for Gmail."""
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="gmail",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {
            "enable_search_fallback": False,
            "enable_homepage_fallback": True,
        }
        chain = FallbackChain(resolver, settings)
        result = chain.execute("gmail")

        assert result.status == "ok"
        assert result.final_url == "https://mail.google.com"

    def test_domain_extraction_generic(self):
        """Test homepage fallback for generic domains."""
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="example",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {
            "enable_search_fallback": False,
            "enable_homepage_fallback": True,
        }
        chain = FallbackChain(resolver, settings)
        result = chain.execute("example")

        assert result.status == "ok"
        assert result.final_url == "https://example.com"

    def test_domain_extraction_with_tld_removal(self):
        """Test that existing TLDs are removed before .com is added."""
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="example.net",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {
            "enable_search_fallback": False,
            "enable_homepage_fallback": True,
        }
        chain = FallbackChain(resolver, settings)
        result = chain.execute("example.net")

        assert result.status == "ok"
        # Should strip .net and add .com
        assert result.final_url == "https://example.com"

    def test_domain_extraction_multi_word_query(self):
        """Test homepage fallback extracts first word from multi-word query."""
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="youtube cats video",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {
            "enable_search_fallback": False,
            "enable_homepage_fallback": True,
        }
        chain = FallbackChain(resolver, settings)
        result = chain.execute("youtube cats video")

        assert result.status == "ok"
        assert result.final_url == "https://www.youtube.com"

    def test_invalid_domain_fails_homepage_fallback(self):
        """Test that invalid domains fail homepage fallback."""
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="a",  # Too short
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {
            "enable_search_fallback": False,
            "enable_homepage_fallback": True,
        }
        chain = FallbackChain(resolver, settings)
        result = chain.execute("a")

        # Should fail because domain is too short
        assert result.status == "all_failed"

    def test_attempts_made_tracking(self):
        """Test that attempts_made correctly tracks fallback sequence."""
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="test",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {
            "enable_search_fallback": True,
            "enable_homepage_fallback": False,
        }
        chain = FallbackChain(resolver, settings)
        result = chain.execute("test")

        assert "resolution" in result.attempts_made
        assert "search" in result.attempts_made

    def test_elapsed_time_tracking(self):
        """Test that elapsed_ms is tracked."""
        resolution = URLResolutionResult(
            status="ok",
            resolved_url="https://youtube.com",
            search_query="youtube",
            candidates_found=1,
            selected_reason="text_match",
            elapsed_ms=500,
        )
        resolver = self._create_mock_resolver(resolution)

        chain = FallbackChain(resolver)
        result = chain.execute("youtube")

        assert result.elapsed_ms >= 0
        assert isinstance(result.elapsed_ms, int)

    def test_exception_in_resolution_triggers_fallback(self):
        """Test that exceptions in resolution trigger fallback chain."""
        resolver = Mock()
        resolver.resolve = Mock(side_effect=Exception("Network error"))

        settings = {"enable_search_fallback": True}
        chain = FallbackChain(resolver, settings)
        result = chain.execute("test")

        # Should fall back to search despite exception
        assert result.status == "ok"
        assert result.fallback_used == "search"

    def test_timeout_status_triggers_fallback(self):
        """Test that timeout status triggers fallback."""
        resolution = URLResolutionResult(
            status="timeout",
            resolved_url=None,
            search_query="slow site",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=30000,
            error_message="Navigation timeout",
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {"enable_search_fallback": True}
        chain = FallbackChain(resolver, settings)
        result = chain.execute("slow site")

        assert result.status == "ok"
        assert result.fallback_used == "search"

    def test_resolution_details_preserved(self):
        """Test that resolution details are preserved in successful resolution."""
        resolution = URLResolutionResult(
            status="ok",
            resolved_url="https://youtube.com",
            search_query="youtube",
            candidates_found=5,
            selected_reason="text_match",
            elapsed_ms=500,
        )
        resolver = self._create_mock_resolver(resolution)

        chain = FallbackChain(resolver)
        result = chain.execute("youtube")

        assert result.resolution_details is not None
        assert result.resolution_details.candidates_found == 5
        assert result.resolution_details.selected_reason == "text_match"

    def test_fallback_used_none_when_all_fail(self):
        """Test fallback_used is 'none' when all attempts fail."""
        resolution = URLResolutionResult(
            status="failed",
            resolved_url=None,
            search_query="invalid",
            candidates_found=0,
            selected_reason=None,
            elapsed_ms=100,
        )
        resolver = self._create_mock_resolver(resolution)

        settings = {
            "enable_search_fallback": False,
            "enable_homepage_fallback": False,
        }
        chain = FallbackChain(resolver, settings)
        result = chain.execute("invalid")

        assert result.fallback_used == "none"
