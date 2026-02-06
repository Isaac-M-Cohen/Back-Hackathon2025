# Web Executor Quick Start

## 3-Minute Setup

### 1. Install Chromium

```bash
playwright install chromium
```

### 2. Enable Enhanced Mode

Edit `config/app_settings.json`:

```json
{
  "use_playwright_for_web": true
}
```

### 3. Test URL Resolution

```bash
python -c "
from command_controller.url_resolver import URLResolver
resolver = URLResolver()
result = resolver.resolve('youtube cats')
print(f'✓ Status: {result.status}')
print(f'✓ URL: {result.resolved_url}')
resolver.shutdown()
"
```

Expected:
```
✓ Status: ok
✓ URL: https://www.youtube.com/results?search_query=cats
```

## Common Tasks

### Execute a URL Command

```python
from command_controller.web_executor import WebExecutor

executor = WebExecutor()
step = {"intent": "open_url", "url": "youtube cats"}
executor.execute_step(step)
executor.shutdown()
```

### Customize Fallback Behavior

```json
{
  "enable_search_fallback": true,      // Try search if resolution fails
  "enable_homepage_fallback": true,    // Try homepage if search fails
  "search_engine_url": "https://duckduckgo.com/?q={query}"
}
```

### Disable Caching (for testing)

```python
from command_controller.url_resolver import URLResolver

resolver = URLResolver()
resolver._cache.clear()  // Clear cache manually
# or
resolver._cache = URLResolutionCache(ttl_secs=0)  // Disable caching
```

### Check Cache Status

```python
print(f"Cache size: {resolver._cache.size()}")
print(f"Cache hit rate: {cache_hits / (cache_hits + cache_misses)}")
```

### Enable Deep Logging

```json
{
  "log_level": "DEEP"
}
```

Check logs for:
```
[DEEP][URL_RESOLVER] Cache hit for query='youtube cats'
[DEEP][URL_RESOLVER] Found 15 candidates for query='youtube cats'
[DEEP][FALLBACK_CHAIN] Resolution succeeded for query='youtube cats'
```

## Troubleshooting

### Issue: Resolution fails with timeout

**Quick Fix:**
```json
{
  "playwright_navigation_timeout_ms": 60000  // Increase to 60s
}
```

### Issue: Always opens search engine

**Quick Fix:** Add domain to `command_controller/web_constants.py`:

```python
COMMON_DOMAINS = {
    "spotify": "open.spotify.com",  // Add custom mapping
    # ... existing mappings
}
```

### Issue: Slow first resolution

**Quick Fix:** Enable warm-up:
```json
{
  "warmup_url_resolver": true  // Pre-initialize browser
}
```

## Security Checklist

Before production:

- [ ] `allow_headless_form_fill: false` (default)
- [ ] `request_before_open_url: true` (for sensitive environments)
- [ ] `log_level: "INFO"` (avoid DEEP in production)
- [ ] Review `security_notes.md` for critical fixes
- [ ] Test URL validation with malicious inputs

## Next Steps

- **Full Guide:** Read `docs/WEB_EXECUTOR.md` for complete documentation
- **Configuration:** See `docs/CONFIGURATION.md` for all settings
- **Security:** Review `security_notes.md` for hardening recommendations
- **Architecture:** Check `HANDOFF.md` for implementation details

## Performance Tips

1. **Enable warm-up:** `warmup_url_resolver: true`
2. **Tune timeouts:** Reduce `playwright_navigation_timeout_ms` for fast networks
3. **Monitor cache:** Track cache hit rate (target >30%)
4. **Limit DOM search:** Default 100 links is optimal for most pages
5. **Use cache:** Repeated queries are instant with 15-minute cache

## Common Queries

| Query | Resolution | Fallback Used |
|-------|-----------|---------------|
| `youtube cats` | `https://youtube.com/results?search_query=cats` | Direct resolution |
| `gmail inbox` | `https://mail.google.com/mail/u/0/#inbox` | Direct resolution |
| `unknown-site xyz` | `https://duckduckgo.com/?q=unknown-site+xyz` | Search fallback |
| `spotify` | `https://spotify.com` | Homepage fallback |
| `github` | `https://github.com` | Homepage fallback |

## API Quick Reference

```python
# URLResolutionResult
result.status           # "ok" | "failed" | "timeout"
result.resolved_url     # Final URL or None
result.candidates_found # Number of DOM links found
result.elapsed_ms       # Resolution time

# FallbackResult
result.status           # "ok" | "all_failed"
result.final_url        # Final URL or None
result.fallback_used    # "resolution" | "search" | "homepage" | "none"
result.attempts_made    # ["resolution", "search", "homepage"]
result.elapsed_ms       # Total elapsed time
```

## Contact

For issues:
1. Check `docs/WEB_EXECUTOR.md` troubleshooting section
2. Enable deep logging and check logs
3. Review `security_notes.md` for security issues
4. Check `HANDOFF.md` for known limitations
