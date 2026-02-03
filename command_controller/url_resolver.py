"""Headless Playwright-based URL resolver with DOM search."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
import re

from playwright.sync_api import (
    sync_playwright,
    Page,
    Browser,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)
from utils.log_utils import tprint
from utils.settings_store import get_settings, deep_log, is_deep_logging
from command_controller.url_resolution_cache import URLResolutionCache
from command_controller.web_constants import (
    COMMON_DOMAINS,
    SCORE_EXACT_TEXT_MATCH,
    SCORE_ARIA_LABEL_MATCH,
    SCORE_PER_TERM_MATCH,
)


@dataclass
class LinkCandidate:
    """A candidate URL found during DOM search."""

    url: str
    link_text: str
    position_score: float  # 0.0-1.0, higher = more prominent
    aria_label: str | None = None
    selector: str | None = None


@dataclass
class URLResolutionResult:
    """Result of URL resolution attempt."""

    status: str  # "ok" | "failed" | "timeout"
    resolved_url: str | None
    search_query: str
    candidates_found: int
    selected_reason: str | None  # "text_match" | "position" | "aria_label"
    elapsed_ms: int
    error_message: str | None = None


class URLResolver:
    """Headless Playwright-based URL resolver with DOM search."""

    def __init__(self, settings: dict | None = None) -> None:
        """Initialize URL resolver with separate headless Playwright context.

        Args:
            settings: Configuration dict (uses get_settings() if None)
        """
        self._settings = settings or get_settings()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None  # Reuse single page across resolutions
        self._initialized = False
        self._cache = URLResolutionCache(ttl_secs=900)  # 15 minutes

    def warmup(self) -> None:
        """Eagerly initialize browser context to amortize startup cost.

        This can be called during application startup to avoid
        paying the 1-3 second browser launch cost on first resolution.
        """
        if not self._initialized:
            if is_deep_logging():
                deep_log("[DEEP][URL_RESOLVER] Warming up browser context")
            self._ensure_browser()
            tprint("[URL_RESOLVER] Browser warm-up completed")

    def resolve(self, query: str) -> URLResolutionResult:
        """Resolve a search query or partial URL to a final URL.

        Args:
            query: Search query or partial URL (e.g., "youtube cats", "gmail inbox")

        Returns:
            URLResolutionResult with status, resolved_url, and metadata
        """
        start = time.monotonic()

        # Check cache
        cached = self._cache.get(query)
        if cached:
            if is_deep_logging():
                deep_log(f"[DEEP][URL_RESOLVER] Cache hit for query={query!r}")
            return cached

        try:
            self._ensure_browser()

            # Infer initial URL to navigate to
            initial_url = self._infer_initial_url(query)
            if is_deep_logging():
                deep_log(
                    f"[DEEP][URL_RESOLVER] Resolving query={query!r} initial_url={initial_url}"
                )

            # Reuse single page across resolutions
            timeout_ms = self._settings.get("playwright_navigation_timeout_ms", 30000)

            # Navigate to initial URL
            self._page.goto(initial_url, wait_until="domcontentloaded", timeout=timeout_ms)
            self._page.wait_for_load_state("networkidle", timeout=timeout_ms)

            # Search DOM for relevant links
            candidates = self._search_dom_for_links(self._page, query)

            if is_deep_logging():
                deep_log(
                    f"[DEEP][URL_RESOLVER] Found {len(candidates)} candidates for query={query!r}"
                )

            # Rank and select best match
            best_candidate = self._rank_candidates(candidates, query)

            elapsed_ms = int((time.monotonic() - start) * 1000)

            if best_candidate:
                result = URLResolutionResult(
                    status="ok",
                    resolved_url=best_candidate.url,
                    search_query=query,
                    candidates_found=len(candidates),
                    selected_reason="text_match",
                    elapsed_ms=elapsed_ms,
                )
            else:
                result = URLResolutionResult(
                    status="failed",
                    resolved_url=None,
                    search_query=query,
                    candidates_found=len(candidates),
                    selected_reason=None,
                    elapsed_ms=elapsed_ms,
                    error_message="No matching links found",
                )

            # Cache result
            self._cache.put(query, result)
            return result

        except PlaywrightTimeoutError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            result = URLResolutionResult(
                status="timeout",
                resolved_url=None,
                search_query=query,
                candidates_found=0,
                selected_reason=None,
                elapsed_ms=elapsed_ms,
                error_message=f"Navigation timeout: {exc}",
            )
            # Cache failures to avoid repeated attempts
            self._cache.put(query, result)
            return result
        except PlaywrightError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            result = URLResolutionResult(
                status="failed",
                resolved_url=None,
                search_query=query,
                candidates_found=0,
                selected_reason=None,
                elapsed_ms=elapsed_ms,
                error_message=f"Browser error: {exc}",
            )
            self._cache.put(query, result)
            return result
        except Exception as exc:
            # Catch-all for unexpected errors
            elapsed_ms = int((time.monotonic() - start) * 1000)
            result = URLResolutionResult(
                status="failed",
                resolved_url=None,
                search_query=query,
                candidates_found=0,
                selected_reason=None,
                elapsed_ms=elapsed_ms,
                error_message=f"Unexpected error: {exc}",
            )
            self._cache.put(query, result)
            return result

    def _ensure_browser(self) -> None:
        """Initialize headless Playwright context on first call."""
        if self._initialized:
            return

        profile_dir = self._settings.get(
            "playwright_resolver_profile", "user_data/playwright_resolver"
        )
        Path(profile_dir).mkdir(parents=True, exist_ok=True, mode=0o700)

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=True,  # Always headless for resolver
                accept_downloads=False,
            )
            # Create single page to reuse across all resolutions
            self._page = (
                self._browser.pages[0]
                if self._browser.pages
                else self._browser.new_page()
            )
            self._initialized = True
            tprint("[URL_RESOLVER] Headless Playwright context initialized")
        except PlaywrightError as exc:
            # Cleanup on failure
            if self._playwright:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
            self._playwright = None
            raise RuntimeError(
                f"Failed to launch resolver browser: {exc}\n"
                "If Chromium is not installed, run: playwright install chromium"
            ) from exc
        except Exception as exc:
            # Unexpected errors during initialization
            if self._playwright:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
            self._playwright = None
            raise RuntimeError(
                f"Unexpected error initializing browser: {exc}"
            ) from exc

    def _search_dom_for_links(self, page: Page, query: str) -> list[LinkCandidate]:
        """Extract candidate URLs from DOM based on text matching.

        Args:
            page: Playwright Page object
            query: Search query for filtering links

        Returns:
            List of LinkCandidate objects with scoring
        """
        candidates: list[LinkCandidate] = []
        query_terms = query.lower().split()

        try:
            # Find all anchor tags (limit to first 100 for performance)
            links = page.locator("a[href]").all()
            max_links = min(len(links), 100)  # Process top 100 links only

            if is_deep_logging():
                deep_log(f"[DEEP][URL_RESOLVER] Processing {max_links} of {len(links)} links")

            # Batch extract link data to minimize round-trips
            for i in range(max_links):
                link = links[i]
                try:
                    href = link.get_attribute("href")
                    if not href or href.startswith("#") or href == "javascript:void(0)":
                        continue

                    # Get link text and aria label (batched where possible)
                    link_text = link.inner_text().strip()
                    aria_label = link.get_attribute("aria-label")

                    # Skip empty links
                    if not link_text and not aria_label:
                        continue

                    # Check if any query term appears in link text or aria label
                    search_text = (link_text + " " + (aria_label or "")).lower()
                    if not any(term in search_text for term in query_terms):
                        continue

                    # Calculate position score (earlier = higher)
                    position_score = max(0.1, 1.0 - (i / max(max_links, 1)))

                    # Make URL absolute
                    resolved_href = page.evaluate(
                        f"(href) => new URL(href, document.baseURI).href", href
                    )

                    candidates.append(
                        LinkCandidate(
                            url=resolved_href,
                            link_text=link_text,
                            position_score=position_score,
                            aria_label=aria_label,
                        )
                    )

                    # Early exit if we found enough good candidates
                    if len(candidates) >= 20:
                        if is_deep_logging():
                            deep_log(f"[DEEP][URL_RESOLVER] Early exit with {len(candidates)} candidates")
                        break

                except Exception:
                    # Skip problematic links
                    continue

        except Exception as exc:
            if is_deep_logging():
                deep_log(f"[DEEP][URL_RESOLVER] DOM search error: {exc}")

        return candidates

    def _rank_candidates(
        self, candidates: list[LinkCandidate], query: str
    ) -> LinkCandidate | None:
        """Rank candidates and return best match.

        Args:
            candidates: List of LinkCandidate objects
            query: Original search query

        Returns:
            Best matching candidate or None if no good matches
        """
        if not candidates:
            return None

        query_lower = query.lower()
        query_terms = query_lower.split()

        scored_candidates: list[tuple[float, LinkCandidate]] = []

        for candidate in candidates:
            score = 0.0

            # Score 1: Exact text match (high priority)
            if query_lower in candidate.link_text.lower():
                score += SCORE_EXACT_TEXT_MATCH

            # Score 2: Aria label match
            if candidate.aria_label and query_lower in candidate.aria_label.lower():
                score += SCORE_ARIA_LABEL_MATCH

            # Score 3: All query terms present
            search_text = (
                candidate.link_text + " " + (candidate.aria_label or "")
            ).lower()
            matching_terms = sum(1 for term in query_terms if term in search_text)
            score += matching_terms * SCORE_PER_TERM_MATCH

            # Score 4: Position score (earlier links preferred)
            score += candidate.position_score

            scored_candidates.append((score, candidate))

        # Sort by score descending
        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        # Return highest scoring candidate
        return scored_candidates[0][1] if scored_candidates else None

    def _infer_initial_url(self, query: str) -> str:
        """Infer starting URL from query.

        Args:
            query: User's search query or partial URL

        Returns:
            Full URL to navigate to
        """
        query_lower = query.lower().strip()

        # Check if it's already a full URL
        if query_lower.startswith("http://") or query_lower.startswith("https://"):
            return query

        # Extract first word as potential domain
        first_word = query_lower.split()[0] if " " in query_lower else query_lower

        # Check common domain mapping
        if first_word in COMMON_DOMAINS:
            return f"https://{COMMON_DOMAINS[first_word]}"

        # Try to construct URL from domain keyword
        # Remove common TLDs if present
        domain = re.sub(r"\.(com|net|org|io|co)$", "", first_word)

        # Check if it looks like a domain
        if "." in domain or len(domain) > 3:
            # Try .com first
            return f"https://{domain}.com"

        # Fallback to search engine
        search_engine = self._settings.get(
            "search_engine_url", "https://duckduckgo.com/?q={query}"
        )
        from urllib.parse import quote_plus

        encoded_query = quote_plus(query)
        return search_engine.replace("{query}", encoded_query)

    def shutdown(self) -> None:
        """Close headless browser and Playwright instance."""
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._initialized = False
        self._page = None
        self._browser = None
        self._playwright = None
