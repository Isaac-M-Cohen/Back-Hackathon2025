"""Headless Playwright-based URL resolver with DOM search."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
import threading
from urllib.parse import urljoin, urlparse
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

LOGIN_TERMS = (
    "sign in",
    "signin",
    "log in",
    "login",
    "log-in",
    "account",
    "my account",
)

LOGIN_ACTION_TERMS = (
    "sign in",
    "signin",
    "log in",
    "login",
    "log-in",
    "sign up",
    "signup",
    "register",
    "join",
    "account",
    "profile",
    "user",
)

LOGIN_HREF_HINTS = (
    "signin",
    "login",
    "log-in",
    "sign-in",
    "account",
    "ap/signin",
)

LOGIN_CLICK_SELECTORS = (
    "button:has-text('Sign in')",
    "button:has-text('Log in')",
    "button:has-text('Login')",
    "a:has-text('Sign in')",
    "a:has-text('Log in')",
    "a:has-text('Login')",
    "[role=button]:has-text('Sign in')",
    "[role=button]:has-text('Log in')",
    "[role=button]:has-text('Login')",
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
    from_cache: bool = False  # Indicates if result came from cache


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
        self._page_lock = Lock()  # Protect page access for thread safety
        self._initialized = False
        self._playwright_thread_id: int | None = None
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

        # Check cache (outside lock for performance)
        cached = self._cache.get(query)
        if cached:
            if is_deep_logging():
                deep_log(f"[DEEP][URL_RESOLVER] Cache hit for query={query!r}")
            # Mark as cached result for transparency
            cached.from_cache = True
            return cached

        # Acquire lock for all browser operations to prevent race conditions
        with self._page_lock:
            try:
                self._ensure_browser()

                # Infer initial URL to navigate to
                initial_url = self._infer_initial_url(query)
                login_probe_url = initial_url
                if self._is_login_query(query):
                    login_probe_url = self._login_base_url(initial_url)
                if is_deep_logging():
                    deep_log(
                        f"[DEEP][URL_RESOLVER] Resolving query={query!r} initial_url={initial_url}"
                    )

                # Reuse single page across resolutions
                timeout_ms = self._settings.get("playwright_navigation_timeout_ms", 30000)

                # Navigate to initial URL
                self._page.goto(
                    login_probe_url, wait_until="domcontentloaded", timeout=timeout_ms
                )
                self._page.wait_for_load_state("networkidle", timeout=timeout_ms)

                if self._is_login_query(query):
                    self._page.wait_for_timeout(1500)
                    if is_deep_logging():
                        deep_log("[DEEP][URL_RESOLVER] Login query: waited for dynamic content")

                # Search DOM for relevant links
                candidates: list[LinkCandidate] = []
                best_candidate: LinkCandidate | None = None
                if self._is_login_query(query):
                    candidates = self._search_login_links(self._page)
                    best_candidate = self._rank_login_candidates(candidates)
                    if best_candidate is None:
                        deep_log(
                            f"[DEEP][URL_RESOLVER] Login link search empty; trying network fallback for base_url={login_probe_url!r}"
                        )
                        network_url = self._resolve_login_via_network(
                            self._page, login_probe_url
                        )
                        if network_url:
                            best_candidate = LinkCandidate(
                                url=network_url,
                                link_text="login_network",
                                position_score=1.0,
                                aria_label=None,
                            )
                if best_candidate is None:
                    candidates = self._search_dom_for_links(self._page, query)
                    best_candidate = self._rank_candidates(candidates, query)

                if is_deep_logging():
                    deep_log(
                        f"[DEEP][URL_RESOLVER] Found {len(candidates)} candidates for query={query!r}"
                    )

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
            current_thread_id = threading.get_ident()
            if self._playwright_thread_id != current_thread_id:
                tprint(
                    "[URL_RESOLVER] Playwright initialized on different thread; restarting browser context."
                )
                self.shutdown()
            else:
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
            self._playwright_thread_id = threading.get_ident()
            tprint("[URL_RESOLVER] Headless Playwright context initialized")
        except PlaywrightError as exc:
            # Cleanup on failure
            if self._playwright:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
            self._playwright = None
            self._playwright_thread_id = None
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
            self._playwright_thread_id = None
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

                    # Make URL absolute using Python's urljoin (avoids XSS via page.evaluate)
                    try:
                        current_url = page.url
                        resolved_href = urljoin(current_url, href)
                    except Exception:
                        # Skip links that can't be resolved
                        continue

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

    def _search_login_links(self, page: Page) -> list[LinkCandidate]:
        """Find candidate login links based on common login text/hints."""
        candidates: list[LinkCandidate] = []
        try:
            links = page.locator("a[href]").all()
            max_links = min(len(links), 150)
            if is_deep_logging():
                deep_log(
                    f"[DEEP][URL_RESOLVER] Login search scanning {max_links} links"
                )

            for i in range(max_links):
                link = links[i]
                try:
                    href = link.get_attribute("href")
                    if not href or href.startswith("#") or href == "javascript:void(0)":
                        continue
                    link_text = link.inner_text().strip()
                    aria_label = link.get_attribute("aria-label")
                    search_text = (link_text + " " + (aria_label or "")).lower()
                    href_lower = href.lower()

                    if not any(term in search_text for term in LOGIN_TERMS) and not any(
                        hint in href_lower for hint in LOGIN_HREF_HINTS
                    ):
                        continue

                    position_score = max(0.1, 1.0 - (i / max(max_links, 1)))
                    try:
                        current_url = page.url
                        resolved_href = urljoin(current_url, href)
                    except Exception:
                        continue

                    candidates.append(
                        LinkCandidate(
                            url=resolved_href,
                            link_text=link_text,
                            position_score=position_score,
                            aria_label=aria_label,
                        )
                    )

                    if len(candidates) >= 20:
                        break
                except Exception:
                    continue
        except Exception as exc:
            if is_deep_logging():
                deep_log(f"[DEEP][URL_RESOLVER] Login link search error: {exc}")
        return candidates

    def _rank_login_candidates(
        self, candidates: list[LinkCandidate]
    ) -> LinkCandidate | None:
        if not candidates:
            return None

        scored_candidates: list[tuple[float, LinkCandidate]] = []
        for candidate in candidates:
            score = candidate.position_score
            link_text = candidate.link_text.lower()
            aria_text = (candidate.aria_label or "").lower()
            url_lower = candidate.url.lower()

            if "sign in" in link_text or "sign in" in aria_text:
                score += 4.0
            if "log in" in link_text or "log in" in aria_text:
                score += 3.0
            if "signin" in url_lower or "login" in url_lower:
                score += 3.0
            if "account" in link_text or "account" in aria_text:
                score += 1.5
            if "ap/signin" in url_lower:
                score += 2.0

            scored_candidates.append((score, candidate))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        return scored_candidates[0][1]

    def _is_login_query(self, query: str) -> bool:
        query_lower = query.lower()
        return any(term in query_lower for term in ("login", "log in", "sign in", "signin"))

    def _login_base_url(self, initial_url: str) -> str:
        try:
            parsed = urlparse(initial_url)
            path_lower = parsed.path.lower()
            if any(term in path_lower for term in LOGIN_HREF_HINTS) or "login" in path_lower:
                return f"{parsed.scheme}://{parsed.netloc}/"
        except Exception:
            return initial_url
        return initial_url

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

    def _resolve_login_via_network(self, page: Page, base_url: str) -> str | None:
        """Fallback: trigger login UI and infer URL from network traffic."""
        if not self._wait_for_login_nav(page):
            deep_log(
                "[DEEP][URL_RESOLVER] Login nav not ready; skipping network fallback"
            )
            return None
        click_target = self._find_login_click_target(page)
        hover_target = None
        use_screen_hover = False
        if click_target is None:
            hover_target = self._find_login_hover_target(page)
            if hover_target is None:
                use_screen_hover = True
                deep_log(
                    "[DEEP][URL_RESOLVER] No login click/hover target found; using screen hover fallback"
                )

        captured: list[dict[str, str]] = []
        pre_click_url = page.url
        base_host = urlparse(base_url).netloc.lower()
        deep_log(f"[DEEP][URL_RESOLVER] Network fallback capture on {pre_click_url!r}")

        def record_url(url: str, resource_type: str, status: str) -> None:
            if not url.startswith("http"):
                return
            captured.append(
                {"url": url, "resource_type": resource_type, "status": status}
            )

        def on_request(request) -> None:
            try:
                if request.method != "GET":
                    return
                resource_type = request.resource_type
                if resource_type in ("image", "stylesheet", "font", "script", "media"):
                    return
                record_url(request.url, resource_type, "pending")
            except Exception:
                return

        def on_response(response) -> None:
            try:
                req = response.request
                if req.method != "GET":
                    return
                resource_type = req.resource_type
                if resource_type in ("image", "stylesheet", "font", "script", "media"):
                    return
                status = response.status
                if status < 200 or status >= 400:
                    return
                record_url(response.url, resource_type, str(status))
            except Exception:
                return

        page.on("request", on_request)
        page.on("response", on_response)
        try:
            hovered = False
            if click_target is not None:
                try:
                    click_target.click(timeout=2000)
                except Exception:
                    deep_log(
                        "[DEEP][URL_RESOLVER] Login click failed during network fallback"
                    )
                    return None
            elif hover_target is not None:
                try:
                    hover_target.hover(timeout=2000)
                    hovered = True
                except Exception:
                    deep_log(
                        "[DEEP][URL_RESOLVER] Login hover failed during network fallback"
                    )
                    return None
            elif use_screen_hover:
                try:
                    viewport = page.viewport_size or {"width": 1280, "height": 720}
                    x = int(viewport["width"] * 0.88)
                    y = int(viewport["height"] * 0.12)
                    deep_log(
                        f"[DEEP][URL_RESOLVER] Screen hover fallback at x={x} y={y}"
                    )
                    page.mouse.move(x, y)
                    hovered = True
                except Exception:
                    deep_log(
                        "[DEEP][URL_RESOLVER] Screen hover failed during network fallback"
                    )
                    return None

            if click_target is None and hovered:
                page.wait_for_timeout(500)
                post_hover_click = self._find_login_click_target(page)
                if post_hover_click is not None:
                    try:
                        deep_log(
                            "[DEEP][URL_RESOLVER] Login click target found after hover"
                        )
                        post_hover_click.click(timeout=2000)
                    except Exception:
                        deep_log(
                            "[DEEP][URL_RESOLVER] Login click after hover failed during network fallback"
                        )

            page.wait_for_timeout(2000)
            new_url = page.url
            if new_url != pre_click_url and self._url_has_login_terms(new_url):
                deep_log(f"[DEEP][URL_RESOLVER] Login trigger changed URL to {new_url!r}")
                return new_url
            deep_log(
                f"[DEEP][URL_RESOLVER] Network fallback captured {len(captured)} requests/responses"
            )
            resolved = self._pick_login_url_from_network(captured, base_host)
            if resolved:
                deep_log(
                    f"[DEEP][URL_RESOLVER] Network fallback resolved URL {resolved!r}"
                )
            else:
                deep_log("[DEEP][URL_RESOLVER] Network fallback found no login URL")
            return resolved
        finally:
            try:
                page.off("request", on_request)
            except Exception:
                pass
            try:
                page.off("response", on_response)
            except Exception:
                pass

    def _wait_for_login_nav(self, page: Page) -> bool:
        url_lower = (page.url or "").lower()
        if "/_____tmd_____/punish" in url_lower or "x5secdata" in url_lower:
            deep_log(
                "[DEEP][URL_RESOLVER] Login nav wait aborted: bot-check page detected"
            )
            return False

        nav_selectors = [
            "header",
            "nav",
            "[data-role*='nav' i]",
            "[data-spm*='nav' i]",
            "[data-spm-anchor-id*='nav' i]",
            "[data-testid*='header' i]",
            "[class*='header' i]",
            "[id*='header' i]",
            "[class*='nav' i]",
            "[id*='nav' i]",
        ]
        for selector in nav_selectors:
            try:
                page.wait_for_selector(selector, state="visible", timeout=3000)
                deep_log(
                    f"[DEEP][URL_RESOLVER] Login nav detected via selector {selector!r}"
                )
                return True
            except Exception:
                continue

        try:
            text_locator = page.locator(
                "text=/sign\\s*in|log\\s*in|login|sign\\s*up|register|join|account/i"
            )
            if text_locator.count() > 0:
                deep_log("[DEEP][URL_RESOLVER] Login text detected without nav")
                return True
        except Exception:
            pass

        deep_log("[DEEP][URL_RESOLVER] Login nav not detected after wait")
        return False

    def _find_login_click_target(self, page: Page):
        frames = [page.main_frame] + [
            frame for frame in page.frames if frame != page.main_frame
        ]
        for frame in frames:
            frame_desc = f"frame={frame.url!r}"

            for selector in LOGIN_CLICK_SELECTORS:
                try:
                    locator = frame.locator(selector)
                    count = locator.count()
                    for i in range(min(count, 3)):
                        candidate = locator.nth(i)
                        if not candidate.is_visible():
                            continue
                        href = candidate.get_attribute("href")
                        if href and href.strip() not in ("#", "javascript:void(0)"):
                            continue
                        if is_deep_logging():
                            deep_log(
                                f"[DEEP][URL_RESOLVER] Login click target found via selector {selector!r} ({frame_desc})"
                            )
                        return candidate
                except Exception:
                    continue

            text_locator = frame.locator(
                "text=/sign\\s*in|log\\s*in|login|sign\\s*up|register|join|account/i"
            )
            try:
                text_count = text_locator.count()
            except Exception:
                text_count = 0
            for i in range(min(text_count, 10)):
                try:
                    candidate = text_locator.nth(i)
                    if not candidate.is_visible():
                        continue
                    clickable = candidate.locator(
                        "xpath=ancestor-or-self::a|ancestor-or-self::button|ancestor-or-self::*[@role='button']"
                    ).first
                    if clickable.count() == 0:
                        continue
                    if is_deep_logging():
                        deep_log(
                            f"[DEEP][URL_RESOLVER] Login click target found via text fallback ({frame_desc})"
                        )
                    return clickable
                except Exception:
                    continue

            attr_locator = frame.locator(
                "[data-testid*='login' i], [data-testid*='signin' i], "
                "[data-testid*='account' i], [data-testid*='profile' i], "
                "[data-qa*='login' i], [data-qa*='signin' i], "
                "[data-qa*='account' i], [data-qa*='profile' i], "
                "[id*='login' i], [id*='signin' i], [id*='account' i], [id*='profile' i], "
                "[class*='login' i], [class*='signin' i], [class*='account' i], [class*='profile' i]"
            )
            try:
                attr_count = attr_locator.count()
            except Exception:
                attr_count = 0
            for i in range(min(attr_count, 10)):
                try:
                    candidate = attr_locator.nth(i)
                    if not candidate.is_visible():
                        continue
                    clickable = candidate.locator(
                        "xpath=ancestor-or-self::a|ancestor-or-self::button|ancestor-or-self::*[@role='button']"
                    ).first
                    if clickable.count() == 0:
                        continue
                    if is_deep_logging():
                        deep_log(
                            f"[DEEP][URL_RESOLVER] Login click target found via attribute fallback ({frame_desc})"
                        )
                    return clickable
                except Exception:
                    continue

            generic_locator = frame.locator("a, button, [role=button]")
            try:
                generic_count = generic_locator.count()
            except Exception:
                generic_count = 0
            for i in range(min(generic_count, 200)):
                try:
                    candidate = generic_locator.nth(i)
                    if not candidate.is_visible():
                        continue
                    text = candidate.inner_text().strip().lower()
                    aria_label = (candidate.get_attribute("aria-label") or "").lower()
                    title = (candidate.get_attribute("title") or "").lower()
                    data_role = (candidate.get_attribute("data-role") or "").lower()
                    data_testid = (candidate.get_attribute("data-testid") or "").lower()
                    data_qa = (candidate.get_attribute("data-qa") or "").lower()
                    data_spm = (candidate.get_attribute("data-spm") or "").lower()
                    data_spm_anchor = (
                        candidate.get_attribute("data-spm-anchor-id") or ""
                    ).lower()
                    elem_id = (candidate.get_attribute("id") or "").lower()
                    class_name = (candidate.get_attribute("class") or "").lower()
                    combined = " ".join(
                        [
                            text,
                            aria_label,
                            title,
                            data_role,
                            data_testid,
                            data_qa,
                            data_spm,
                            data_spm_anchor,
                            elem_id,
                            class_name,
                        ]
                    ).strip()
                    if not combined:
                        continue
                    if not any(term in combined for term in LOGIN_ACTION_TERMS):
                        continue
                    if is_deep_logging():
                        deep_log(
                            f"[DEEP][URL_RESOLVER] Login click target found via generic scan ({frame_desc})"
                        )
                    return candidate
                except Exception:
                    continue
        return None

    def _url_has_login_terms(self, url: str) -> bool:
        url_lower = url.lower()
        return any(term in url_lower for term in LOGIN_HREF_HINTS) or any(
            term in url_lower for term in LOGIN_TERMS
        )

    def _pick_login_url_from_network(
        self, captured: list[dict[str, str]], base_host: str
    ) -> str | None:
        if not captured:
            return None

        scored: list[tuple[float, str]] = []
        for entry in captured:
            url = entry.get("url", "")
            if not url.startswith("http"):
                continue
            if url.endswith((".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".gif")):
                continue
            if not self._url_has_login_terms(url):
                continue
            try:
                host = urlparse(url).netloc.lower()
            except Exception:
                host = ""
            score = 0.0
            if "login" in host or "auth" in host or "signin" in host:
                score += 3.0
            if "login" in url or "signin" in url or "sign-in" in url:
                score += 2.0
            if host and host != base_host:
                score += 1.0
            scored.append((score, url))

        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]

    def _find_login_hover_target(self, page: Page):
        frames = [page.main_frame] + [
            frame for frame in page.frames if frame != page.main_frame
        ]
        for frame in frames:
            frame_desc = f"frame={frame.url!r}"
            locator = frame.locator(
                "text=/sign\\s*in|log\\s*in|login|sign\\s*up|register|join|account/i"
            )
            try:
                count = locator.count()
            except Exception:
                count = 0
            for i in range(min(count, 10)):
                try:
                    candidate = locator.nth(i)
                    if not candidate.is_visible():
                        continue
                    hoverable = candidate.locator(
                        "xpath=ancestor-or-self::a|ancestor-or-self::button|ancestor-or-self::*[@role='button']"
                    ).first
                    if hoverable.count() > 0:
                        candidate = hoverable
                    if is_deep_logging():
                        deep_log(
                            f"[DEEP][URL_RESOLVER] Login hover target found via text ({frame_desc})"
                        )
                    return candidate
                except Exception:
                    continue

            generic_locator = frame.locator("a, button, [role=button]")
            try:
                generic_count = generic_locator.count()
            except Exception:
                generic_count = 0
            for i in range(min(generic_count, 200)):
                try:
                    candidate = generic_locator.nth(i)
                    if not candidate.is_visible():
                        continue
                    text = candidate.inner_text().strip().lower()
                    aria_label = (candidate.get_attribute("aria-label") or "").lower()
                    title = (candidate.get_attribute("title") or "").lower()
                    data_role = (candidate.get_attribute("data-role") or "").lower()
                    data_testid = (candidate.get_attribute("data-testid") or "").lower()
                    data_qa = (candidate.get_attribute("data-qa") or "").lower()
                    data_spm = (candidate.get_attribute("data-spm") or "").lower()
                    data_spm_anchor = (
                        candidate.get_attribute("data-spm-anchor-id") or ""
                    ).lower()
                    elem_id = (candidate.get_attribute("id") or "").lower()
                    class_name = (candidate.get_attribute("class") or "").lower()
                    combined = " ".join(
                        [
                            text,
                            aria_label,
                            title,
                            data_role,
                            data_testid,
                            data_qa,
                            data_spm,
                            data_spm_anchor,
                            elem_id,
                            class_name,
                        ]
                    ).strip()
                    if not combined:
                        continue
                    if not any(term in combined for term in LOGIN_ACTION_TERMS):
                        continue
                    if is_deep_logging():
                        deep_log(
                            f"[DEEP][URL_RESOLVER] Login hover target found via generic scan ({frame_desc})"
                        )
                    return candidate
                except Exception:
                    continue
        return None

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
        self._playwright_thread_id = None
