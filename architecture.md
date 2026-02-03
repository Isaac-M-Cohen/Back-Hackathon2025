# Executor Rework: Architecture Document

## Executive Summary

This architecture introduces a headless Playwright-based URL resolution system with modular fallback chains and enhanced execution results. The design maintains backward compatibility while adding rich metadata tracking, subject extraction capabilities, and toggleable features.

**Core Principles:**
- Additive enhancements - no breaking changes to existing step execution
- Feature toggles for all new capabilities
- Separate Playwright contexts to avoid resource conflicts
- Rich result metadata for debugging and analytics
- Clean separation of concerns between resolution, fallback, and execution

---

## System Overview

### High-Level Data Flow

```
Command Text
    ↓
[Engine] Parse & Validate
    ↓
[Executor] Route Steps
    ↓
    ├─→ [OS Target] → OSRouter → MacOSExecutor/WindowsExecutor
    │                              ↓
    │                     ExecutionResult (basic)
    │
    └─→ [Web Target] → WebExecutor
                          ↓
                    [Check: use_playwright_for_web?]
                          ↓
                     Yes: Enhanced Flow
                          ↓
                    [open_url detected?]
                          ↓
                     [URLResolver] - Headless navigation & DOM search
                          ↓
                     [FallbackChain] - Resolution → Search → Homepage
                          ↓
                     [Check: request_before_open_url?]
                          ↓
                     [Open in default browser via macOS 'open']
                          ↓
                     ExecutionResult (enhanced metadata)
```

### Module Dependency Graph

```
engine.py
    ↓
executor.py
    ↓
    ├─→ OSRouter ──→ MacOSExecutor
    │                WindowsExecutor
    │
    └─→ WebExecutor
            ↓
            ├─→ URLResolver (new) ──→ Playwright (headless)
            │       ↓
            │   url_resolution_cache.py (new)
            │
            ├─→ FallbackChain (new)
            │       ↓
            │   ├─→ URLResolver
            │   ├─→ SearchFallback
            │   └─→ HomepageFallback
            │
            ├─→ SubjectExtractor (new, optional)
            │       ↓
            │   LocalLLMInterpreter (existing)
            │
            └─→ Site Adapters (existing)
                    whatsapp.py
                    [future adapters]
```

---

## Module Architecture

### 1. URLResolver (`command_controller/url_resolver.py`)

**Responsibility:** Navigate to URLs headless, search DOM for relevant links, return resolved final URLs.

**Key Interfaces:**
```python
class URLResolver:
    def __init__(self, settings: dict):
        """Initialize with separate headless Playwright context."""

    def resolve(self, query: str) -> URLResolutionResult:
        """Main entry point: resolve query to final URL."""

    def _search_dom_for_links(self, page: Page, query: str) -> list[LinkCandidate]:
        """Extract candidate URLs from DOM based on text matching."""

    def _rank_candidates(self, candidates: list[LinkCandidate], query: str) -> str | None:
        """Rank candidates and return best match."""

    def shutdown(self):
        """Clean up Playwright context."""
```

**URLResolutionResult Structure:**
```python
@dataclass
class URLResolutionResult:
    status: str  # "ok" | "failed" | "timeout"
    resolved_url: str | None
    search_query: str
    candidates_found: int
    selected_reason: str | None  # "text_match" | "position" | "aria_label"
    elapsed_ms: int
```

**Implementation Notes:**
- Uses separate Playwright instance with `playwright_resolver_profile` directory
- Always runs in headless mode regardless of global `playwright_headless` setting
- Implements 15-minute TTL cache via `URLResolutionCache`
- Timeout controlled by `playwright_navigation_timeout_ms` config
- DOM search heuristics:
  1. Find all `<a>` tags
  2. Filter by visible text containing query terms
  3. Rank by DOM position (header links preferred), ARIA labels, link text similarity
  4. Return top candidate

