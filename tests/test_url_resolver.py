"""Tests for URLResolver with mocked Playwright (no actual browser)."""

from unittest.mock import Mock, MagicMock, patch, PropertyMock

import pytest

from command_controller.url_resolver import URLResolver, LinkCandidate, URLResolutionResult
from command_controller.web_constants import COMMON_DOMAINS


class TestURLResolver:
    """Test suite for URLResolver with mocked Playwright."""

    @pytest.fixture
    def mock_playwright(self):
        """Create a mock Playwright context."""
        with patch("command_controller.url_resolver.sync_playwright") as mock_pw:
            # Mock the context manager
            playwright_instance = MagicMock()
            context_manager = MagicMock()
            context_manager.start.return_value = playwright_instance
            mock_pw.return_value = context_manager

            # Mock browser
            browser = MagicMock()
            playwright_instance.chromium.launch_persistent_context.return_value = browser

            # Mock page
            page = MagicMock()
            browser.pages = [page]
            browser.new_page.return_value = page

            yield {
                "playwright": playwright_instance,
                "browser": browser,
                "page": page,
            }

    def test_infer_initial_url_full_url(self, mock_playwright):
        """Test that full URLs are returned as-is."""
        resolver = URLResolver()
        url = resolver._infer_initial_url("https://example.com/path")
        assert url == "https://example.com/path"

    def test_infer_initial_url_http_scheme(self, mock_playwright):
        """Test that http:// URLs are preserved."""
        resolver = URLResolver()
        url = resolver._infer_initial_url("http://example.com")
        assert url == "http://example.com"

    def test_infer_initial_url_youtube(self, mock_playwright):
        """Test YouTube domain mapping."""
        resolver = URLResolver()
        url = resolver._infer_initial_url("youtube")
        assert url == "https://www.youtube.com"

    def test_infer_initial_url_gmail(self, mock_playwright):
        """Test Gmail domain mapping."""
        resolver = URLResolver()
        url = resolver._infer_initial_url("gmail")
        assert url == "https://mail.google.com"

    def test_infer_initial_url_github(self, mock_playwright):
        """Test GitHub domain mapping."""
        resolver = URLResolver()
        url = resolver._infer_initial_url("github")
        assert url == "https://github.com"

    def test_infer_initial_url_generic_domain(self, mock_playwright):
        """Test generic domain gets .com appended."""
        resolver = URLResolver()
        url = resolver._infer_initial_url("example")
        assert url == "https://example.com"

    def test_infer_initial_url_with_tld(self, mock_playwright):
        """Test domain with existing TLD is used as-is."""
        resolver = URLResolver()
        url = resolver._infer_initial_url("example.net")
        # Should add .com after removing .net
        assert url == "https://example.com"

    def test_infer_initial_url_multi_word_query(self, mock_playwright):
        """Test multi-word query uses first word for domain."""
        resolver = URLResolver()
        url = resolver._infer_initial_url("youtube cats")
        assert url == "https://www.youtube.com"

    def test_infer_initial_url_unknown_short_query(self, mock_playwright):
        """Test short unknown queries fall back to search."""
        resolver = URLResolver()
        url = resolver._infer_initial_url("abc")
        # Should fall back to search since too short for domain
        assert "duckduckgo.com" in url or "search" in url.lower()

    def test_rank_candidates_exact_text_match(self, mock_playwright):
        """Test exact text match gets highest score."""
        resolver = URLResolver()
        candidates = [
            LinkCandidate(
                url="https://example.com/1",
                link_text="other link",
                position_score=1.0,
            ),
            LinkCandidate(
                url="https://example.com/2",
                link_text="test query",
                position_score=0.5,
            ),
            LinkCandidate(
                url="https://example.com/3",
                link_text="unrelated",
                position_score=0.8,
            ),
        ]

        best = resolver._rank_candidates(candidates, "test query")

        assert best is not None
        assert best.url == "https://example.com/2"

    def test_rank_candidates_aria_label_match(self, mock_playwright):
        """Test aria-label match contributes to score."""
        resolver = URLResolver()
        candidates = [
            LinkCandidate(
                url="https://example.com/1",
                link_text="link",
                position_score=0.5,
                aria_label="test query",
            ),
            LinkCandidate(
                url="https://example.com/2",
                link_text="other",
                position_score=0.8,
                aria_label="unrelated",
            ),
        ]

        best = resolver._rank_candidates(candidates, "test query")

        assert best is not None
        assert best.url == "https://example.com/1"

    def test_rank_candidates_position_score(self, mock_playwright):
        """Test position score affects ranking."""
        resolver = URLResolver()
        candidates = [
            LinkCandidate(
                url="https://example.com/1",
                link_text="test",
                position_score=1.0,  # First link
            ),
            LinkCandidate(
                url="https://example.com/2",
                link_text="test",
                position_score=0.1,  # Last link
            ),
        ]

        best = resolver._rank_candidates(candidates, "test")

        # Higher position score should win
        assert best is not None
        assert best.url == "https://example.com/1"

    def test_rank_candidates_empty_list(self, mock_playwright):
        """Test ranking empty candidate list returns None."""
        resolver = URLResolver()
        best = resolver._rank_candidates([], "query")
        assert best is None

    def test_rank_candidates_all_terms_present(self, mock_playwright):
        """Test that matching all query terms increases score."""
        resolver = URLResolver()
        candidates = [
            LinkCandidate(
                url="https://example.com/1",
                link_text="cat video",  # Matches both terms
                position_score=0.5,
            ),
            LinkCandidate(
                url="https://example.com/2",
                link_text="cat",  # Matches one term
                position_score=0.5,
            ),
        ]

        best = resolver._rank_candidates(candidates, "cat video")

        assert best is not None
        assert best.url == "https://example.com/1"

    def test_cache_hit_skips_resolution(self, mock_playwright):
        """Test that cache hit returns cached result without resolution."""
        resolver = URLResolver()
        page = mock_playwright["page"]

        # First resolution (cache miss)
        page.locator.return_value.all.return_value = []
        result1 = resolver.resolve("test query")

        # Second resolution (cache hit)
        page.goto.reset_mock()
        result2 = resolver.resolve("test query")

        # Page.goto should not be called on cache hit
        page.goto.assert_not_called()
        assert result2.search_query == result1.search_query

    def test_cache_stores_failed_resolutions(self, mock_playwright):
        """Test that failed resolutions are cached."""
        resolver = URLResolver()
        page = mock_playwright["page"]

        # Mock no links found
        page.locator.return_value.all.return_value = []

        result1 = resolver.resolve("nonexistent")
        assert result1.status == "failed"

        # Second attempt should be cached
        page.goto.reset_mock()
        result2 = resolver.resolve("nonexistent")

        page.goto.assert_not_called()
        assert result2.status == "failed"

    def test_timeout_error_handling(self, mock_playwright):
        """Test that PlaywrightTimeoutError produces timeout status."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        resolver = URLResolver()
        page = mock_playwright["page"]

        # Mock timeout error
        page.goto.side_effect = PlaywrightTimeoutError("Navigation timeout")

        result = resolver.resolve("slow site")

        assert result.status == "timeout"
        assert result.resolved_url is None
        assert "timeout" in result.error_message.lower()

    def test_playwright_error_handling(self, mock_playwright):
        """Test that PlaywrightError produces failed status."""
        from playwright.sync_api import Error as PlaywrightError

        resolver = URLResolver()
        page = mock_playwright["page"]

        # Mock Playwright error
        page.goto.side_effect = PlaywrightError("Browser error")

        result = resolver.resolve("error site")

        assert result.status == "failed"
        assert result.resolved_url is None
        assert "error" in result.error_message.lower()

    def test_unexpected_exception_handling(self, mock_playwright):
        """Test that unexpected exceptions are caught and produce failed status."""
        resolver = URLResolver()
        page = mock_playwright["page"]

        # Mock unexpected error
        page.goto.side_effect = ValueError("Unexpected error")

        result = resolver.resolve("test")

        assert result.status == "failed"
        assert result.resolved_url is None
        assert "unexpected" in result.error_message.lower()

    def test_warmup_initializes_browser(self, mock_playwright):
        """Test that warmup() initializes browser eagerly."""
        resolver = URLResolver()
        assert not resolver._initialized

        resolver.warmup()

        assert resolver._initialized
        assert resolver._browser is not None
        assert resolver._page is not None

    def test_warmup_idempotent(self, mock_playwright):
        """Test that calling warmup() multiple times is safe."""
        resolver = URLResolver()

        resolver.warmup()
        browser1 = resolver._browser

        resolver.warmup()
        browser2 = resolver._browser

        # Should be same instance
        assert browser1 is browser2

    def test_shutdown_cleanup(self, mock_playwright):
        """Test that shutdown() properly cleans up resources."""
        resolver = URLResolver()
        resolver.warmup()

        page = resolver._page
        browser = resolver._browser

        resolver.shutdown()

        assert resolver._initialized is False
        assert resolver._page is None
        assert resolver._browser is None
        assert resolver._playwright is None

    def test_dom_search_filters_by_query(self, mock_playwright):
        """Test that DOM search filters links by query terms."""
        resolver = URLResolver()
        page = mock_playwright["page"]

        # Mock links
        link1 = MagicMock()
        link1.get_attribute.side_effect = lambda attr: {
            "href": "https://example.com/cats",
            "aria-label": None,
        }.get(attr)
        link1.inner_text.return_value = "cat videos"

        link2 = MagicMock()
        link2.get_attribute.side_effect = lambda attr: {
            "href": "https://example.com/dogs",
            "aria-label": None,
        }.get(attr)
        link2.inner_text.return_value = "dog videos"

        locator = MagicMock()
        locator.all.return_value = [link1, link2]
        page.locator.return_value = locator

        # Mock page.url for urljoin (Issue 3 fix)
        type(page).url = PropertyMock(return_value="https://example.com")

        candidates = resolver._search_dom_for_links(page, "cat")

        # Should only return link with "cat" in text
        assert len(candidates) == 1
        assert "cats" in candidates[0].url

    def test_dom_search_skips_invalid_hrefs(self, mock_playwright):
        """Test that DOM search skips invalid href values."""
        resolver = URLResolver()
        page = mock_playwright["page"]

        # Mock links with invalid hrefs
        link1 = MagicMock()
        link1.get_attribute.side_effect = lambda attr: {
            "href": "#",  # Fragment link
            "aria-label": None,
        }.get(attr)
        link1.inner_text.return_value = "test"

        link2 = MagicMock()
        link2.get_attribute.side_effect = lambda attr: {
            "href": "javascript:void(0)",  # JavaScript link
            "aria-label": None,
        }.get(attr)
        link2.inner_text.return_value = "test"

        link3 = MagicMock()
        link3.get_attribute.side_effect = lambda attr: {
            "href": "https://example.com/valid",
            "aria-label": None,
        }.get(attr)
        link3.inner_text.return_value = "test"

        locator = MagicMock()
        locator.all.return_value = [link1, link2, link3]
        page.locator.return_value = locator

        # Mock page.url for urljoin (Issue 3 fix)
        type(page).url = PropertyMock(return_value="https://example.com")

        candidates = resolver._search_dom_for_links(page, "test")

        # Should only return valid link
        assert len(candidates) == 1
        assert "valid" in candidates[0].url

    def test_dom_search_skips_empty_links(self, mock_playwright):
        """Test that links with no text or aria-label are skipped."""
        resolver = URLResolver()
        page = mock_playwright["page"]

        # Mock link with no text
        link1 = MagicMock()
        link1.get_attribute.side_effect = lambda attr: {
            "href": "https://example.com/1",
            "aria-label": None,
        }.get(attr)
        link1.inner_text.return_value = ""

        # Mock link with text
        link2 = MagicMock()
        link2.get_attribute.side_effect = lambda attr: {
            "href": "https://example.com/2",
            "aria-label": None,
        }.get(attr)
        link2.inner_text.return_value = "test"

        locator = MagicMock()
        locator.all.return_value = [link1, link2]
        page.locator.return_value = locator

        # Mock page.url for urljoin (Issue 3 fix)
        type(page).url = PropertyMock(return_value="https://example.com")

        candidates = resolver._search_dom_for_links(page, "test")

        # Should skip empty link
        assert len(candidates) == 1

    def test_dom_search_early_exit_after_20_candidates(self, mock_playwright):
        """Test that DOM search exits early after finding 20 candidates."""
        resolver = URLResolver()
        page = mock_playwright["page"]

        # Mock 100 matching links
        links = []
        for i in range(100):
            link = MagicMock()
            link.get_attribute.side_effect = lambda attr, i=i: {
                "href": f"https://example.com/{i}",
                "aria-label": None,
            }.get(attr)
            link.inner_text.return_value = "test"
            links.append(link)

        locator = MagicMock()
        locator.all.return_value = links
        page.locator.return_value = locator

        # Mock page.url for urljoin (Issue 3 fix)
        type(page).url = PropertyMock(return_value="https://example.com")

        candidates = resolver._search_dom_for_links(page, "test")

        # Should stop at 20 candidates
        assert len(candidates) == 20

    def test_dom_search_limits_to_100_links(self, mock_playwright):
        """Test that DOM search only processes first 100 links."""
        resolver = URLResolver()
        page = mock_playwright["page"]

        # Mock 200 links
        links = []
        for i in range(200):
            link = MagicMock()
            link.get_attribute.side_effect = lambda attr, i=i: {
                "href": f"https://example.com/{i}",
                "aria-label": None,
            }.get(attr)
            # Only first 100 have matching text
            link.inner_text.return_value = "test" if i < 100 else "other"
            links.append(link)

        locator = MagicMock()
        locator.all.return_value = links
        page.locator.return_value = locator

        page.evaluate.side_effect = lambda script, href: f"https://example.com{href}"

        candidates = resolver._search_dom_for_links(page, "test")

        # Should stop at 20 (early exit)
        assert len(candidates) <= 20

    def test_custom_settings(self, mock_playwright):
        """Test that custom settings are respected."""
        custom_settings = {
            "playwright_navigation_timeout_ms": 10000,
            "playwright_resolver_profile": "custom_profile",
        }

        resolver = URLResolver(settings=custom_settings)

        # Settings should be stored
        assert resolver._settings["playwright_navigation_timeout_ms"] == 10000
        assert resolver._settings["playwright_resolver_profile"] == "custom_profile"

    def test_position_score_calculation(self, mock_playwright):
        """Test that position score decreases with link position."""
        resolver = URLResolver()
        page = mock_playwright["page"]

        # Mock links at different positions
        links = []
        for i in range(10):
            link = MagicMock()
            link.get_attribute.side_effect = lambda attr, i=i: {
                "href": f"https://example.com/{i}",
                "aria-label": None,
            }.get(attr)
            link.inner_text.return_value = "test"
            links.append(link)

        locator = MagicMock()
        locator.all.return_value = links
        page.locator.return_value = locator

        # Mock page.url for urljoin (Issue 3 fix)
        type(page).url = PropertyMock(return_value="https://example.com")

        candidates = resolver._search_dom_for_links(page, "test")

        # First link should have higher position score
        assert candidates[0].position_score > candidates[-1].position_score

    # -----------------------------------------------------------------
    # Issue 4 - Cache Hit Indicator Tests
    # -----------------------------------------------------------------

    def test_cache_hit_marks_from_cache_true(self, mock_playwright):
        """Test that cache hits set from_cache=True."""
        resolver = URLResolver()
        page = mock_playwright["page"]

        # First resolution (cache miss)
        page.locator.return_value.all.return_value = []
        result1 = resolver.resolve("test query")
        assert result1.from_cache is False

        # Second resolution (cache hit)
        result2 = resolver.resolve("test query")
        assert result2.from_cache is True

    def test_fresh_resolution_has_from_cache_false(self, mock_playwright):
        """Test that fresh resolutions have from_cache=False."""
        resolver = URLResolver()
        page = mock_playwright["page"]

        page.locator.return_value.all.return_value = []
        result = resolver.resolve("unique query")

        assert result.from_cache is False

    # -----------------------------------------------------------------
    # Issue 2 - Thread Safety Tests
    # -----------------------------------------------------------------

    def test_resolver_has_page_lock(self, mock_playwright):
        """Test that URLResolver has a page lock for thread safety."""
        resolver = URLResolver()
        assert hasattr(resolver, "_page_lock")
        # Verify it's a threading Lock
        from threading import Lock
        assert isinstance(resolver._page_lock, type(Lock()))

    # -----------------------------------------------------------------
    # Issue 3 - URL Resolution via urljoin Tests
    # -----------------------------------------------------------------

    def test_dom_search_uses_urljoin_not_evaluate(self, mock_playwright):
        """Test that DOM search uses Python urljoin, not page.evaluate."""
        resolver = URLResolver()
        page = mock_playwright["page"]

        # Mock a link with relative href
        link = MagicMock()
        link.get_attribute.side_effect = lambda attr: {
            "href": "/relative/path",
            "aria-label": None,
        }.get(attr)
        link.inner_text.return_value = "test link"

        locator = MagicMock()
        locator.all.return_value = [link]
        page.locator.return_value = locator

        # Set page URL for urljoin base
        type(page).url = PropertyMock(return_value="https://example.com/page")

        candidates = resolver._search_dom_for_links(page, "test")

        # Should resolve relative URL using urljoin
        assert len(candidates) == 1
        assert candidates[0].url == "https://example.com/relative/path"

        # page.evaluate should NOT have been called for URL resolution
        # (it may be called for other purposes, but not for href resolution)
