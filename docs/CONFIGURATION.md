# Configuration Reference

## Overview

Back-Hackathon2025 uses JSON-based configuration stored in `config/app_settings.json`. This document covers all web executor and URL resolution settings added in the executor rework.

## Configuration File Location

**Primary:** `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/config/app_settings.json`

**Loading:** Configuration is loaded via `utils.settings_store.get_settings()`

## Web Executor Configuration

### Core Settings

#### `use_playwright_for_web`

**Type:** `boolean`
**Default:** `true`
**Purpose:** Enable headless URL resolution and fallback chain

**Values:**
- `true`: Enhanced mode with URL resolution, fallback chain, and default browser opening
- `false`: Legacy mode with direct Playwright navigation

**Impact:**
- When `true`: URLs are resolved using headless browser, DOM search, and fallback strategies before opening in default browser
- When `false`: URLs navigate directly in Playwright context without resolution

**Recommendation:** Keep `true` for best user experience

---

#### `request_before_open_url`

**Type:** `boolean`
**Default:** `false`
**Purpose:** Show confirmation dialog before opening resolved URLs

**Values:**
- `true`: Require user confirmation (security-focused environments)
- `false`: Open URLs automatically (convenience-focused)

**Use Cases:**
- Enable in shared/public computers
- Enable when processing untrusted commands
- Disable for personal, trusted usage

**Security Impact:** HIGH - Prevents accidental opening of malicious URLs

---

#### `enable_search_fallback`

**Type:** `boolean`
**Default:** `true`
**Purpose:** Fallback to search engine if URL resolution fails

**Values:**
- `true`: Search engine fallback enabled
- `false`: Skip search fallback, try homepage fallback next

**Behavior When Disabled:**
```
Query: "unknown-site cats"
→ Direct resolution: FAIL
→ Search fallback: SKIPPED (disabled)
→ Homepage fallback: https://unknown-site.com
```

**Recommendation:** Keep enabled for better UX (user likely wants search results)

---

#### `enable_homepage_fallback`

**Type:** `boolean`
**Default:** `true`
**Purpose:** Fallback to domain homepage if search fallback fails

**Values:**
- `true`: Homepage fallback enabled
- `false`: Fail if search fallback fails

**Behavior:**
```
Query: "spotify"
→ Direct resolution: FAIL (no matching links)
→ Search fallback: FAIL (disabled)
→ Homepage fallback: https://spotify.com ✓
```

**Recommendation:** Keep enabled for better resilience

---

#### `allow_headless_form_fill`

**Type:** `boolean`
**Default:** `false`
**Purpose:** Enable `web_fill_form` intent

**Values:**
- `true`: Allow form automation (SECURITY RISK)
- `false`: Reject form fill intents with error

**Security Warning:**
- Enables credential theft if malicious commands are processed
- Should only be enabled with explicit user consent
- Always requires user confirmation (enforced in `engine.py:ALWAYS_CONFIRM_INTENTS`)

**Use Cases:**
- Automated testing environments
- Trusted workflow automation
- NEVER enable in production without user consent

**Recommendation:** Keep `false` in production

---

### Advanced Settings

#### `search_engine_url`

**Type:** `string`
**Default:** `"https://duckduckgo.com/?q={query}"`
**Purpose:** Template for search fallback URL

**Format:** Use `{query}` as placeholder for URL-encoded search terms

**Examples:**
```json
"https://duckduckgo.com/?q={query}"          // DuckDuckGo
"https://www.google.com/search?q={query}"    // Google
"https://www.bing.com/search?q={query}"      // Bing
```

**Security Note:** Query is automatically URL-encoded to prevent injection attacks

---

#### `playwright_navigation_timeout_ms`

**Type:** `number`
**Default:** `30000`
**Purpose:** Navigation timeout for URL resolution

**Valid Range:** 5000 - 120000 (5s - 2min)

**Tuning Guidance:**
- **Fast networks:** 15000 (15s)
- **Average networks:** 30000 (30s) - recommended
- **Slow networks:** 60000 (60s)
- **Testing/CI:** 120000 (2min)

**Impact:**
- Too low: Legitimate slow pages time out
- Too high: Hung navigations block execution

**Symptoms of Incorrect Value:**
- Frequent "timeout" status in resolution results
- Long waits before fallback triggers

---

#### `playwright_resolver_profile`

**Type:** `string`
**Default:** `"user_data/playwright_resolver"`
**Purpose:** Profile directory for headless resolver browser

**Format:** Relative or absolute path

**Security Requirements:**
- Directory created with `mode=0o700` (user-only access)
- Should NOT be shared with user-visible browser profile
- Contains cookies, session tokens, and cached data

**Customization:**
```json
"playwright_resolver_profile": "/path/to/secure/location"
```

**Warning:** Never use the same profile for resolver and user browser (causes context conflicts)

---

#### `warmup_url_resolver`

**Type:** `boolean`
**Default:** `true`
**Purpose:** Pre-initialize browser context on startup

**Values:**
- `true`: Eager warm-up (first resolution is fast)
- `false`: Lazy initialization (first resolution slow)

**Performance Impact:**
- When `true`: 1-3s startup delay, all resolutions fast
- When `false`: First resolution +1-3s, subsequent fast

**Recommendation:** Keep `true` for better UX (amortize cold-start cost)

---

### Legacy Settings

#### `playwright_profile_dir`

**Type:** `string`
**Default:** `"user_data/playwright_profile"`
**Purpose:** Profile directory for user-visible browser

**Note:** This is for the user's browser context (WebExecutor), NOT the resolver. Keep separate from `playwright_resolver_profile`.

---

#### `playwright_headless`