**Lifecycle:**
- Instantiated lazily on first URL resolution request
- Playwright context kept alive across resolutions (shared session)
- Cleaned up via `shutdown()` when WebExecutor shuts down

---

### 2. FallbackChain (`command_controller/fallback_chain.py`)

**Responsibility:** Orchestrate fallback attempts when URL resolution fails.

**Key Interfaces:**
```python
class FallbackChain:
    def __init__(self, resolver: URLResolver, settings: dict):
        """Initialize with URLResolver and config toggles."""

    def execute(self, query: str) -> FallbackResult:
        """Try resolution, then search, then homepage in sequence."""

    def _try_direct_resolution(self, query: str) -> FallbackResult | None:
        """Attempt 1: URLResolver direct resolution."""

    def _try_search_fallback(self, query: str) -> FallbackResult | None:
        """Attempt 2: Navigate to search engine with query."""

    def _try_homepage_fallback(self, query: str) -> FallbackResult | None:
        """Attempt 3: Extract domain from query, navigate to homepage."""
```

**FallbackResult Structure:**
```python
@dataclass
class FallbackResult:
    status: str  # "ok" | "all_failed"
    final_url: str | None
    fallback_used: str  # "resolution" | "search" | "homepage" | "none"
    attempts_made: list[str]  # ["resolution", "search"]
    resolution_details: URLResolutionResult | None
    elapsed_ms: int
```

**Fallback Order Logic:**
```
1. Direct Resolution (if use_playwright_for_web=true)
   ├─ Success? → Return with fallback_used="resolution"
   └─ Failure → Continue

2. Search Engine Fallback (if enable_search_fallback=true)
   ├─ Format: search_engine_url.format(query=url_encoded_query)
   ├─ Success? → Return with fallback_used="search"
   └─ Failure → Continue

3. Homepage Fallback (if enable_homepage_fallback=true)
   ├─ Extract domain from query (e.g., "youtube" → "https://youtube.com")
   ├─ Success? → Return with fallback_used="homepage"
   └─ Failure → Return status="all_failed"
```

**Config Interaction:**
- Checks `enable_search_fallback` before attempting search
- Checks `enable_homepage_fallback` before attempting homepage
- Uses `search_engine_url` template from config (default: DuckDuckGo)
- Logs each attempt at DEEP level for diagnostics

---

### 3. SubjectExtractor (`command_controller/subject_extractor.py`)

**Responsibility:** Parse commands into distinct subjects with associated steps.

**Key Interfaces:**
```python
class SubjectExtractor:
    def __init__(self, llm_interpreter: LocalLLMInterpreter | None = None):
        """Initialize with optional LLM for semantic analysis."""

    def extract(self, text: str, steps: list[dict]) -> list[SubjectGroup]:
        """Group steps by subject (URL, app, file)."""

    def _identify_subjects(self, text: str, steps: list[dict]) -> list[str]:
        """Identify distinct entities in command text."""

    def _assign_steps_to_subjects(self, subjects: list[str], steps: list[dict]) -> list[SubjectGroup]:
        """Associate steps with their target subjects."""
```

**SubjectGroup Structure:**
```python
@dataclass
class SubjectGroup:
    subject_name: str  # "YouTube", "Gmail", "Spotify"
    subject_type: str  # "url" | "app" | "file" | "unknown"
    steps: list[dict]  # Steps associated with this subject
    start_index: int   # Original step index (for ordering)
```

**Extraction Heuristics:**
1. **Simple Case (single subject):** All steps → one SubjectGroup
2. **Multi-app Case:** "open Gmail and Spotify"
   - LLM identifies two subjects: ["Gmail", "Spotify"]
   - `open_app(Gmail)` → Subject 1
   - `open_app(Spotify)` → Subject 2
3. **URL + Actions Case:** "open YouTube and search for cats"
   - Subject: "YouTube"
   - Steps: `open_url`, `type_text` → Same group
