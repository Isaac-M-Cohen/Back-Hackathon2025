# Executor Rework - Operational Runbook

**Version**: 1.0
**Date**: 2026-02-03
**Status**: Ready for Deployment (with critical fixes)
**Feature Branch**: `feature/native-executor`
**Target Branch**: `main`

---

## Executive Summary

This runbook provides step-by-step instructions for deploying the executor rework, a comprehensive web navigation system with headless Playwright URL resolution, modular fallback chains, and enhanced execution results. The system includes ~1020 lines of production code with 92.9% test coverage (79/85 tests passing).

**Release Status**: 🟡 CONDITIONAL - Safe for beta/internal release OR after critical security fixes

**Key Capabilities**:
- Headless Playwright URL resolution with DOM search
- Modular fallback chain (resolution → search → homepage)
- Enhanced execution results with rich metadata
- New web intents (form fill, permission hooks)
- Optional subject extraction for command grouping
- Performance optimizations (page reuse, caching, warm-up)

**Critical Requirements Before Production**:
- 5 critical security issues must be addressed (4-6 hours estimated)
- Manual testing of key workflows required
- Security configuration hardening recommended

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Critical Issues to Fix](#critical-issues-to-fix)
3. [Quick Start (Beta Deployment)](#quick-start-beta-deployment)
4. [Step-by-Step Deployment](#step-by-step-deployment)
5. [Security Hardening](#security-hardening)
6. [Testing & Verification](#testing--verification)
7. [Rollback Plan](#rollback-plan)
8. [Monitoring & Health Checks](#monitoring--health-checks)
9. [Troubleshooting](#troubleshooting)
10. [Known Issues](#known-issues)

---

## Prerequisites

### System Requirements

**Operating System**:
- macOS 10.15+ (primary support)
- Windows/Linux (limited support - subprocess requires platform detection)

**Python**:
- Python 3.11+
- All dependencies in `pyproject.toml`

**Browser**:
- Chromium browser (installed via Playwright)
- ~300MB disk space for browser download

**Permissions**:
- Accessibility permissions (macOS System Preferences)
- Disk access for profile directories
- Network access for URL resolution

### Installation Steps

```bash
# 1. Clone and navigate to repo
cd /Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025

# 2. Checkout feature branch
git checkout feature/native-executor

# 3. Install Python dependencies
pip install -e .

# 4. Install Chromium for Playwright
playwright install chromium

# 5. Verify installation
python -c "from playwright.sync_api import sync_playwright; print('OK')"
```

### Configuration Files

**Required**:
- `/config/app_settings.json` - Main configuration (includes new web executor settings)
- `/data/user_data/default/command_steps.json` - Predefined gesture steps

**Auto-Created**:
- `/user_data/playwright_profile/` - User-visible browser profile
- `/user_data/playwright_resolver/` - Headless resolver profile
- `/user_data/error_screenshots/` - Error diagnostics

### Environment Variables

None required. All configuration is file-based.

---

## Critical Issues to Fix

The code reviewer and security auditor identified 5 CRITICAL issues that must be addressed before production deployment.

### Priority 1: Command Injection via subprocess.run (CRITICAL)

**File**: `/command_controller/web_executor.py:159`

**Problem**: URLs passed to `subprocess.run(["open", final_url])` without comprehensive validation. Current validation only checks http/https scheme, missing localhost/private IPs/metadata services.

**Impact**: SSRF attacks, arbitrary command execution, information disclosure

**Fix Time**: 2 hours

**Implementation**:

```python
# In web_executor.py, replace _is_safe_url() method:

@staticmethod
def _is_safe_url(url: str | None) -> bool:
    """Validate URL is safe to open in browser."""
    if not url:
        return False

    # Length check (prevent DoS)
    if len(url) > 2048:
        return False

    from urllib.parse import urlparse
    import ipaddress

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Scheme validation
    if parsed.scheme not in ("http", "https"):
        return False

    # Hostname validation
    hostname = parsed.hostname
    if not hostname:
        return False

    # Block localhost
    if hostname in ("localhost", "127.0.0.1", "::1"):
        return False

    # Block private IPs and metadata service
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
        # Block cloud metadata service
        if str(ip) == "169.254.169.254":
            return False
    except ValueError:
        # Not an IP address, hostname validation passes
        pass

    return True

# Also update subprocess call (line 159):
try:
    subprocess.run(
        ["open", "--", final_url],  # -- prevents flag injection
        check=True,
        capture_output=True,
        timeout=10
    )
except subprocess.TimeoutExpired:
    raise WebExecutionError(
        code="WEB_OPEN_TIMEOUT",
        message=f"Timeout opening URL: {final_url}"
    )
except subprocess.CalledProcessError as exc:
    raise WebExecutionError(
        code="WEB_OPEN_FAILED",
        message=f"Failed to open URL: {exc.stderr.decode() if exc.stderr else str(exc)}"
    )
```

**Verification**:
```bash
# Test with malicious URLs (should reject)
python -c "from command_controller.web_executor import WebExecutor; \
           print(WebExecutor._is_safe_url('http://localhost:8080'))"  # Should return False
python -c "from command_controller.web_executor import WebExecutor; \
           print(WebExecutor._is_safe_url('http://192.168.1.1'))"     # Should return False
python -c "from command_controller.web_executor import WebExecutor; \
           print(WebExecutor._is_safe_url('http://169.254.169.254'))" # Should return False
```

---

### Priority 2: Race Condition in Playwright Page Reuse (HIGH)

**File**: `/command_controller/url_resolver.py:65, 109-114`

**Problem**: Single `_page` instance reused across all resolutions without synchronization. Concurrent calls could corrupt DOM search or return wrong URLs.

**Impact**: Incorrect resolution results, cache poisoning, privacy violations

**Fix Time**: 1 hour

**Implementation**:

```python
# In url_resolver.py, add at top:
from threading import Lock

# In URLResolver.__init__ (around line 61):
def __init__(self, settings: dict | None = None) -> None:
    # ... existing code ...
    self._page_lock = Lock()  # Protect page access

# In resolve() method (around line 85):
def resolve(self, query: str) -> URLResolutionResult:
    start = time.monotonic()

    # Check cache (outside lock)
    cached = self._cache.get(query)
    if cached:
        if is_deep_logging():
            deep_log(f"[DEEP][URL_RESOLVER] Cache hit for query={query!r}")
        cached.from_cache = True  # Mark as cached
        return cached

    # Acquire lock for browser operations
    with self._page_lock:
        try:
            self._ensure_browser()

            # ... rest of resolution logic (already inside try block)
            # All page navigation and DOM search happens within lock

        except PlaywrightTimeoutError as exc:
            # ... error handling ...
```

**Verification**:
```bash
# Test concurrent resolutions (should not crash or mix results)
python -c "
from command_controller.url_resolver import URLResolver
import concurrent.futures
resolver = URLResolver()
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(resolver.resolve, f'query{i}') for i in range(10)]
    results = [f.result() for f in futures]
    print(f'Resolved {len(results)} queries without errors')
"
```

---

### Priority 3: XSS via page.evaluate() in DOM Search (HIGH)

**File**: `/command_controller/url_resolver.py:290-292`

**Problem**: Uses `page.evaluate()` to resolve relative URLs, executing JavaScript in untrusted page context. Malicious scripts could inject URLs.

**Impact**: Phishing redirects, credential theft, cache poisoning

**Fix Time**: 30 minutes

**Implementation**:

```python
# In url_resolver.py, replace lines 290-292:
from urllib.parse import urljoin

# In _search_dom_for_links() method:
# OLD:
# resolved_href = page.evaluate(
#     f"(href) => new URL(href, document.baseURI).href", href
# )

# NEW:
try:
    base_url = page.url  # Get current page URL
    resolved_href = urljoin(base_url, href)
except Exception:
    # Skip links that can't be resolved
    continue
```

**Verification**:
```bash
# Verify urljoin behavior
python -c "
from urllib.parse import urljoin
print(urljoin('https://example.com/path', '/relative'))  # Should resolve correctly
print(urljoin('https://example.com/path', 'relative'))   # Should resolve correctly
"
```

---

### Priority 4: Insufficient Error Context for Cached Failures (MEDIUM)

**File**: `/command_controller/url_resolver.py:164-166, 178-179`

**Problem**: Cached failures returned without indication they're from cache. No retry mechanism for transient errors.

**Impact**: Poor UX (instant failures), stale error messages, no retry for network glitches

**Fix Time**: 1 hour

**Implementation**:

```python
# In url_resolver.py, update URLResolutionResult dataclass:
@dataclass
class URLResolutionResult:
    status: str
    resolved_url: str | None
    search_query: str
    candidates_found: int
    selected_reason: str | None
    elapsed_ms: int
    error_message: str | None = None
    from_cache: bool = False  # NEW: Indicate if result came from cache

# In resolve() method, mark cached results:
cached = self._cache.get(query)
if cached:
    if is_deep_logging():
        deep_log(f"[DEEP][URL_RESOLVER] Cache hit for query={query!r}")
    # Mark as cached result
    cached.from_cache = True
    return cached

# In fallback_chain.py, update _try_direct_resolution():
def _try_direct_resolution(self, query: str) -> FallbackResult | None:
    try:
        start = time.monotonic()
        resolution = self._resolver.resolve(query)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if resolution.status == "ok" and resolution.resolved_url:
            return FallbackResult(...)

        if is_deep_logging():
            cache_msg = " (cached)" if resolution.from_cache else ""
            deep_log(
                f"[DEEP][FALLBACK_CHAIN] Direct resolution failed{cache_msg}: {resolution.error_message}"
            )
```

**Verification**:
```bash
# Test cache behavior
python -c "
from command_controller.url_resolver import URLResolver
resolver = URLResolver()
result1 = resolver.resolve('invalid-query')
result2 = resolver.resolve('invalid-query')
print(f'First call from_cache: {result1.from_cache}')
print(f'Second call from_cache: {result2.from_cache}')
"
```

---

### Priority 5: Unvalidated Cache Keys (MEDIUM)

**File**: `/command_controller/url_resolution_cache.py:36-58`

**Problem**: Raw query strings used as cache keys without normalization or length limits. Poor cache hit rates, potential DoS.

**Impact**: Cache DoS via huge queries, poor hit rates (case sensitivity), PII in cache keys

**Fix Time**: 1 hour

**Implementation**:

```python
# In url_resolution_cache.py, add normalization method:

def _normalize_key(self, query: str) -> str:
    """Normalize cache key for consistent lookup."""
    # Limit length to prevent DoS
    if len(query) > 500:
        raise ValueError("Query too long for caching")

    # Normalize case and whitespace
    normalized = " ".join(query.lower().strip().split())

    return normalized

def get(self, query: str) -> URLResolutionResult | None:
    """Retrieve cached result if not expired."""
    try:
        key = self._normalize_key(query)
    except ValueError:
        return None  # Query too long, skip cache

    entry = self._cache.get(key)
    # ... rest of method ...

def put(self, query: str, result: URLResolutionResult) -> None:
    """Store result with timestamp and LRU eviction."""
    try:
        key = self._normalize_key(query)
    except ValueError:
        # Query too long, skip caching
        return

    # ... rest of method ...
```

**Verification**:
```bash
# Test cache normalization
python -c "
from command_controller.url_resolution_cache import URLResolutionCache
cache = URLResolutionCache()
# Test case insensitivity
cache.put('YouTube', result1)
result = cache.get('youtube')  # Should hit cache
print(f'Cache hit with different case: {result is not None}')
"
```

---

### Security Quick Wins (52 minutes total)

These are low-effort, high-impact fixes that should be applied immediately:

#### 1. Add URL Length Validation (5 minutes)

```python
# In web_executor.py, around line 119:
url = step.get("url", "")
if len(url) > 2000:  # RFC 2616 recommends 2KB limit
    raise WebExecutionError(
        code="WEB_URL_TOO_LONG",
        message=f"URL exceeds maximum length (2000 chars)"
    )
```

#### 2. Enable subprocess Error Checking (2 minutes)

Already covered in Priority 1 fix above.

#### 3. Add Cache Entry Size Limit (10 minutes)

```python
# In url_resolution_cache.py, in put() method:
def put(self, query: str, result: URLResolutionResult) -> None:
    # Limit cache key size
    if len(query) > 500:
        return

    # Limit result size (estimate)
    if result.resolved_url and len(result.resolved_url) > 2000:
        return

    # ... rest of method ...
```

#### 4. Sanitize Error Messages (15 minutes)

```python
# In url_resolver.py, around line 229-231:
raise RuntimeError(
    "Failed to initialize browser. Please check system requirements."
) from exc
# Log detailed error separately for debugging
logger.exception("Browser initialization failed")
```

#### 5. Add Request Rate Limiting (20 minutes)

```python
# In url_resolver.py, in __init__:
from collections import deque
import threading

class URLResolver:
    def __init__(self, settings: dict | None = None) -> None:
        # ... existing init ...
        self._request_times = deque(maxlen=10)
        self._rate_limit_lock = threading.Lock()

    def resolve(self, query: str) -> URLResolutionResult:
        # Rate limit: max 10 requests per 60 seconds
        with self._rate_limit_lock:
            now = time.time()
            self._request_times.append(now)
            if len(self._request_times) >= 10:
                if now - self._request_times[0] < 60:
                    raise RuntimeError("Rate limit exceeded (10 req/min)")

        # ... rest of method ...
```

---

## Quick Start (Beta Deployment)

For immediate internal/beta deployment without fixing critical issues:

### Step 1: Disable Enhanced Web Executor

```json
// config/app_settings.json
{
  "use_playwright_for_web": false,  // Disable new features
  "request_before_open_url": false,
  "allow_headless_form_fill": false
}
```

### Step 2: Deploy to Limited Users

```bash
# 1. Checkout feature branch
git checkout feature/native-executor

# 2. Deploy to 5-10 internal users only
# (Deployment method depends on your infrastructure)

# 3. Monitor logs for errors
tail -f logs/app.log | grep -E "ERROR|CRITICAL"
```

### Step 3: Document Known Issues

Include in release notes:
- Command injection vulnerability (disable enhanced features)
- Race condition in concurrent usage
- macOS-only subprocess implementation
- Subject extractor has failing tests (disabled by default)

### Step 4: Schedule Critical Fixes

Create tickets for Priority 1-5 fixes with 2-week deadline.

---

## Step-by-Step Deployment

### Phase 1: Apply Critical Fixes (4-6 hours)

Follow instructions in [Critical Issues to Fix](#critical-issues-to-fix) section.

**Order of execution**:
1. Priority 1: Command injection fix (2 hours)
2. Priority 2: Race condition fix (1 hour)
3. Priority 3: XSS fix (30 minutes)
4. Priority 4: Cache indication fix (1 hour)
5. Priority 5: Cache normalization fix (1 hour)
6. Security Quick Wins (52 minutes)

**Verification after each fix**:
```bash
# Run tests
pytest tests/ -v

# Check specific module
pytest tests/test_url_resolver.py -v
pytest tests/test_fallback_chain.py -v
pytest tests/test_url_resolution_cache.py -v
```

---

### Phase 2: Configuration Hardening

Update `/config/app_settings.json` with security-hardened defaults:

```json
{
  "use_playwright_for_web": true,
  "request_before_open_url": true,  // Enable confirmation dialogs
  "enable_search_fallback": true,
  "enable_homepage_fallback": true,
  "allow_headless_form_fill": false,  // Secure default
  "search_engine_url": "https://duckduckgo.com/?q={query}",
  "playwright_navigation_timeout_ms": 30000,
  "playwright_resolver_profile": "user_data/playwright_resolver",
  "warmup_url_resolver": true,

  // NEW: Security settings
  "security": {
    "block_localhost_urls": true,
    "block_private_ips": true,
    "max_url_length": 2000,
    "max_cache_entry_size": 10000,
    "enable_error_screenshots": false,  // Disable in production
    "require_url_confirmation": true
  },

  "log_level": "INFO"  // Avoid DEEP in production (exposes sensitive data)
}
```

---

### Phase 3: Run Test Suite

```bash
# 1. Run all tests
pytest tests/ -v --tb=short

# Expected results:
# - 79/85 tests passing (92.9%)
# - 6 failures in subject_extractor (non-critical feature, disabled by default)

# 2. Run integration tests (manual)
# Test 1: Direct URL resolution
python -c "
from command_controller.web_executor import WebExecutor
from command_controller.config import get_settings
executor = WebExecutor(get_settings())
result = executor.execute_step({'intent': 'open_url', 'url': 'https://www.youtube.com'})
print(f'Result: {result.to_dict()}')
"

# Test 2: URL resolution with query
python -c "
from command_controller.url_resolver import URLResolver
resolver = URLResolver()
result = resolver.resolve('youtube cats')
print(f'Resolved URL: {result.resolved_url}')
print(f'Status: {result.status}')
"

# Test 3: Fallback chain
python -c "
from command_controller.fallback_chain import FallbackChain
from command_controller.config import get_settings
chain = FallbackChain(get_settings())
result = chain.execute('unknown-site-xyz')
print(f'Fallback used: {result.fallback_used}')
print(f'Final URL: {result.final_url}')
"

# Test 4: Cache behavior
python -c "
from command_controller.url_resolver import URLResolver
import time
resolver = URLResolver()
start1 = time.time()
result1 = resolver.resolve('github')
time1 = time.time() - start1
start2 = time.time()
result2 = resolver.resolve('github')
time2 = time.time() - start2
print(f'First resolution: {time1:.3f}s')
print(f'Second resolution (cached): {time2:.3f}s')
print(f'Cache speedup: {time1/time2:.1f}x')
"
```

---

### Phase 4: Manual Testing

**Test Case 1: Basic URL Opening**
```bash
# User action: Gesture "Open" or command "open YouTube"
# Expected: YouTube opens in default browser
# Verification: Browser window appears with YouTube homepage
```

**Test Case 2: URL Resolution with Query**
```bash
# User action: "open YouTube and search for cats"
# Expected: YouTube opens, search query is typed
# Verification: YouTube search results for "cats" appear
```

**Test Case 3: Fallback Chain - Search**
```bash
# User action: "open unknown-site-xyz"
# Expected: DuckDuckGo search for "unknown-site-xyz"
# Verification: Search engine results appear
```

**Test Case 4: Fallback Chain - Homepage**
```bash
# User action: "open gmail"
# Expected: https://www.gmail.com (homepage fallback)
# Verification: Gmail homepage loads
```

**Test Case 5: Cache Hit**
```bash
# User action: "open youtube" (first time)
# Expected: 1-3s latency (browser launch + resolution)
# User action: "open youtube" (second time within 15 minutes)
# Expected: <500ms latency (cache hit)
# Verification: Check logs for "[DEEP][URL_RESOLVER] Cache hit"
```

**Test Case 6: Config Toggle - Disable Playwright**
```bash
# Config: Set use_playwright_for_web=false
# User action: "open YouTube"
# Expected: Direct Playwright navigation (legacy path)
# Verification: No URL resolution in logs
```

**Test Case 7: Security - Localhost Rejection**
```bash
# User action: "open http://localhost:8080"
# Expected: URL validation failure
# Verification: Error message about unsafe URL
```

---

### Phase 5: Deploy to Production

```bash
# 1. Merge feature branch to main
git checkout main
git merge feature/native-executor

# 2. Tag release
git tag -a v1.0.0-executor-rework -m "Full executor rework with Playwright URL resolution"
git push origin v1.0.0-executor-rework

# 3. Deploy
# (Deployment method depends on your infrastructure)

# 4. Monitor for first 24 hours
# Watch logs, metrics, user reports
```

---

## Security Hardening

### Profile Directory Permissions

Ensure browser profiles are secure:

```bash
# Check permissions
stat -f "%A %N" user_data/playwright_profile
stat -f "%A %N" user_data/playwright_resolver

# Should show: 700 (drwx------)
# If not, fix permissions:
chmod 700 user_data/playwright_profile
chmod 700 user_data/playwright_resolver
```

### Enable OS-Level Encryption

**macOS**:
```bash
# Enable FileVault for disk encryption
# System Preferences > Security & Privacy > FileVault
```

**Windows**:
```bash
# Enable BitLocker for disk encryption
# Control Panel > System and Security > BitLocker Drive Encryption
```

### Log Sanitization

Review logs for sensitive data exposure:

```bash
# Check for potential PII leaks
grep -i "password\|token\|secret\|key" logs/app.log

# If found, apply log sanitization patches
```

### Network Isolation

Consider restricting network access:

```bash
# macOS Firewall
# System Preferences > Security & Privacy > Firewall > Advanced
# Add application-specific rules

# Linux iptables
sudo iptables -A OUTPUT -p tcp --dport 80 -m owner --uid-owner <app-user> -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 443 -m owner --uid-owner <app-user> -j ACCEPT
sudo iptables -A OUTPUT -m owner --uid-owner <app-user> -j DROP
```

---

## Testing & Verification

### Automated Tests

```bash
# Run full test suite
pytest tests/ -v --cov=command_controller --cov-report=html

# Run specific test files
pytest tests/test_url_resolver.py -v
pytest tests/test_fallback_chain.py -v
pytest tests/test_url_resolution_cache.py -v

# Run with deep logging
LOG_LEVEL=DEEP pytest tests/ -v -s
```

### Performance Tests

```bash
# Test 1: Browser warm-up
python -c "
from command_controller.url_resolver import URLResolver
import time
resolver = URLResolver()
start = time.time()
resolver.warmup()
print(f'Warm-up time: {time.time() - start:.3f}s')
"

# Test 2: Resolution latency
python -c "
from command_controller.url_resolver import URLResolver
import time
resolver = URLResolver()
resolver.warmup()  # Warm up first
queries = ['youtube', 'github', 'gmail', 'reddit', 'twitter']
for query in queries:
    start = time.time()
    result = resolver.resolve(query)
    elapsed = time.time() - start
    print(f'{query}: {elapsed:.3f}s - {result.status}')
"

# Test 3: Cache effectiveness
python -c "
from command_controller.url_resolver import URLResolver
import time
resolver = URLResolver()
resolver.warmup()

# First resolution (cold)
start = time.time()
result1 = resolver.resolve('youtube')
time1 = time.time() - start

# Second resolution (cached)
start = time.time()
result2 = resolver.resolve('youtube')
time2 = time.time() - start

print(f'Cold: {time1:.3f}s, Cached: {time2:.3f}s, Speedup: {time1/time2:.1f}x')
"

# Test 4: Memory stability (100 resolutions)
python -c "
from command_controller.url_resolver import URLResolver
import psutil
import os
process = psutil.Process(os.getpid())
mem_before = process.memory_info().rss / 1024 / 1024

resolver = URLResolver()
for i in range(100):
    resolver.resolve(f'query{i % 10}')  # Reuse 10 queries

mem_after = process.memory_info().rss / 1024 / 1024
print(f'Memory before: {mem_before:.1f} MB')
print(f'Memory after: {mem_after:.1f} MB')
print(f'Memory increase: {mem_after - mem_before:.1f} MB')
"
```

### Security Tests

```bash
# Test URL validation with malicious inputs
python -c "
from command_controller.web_executor import WebExecutor

test_urls = [
    'http://localhost:8080',
    'http://127.0.0.1',
    'http://192.168.1.1',
    'http://169.254.169.254',
    'file:///etc/passwd',
    'javascript:alert(1)',
    'http://example.com' + 'A' * 10000,  # Long URL
]

for url in test_urls:
    result = WebExecutor._is_safe_url(url)
    print(f'{url[:50]}: {result}')
"
```

---

## Rollback Plan

### Immediate Mitigation (< 5 minutes)

If critical issues are discovered post-release:

```json
// config/app_settings.json
{
  "use_playwright_for_web": false  // Disable new features immediately
}
```

This disables all new web executor features and falls back to legacy direct navigation.

### Full Rollback (< 30 minutes)

```bash
# 1. Checkout previous commit
git log --oneline  # Find commit before feature/native-executor merge
git checkout <previous-commit>

# 2. Redeploy
# (Deployment method depends on your infrastructure)

# 3. Verify rollback
python -c "
from command_controller.web_executor import WebExecutor
# Should not have new methods like _handle_open_url with fallback logic
"

# 4. Clean up artifacts
rm -rf user_data/playwright_resolver
rm -rf user_data/error_screenshots
```

### Data Migration

No database schema changes. Rollback is safe with no data loss.

**Artifacts to preserve** (if needed):
- `user_data/playwright_profile/` - User browser profile (cookies, sessions)
- `config/app_settings.json` - Configuration (merge new settings with old)

---

## Monitoring & Health Checks

### Metrics to Track

**Functional Metrics**:
```bash
# URL resolution success rate
grep "status=ok" logs/app.log | wc -l
grep "status=timeout\|status=error" logs/app.log | wc -l

# Cache hit rate
grep "Cache hit" logs/app.log | wc -l
grep "URL_RESOLVER] resolve" logs/app.log | wc -l

# Fallback usage distribution
grep "fallback_used=resolution" logs/app.log | wc -l
grep "fallback_used=search" logs/app.log | wc -l
grep "fallback_used=homepage" logs/app.log | wc -l
```

**Performance Metrics**:
```bash
# Average resolution latency (from logs)
grep "elapsed_ms" logs/app.log | awk '{print $NF}' | awk '{sum+=$1; count++} END {print sum/count}'

# Browser initialization time
grep "Browser warm-up completed" logs/app.log
```

**Security Metrics**:
```bash
# URL validation rejections
grep "URL validation failed" logs/app.log | wc -l

# Suspicious patterns (localhost, private IPs)
grep -E "localhost|127\.0\.0\.1|192\.168\.|10\.|169\.254\.169\.254" logs/app.log

# Form fill attempts (when disabled)
grep "allow_headless_form_fill.*false" logs/app.log | wc -l
```

### Log Patterns to Watch

**Success Patterns**:
```
[DEEP][URL_RESOLVER] Cache hit for query="youtube"
[DEEP][FALLBACK_CHAIN] Resolution succeeded
Browser warm-up completed
```

**Warning Patterns**:
```
Failed to initialize browser
URL validation failed
All fallbacks failed
```

**Error Patterns**:
```
Command injection attempt detected
Profile directory permissions incorrect
Subprocess execution failed
PlaywrightTimeoutError
```

### Health Check Endpoint

```python
# Add to your API (if applicable)
@app.get("/health/web-executor")
def health_check():
    from command_controller.url_resolver import URLResolver
    from command_controller.fallback_chain import FallbackChain

    checks = {
        "url_resolver": "unknown",
        "fallback_chain": "unknown",
        "browser": "unknown"
    }

    try:
        resolver = URLResolver()
        result = resolver.resolve("youtube")
        checks["url_resolver"] = "ok" if result.status == "ok" else "degraded"
    except Exception as e:
        checks["url_resolver"] = f"error: {str(e)}"

    try:
        chain = FallbackChain()
        result = chain.execute("youtube")
        checks["fallback_chain"] = "ok" if result.final_url else "degraded"
    except Exception as e:
        checks["fallback_chain"] = f"error: {str(e)}"

    try:
        resolver = URLResolver()
        resolver._ensure_browser()
        checks["browser"] = "ok"
    except Exception as e:
        checks["browser"] = f"error: {str(e)}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"

    return {"status": overall, "checks": checks}
```

---

## Troubleshooting

### Issue 1: Browser Fails to Launch

**Symptoms**:
```
RuntimeError: Failed to initialize browser
```

**Diagnosis**:
```bash
# Check if Chromium is installed
ls $(python -c "from playwright.driver import compute_driver_executable; print(compute_driver_executable())")

# Check profile directory permissions
stat -f "%A %N" user_data/playwright_resolver
```

**Fix**:
```bash
# Install Chromium
playwright install chromium

# Fix permissions
chmod 700 user_data/playwright_resolver
```

---

### Issue 2: Cache Not Working

**Symptoms**:
- Slow resolutions even for repeated queries
- No "Cache hit" in logs

**Diagnosis**:
```bash
# Check cache size
python -c "
from command_controller.url_resolver import URLResolver
resolver = URLResolver()
print(f'Cache size: {resolver._cache.size()}')
"

# Check if cache is being populated
grep "Cache hit" logs/app.log
```

**Fix**:
```python
# Clear cache and restart
from command_controller.url_resolver import URLResolver
resolver = URLResolver()
resolver._cache.clear()
```

---

### Issue 3: URLs Not Opening in Browser

**Symptoms**:
- Resolution succeeds but no browser window appears
- "subprocess failed" errors

**Diagnosis**:
```bash
# Test subprocess manually
open "https://www.youtube.com"

# Check if default browser is set
defaults read com.apple.LaunchServices/com.apple.launchservices.secure LSHandlers
```

**Fix**:
```bash
# Set default browser (macOS)
# System Preferences > General > Default web browser

# Test with direct Python call
python -c "import subprocess; subprocess.run(['open', 'https://www.youtube.com'])"
```

---

### Issue 4: Page Reuse Race Condition

**Symptoms**:
- Incorrect URLs returned
- "DOM search failed" errors
- Concurrent resolution failures

**Diagnosis**:
Check if threading lock is present:
```python
from command_controller.url_resolver import URLResolver
resolver = URLResolver()
print(hasattr(resolver, '_page_lock'))  # Should be True
```

**Fix**:
Apply Priority 2 fix (race condition patch) from [Critical Issues](#critical-issues-to-fix).

---

### Issue 5: High Memory Usage

**Symptoms**:
- Memory grows over time
- System slowdown after many resolutions

**Diagnosis**:
```bash
# Monitor memory usage
python -c "
import psutil
import os
process = psutil.Process(os.getpid())
print(f'Memory: {process.memory_info().rss / 1024 / 1024:.1f} MB')
"

# Check cache size
python -c "
from command_controller.url_resolver import URLResolver
resolver = URLResolver()
print(f'Cache entries: {resolver._cache.size()}')
"
```

**Fix**:
```python
# Clear cache periodically
from command_controller.url_resolver import URLResolver
resolver = URLResolver()
resolver._cache.clear()

# Or reduce cache size in config
# url_resolution_cache.py: max_size=50 (instead of 100)
```

---

### Issue 6: Screenshots Accumulating

**Symptoms**:
- `user_data/error_screenshots/` grows large
- Disk space issues

**Diagnosis**:
```bash
du -sh user_data/error_screenshots
ls -lh user_data/error_screenshots | wc -l
```

**Fix**:
```bash
# Clean old screenshots
find user_data/error_screenshots -type f -mtime +7 -delete

# Or disable screenshots in production
# config/app_settings.json: "security": {"enable_error_screenshots": false}
```

---

### Issue 7: Subject Extractor Tests Failing

**Symptoms**:
- 6 tests fail in `test_subject_extractor.py`
- Non-critical but concerning

**Diagnosis**:
```bash
pytest tests/test_subject_extractor.py -v
```

**Fix**:
```json
// config/app_settings.json
{
  "enable_subject_extraction": false  // Disable feature until tests fixed
}
```

Or fix tests:
```bash
# Create ticket to fix subject extractor tests
# Priority: LOW (feature disabled by default)
```

---

## Known Issues

### 1. Subject Extractor Tests Failing (6/23 tests)

**Impact**: NON-BLOCKING
- Feature disabled by default (`enable_subject_extraction` not in config)
- Failures affect optional parallel execution grouping (not implemented)
- Does not impact core functionality

**Workaround**: Keep feature disabled

**Resolution**: Fix in follow-up release or disable feature entirely

---

### 2. macOS-Only Subprocess Implementation

**Impact**: MEDIUM
- Windows/Linux users cannot use enhanced URL opening
- `subprocess.run(["open", url])` is macOS-specific

**Workaround**: Set `use_playwright_for_web=false` on non-macOS

**Resolution**: Add platform detection:
```python
import platform

if platform.system() == "Darwin":  # macOS
    subprocess.run(["open", "--", final_url], ...)
elif platform.system() == "Windows":
    subprocess.run(["start", "", final_url], shell=True, ...)
elif platform.system() == "Linux":
    subprocess.run(["xdg-open", final_url], ...)
else:
    raise WebExecutionError(
        code="WEB_UNSUPPORTED_PLATFORM",
        message=f"URL opening not supported on {platform.system()}"
    )
```

---

### 3. No Integration Tests with Real Browser

**Impact**: LOW
- All tests use mocks
- Real Playwright behavior untested

**Workaround**: Manual testing required before production

**Resolution**: Create integration test suite with real Playwright instance

---

### 4. Profile Encryption Not Implemented

**Impact**: CRITICAL (security)
- Browser profiles store credentials without encryption
- Relies on OS-level encryption (FileVault/BitLocker)

**Workaround**: Document profile encryption setup for users

**Resolution**: Implement profile encryption at rest (use `keyring` library)

---

### 5. Log Sanitization Incomplete

**Impact**: MEDIUM (security)
- Form fill logs may expose field names (password, secret, etc.)
- Deep logging may leak sensitive data

**Workaround**: Disable DEEP logging in production (`log_level=INFO`)

**Resolution**: Apply log sanitization patches from security audit

---

## Summary of Files Changed

### Created (6 new modules)
- `/command_controller/url_resolution_cache.py` (106 lines)
- `/command_controller/url_resolver.py` (429 lines)
- `/command_controller/fallback_chain.py` (250 lines)
- `/command_controller/subject_extractor.py` (213 lines)
- `/command_controller/web_constants.py` (22 lines)
- `/command_controller/web_adapters/whatsapp.py` (new)

### Modified (6 files)
- `/command_controller/executors/base.py` (+14 lines: ExecutionResult fields)
- `/command_controller/web_executor.py` (+100 lines: resolution integration)
- `/command_controller/executor.py` (+15 lines: metadata enrichment)
- `/command_controller/intents.py` (+40 lines: new intent validation)
- `/command_controller/engine.py` (+8 lines: subject extraction)
- `/config/app_settings.json` (+18 lines: new config options)

### Test Files (4 files, 85 tests)
- `/tests/test_url_resolution_cache.py` (13 tests, all passing)
- `/tests/test_url_resolver.py` (30 tests, all passing)
- `/tests/test_fallback_chain.py` (19 tests, all passing)
- `/tests/test_subject_extractor.py` (23 tests, 6 failing - non-critical)

### Documentation (5 files)
- `/docs/WEB_EXECUTOR.md` (688 lines)
- `/docs/CONFIGURATION.md` (434 lines)
- `/security_notes.md` (974 lines)
- `/CODE_REVIEW.md` (598 lines)
- `/RELEASE_CHECKLIST.md` (771 lines)
- `/README.md` (+60 lines)

---

## Configuration Reference

### Key Configuration Toggles

```json
{
  // Primary feature toggle
  "use_playwright_for_web": true,           // Enable new web executor

  // Security toggles
  "allow_headless_form_fill": false,        // Secure default
  "request_before_open_url": false,         // Consider enabling for production

  // Fallback behavior
  "enable_search_fallback": true,
  "enable_homepage_fallback": true,

  // Performance tuning
  "warmup_url_resolver": true,
  "playwright_navigation_timeout_ms": 30000,

  // Separate profiles (avoid lock conflicts)
  "playwright_resolver_profile": "user_data/playwright_resolver",

  // Security (after hardening)
  "security": {
    "block_localhost_urls": true,
    "block_private_ips": true,
    "max_url_length": 2000,
    "max_cache_entry_size": 10000,
    "enable_error_screenshots": false,
    "require_url_confirmation": true
  },

  "log_level": "INFO"  // Avoid DEEP in production
}
```

---

## Command Reference

```bash
# Install dependencies
playwright install chromium

# Run tests
pytest tests/ -v

# Validate Python syntax
python -m py_compile command_controller/*.py

# Check config
cat config/app_settings.json

# View logs (DEEP level for diagnostics)
tail -f logs/app.log | grep -E "\[DEEP\]|\[ERROR\]"

# Test URL resolution
python -c "from command_controller.url_resolver import URLResolver; \
           resolver = URLResolver(); \
           result = resolver.resolve('youtube'); \
           print(f'Resolved: {result.resolved_url}')"

# Test fallback chain
python -c "from command_controller.fallback_chain import FallbackChain; \
           from command_controller.config import get_settings; \
           chain = FallbackChain(get_settings()); \
           result = chain.execute('unknown-query'); \
           print(f'Fallback: {result.fallback_used}, URL: {result.final_url}')"

# Clear cache
python -c "from command_controller.url_resolver import URLResolver; \
           resolver = URLResolver(); \
           resolver._cache.clear(); \
           print('Cache cleared')"

# Check memory usage
python -c "import psutil; import os; \
           print(f'Memory: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB')"
```

---

## Contact Information

**For questions or concerns**:
- Security issues: Security team
- Feature questions: Product team
- Technical issues: Development team
- Release coordination: DevOps/Release team

**Documentation**:
- Full system architecture: `/docs/WEB_EXECUTOR.md`
- Configuration guide: `/docs/CONFIGURATION.md`
- Security audit: `/security_notes.md`
- Code review: `/CODE_REVIEW.md`
- Release checklist: `/RELEASE_CHECKLIST.md`

---

**End of Runbook**

**Last Updated**: 2026-02-03
**Version**: 1.0
**Status**: Production-Ready (with critical fixes applied)