**Type:** `boolean`
**Default:** `false`
**Purpose:** Run user-visible browser in headless mode

**Note:** Resolver always runs headless regardless of this setting.

---

## Configuration Examples

### Development (Verbose Logging)

```json
{
  "log_level": "DEEP",
  "use_playwright_for_web": true,
  "request_before_open_url": false,
  "enable_search_fallback": true,
  "enable_homepage_fallback": true,
  "allow_headless_form_fill": false,
  "warmup_url_resolver": true,
  "playwright_navigation_timeout_ms": 30000
}
```

### Production (Security-Focused)

```json
{
  "log_level": "INFO",
  "use_playwright_for_web": true,
  "request_before_open_url": true,
  "enable_search_fallback": true,
  "enable_homepage_fallback": true,
  "allow_headless_form_fill": false,
  "warmup_url_resolver": true,
  "playwright_navigation_timeout_ms": 30000
}
```

### Testing/CI (Fast Failures)

```json
{
  "log_level": "DEBUG",
  "use_playwright_for_web": true,
  "request_before_open_url": false,
  "enable_search_fallback": false,
  "enable_homepage_fallback": false,
  "allow_headless_form_fill": true,
  "warmup_url_resolver": false,
  "playwright_navigation_timeout_ms": 15000
}
```

### Minimal (Direct Resolution Only)

```json
{
  "use_playwright_for_web": true,
  "enable_search_fallback": false,
  "enable_homepage_fallback": false
}
```

Result: Only direct resolution attempted, fails if no DOM matches found.

---

## Environment Variables

While most configuration is JSON-based, the following environment variables are relevant:

### `STT_PROVIDER`

**Default:** `whisper-local`
**Purpose:** Speech-to-text provider for voice commands

**Values:**
- `whisper-local`: Local Whisper model
- `openai-realtime`: OpenAI Realtime API
- `whisperlive`: WhisperLive server

**Impact:** Not directly related to web executor, but affects command input

---

### `GESTURE_USER_ID`

**Default:** `default`
**Purpose:** User identifier for per-user datasets/models

**Impact:** Web executor uses this for profile directory naming in future enhancements

---

## Configuration Loading

### Load Order

1. `config/app_settings.json` (primary)
2. Environment variable overrides (if implemented)
3. Default values in code

### Runtime Updates

Configuration is loaded once at startup. Changes require application restart.

**Future Enhancement:** Hot-reload configuration without restart

---

## Validation

### Required Fields

None. All web executor settings have sensible defaults.

### Type Validation

Settings are validated at load time:
- Booleans must be `true` or `false`
- Numbers must be valid integers
- Strings must be non-empty for URLs and paths

### Invalid Configuration Handling

- **Invalid type:** Falls back to default value, logs warning
- **Missing file:** Uses all defaults, logs info
- **Malformed JSON:** Application fails to start with clear error

---

## Cache Configuration

Cache settings are currently hardcoded in `url_resolution_cache.py`:

```python
URLResolutionCache(ttl_secs=900, max_size=100)
```

**Future Enhancement:** Expose as configuration options:

```json
{
  "url_cache_ttl_secs": 900,
  "url_cache_max_size": 100
}
```

---

## Security Configuration

### Recommended Production Settings

```json
{
  "allow_headless_form_fill": false,
  "request_before_open_url": true,
  "log_level": "INFO",
  "playwright_headless": true
}
```

### Security Toggles (Proposed, Not Yet Implemented)

See `security_notes.md` for detailed recommendations:

```json
{
  "security": {
    "block_localhost_urls": true,
    "block_private_ips": true,
    "max_url_length": 2000,
    "max_cache_entry_size": 10000,
    "enable_error_screenshots": false
  }
}
```

---

## Configuration Migration

### From Legacy to Enhanced Mode

**Before (legacy):**
```json
{
  "use_playwright_for_web": false
}
```

**After (enhanced):**
```json
{
  "use_playwright_for_web": true,
  "enable_search_fallback": true,
  "enable_homepage_fallback": true,
  "warmup_url_resolver": true
}
```

**Behavior Changes:**
- URLs now resolved before opening
- Opens in default browser (not Playwright context)
- Fallback strategies apply
- First resolution may be slower (cold-start)

---

## Troubleshooting Configuration Issues

### Symptom: Settings not taking effect

**Cause:** Configuration not reloaded after changes

**Solution:**
1. Save `app_settings.json`
2. Restart application
3. Check logs for "Loaded settings from config/app_settings.json"

---

### Symptom: Invalid JSON error on startup

**Cause:** Malformed JSON syntax

**Solution:**
1. Validate JSON: `python -m json.tool config/app_settings.json`
2. Common issues:
   - Missing closing brace `}`
   - Trailing comma in last element
   - Unquoted strings
   - Comments not allowed in JSON (use `*_comment` fields instead)

---

### Symptom: Settings reverted to defaults

**Cause:** Configuration file not found or permission denied

**Solution:**
1. Verify file exists: `ls -l config/app_settings.json`
2. Check permissions: `chmod 644 config/app_settings.json`
3. Check logs for "Config file not found, using defaults"

---

## Configuration Best Practices

1. **Use comments:** Leverage `*_comment` fields for documentation
2. **Version control:** Commit `app_settings.json` with sensible defaults
3. **Environment-specific:** Maintain separate configs for dev/staging/prod
4. **Security audit:** Review security-sensitive settings before deployment
5. **Minimal changes:** Only override defaults when necessary
6. **Test changes:** Verify configuration in non-production environment first

---

## Related Documentation

- **Web Executor Guide:** `docs/WEB_EXECUTOR.md`
- **Security Audit:** `security_notes.md`
- **Implementation Details:** `HANDOFF.md`
