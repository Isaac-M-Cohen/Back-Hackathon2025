# Web Executor System Documentation

## Overview

The Web Executor system provides intelligent URL resolution and web automation capabilities for the Back-Hackathon2025 gesture control application. It transforms simple queries like "youtube cats" into fully resolved URLs using headless browser automation, DOM searching, and configurable fallback strategies.

**Key Features:**
- Headless URL resolution with DOM link extraction
- Three-tier fallback chain (resolution → search → homepage)
- 15-minute caching with LRU eviction
- Separate browser profiles for security isolation
- Browser warm-up for performance optimization
- Opens URLs in default system browser (not automation context)

## How It Works

### URL Resolution Flow

```
User Query → URL Resolver → Fallback Chain → Default Browser
     ↓              ↓              ↓
  "youtube    Infer URL     Try resolution
   cats"      Navigate      ↓ (fails?)
              Search DOM    Try search engine
              Rank links    ↓ (fails?)
              ↓            Try homepage
              Return URL
```

**Example:**
```
Query: "youtube cats"
→ Resolver infers: https://www.youtube.com
→ Navigates in headless browser
→ Searches DOM for links matching "cats"
→ Returns: https://www.youtube.com/results?search_query=cats
→ Opens in Safari/Chrome (default browser)
```

### Fallback Chain Strategy

The system tries three strategies in order:

1. **Direct Resolution** (primary): Navigate to inferred URL, search DOM for matching links
2. **Search Fallback**: Construct search engine URL with query
3. **Homepage Fallback**: Extract domain from query and navigate to homepage

Each stage can be independently enabled/disabled via configuration.

## Architecture Components

### 1. URLResolver (`url_resolver.py`)

Headless Playwright-based resolver that:
- Maintains a separate browser profile (`user_data/playwright_resolver/`)
- Reuses a single page across resolutions for performance
- Searches DOM for links matching query terms
- Ranks candidates by text match, position, and ARIA labels
- Caches results for 15 minutes

**Key Methods:**
- `resolve(query: str) -> URLResolutionResult`: Main entry point
- `warmup()`: Pre-initialize browser to avoid cold-start latency
- `shutdown()`: Cleanup resources

### 2. FallbackChain (`fallback_chain.py`)

Orchestrates the three-tier fallback strategy:
- Attempts direct resolution first
- Falls back to search engine if resolution fails
- Falls back to homepage if search is disabled/fails
- Tracks which method succeeded for telemetry

**Key Methods:**
- `execute(query: str) -> FallbackResult`: Run fallback chain
- Returns metadata including attempts made and elapsed time

### 3. URLResolutionCache (`url_resolution_cache.py`)

In-memory cache with:
- 15-minute TTL (time-to-live)
- 100-entry LRU eviction
- Proactive expired entry cleanup on `put()`
- Caches both successful and failed resolutions

**Configuration:**
- TTL: 900 seconds (15 minutes)
- Max size: 100 entries
- Eviction: Least Recently Used (LRU)

### 4. WebExecutor (`web_executor.py`)

Main executor for web-target intents:
- Manages user-visible Playwright context (separate from resolver)
- Routes intents to appropriate handlers
- Integrates URL resolution with browser opening
- Provides metadata enrichment for execution results

**Supported Intents:**
- `open_url`: Enhanced with resolution and fallback
- `type_text`: Type into web elements
- `key_combo`: Press key combinations
- `click`: Click elements or coordinates
- `scroll`: Scroll pages
- `web_send_message`: Site-specific adapters (WhatsApp)
- `web_fill_form`: Form automation (requires config opt-in)
- `web_request_permission`: Browser permission hooks (future)

### 5. SubjectExtractor (`subject_extractor.py`)

Groups multi-subject commands:
- Identifies distinct subjects in commands like "open Gmail and Spotify"
- Groups steps by subject for parallel execution (future)
- Preserves execution order via start_index

## Configuration Guide

### Required Settings (`config/app_settings.json`)