4. **Ambiguous Case:** Fallback to keyword matching or single group

**Integration Point:**
- Called in `engine.py` after step normalization (Milestone 9, optional)
- Results logged at DEBUG/DEEP level
- Future enhancement: parallel subject execution

---

### 4. Enhanced ExecutionResult (`command_controller/executors/base.py`)

**Updated Structure:**
```python
@dataclass
class ExecutionResult:
    intent: str
    status: str
    target: str = "os"
    details: dict[str, Any] | None = None
    elapsed_ms: int | None = None

    # New optional fields (Milestone 2)
    resolved_url: str | None = None
    fallback_used: str | None = None
    navigation_time_ms: int | None = None
    dom_search_query: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize, including new fields only when present."""
```

**Backward Compatibility:**
- All new fields are `None` by default
- `to_dict()` only includes new fields if they are not `None`
- Existing executors (OSRouter, MacOSExecutor) don't need changes
- API consumers see same structure for OS-target steps

**Usage Examples:**
```python
# OS executor (no changes):
ExecutionResult(intent="open_app", status="ok", target="os", elapsed_ms=45)

# Web executor (URL resolution):
ExecutionResult(
    intent="open_url",
    status="ok",
    target="web",
    resolved_url="https://youtube.com/results?search_query=cats",
    fallback_used="resolution",
    navigation_time_ms=2340,
    dom_search_query="cats"
)

# Web executor (search fallback):
ExecutionResult(
    intent="open_url",
    status="ok",
    target="web",
    resolved_url="https://duckduckgo.com/?q=youtube+cats",
    fallback_used="search"
)
```

---

### 5. WebExecutor Rework (`command_controller/web_executor.py`)

**Refactored `_handle_open_url` Method:**
```python
def _handle_open_url(self, step: dict) -> None:
    """Enhanced open_url handler with resolution and fallback."""
    url = step.get("url", "")
    settings = get_settings()

    # Step 1: Check if enhanced web flow is enabled
    if not settings.get("use_playwright_for_web", True):
        # Legacy: direct navigation in Playwright
        self._page.goto(url, wait_until="domcontentloaded")
        return

    # Step 2: URL Resolution + Fallback
    fallback_chain = self._get_fallback_chain()
    result = fallback_chain.execute(url)

    if result.status == "all_failed":
        raise WebExecutionError(
            code="WEB_RESOLUTION_FAILED",
            message=f"Failed to resolve URL: {url}"
        )

    final_url = result.final_url

    # Step 3: Check confirmation before opening in default browser
    if settings.get("request_before_open_url", False):
        # Placeholder for future confirmation hook
        # Currently: just log warning
        tprint(f"[WEB_EXEC] Opening URL in default browser: {final_url}")

    # Step 4: Open resolved URL in user's default browser (OS native)
    subprocess.run(["open", final_url], check=False)  # macOS
    # OR: self._page.goto(final_url) if opening in Playwright context

    # Step 5: Store metadata for ExecutionResult enrichment
    self._last_resolution = result
```

**Integration with Executor:**
```python
# In executor.py _execute_web_step():
def _execute_web_step(self, step: dict) -> ExecutionResult:
    intent = str(step.get("intent", "")).strip() or "web"
    try:
        self._get_web_executor().execute_step(step)

        # Check if web executor has resolution metadata
        web_exec = self._get_web_executor()
        if hasattr(web_exec, '_last_resolution') and web_exec._last_resolution:
            res_data = web_exec._last_resolution
            return ExecutionResult(
                intent=intent,
                status="ok",
                target="web",
                resolved_url=res_data.final_url,
                fallback_used=res_data.fallback_used,
                navigation_time_ms=res_data.elapsed_ms,
                dom_search_query=res_data.resolution_details.search_query if res_data.resolution_details else None
            )

        return ExecutionResult(intent=intent, status="ok", target="web")
    except WebExecutionError as exc:
        # Existing error handling...
```

