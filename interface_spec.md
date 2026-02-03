# Executor Rework: Interface Specifications

This document provides detailed Python interface specifications for all new modules and modified components. All interfaces use type hints and follow Python Protocol/ABC patterns for clarity.

---

## 1. URLResolver Interface

**File:** `command_controller/url_resolver.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import time

from playwright.sync_api import sync_playwright, Page, Browser, Playwright
from utils.log_utils import tprint
from utils.settings_store import get_settings, deep_log, is_deep_logging


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
        self._initialized = False
        self._cache = URLResolutionCache(ttl_secs=900)  # 15 minutes

    def resolve(self, query: str) -> URLResolutionResult:
        """Resolve a search query or partial URL to a final URL.

        Args:
            query: Search query or partial URL (e.g., "youtube cats", "gmail inbox")

        Returns:
            URLResolutionResult with status, resolved_url, and metadata

        Flow:
            1. Check cache for recent resolution
            2. Ensure headless browser is initialized
            3. Navigate to initial URL (infer from query or use search engine)
            4. Search DOM for relevant links
            5. Rank candidates and select best match
            6. Cache result and return
        """
        pass

    def _ensure_browser(self) -> None:
        """Initialize headless Playwright context on first call.

        - Uses separate profile directory (playwright_resolver_profile)
        - Always runs in headless mode (ignores global playwright_headless)
        - Timeout set by playwright_navigation_timeout_ms config
        """
        pass

    def _search_dom_for_links(self, page: Page, query: str) -> list[LinkCandidate]:
        """Extract candidate URLs from DOM based on text matching.

        Args:
            page: Playwright Page object
            query: Search query for filtering links

        Returns:
            List of LinkCandidate objects with scoring

        Heuristics:
            1. Find all <a> tags with href attribute
            2. Filter by visible text containing query terms (case-insensitive)
            3. Calculate position_score (header links score higher)
            4. Extract ARIA labels for accessibility context
            5. Return all matching candidates (ranking happens later)
        """
        pass

    def _rank_candidates(
        self, candidates: list[LinkCandidate], query: str
    ) -> LinkCandidate | None:
        """Rank candidates and return best match.

        Args:
            candidates: List of LinkCandidate objects
            query: Original search query

        Returns:
            Best matching candidate or None if no good matches

        Ranking Criteria (in order):
            1. Exact text match (case-insensitive)
            2. Position score (header > body > footer)
            3. ARIA label relevance
            4. Link text similarity (Levenshtein distance or fuzzy match)
        """
        pass

    def _infer_initial_url(self, query: str) -> str:
        """Infer starting URL from query.

        Args:
            query: User's search query or partial URL

        Returns:
            Full URL to navigate to

        Examples:
            "youtube cats" → "https://youtube.com"
            "gmail inbox" → "https://mail.google.com"
            "cats" → "https://duckduckgo.com/?q=cats"
        """
        pass

    def shutdown(self) -> None:
        """Close headless browser and Playwright instance."""
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
        self._browser = None
        self._playwright = None
```

---

## 2. FallbackChain Interface

**File:** `command_controller/fallback_chain.py`