```json
{
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
  "playwright_resolver_profile_comment": "Separate profile for headless URL resolver to avoid context conflicts.",

  "warmup_url_resolver": true,
  "warmup_url_resolver_comment": "Pre-initialize browser on startup to amortize cold-start cost."
}
```

### Configuration Options Explained

| Option | Type | Default | Purpose |
|--------|------|---------|---------|
| `use_playwright_for_web` | boolean | true | Enable enhanced resolution (disable for legacy direct navigation) |
| `request_before_open_url` | boolean | false | Require user confirmation before opening URLs |
| `enable_search_fallback` | boolean | true | Allow search engine fallback when resolution fails |
| `enable_homepage_fallback` | boolean | true | Allow homepage fallback when search fails |
| `allow_headless_form_fill` | boolean | false | Enable form automation (security risk if enabled) |
| `search_engine_url` | string | DuckDuckGo | Search engine template with `{query}` placeholder |
| `playwright_navigation_timeout_ms` | number | 30000 | Navigation timeout in milliseconds |
| `playwright_resolver_profile` | string | `user_data/playwright_resolver` | Directory for resolver browser profile |
| `warmup_url_resolver` | boolean | true | Pre-initialize browser on first use |

### Domain Mappings (`web_constants.py`)

The system includes common domain mappings:

```python
COMMON_DOMAINS = {
    "youtube": "www.youtube.com",
    "gmail": "mail.google.com",
    "google": "www.google.com",
    "github": "github.com",
    "twitter": "twitter.com",
    # ... 5 more
}
```

**Customization:** Edit `command_controller/web_constants.py` to add/modify domain mappings.

## Usage Examples

### Basic URL Opening

```python
# User command: "open youtube cats"
step = {
    "intent": "open_url",
    "url": "youtube cats"
}

# System flow:
# 1. WebExecutor receives step
# 2. FallbackChain.execute("youtube cats")
# 3. URLResolver:
#    - Infers: https://www.youtube.com
#    - Navigates headless browser
#    - Searches DOM for links with "cats"
#    - Ranks candidates, returns best match
# 4. Validates URL scheme (http/https only)
# 5. Opens in default browser: subprocess.run(["open", final_url])
```

### Fallback Example: Search

```python
# User command: "open unknown-domain cats"
step = {
    "intent": "open_url",
    "url": "unknown-domain cats"
}

# System flow:
# 1. Direct resolution fails (no matches found)
# 2. Search fallback triggered
# 3. Constructs: https://duckduckgo.com/?q=unknown-domain+cats
# 4. Opens search results in default browser
```

### Fallback Example: Homepage

```python
# User command: "open spotify"
step = {
    "intent": "open_url",
    "url": "spotify"
}

# With search_fallback disabled:
# 1. Direct resolution fails
# 2. Homepage fallback triggered
# 3. Extracts domain: "spotify" → "spotify.com"
# 4. Opens: https://spotify.com
```

### Cache Behavior

```python
# First request: Full resolution (200-800ms)
resolve("youtube cats")  # → 650ms

# Second request within 15 minutes: Cache hit (~0-5ms)
resolve("youtube cats")  # → 2ms (cache hit)

# After 15 minutes: Cache expired, full resolution
resolve("youtube cats")  # → 680ms (cache miss)
```

## Security Considerations

### Critical Security Features

1. **URL Scheme Validation**: Only `http://` and `https://` schemes allowed
2. **Separate Browser Profiles**: Resolver and user contexts are isolated
3. **Profile Permissions**: Directories created with `mode=0o700` (user-only access)
4. **Form Fill Gate**: Disabled by default, requires explicit config opt-in
5. **Search Query Encoding**: URL-encoded to prevent injection attacks

### Known Security Gaps (See `security_notes.md` for details)

**CRITICAL:**
- Playwright profiles store credentials unencrypted
- Subprocess command injection possible via crafted URLs
- Insufficient URL validation (allows localhost, private IPs)

**HIGH:**
- Form fill logging may expose sensitive data
- Cache poisoning via unvalidated queries
- DOM search XSS via JavaScript URL resolution