**New Method: `_handle_form_fill`** (Milestone 6, gated by config):
```python
def _handle_form_fill(self, step: dict) -> None:
    """Fill web forms using Playwright (gated by allow_headless_form_fill)."""
    settings = get_settings()
    if not settings.get("allow_headless_form_fill", False):
        raise WebExecutionError(
            code="WEB_FORM_FILL_DISABLED",
            message="Form fill is disabled. Enable via allow_headless_form_fill config."
        )

    form_fields = step.get("form_fields", {})
    submit = step.get("submit", False)

    # Iterate over form_fields dict and fill inputs
    for selector, value in form_fields.items():
        el = self._page.wait_for_selector(selector, timeout=10000)
        el.fill(str(value))

    if submit:
        # Find and click submit button
        # Heuristic: button[type="submit"] or input[type="submit"]
        submit_btn = self._page.locator('button[type="submit"], input[type="submit"]').first
        submit_btn.click()
```

**Permission Hook Infrastructure** (Milestone 6, stub):
```python
def _handle_request_permission(self, step: dict) -> None:
    """Placeholder for future permission handling."""
    permission_type = step.get("permission_type", "")
    tprint(f"[WEB_EXEC] Permission requested: {permission_type}")
    # Future: integrate with browser permission APIs or confirmation system
    pass
```

---

### 6. URLResolutionCache (`command_controller/url_resolution_cache.py`)

**Responsibility:** In-memory cache with TTL for resolved URLs.

**Key Interfaces:**
```python
class URLResolutionCache:
    def __init__(self, ttl_secs: int = 900):  # 15 minutes default
        """Initialize cache with TTL."""
        self._cache: dict[str, CacheEntry] = {}
        self._ttl = ttl_secs

    def get(self, query: str) -> URLResolutionResult | None:
        """Retrieve cached result if not expired."""

    def put(self, query: str, result: URLResolutionResult) -> None:
        """Store result with timestamp."""

    def clear(self) -> None:
        """Invalidate all cached entries."""
```

**CacheEntry Structure:**
```python
@dataclass
class CacheEntry:
    result: URLResolutionResult
    timestamp: float  # time.time()
```

**Implementation Notes:**
- Simple in-memory dict (no persistence)
- Expiration check on `get()`: if `time.time() - timestamp > ttl`, return None
- No background cleanup thread (lazy expiration)
- Future enhancement: Redis or SQLite for persistence

---

## Configuration Schema

**Updated `config/app_settings.json`:**
```json
{
  "app_name": "easy",
  "theme": "light",
  "language": "en",
  "log_level": "DEEP",

  // Existing Playwright config
  "playwright_profile_dir": "user_data/playwright_profile",
  "playwright_headless": false,

  // NEW: Web executor features (Milestone 1)
  "use_playwright_for_web": true,
  "use_playwright_for_web_comment": "Enable headless URL resolution and fallback chain. Set false to use legacy direct navigation.",

  "request_before_open_url": false,
  "request_before_open_url_comment": "If true, show confirmation before opening resolved URLs in default browser.",

  "enable_search_fallback": true,
  "enable_search_fallback_comment": "Fallback to search engine if URL resolution fails.",

  "enable_homepage_fallback": true,
  "enable_homepage_fallback_comment": "Fallback to domain homepage if search fallback fails.",

  "allow_headless_form_fill": false,
  "allow_headless_form_fill_comment": "SECURITY: Allow web_fill_form intent. Default false for safety.",

  "search_engine_url": "https://duckduckgo.com/?q={query}",
  "search_engine_url_comment": "Template for search fallback. Use {query} placeholder.",

  "playwright_navigation_timeout_ms": 30000,
  "playwright_navigation_timeout_ms_comment": "Timeout for URL resolution navigation.",

  "playwright_resolver_profile": "user_data/playwright_resolver",
  "playwright_resolver_profile_comment": "Separate profile for headless URL resolver to avoid context conflicts."
}
```