```python
from __future__ import annotations

from dataclasses import dataclass
import time
from urllib.parse import quote_plus, urlparse

from command_controller.url_resolver import URLResolver, URLResolutionResult
from utils.log_utils import tprint
from utils.settings_store import get_settings, deep_log


@dataclass
class FallbackResult:
    """Result of fallback chain execution."""
    status: str  # "ok" | "all_failed"
    final_url: str | None
    fallback_used: str  # "resolution" | "search" | "homepage" | "none"
    attempts_made: list[str]  # ["resolution", "search"]
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

        Flow:
            1. Attempt direct resolution (if use_playwright_for_web=true)
            2. If failed, attempt search fallback (if enable_search_fallback=true)
            3. If failed, attempt homepage fallback (if enable_homepage_fallback=true)
            4. If all failed, return status="all_failed"

        Each attempt is logged at DEEP level with timing information.
        """
        start = time.monotonic()
        attempts_made: list[str] = []

        # Attempt 1: Direct resolution
        result = self._try_direct_resolution(query)
        if result:
            return result

        # Attempt 2: Search fallback
        if self._settings.get("enable_search_fallback", True):
            attempts_made.append("search")
            result = self._try_search_fallback(query)
            if result:
                return result

        # Attempt 3: Homepage fallback
        if self._settings.get("enable_homepage_fallback", True):
            attempts_made.append("homepage")
            result = self._try_homepage_fallback(query)
            if result:
                return result

        # All attempts failed
        elapsed_ms = int((time.monotonic() - start) * 1000)
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

        Success Condition: URLResolutionResult.status == "ok"
        """
        pass

    def _try_search_fallback(self, query: str) -> FallbackResult | None:
        """Attempt 2: Navigate to search engine with query.

        Args:
            query: Search query

        Returns:
            FallbackResult if successful, None if failed

        Implementation:
            1. Get search_engine_url template from config
            2. URL-encode query to prevent injection
            3. Replace {query} placeholder
            4. Return FallbackResult with fallback_used="search"
        """
        pass

    def _try_homepage_fallback(self, query: str) -> FallbackResult | None:
        """Attempt 3: Extract domain from query and navigate to homepage.

        Args:
            query: Search query (e.g., "youtube", "gmail")

        Returns:
            FallbackResult if successful, None if failed

        Implementation:
            1. Extract domain keywords (e.g., "youtube" → "youtube.com")
            2. Construct homepage URL (https://{domain})
            3. Return FallbackResult with fallback_used="homepage"

        Examples:
            "youtube" → "https://youtube.com"
            "gmail" → "https://gmail.com"
            "github python" → "https://github.com"
        """
        pass
```

---

## 3. SubjectExtractor Interface

**File:** `command_controller/subject_extractor.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from command_controller.llm import LocalLLMInterpreter

from utils.log_utils import tprint


@dataclass
class SubjectGroup:
    """A group of steps associated with a single subject."""
    subject_name: str  # "YouTube", "Gmail", "Spotify"
    subject_type: str  # "url" | "app" | "file" | "unknown"
    steps: list[dict]  # Steps associated with this subject
    start_index: int   # Original step index (preserves execution order)


class SubjectExtractor:
    """Extract distinct subjects and group associated steps."""

    def __init__(self, llm_interpreter: LocalLLMInterpreter | None = None) -> None:
        """Initialize subject extractor.

        Args:
            llm_interpreter: Optional LLM for semantic subject identification.
                           If None, uses keyword-based heuristics.
        """
        self._llm = llm_interpreter

    def extract(self, text: str, steps: list[dict]) -> list[SubjectGroup]:
        """Group steps by subject.

        Args:
            text: Original command text (e.g., "open Gmail and Spotify")
            steps: Validated step list from engine

        Returns:
            List of SubjectGroup objects, preserving execution order

        Flow:
            1. Identify distinct subjects from text and steps
            2. Assign each step to a subject
            3. Create SubjectGroup for each subject
            4. If no clear subjects, return single group with all steps

        Examples:
            Input: "open YouTube and search for cats"
            Steps: [open_url(youtube), type_text(cats)]
            Output: [SubjectGroup("YouTube", "url", [both steps])]

            Input: "open Gmail and Spotify"
            Steps: [open_app(Gmail), open_app(Spotify)]
            Output: [
                SubjectGroup("Gmail", "app", [step1]),
                SubjectGroup("Spotify", "app", [step2])
            ]
        """
        pass

    def _identify_subjects(self, text: str, steps: list[dict]) -> list[str]:
        """Identify distinct entities in command text.

        Args:
            text: Command text
            steps: Step list

        Returns:
            List of subject names (e.g., ["Gmail", "Spotify"])

        Heuristics:
            1. Extract app names from open_app intents
            2. Extract URLs/domains from open_url intents
            3. Look for conjunctions ("and", "then") in text
            4. Use LLM for ambiguous cases (if available)

        Fallback: Return empty list (all steps → single group)
        """
        pass

    def _assign_steps_to_subjects(
        self, subjects: list[str], steps: list[dict]
    ) -> list[SubjectGroup]:
        """Associate steps with their target subjects.

        Args:
            subjects: List of identified subjects
            steps: Step list

        Returns:
            List of SubjectGroup objects

        Algorithm:
            1. If no subjects, return single group with all steps
            2. For each subject, find steps that reference it
            3. Create SubjectGroup with matched steps
            4. Preserve original step order via start_index
        """
        pass

    def _infer_subject_type(self, subject: str, step: dict) -> str:
        """Infer subject type from step intent.

        Args:
            subject: Subject name
            step: First step associated with subject

        Returns:
            "url" | "app" | "file" | "unknown"

        Rules:
            open_url → "url"
            open_app → "app"
            open_file → "file"
            Other → "unknown"
        """
        pass
```