**Recommended Actions:**
1. Block localhost and private IP ranges in `_is_safe_url()`
2. Add subprocess argument escaping
3. Sanitize form field names in logs
4. Implement profile encryption at rest

### Secure Configuration

For production deployments:

```json
{
  "allow_headless_form_fill": false,
  "request_before_open_url": true,
  "log_level": "INFO",
  "playwright_headless": true
}
```

### Security Best Practices

1. **Never enable `allow_headless_form_fill` in production** without explicit user consent
2. **Enable `request_before_open_url`** for sensitive environments
3. **Avoid DEEP logging** in production (may expose sensitive commands)
4. **Restrict profile directory permissions** to user-only access
5. **Monitor subprocess execution** for anomalous URLs
6. **Regularly update domain mappings** in `web_constants.py`

## Performance Optimization

### Browser Warm-up

Cold-start browser initialization takes 1-3 seconds. The system supports eager warm-up:

```python
# Automatic (default):
# First resolution triggers warm-up, subsequent resolutions are fast

# Manual (for testing):
from command_controller.url_resolver import URLResolver
resolver = URLResolver()
resolver.warmup()  # Pre-initialize browser
```

**Impact:**
- First resolution (cold): 1-3s
- First resolution (warm): 200-800ms
- Cached resolution: 0-5ms

### Page Reuse

URLResolver reuses a single Playwright page across all resolutions:

**Before optimization:**
- Each resolution: `new_page()` → navigate → `close()` → 50-200ms overhead per call

**After optimization:**
- Single page created on initialization
- Reused for all resolutions → 50-200ms saved per resolution after first

### DOM Search Efficiency

DOM search is limited to:
- First 100 links on page (performance)
- Early exit after 20 matching candidates (optimization)

**Impact:**
- Large pages (Reddit, news sites): 100-500ms faster
- Typical pages: Minimal impact

### Cache Effectiveness

**Metrics to monitor:**

```python
cache_hit_rate = cache_hits / (cache_hits + cache_misses)
# Target: >30% for typical usage patterns
```

**Cache tuning:**
- Increase `ttl_secs` for longer retention (trade-off: stale results)
- Increase `max_size` for more entries (trade-off: memory usage)
- Decrease `ttl_secs` to 0 to disable caching entirely

### Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Cold-start resolution | <3s | First resolution (browser launch) |
| Warm resolution | <500ms | Average after warm-up |
| Cache hit latency | <5ms | In-memory cache lookup |
| DOM search time | <200ms | Most pages |
| Cache hit rate | >30% | Typical usage patterns |

## Troubleshooting

### Problem: "Failed to launch resolver browser"

**Cause:** Chromium not installed for Playwright

**Solution:**
```bash
playwright install chromium
```

**Verification:**
```bash
which chromium  # Should return path
```

---

### Problem: Resolution always returns search engine

**Cause:** Direct resolution failing, search fallback succeeding

**Diagnosis:**
1. Enable deep logging: Set `log_level: "DEEP"` in `app_settings.json`
2. Check logs for: `[DEEP][URL_RESOLVER] Direct resolution failed: ...`
3. Look for error message indicating cause

**Common Causes:**
- Domain not in `COMMON_DOMAINS` → Add mapping or use full URL
- Navigation timeout → Increase `playwright_navigation_timeout_ms`
- No matching links found → Query terms too specific

**Solution:**
- Add domain to `web_constants.py:COMMON_DOMAINS`
- Use more generic query terms
- Provide full URL instead of search query

---

### Problem: Cache not being hit (slow repeated queries)

**Cause:** Query variations not matching cache keys

**Example:**
```python
resolve("youtube cats")    # Cache miss (first time)
resolve("YouTube cats")    # Cache miss (case-sensitive key)
resolve("youtube  cats")   # Cache miss (extra space)
```

**Solution:** Queries must match exactly (including case and whitespace)

**Workaround:** Normalize queries before passing to resolver:
```python
query = query.strip().lower()
```

---

### Problem: URLs open in Playwright instead of default browser

**Cause:** `use_playwright_for_web` is disabled

**Solution:** Enable enhanced mode in `app_settings.json`:
```json
{
  "use_playwright_for_web": true
}
```