**Config Access Pattern:**
```python
from utils.settings_store import get_settings

settings = get_settings()
use_playwright = settings.get("use_playwright_for_web", True)
```

---

## Intent Schema Extensions

**New Intents (Milestone 8):**

### `web_fill_form`
```json
{
  "intent": "web_fill_form",
  "target": "web",
  "form_fields": {
    "#email": "user@example.com",
    "#password": "secret123"
  },
  "submit": true
}
```

**Validation:**
- `form_fields`: required, dict of `{selector: value}`
- `submit`: optional, bool (default: false)
- Gated by `allow_headless_form_fill` config
- Added to `ALWAYS_CONFIRM_INTENTS` for safety

### `web_request_permission`
```json
{
  "intent": "web_request_permission",
  "target": "web",
  "permission_type": "location"
}
```

**Validation:**
- `permission_type`: required, string (e.g., "location", "camera", "notifications")
- Stub implementation in Milestone 6
- Future: integrate with browser permission dialogs

**Updated `intents.py` ALLOWED_INTENTS:**
```python
ALLOWED_INTENTS = {
    # Existing intents...
    "open_url",
    "type_text",
    "web_send_message",

    # New intents (Milestone 8)
    "web_fill_form",
    "web_request_permission",
}
```

---

## Data Flow Examples

### Example 1: URL Resolution Success
```
User Command: "open YouTube and search for cats"

1. Engine parses to steps:
   [
     {"intent": "open_url", "url": "youtube", "target": "web"},
     {"intent": "type_text", "text": "cats", "target": "web"}
   ]

2. Executor routes to WebExecutor

3. WebExecutor._handle_open_url():
   - FallbackChain.execute("youtube")
   - URLResolver.resolve("youtube")
     → Navigates to youtube.com headless
     → Searches DOM for search box link
     → Finds "https://youtube.com/results?search_query=..."
     → Returns URLResolutionResult(status="ok", resolved_url="...", candidates_found=5)
   - FallbackResult(final_url="...", fallback_used="resolution")
   - subprocess.run(["open", final_url])

4. ExecutionResult returned:
   {
     "intent": "open_url",
     "status": "ok",
     "target": "web",
     "resolved_url": "https://youtube.com/results?search_query=...",
     "fallback_used": "resolution",
     "navigation_time_ms": 2340
   }
```

### Example 2: Search Fallback
```
User Command: "open unknown-site-xyz"

1. URLResolver.resolve("unknown-site-xyz") → status="failed" (timeout)
2. FallbackChain._try_search_fallback("unknown-site-xyz")
   → Returns "https://duckduckgo.com/?q=unknown-site-xyz"
3. FallbackResult(final_url="...", fallback_used="search")
4. ExecutionResult:
   {
     "fallback_used": "search",
     "resolved_url": "https://duckduckgo.com/?q=unknown-site-xyz"
   }
```

### Example 3: Subject Extraction (Optional)
```
User Command: "open Gmail and Spotify"

1. Engine parses to steps:
   [
     {"intent": "open_app", "app": "Gmail"},
     {"intent": "open_app", "app": "Spotify"}
   ]

2. SubjectExtractor.extract():
   → Returns [
       SubjectGroup(subject_name="Gmail", subject_type="app", steps=[step1]),
       SubjectGroup(subject_name="Spotify", subject_type="app", steps=[step2])
     ]

3. Executor executes each group in sequence (or parallel in future)
```

---

## Design Rationale

### 1. Separate Playwright Contexts
**Decision:** Use distinct profile directories for URLResolver (headless) and WebExecutor (headed).

**Rationale:**
- Playwright locks user data directories when contexts are open
- Concurrent usage (resolution + web automation) would conflict
- Headless resolver needs clean state, web executor needs persistent login sessions

**Trade-off:** Increased disk usage (~200MB per profile), but prevents runtime errors.