---

## 4. URLResolutionCache Interface

**File:** `command_controller/url_resolution_cache.py`

```python
from __future__ import annotations

from dataclasses import dataclass
import time

from command_controller.url_resolver import URLResolutionResult


@dataclass
class CacheEntry:
    """Cache entry with timestamp for TTL expiration."""
    result: URLResolutionResult
    timestamp: float  # time.time()


class URLResolutionCache:
    """In-memory cache with TTL for URL resolutions."""

    def __init__(self, ttl_secs: int = 900) -> None:
        """Initialize cache with TTL.

        Args:
            ttl_secs: Time-to-live in seconds (default: 15 minutes)
        """
        self._cache: dict[str, CacheEntry] = {}
        self._ttl = ttl_secs

    def get(self, query: str) -> URLResolutionResult | None:
        """Retrieve cached result if not expired.

        Args:
            query: Search query (cache key)

        Returns:
            URLResolutionResult if found and not expired, None otherwise

        Lazy Expiration: Checks timestamp on get(), doesn't clean up proactively.
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

        return entry.result

    def put(self, query: str, result: URLResolutionResult) -> None:
        """Store result with timestamp.

        Args:
            query: Search query (cache key)
            result: URLResolutionResult to cache
        """
        self._cache[query] = CacheEntry(result=result, timestamp=time.time())

    def clear(self) -> None:
        """Invalidate all cached entries."""
        self._cache.clear()

    def size(self) -> int:
        """Return number of cached entries (includes expired entries)."""
        return len(self._cache)
```

---

## 5. Enhanced ExecutionResult

**File:** `command_controller/executors/base.py` (modified)

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ExecutionResult:
    """Enhanced execution result with optional web metadata."""
    intent: str
    status: str  # "ok" | "failed" | "unsupported" | "timeout"
    target: str = "os"
    details: dict[str, Any] | None = None
    elapsed_ms: int | None = None

    # NEW: Optional web navigation metadata (Milestone 2)
    resolved_url: str | None = None
    """Final URL after resolution/fallback."""

    fallback_used: str | None = None
    """Which fallback was triggered: "resolution" | "search" | "homepage" | "none"."""

    navigation_time_ms: int | None = None
    """Time spent in URL resolution (separate from elapsed_ms)."""

    dom_search_query: str | None = None
    """Original query used for DOM search."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict, including new fields only when present.

        Backward Compatibility: Existing consumers ignore new fields.
        """
        payload: dict[str, Any] = {
            "intent": self.intent,
            "status": self.status,
            "target": self.target,
        }
        if self.details is not None:
            payload["details"] = self.details
        if self.elapsed_ms is not None:
            payload["elapsed_ms"] = self.elapsed_ms

        # NEW: Include new fields only if set
        if self.resolved_url is not None:
            payload["resolved_url"] = self.resolved_url
        if self.fallback_used is not None:
            payload["fallback_used"] = self.fallback_used
        if self.navigation_time_ms is not None:
            payload["navigation_time_ms"] = self.navigation_time_ms
        if self.dom_search_query is not None:
            payload["dom_search_query"] = self.dom_search_query

        return payload
```

---

## 6. WebExecutor Modifications

**File:** `command_controller/web_executor.py` (modified)

```python
# New imports
from command_controller.fallback_chain import FallbackChain, FallbackResult
from command_controller.url_resolver import URLResolver
import subprocess