**Note:** Legacy mode (`false`) navigates directly in Playwright context without resolution or default browser opening.

---

### Problem: "Permission denied" on profile directory

**Cause:** Incorrect directory permissions

**Diagnosis:**
```bash
ls -ld user_data/playwright_resolver
# Should show: drwx------ (700)
```

**Solution:**
```bash
chmod 700 user_data/playwright_resolver
```

**Prevention:** Profile directories are automatically created with `mode=0o700`, but manual modification may break permissions.

---

### Problem: Fallback chain always uses homepage

**Cause:** Both resolution and search fallback disabled or failing

**Diagnosis:**
1. Check config:
   ```json
   {
     "enable_search_fallback": true,  // Should be true
     "enable_homepage_fallback": true
   }
   ```
2. Enable deep logging and check for errors in resolution/search attempts

**Solution:**
- Enable search fallback in config
- Verify search engine URL template is valid: `"search_engine_url": "https://duckduckgo.com/?q={query}"`
- Check network connectivity (resolution requires internet)

---

### Problem: High memory usage over time

**Cause:** Cache not evicting entries or browser contexts accumulating

**Diagnosis:**
```python
# Monitor cache size
cache.size()  # Should stay below max_size (100)
```

**Solutions:**
1. **Cache accumulation:** Reduce `max_size` in URLResolutionCache constructor
2. **Browser contexts:** Call `resolver.shutdown()` and `web_executor.shutdown()` on app exit
3. **Memory leak:** Check Playwright browser process count: should be 2 (resolver + user)

**Verification:**
```bash
ps aux | grep chromium  # Should show 2 processes
```

---

### Problem: Rate limiting or DoS protection

**Symptom:** Consecutive resolutions fail with timeouts

**Cause:** Target site blocking automated requests

**Solutions:**
1. **Reduce frequency:** Add delays between resolutions
2. **Use cache:** Repeated queries hit cache instead of site
3. **Custom headers:** Add user-agent to Playwright context (advanced)

**Configuration:**
```python
# In url_resolver.py, _ensure_browser():
self._browser = self._playwright.chromium.launch_persistent_context(
    user_data_dir=profile_dir,
    headless=True,
    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ...",
)
```

---

### Problem: Deep logging shows "Early exit with N candidates"

**Symptom:** Not a problem, expected behavior

**Explanation:** DOM search found 20+ matching candidates and stopped searching to save time.

**Action:** None required. This is a performance optimization.

**Disable (if needed):** Remove early exit logic in `url_resolver.py:304-307` (not recommended).

---

## Testing Recommendations

### Unit Tests

**URLResolutionCache:**
- Cache hit/miss behavior
- TTL expiration
- LRU eviction (add 150 entries, verify oldest evicted)
- Proactive pruning on `put()`

**URLResolver (with mocked Playwright):**
- `_infer_initial_url()` logic for various queries
- `_rank_candidates()` scoring algorithm
- Domain mapping application
- Cache integration

**FallbackChain (with mocked URLResolver):**
- Direct resolution success
- Search fallback triggered on resolution failure
- Homepage fallback triggered on search failure
- All fallbacks failed scenario
- Config toggles (`enable_search_fallback`, etc.)

### Integration Tests

**WebExecutor (with real Playwright):**
- Open YouTube and verify URL resolution
- Test search fallback with unknown domain
- Test homepage fallback with domain-only query
- Verify legacy mode (direct navigation)
- Test form fill with config enabled/disabled

**End-to-End:**
- Full gesture → command → resolution → browser opening workflow
- Cache effectiveness across repeated queries
- Error handling and screenshot capture

### Performance Tests

**Browser Reuse:**
- Execute 10 consecutive resolutions
- Verify only 1 page created (check DevTools)
- Measure latency decrease after first resolution

**Cache Effectiveness:**
- Resolve same query twice within 15 minutes
- Verify second resolution is instant (<10ms)

**Warm-up Mechanism:**
- Fresh start, trigger first resolution
- Verify no 1-3s browser launch delay