---

### 2. Open Resolved URLs in Default Browser (Not Playwright)
**Decision:** After URL resolution, use macOS `open` command to launch URL in user's default browser.

**Rationale:**
- User's default browser has their bookmarks, passwords, extensions
- Playwright context is for automation, not browsing
- Matches user expectation: "open YouTube" → launches in Safari/Chrome

**Trade-off:** Cannot automate actions in default browser, but that's a security feature.

---

### 3. Fixed Fallback Order (Resolution → Search → Homepage)
**Decision:** Hardcode fallback sequence, make each step toggleable.

**Rationale:**
- Simplifies implementation (no config ordering logic)
- Covers 95% of use cases with sensible defaults
- Individual toggles provide sufficient flexibility

**Trade-off:** Power users can't reorder, but can disable unwanted steps.

---

### 4. In-Memory Cache with TTL
**Decision:** Use simple dict-based cache with 15-minute expiration.

**Rationale:**
- Fast lookups (no I/O)
- Stateless (survives restarts gracefully)
- Matches WebFetch cache pattern (consistency)

**Trade-off:** Cache lost on restart, but URLs resolve fresh anyway.

---

### 5. Subject Extraction Optional (Milestone 9)
**Decision:** Make subject extraction a non-blocking enhancement.

**Rationale:**
- Complex feature with unclear accuracy requirements
- Not critical for core URL resolution functionality
- Can be deferred without impacting other milestones

**Trade-off:** Won't get parallel execution benefits initially, but reduces risk.

---

### 6. Form Fill Gated Behind Config
**Decision:** Default `allow_headless_form_fill=false`, require explicit opt-in.

**Rationale:**
- Security risk: malicious commands could submit forms with user data
- Aligns with principle of least privilege
- Users must consciously enable dangerous features

**Trade-off:** Extra friction for legitimate use, but prevents abuse.

---

## Integration Points

### 1. Engine → Executor
**Contract:** Engine validates steps, Executor executes and returns results.

**Changes:** None (existing contract preserved).

**New Data:** Enhanced ExecutionResult with optional metadata fields.

---

### 2. Executor → WebExecutor
**Contract:** Executor calls `_execute_web_step()`, catches `WebExecutionError`.

**Changes:** Executor now checks for `_last_resolution` attribute to enrich ExecutionResult.

**Backward Compatibility:** Attribute is optional; if missing, returns basic result.

---

### 3. WebExecutor → URLResolver
**Contract:** WebExecutor calls `URLResolver.resolve(query)`, receives `URLResolutionResult`.

**Lifecycle:** URLResolver instantiated lazily, shared across resolutions, cleaned up in `shutdown()`.

---

### 4. WebExecutor → FallbackChain
**Contract:** WebExecutor calls `FallbackChain.execute(query)`, receives `FallbackResult`.

**Dependencies:** FallbackChain depends on URLResolver instance.

---

### 5. SubjectExtractor → LocalLLMInterpreter
**Contract:** SubjectExtractor can optionally use LLM for semantic subject identification.

**Integration:** SubjectExtractor accepts `LocalLLMInterpreter` in constructor (dependency injection).

---

## Error Handling Strategy

### URL Resolution Errors
```python
# URLResolver errors
- "RESOLUTION_TIMEOUT": Navigation timeout exceeded
- "RESOLUTION_DOM_SEARCH_FAILED": No candidate links found
- "RESOLUTION_CHROMIUM_MISSING": Playwright Chromium not installed

# FallbackChain errors
- "FALLBACK_ALL_FAILED": All fallback attempts exhausted
- "FALLBACK_SEARCH_DISABLED": Search fallback disabled but needed
```

**Recovery:** FallbackChain automatically tries next fallback. Only raises error if all fail.

---

