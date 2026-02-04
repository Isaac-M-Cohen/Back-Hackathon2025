"""Orchestrate URL resolution with multiple fallback strategies."""

from __future__ import annotations

from dataclasses import dataclass
import time
import re
from urllib.parse import quote_plus

from command_controller.url_resolver import URLResolver, URLResolutionResult
from command_controller.web_constants import COMMON_DOMAINS
from utils.log_utils import tprint
from utils.settings_store import get_settings, deep_log, is_deep_logging


@dataclass
class FallbackResult:
    """Result of fallback chain execution."""

    status: str  # "ok" | "all_failed"
    final_url: str | None
    fallback_used: str  # "resolution" | "search" | "homepage" | "none"
    attempts_made: list[str]
    resolution_details: URLResolutionResult | None
    elapsed_ms: int
    error_message: str | None = None


class FallbackChain:
    """Orchestrate URL resolution with multiple fallback strategies."""

    def __init__(self, resolver: URLResolver, settings: dict | None = None) -> None:
        """Initialize fallback chain.

        Args:
            resolver: URLResolver instance (shared across fallbacks)
            settings: Configuration dict (uses get_settings() if None)
        """
        self._resolver = resolver
        self._settings = settings or get_settings()

    def execute(self, query: str) -> FallbackResult:
        """Execute fallback chain: resolution → search → homepage.

        Args:
            query: Search query or partial URL

        Returns:
            FallbackResult with final URL and metadata
        """
        start = time.monotonic()
        attempts_made: list[str] = []

        if is_deep_logging():
            deep_log(f"[DEEP][FALLBACK_CHAIN] Starting fallback chain for query={query!r}")

        # Attempt 1: Direct resolution
        result = self._try_direct_resolution(query)
        if result:
            result.attempts_made = attempts_made + ["resolution"]
            if is_deep_logging():
                deep_log(
                    f"[DEEP][FALLBACK_CHAIN] Resolution succeeded for query={query!r}"
                )
            return result

        # Attempt 2: Search fallback
        if self._settings.get("enable_search_fallback", True):
            attempts_made.append("resolution")
            result = self._try_search_fallback(query)
            if result:
                result.attempts_made = attempts_made + ["search"]
                if is_deep_logging():
                    deep_log(
                        f"[DEEP][FALLBACK_CHAIN] Search fallback succeeded for query={query!r}"
                    )
                return result

        # Attempt 3: Homepage fallback
        if self._settings.get("enable_homepage_fallback", True):
            attempts_made.append("resolution")
            if "search" not in attempts_made and self._settings.get(
                "enable_search_fallback", True
            ):
                attempts_made.append("search")

            result = self._try_homepage_fallback(query)
            if result:
                result.attempts_made = attempts_made + ["homepage"]
                if is_deep_logging():
                    deep_log(
                        f"[DEEP][FALLBACK_CHAIN] Homepage fallback succeeded for query={query!r}"
                    )
                return result

        # All attempts failed
        elapsed_ms = int((time.monotonic() - start) * 1000)
        tprint(f"[FALLBACK_CHAIN] All fallback attempts failed for query={query!r}")

        return FallbackResult(
            status="all_failed",
            final_url=None,
            fallback_used="none",
            attempts_made=attempts_made,
            resolution_details=None,
            elapsed_ms=elapsed_ms,
            error_message="All fallback attempts exhausted",
        )

    def _try_direct_resolution(self, query: str) -> FallbackResult | None:
        """Attempt 1: URLResolver direct resolution.

        Args:
            query: Search query or partial URL

        Returns:
            FallbackResult if successful, None if failed
        """
        try:
            start = time.monotonic()
            resolution = self._resolver.resolve(query)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            if resolution.status == "ok" and resolution.resolved_url:
                return FallbackResult(
                    status="ok",
                    final_url=resolution.resolved_url,
                    fallback_used="resolution",
                    attempts_made=["resolution"],
                    resolution_details=resolution,
                    elapsed_ms=elapsed_ms,
                )

            if is_deep_logging():
                cache_msg = " (cached)" if resolution.from_cache else ""
                deep_log(
                    f"[DEEP][FALLBACK_CHAIN] Direct resolution failed{cache_msg}: {resolution.error_message}"
                )

        except Exception as exc:
            if is_deep_logging():
                deep_log(f"[DEEP][FALLBACK_CHAIN] Direct resolution exception: {exc}")

        return None

    def _try_search_fallback(self, query: str) -> FallbackResult | None:
        """Attempt 2: Navigate to search engine with query.

        Args:
            query: Search query

        Returns:
            FallbackResult if successful, None if failed
        """
        try:
            start = time.monotonic()
            search_engine_url = self._settings.get(
                "search_engine_url", "https://duckduckgo.com/?q={query}"
            )

            # URL-encode query to prevent injection
            encoded_query = quote_plus(query)
            final_url = search_engine_url.replace("{query}", encoded_query)

            elapsed_ms = int((time.monotonic() - start) * 1000)

            tprint(f"[FALLBACK_CHAIN] Using search fallback: {final_url}")

            return FallbackResult(
                status="ok",
                final_url=final_url,
                fallback_used="search",
                attempts_made=["resolution", "search"],
                resolution_details=None,
                elapsed_ms=elapsed_ms,
            )

        except Exception as exc:
            if is_deep_logging():
                deep_log(f"[DEEP][FALLBACK_CHAIN] Search fallback exception: {exc}")

        return None

    def _try_homepage_fallback(self, query: str) -> FallbackResult | None:
        """Attempt 3: Extract domain from query and navigate to homepage.

        Args:
            query: Search query (e.g., "youtube", "gmail")

        Returns:
            FallbackResult if successful, None if failed
        """
        try:
            start = time.monotonic()

            # Extract potential domain from query
            domain = self._extract_domain(query)

            if not domain:
                return None

            # Construct homepage URL
            final_url = f"https://{domain}"

            elapsed_ms = int((time.monotonic() - start) * 1000)

            tprint(f"[FALLBACK_CHAIN] Using homepage fallback: {final_url}")

            return FallbackResult(
                status="ok",
                final_url=final_url,
                fallback_used="homepage",
                attempts_made=["resolution", "search", "homepage"],
                resolution_details=None,
                elapsed_ms=elapsed_ms,
            )

        except Exception as exc:
            if is_deep_logging():
                deep_log(f"[DEEP][FALLBACK_CHAIN] Homepage fallback exception: {exc}")

        return None

    def _extract_domain(self, query: str) -> str | None:
        """Extract domain from query string.

        Args:
            query: Search query

        Returns:
            Domain string or None if can't extract
        """
        query_lower = query.lower().strip()

        # Extract first word as potential domain
        first_word = query_lower.split()[0] if " " in query_lower else query_lower

        # Check common domain mapping
        if first_word in COMMON_DOMAINS:
            return COMMON_DOMAINS[first_word]

        # Try to construct domain from keyword
        # Remove common TLDs if already present
        domain = re.sub(r"\.(com|net|org|io|co)$", "", first_word)

        # Check if it looks like a domain (has letters, reasonable length)
        if re.match(r"^[a-z0-9-]+$", domain) and len(domain) >= 3:
            return f"{domain}.com"

        return None