**DOM Search Efficiency:**
- Test on high-link-count page (Reddit homepage)
- Verify logs show "Processing 100 of N links"
- Verify resolution completes in <800ms

### Regression Tests

- All existing web workflows (WhatsApp, etc.) still work
- URL resolution produces same results as before optimization
- Fallback chain tries same sequence
- ExecutionResult metadata correctly propagated

## API Reference

### URLResolutionResult

```python
@dataclass
class URLResolutionResult:
    status: str              # "ok" | "failed" | "timeout"
    resolved_url: str | None
    search_query: str
    candidates_found: int
    selected_reason: str | None  # "text_match" | "position" | "aria_label"
    elapsed_ms: int
    error_message: str | None = None
```

### FallbackResult

```python
@dataclass
class FallbackResult:
    status: str                          # "ok" | "all_failed"
    final_url: str | None
    fallback_used: str                   # "resolution" | "search" | "homepage" | "none"
    attempts_made: list[str]
    resolution_details: URLResolutionResult | None
    elapsed_ms: int
    error_message: str | None = None
```

### LinkCandidate

```python
@dataclass
class LinkCandidate:
    url: str
    link_text: str
    position_score: float        # 0.0-1.0, higher = more prominent
    aria_label: str | None = None
    selector: str | None = None
```

### SubjectGroup

```python
@dataclass
class SubjectGroup:
    subject_name: str            # "YouTube", "Gmail", "Spotify"
    subject_type: str            # "url" | "app" | "file" | "unknown"
    steps: list[dict]            # Steps associated with this subject
    start_index: int             # Original step index (preserves execution order)
```

## File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `url_resolver.py` | 429 | Headless browser URL resolution with DOM search |
| `fallback_chain.py` | 250 | Three-tier fallback orchestration |
| `url_resolution_cache.py` | 106 | In-memory cache with TTL and LRU eviction |
| `web_constants.py` | 22 | Shared domain mappings and scoring weights |
| `web_executor.py` | 387 | Main web intent executor with integration |
| `subject_extractor.py` | 213 | Multi-subject command grouping |

## Metrics Dashboard (Future)

Recommended metrics to track in production:

```python
{
  "cache_hit_rate": 0.42,           # 42% of queries hit cache
  "avg_resolution_ms": 450,          # Average resolution time (excluding cache hits)
  "fallback_distribution": {
    "resolution": 0.65,              # 65% succeed with direct resolution
    "search": 0.25,                  # 25% use search fallback
    "homepage": 0.08,                # 8% use homepage fallback
    "failed": 0.02                   # 2% fail all attempts
  },
  "dom_search_avg_ms": 180,          # Average DOM search time
  "cache_size": 87,                  # Current cache entries
  "cache_evictions": 15,             # Total LRU evictions
  "browser_contexts": 2              # Active Playwright contexts
}
```

## Future Enhancements

**Planned (from HANDOFF.md):**
1. Site-specific adapters (YouTube deep links, Gmail inbox navigation)
2. Vision-based link detection when DOM search fails
3. Parallel subject execution (execute independent subjects concurrently)
4. Redis cache for multi-instance deployments
5. Configurable fallback order (user-defined priority)
6. Cross-platform URL opening (Windows `start`, Linux `xdg-open`)
7. Browser permission API integration for `web_request_permission`
8. LLM integration for subject extraction (semantic analysis)

**Not Planned (Low Priority):**
- Async refactor (minimal immediate benefit)
- Batch link text extraction (minor optimization)
- Parallel fallback chain (high risk, moderate benefit)

## Additional Resources

- **Security Audit:** See `security_notes.md` for detailed vulnerability analysis
- **Architecture Design:** See `HANDOFF.md` for implementation history
- **Performance Analysis:** See HANDOFF.md "Performance Optimization Summary"
- **Code Quality:** See HANDOFF.md "Refactoring Summary"

## Support

For issues or questions:
1. Enable deep logging: `"log_level": "DEEP"` in `app_settings.json`
2. Check troubleshooting section above
3. Review security_notes.md for security-related issues
4. Check HANDOFF.md for implementation details and known limitations