### Form Fill Errors
```python
- "WEB_FORM_FILL_DISABLED": allow_headless_form_fill=false
- "WEB_FORM_FIELD_NOT_FOUND": Selector not found in DOM
- "WEB_FORM_SUBMIT_FAILED": Submit button click timeout
```

**Recovery:** Raise `WebExecutionError` with screenshot, halt execution.

---

### Playwright Context Errors
```python
- "WEB_CONTEXT_LOCK": Profile directory locked (concurrent usage)
- "WEB_BROWSER_CRASH": Chromium process terminated unexpectedly
```

**Recovery:** Log error, re-initialize Playwright context on next call.

---

## Security Considerations

### 1. Form Fill Safety
- **Risk:** Commands could submit forms with sensitive data (passwords, credit cards).
- **Mitigation:** Default disabled, add to `ALWAYS_CONFIRM_INTENTS`, log all form fills at INFO level.

---

### 2. URL Validation Before Opening
- **Risk:** Resolved URLs could be `file://` or other dangerous schemes.
- **Mitigation:** Validate resolved URL scheme is `http://` or `https://` before calling `open`.

```python
def _is_safe_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")
```

---

### 3. Playwright Profile Permissions
- **Risk:** Profile directories may be readable by other users.
- **Mitigation:** Set directory permissions to 0700 (user-only access) on creation.

```python
Path(profile_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
```

---

### 4. Search Query Injection
- **Risk:** User query could contain malicious URL parameters for search engines.
- **Mitigation:** URL-encode query before inserting into `search_engine_url` template.

```python
from urllib.parse import quote_plus
encoded_query = quote_plus(query)
final_url = search_engine_url.replace("{query}", encoded_query)
```

---

## Performance Considerations

### URL Resolution Latency
- **Expected:** 2-5 seconds per resolution (network + DOM search)
- **Impact:** Noticeable delay for voice commands
- **Mitigation:**
  - Cache resolved URLs (15-minute TTL)
  - Provide immediate feedback to user ("Resolving URL...")
  - Make toggleable via `use_playwright_for_web`

---

### Concurrent Context Memory Usage
- **Expected:** ~500MB for dual Playwright contexts (resolver + web executor)
- **Impact:** High memory usage on lower-end systems
- **Mitigation:**
  - Close resolver context when idle (future enhancement)
  - Document memory requirements in README
  - Provide config to disable URL resolution

---

### Cache Memory Usage
- **Expected:** ~100 entries * 1KB/entry = ~100KB
- **Impact:** Negligible
- **Mitigation:** Add max cache size limit (e.g., 500 entries) with LRU eviction

---

## Testing Strategy

### Unit Tests
- `test_url_resolver.py`: Mock Playwright, test DOM search heuristics
- `test_fallback_chain.py`: Mock URLResolver, test fallback order logic
- `test_subject_extractor.py`: Test subject identification with sample commands
- `test_execution_result.py`: Test `to_dict()` serialization with new fields

---

### Integration Tests
- `test_web_executor_integration.py`: Real Playwright, test open_url flow end-to-end
- `test_fallback_chain_integration.py`: Real URLResolver, test all fallback scenarios
- `test_engine_integration.py`: Test command parsing → execution → enhanced results

---

### Regression Tests
- `test_whatsapp_workflow.py`: Verify WhatsApp adapter still works
- `test_existing_intents.py`: Verify all existing intents execute correctly
- `test_backward_compatibility.py`: Verify ExecutionResult.to_dict() compatible with API consumers

---

### Manual Test Cases (Milestone 10)
1. "open YouTube and search for cats" → Verify URL resolution and search typing
2. "open unknown-site-xyz" → Verify search fallback triggers
3. "open example" → Verify homepage fallback triggers
4. Disable all fallbacks → Verify graceful failure
5. Toggle `allow_headless_form_fill` → Verify permission enforcement

---

## Deployment Considerations

### Chromium Installation
- **Requirement:** Playwright Chromium binary (~200MB)
- **Detection:** Check for Chromium in expected path on first run
- **Error Message:** "Chromium not found. Run: playwright install chromium"
- **Documentation:** Add to README installation section