class WebExecutor:
    """Enhanced WebExecutor with URL resolution and fallback."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._page = None
        self._initialized = False

        # NEW: Lazy initialization
        self._url_resolver: URLResolver | None = None
        self._fallback_chain: FallbackChain | None = None
        self._last_resolution: FallbackResult | None = None

    def _get_url_resolver(self) -> URLResolver:
        """Lazy initialize URL resolver with separate headless context."""
        if self._url_resolver is None:
            self._url_resolver = URLResolver()
        return self._url_resolver

    def _get_fallback_chain(self) -> FallbackChain:
        """Lazy initialize fallback chain."""
        if self._fallback_chain is None:
            resolver = self._get_url_resolver()
            self._fallback_chain = FallbackChain(resolver)
        return self._fallback_chain

    def _handle_open_url(self, step: dict) -> None:
        """Enhanced open_url handler with resolution and fallback.

        Flow:
            1. Check use_playwright_for_web config
            2. If enabled, use FallbackChain to resolve URL
            3. If request_before_open_url=true, show confirmation (future)
            4. Open resolved URL in default browser (macOS 'open' command)
            5. Store resolution metadata in self._last_resolution

        Backward Compatibility:
            If use_playwright_for_web=false, use legacy direct navigation.
        """
        url = step.get("url", "")
        settings = get_settings()

        # Legacy path
        if not settings.get("use_playwright_for_web", True):
            self._page.goto(url, wait_until="domcontentloaded")
            self._page.wait_for_load_state("networkidle")
            tprint(f"[WEB_EXEC] Navigated to {url}")
            return

        # Enhanced path: URL resolution + fallback
        fallback_chain = self._get_fallback_chain()
        result = fallback_chain.execute(url)

        if result.status == "all_failed":
            raise WebExecutionError(
                code="WEB_RESOLUTION_FAILED",
                message=f"Failed to resolve URL: {url}",
            )

        final_url = result.final_url

        # Security: validate URL scheme
        if not self._is_safe_url(final_url):
            raise WebExecutionError(
                code="WEB_UNSAFE_URL",
                message=f"Resolved URL has unsafe scheme: {final_url}",
            )

        # Confirmation check (stub for now)
        if settings.get("request_before_open_url", False):
            tprint(f"[WEB_EXEC] Opening URL in default browser: {final_url}")
            # Future: integrate with confirmation system

        # Open in default browser (macOS)
        subprocess.run(["open", final_url], check=False)
        tprint(f"[WEB_EXEC] Opened {final_url} in default browser")

        # Store metadata for ExecutionResult enrichment
        self._last_resolution = result

    def _handle_form_fill(self, step: dict) -> None:
        """Fill web forms using Playwright (gated by config).

        Args:
            step: {
                "intent": "web_fill_form",
                "form_fields": {"#email": "user@example.com", ...},
                "submit": true
            }

        Raises:
            WebExecutionError if allow_headless_form_fill=false
        """
        settings = get_settings()
        if not settings.get("allow_headless_form_fill", False):
            raise WebExecutionError(
                code="WEB_FORM_FILL_DISABLED",
                message="Form fill is disabled. Enable via allow_headless_form_fill config.",
            )

        form_fields = step.get("form_fields", {})
        submit = step.get("submit", False)

        for selector, value in form_fields.items():
            try:
                el = self._page.wait_for_selector(selector, timeout=10000)
                el.fill(str(value))
            except Exception as exc:
                raise WebExecutionError(
                    code="WEB_FORM_FIELD_NOT_FOUND",
                    message=f"Field '{selector}' not found: {exc}",
                )

        if submit:
            try:
                submit_btn = self._page.locator(
                    'button[type="submit"], input[type="submit"]'
                ).first
                submit_btn.click()
            except Exception as exc:
                raise WebExecutionError(
                    code="WEB_FORM_SUBMIT_FAILED",
                    message=f"Submit failed: {exc}",
                )

        tprint("[WEB_EXEC] Form filled successfully")

    def _handle_request_permission(self, step: dict) -> None:
        """Permission hook stub (Milestone 6).

        Args:
            step: {"intent": "web_request_permission", "permission_type": "location"}

        Future: Integrate with browser permission APIs or confirmation system.
        """
        permission_type = step.get("permission_type", "")
        tprint(f"[WEB_EXEC] Permission requested: {permission_type}")
        # Stub implementation
        pass

    @staticmethod
    def _is_safe_url(url: str | None) -> bool:
        """Validate URL scheme is http/https.

        Args:
            url: URL to validate

        Returns:
            True if safe, False otherwise
        """
        if not url:
            return False
        return url.startswith("http://") or url.startswith("https://")

    def shutdown(self) -> None:
        """Close browser, Playwright, and URL resolver."""
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

        # NEW: Cleanup URL resolver
        if self._url_resolver:
            try:
                self._url_resolver.shutdown()
            except Exception:
                pass

        self._initialized = False
        self._browser = None
        self._page = None
        self._playwright = None
        self._url_resolver = None
        self._fallback_chain = None
```

---

## 7. Executor Integration

**File:** `command_controller/executor.py` (modified)

```python
def _execute_web_step(self, step: dict) -> ExecutionResult:
    """Execute web step with enhanced result metadata.

    Changes:
        - Check for _last_resolution attribute on WebExecutor
        - Enrich ExecutionResult with resolution metadata if present
    """
    intent = str(step.get("intent", "")).strip() or "web"
    try:
        web_exec = self._get_web_executor()
        web_exec.execute_step(step)

        # NEW: Check for resolution metadata
        if hasattr(web_exec, "_last_resolution") and web_exec._last_resolution:
            res_data = web_exec._last_resolution
            return ExecutionResult(
                intent=intent,
                status="ok",
                target="web",
                resolved_url=res_data.final_url,
                fallback_used=res_data.fallback_used,
                navigation_time_ms=res_data.elapsed_ms,
                dom_search_query=(
                    res_data.resolution_details.search_query
                    if res_data.resolution_details
                    else None
                ),
            )

        return ExecutionResult(intent=intent, status="ok", target="web")
    except WebExecutionError as exc:
        return ExecutionResult(
            intent=intent,
            status="failed",
            target="web",
            details={
                "code": exc.code,
                "reason": str(exc),
                "screenshot_path": exc.screenshot_path,
            },
        )
```

---

## 8. Intent Validation Extensions

**File:** `command_controller/intents.py` (modified)

```python
# NEW: Add new intents to ALLOWED_INTENTS
ALLOWED_INTENTS = {
    "open_url",
    "wait_for_url",
    "open_app",
    "open_file",
    "key_combo",
    "type_text",
    "scroll",
    "mouse_move",
    "click",
    "web_send_message",
    "find_ui",
    "invoke_ui",
    "wait_for_window",

    # NEW (Milestone 8)
    "web_fill_form",
    "web_request_permission",
}


def validate_step(step: dict) -> dict:
    """Validate an intent step (extended for new intents)."""
    intent = str(step.get("intent", "")).strip()
    if intent not in ALLOWED_INTENTS:
        raise ValueError(f"Unsupported intent '{intent}'")

    cleaned: dict[str, Any] = {"intent": intent}
    target = step.get("target")
    if isinstance(target, str) and target:
        cleaned["target"] = target

    # ... existing validation for other intents ...

    # NEW: web_fill_form validation
    if intent == "web_fill_form":
        form_fields = step.get("form_fields")
        if not isinstance(form_fields, dict) or not form_fields:
            raise ValueError("web_fill_form requires non-empty 'form_fields' dict")

        # Validate selectors are strings
        cleaned_fields = {}
        for selector, value in form_fields.items():
            if not isinstance(selector, str) or not selector.strip():
                raise ValueError("web_fill_form field selectors must be non-empty strings")
            cleaned_fields[selector.strip()] = str(value)

        cleaned["form_fields"] = cleaned_fields
        cleaned["submit"] = bool(step.get("submit", False))
        cleaned["target"] = "web"
        return cleaned

    # NEW: web_request_permission validation
    if intent == "web_request_permission":
        permission_type = str(step.get("permission_type", "")).strip()
        if not permission_type:
            raise ValueError("web_request_permission requires 'permission_type'")

        cleaned["permission_type"] = permission_type
        cleaned["target"] = "web"
        return cleaned

    # ... existing validation continues ...
```

---

## 9. Engine Integration (Subject Extraction)

**File:** `command_controller/engine.py` (modified, Milestone 9)

```python
from command_controller.subject_extractor import SubjectExtractor

class CommandEngine:
    def __init__(
        self,
        *,
        interpreter: LocalLLMInterpreter | None = None,
        executor: Executor | None = None,
        confirmations: ConfirmationStore | None = None,
        logger: CommandLogger | None = None,
    ) -> None:
        self.interpreter = interpreter or LocalLLMInterpreter()
        self.executor = executor or Executor()
        self.confirmations = confirmations or ConfirmationStore()
        self.logger = logger or CommandLogger()
        self._last_result: dict | None = None

        # NEW: Subject extraction (optional)
        self._subject_extractor = SubjectExtractor(self.interpreter)

    def run(self, *, source: str, text: str, context: dict | None = None) -> dict:
        # ... existing parsing and validation ...

        # NEW: Optional subject extraction (Milestone 9)
        settings = get_settings()
        if settings.get("enable_subject_extraction", False):
            subject_groups = self._subject_extractor.extract(text, steps)
            deep_log(f"[DEEP][ENGINE] subject_groups={subject_groups}")
            # Future: execute subject groups in parallel

        return self._safe_execute(steps)
```

---

## 10. Configuration Accessor Pattern

**Access Pattern:** All modules use `utils.settings_store.get_settings()`.

**No new config accessor needed** - existing pattern is sufficient.

**Example Usage:**
```python
from utils.settings_store import get_settings

settings = get_settings()
use_playwright = settings.get("use_playwright_for_web", True)
timeout_ms = settings.get("playwright_navigation_timeout_ms", 30000)
```

---

## Protocol Definitions (Type Safety)

For type-checking and documentation purposes, define protocols for dependency injection:

**File:** `command_controller/protocols.py` (new, optional)

```python
from typing import Protocol

class Resolver(Protocol):
    """Protocol for URL resolvers."""
    def resolve(self, query: str) -> URLResolutionResult: ...
    def shutdown(self) -> None: ...


class Fallback(Protocol):
    """Protocol for fallback strategies."""
    def execute(self, query: str) -> FallbackResult: ...


class SubjectExtractor(Protocol):
    """Protocol for subject extraction."""
    def extract(self, text: str, steps: list[dict]) -> list[SubjectGroup]: ...
```

These protocols enable type-checking without hard dependencies, useful for testing.

---

## Error Code Registry

**File:** `command_controller/web_errors.py` (new, optional)

Centralize error codes for consistency:

```python
"""Web execution error codes."""

# URL Resolution errors
RESOLUTION_TIMEOUT = "RESOLUTION_TIMEOUT"
RESOLUTION_DOM_SEARCH_FAILED = "RESOLUTION_DOM_SEARCH_FAILED"
RESOLUTION_CHROMIUM_MISSING = "RESOLUTION_CHROMIUM_MISSING"

# Fallback errors
FALLBACK_ALL_FAILED = "FALLBACK_ALL_FAILED"
FALLBACK_SEARCH_DISABLED = "FALLBACK_SEARCH_DISABLED"

# Form fill errors
WEB_FORM_FILL_DISABLED = "WEB_FORM_FILL_DISABLED"
WEB_FORM_FIELD_NOT_FOUND = "WEB_FORM_FIELD_NOT_FOUND"
WEB_FORM_SUBMIT_FAILED = "WEB_FORM_SUBMIT_FAILED"

# Existing errors
WEB_UNEXPECTED = "WEB_UNEXPECTED"
WEB_UNSAFE_URL = "WEB_UNSAFE_URL"
WEB_RESOLUTION_FAILED = "WEB_RESOLUTION_FAILED"
```

---

## Summary

This interface specification provides:
- Complete type-annotated signatures for all new modules
- Clear contracts for data structures (dataclasses)
- Integration points with existing codebase
- Protocol definitions for type safety
- Detailed docstrings for implementation guidance

**Implementation Order:**
1. ExecutionResult (base.py) - foundation for metadata
2. URLResolutionCache - simple utility
3. URLResolver - core resolution logic
4. FallbackChain - orchestration layer
5. SubjectExtractor - optional enhancement
6. WebExecutor modifications - integration
7. Executor modifications - result enrichment
8. Intent validation extensions - new intents

All interfaces are designed for backward compatibility and independent testing.