---

### Config Migration
- **Action:** Add new config fields to `app_settings.json` with defaults
- **Backward Compatibility:** All new fields have defaults, no user action required
- **Validation:** Log warnings if deprecated fields are present

---

### Profile Directory Setup
- **Action:** Create `playwright_resolver_profile` directory on first URLResolver instantiation
- **Permissions:** Set to 0700 (user-only)
- **Cleanup:** Document that profiles can be deleted to reset state

---

## Future Enhancements

### 1. Site-Specific Adapters for URL Resolution
- **Goal:** Custom resolution logic for high-value domains (YouTube, Google, Gmail)
- **Pattern:** Similar to `whatsapp.py`, adapter registry with priority

---

### 2. Vision-Based Link Detection
- **Goal:** Use computer vision to identify clickable elements when DOM search fails
- **Approach:** Playwright screenshot → OpenCV contour detection → click coordinates

---

### 3. Parallel Subject Execution
- **Goal:** Execute independent subject groups in parallel (e.g., "open Gmail and Spotify")
- **Requires:** Thread-safe executor, dependency graph analysis

---

### 4. Redis Cache for URL Resolutions
- **Goal:** Persist cache across restarts, share cache across instances
- **Approach:** Replace in-memory dict with Redis client, keep TTL logic

---

### 5. Configurable Fallback Order
- **Goal:** Allow users to customize fallback sequence
- **Config:** `fallback_order: ["search", "resolution", "homepage"]`

---

## Open Questions (from Planner)

### Q1: URL Resolution Scope
**Answer:** Start with simple search query resolution only. Deep links (e.g., "Gmail inbox" → specific URL) deferred to site-specific adapters in future.

---

### Q2: Permission Hook Use Cases
**Answer:** Minimal infrastructure stub in Milestone 6. Specific permissions (location, camera, etc.) deferred until use cases clarify. Intent schema designed for future expansion.

---

### Q3: Subject Extraction Granularity
**Answer:** "search for cats and dogs" = single subject (search query). "open Gmail and Spotify" = two subjects (apps). Use LLM for ambiguous cases, fallback to keyword matching.

---

### Q4: Fallback Chain Order
**Answer:** Fixed order (resolution → search → homepage) initially. Make configurable in future if user demand exists.

---

### Q5: URL Cache TTL
**Answer:** 15-minute TTL matching WebFetch pattern. Manual invalidation via cache.clear() for power users (future CLI command).

---

## Architecture Constraints

### Backward Compatibility
- **Constraint:** Existing step-based execution format must remain unchanged.
- **Enforcement:** All enhancements are additive (new fields, new modules). No breaking changes to step validation or execution flow.

---

### Configuration Philosophy
- **Constraint:** All new features must be toggleable via config.
- **Enforcement:** Every enhancement has an `enable_*` or `allow_*` config option with sensible default.

---

### Playwright Dependency
- **Constraint:** Playwright already integrated; new features leverage existing dependency.
- **Enforcement:** No additional browser automation libraries (e.g., Selenium). Use Playwright for all web interactions.

---

### OS-Specific Executors
- **Constraint:** macOS-native executor pattern must be preserved.
- **Enforcement:** URL resolution opens in default browser via `open` command, not Playwright context.

---

## Summary

This architecture introduces a modular, toggleable URL resolution system with rich metadata tracking while maintaining full backward compatibility. The design separates concerns cleanly (URLResolver, FallbackChain, SubjectExtractor) and provides extension points for future enhancements (site adapters, permission hooks, parallel execution).

**Key Success Metrics:**
- Zero breaking changes to existing step execution
- All new features toggleable via config
- Rich ExecutionResult metadata for debugging
- URL resolution success rate >70% (with fallbacks)
- Latency <3 seconds for 80% of resolutions (with cache)
