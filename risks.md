# Executor Rework: Risks & Assumptions

## Assumptions

### 1. Playwright Headless Stability
**Assumption**: Playwright can reliably run in headless mode for URL resolution without conflicts with the existing headed browser context.

**Rationale**: The current WebExecutor uses a persistent browser context that may be headed or headless based on config. We assume we can create a separate headless context for URL resolution without lock conflicts on the user data directory.

**Impact if Wrong**: URL resolution may fail or cause browser lock errors. May need to use a completely separate profile directory for headless operations.

**Mitigation**: Use separate profile directories for headless resolver (`playwright_resolver_profile`) and headed web executor (`playwright_profile`).

---

### 2. DOM Search Heuristics are Sufficient
**Assumption**: Simple text matching and link extraction from DOM is sufficient for most URL resolution use cases.

**Rationale**: For common scenarios like "open YouTube search for cats", searching for anchor tags containing "search" or related keywords should work.

**Impact if Wrong**: URL resolution may frequently fail, triggering fallbacks more often than desired. Users may get frustrated with incorrect link selection.

**Mitigation**: Implement ranking algorithm that considers link prominence (position in DOM, size, ARIA labels). Add config option to disable URL resolution and use search fallback directly.

---

### 3. User's Default Browser Preference
**Assumption**: Opening URLs in the user's default browser (via OS `open` command) is the desired behavior after headless resolution.

**Rationale**: Requirement states "resolve deep URLs by DOM search, return final URL, then open in user's default browser".

**Impact if Wrong**: Users may want URLs to open in the Playwright-controlled browser instead. Workflow may feel disjointed.

**Mitigation**: Add config option `open_resolved_url_in` with values: "default_browser" | "playwright_browser". Default to "default_browser" per requirements.

---

### 4. Existing Step-Based Execution Format Remains Unchanged
**Assumption**: The existing `steps` structure and execution flow should remain backward compatible.

**Rationale**: Project instruction explicitly states "Keep the existing step-based execution format."

**Impact if Wrong**: Breaking changes would require updates to LLM prompts, API contracts, and existing command workflows.

**Mitigation**: Design all enhancements as additive extensions to ExecutionResult and step metadata. No breaking changes to core step structure.

---

### 5. LLM Can Identify Subjects Effectively
**Assumption**: The existing LocalLLMInterpreter can be extended to identify distinct subjects in commands when provided with appropriate context.

**Rationale**: Subject extraction requires semantic understanding (e.g., "open Gmail and Spotify" has two subjects). The LLM is already parsing commands into structured steps.

**Impact if Wrong**: Subject extraction may be inaccurate or require significant prompt engineering. May fall back to treating all steps as single subject.

**Mitigation**: Start with simple keyword-based subject extraction as fallback. Use LLM for complex cases. Make subject extraction optional (Milestone 9 is marked optional).

---

## Risks

### 1. Playwright Installation & Dependencies
**Risk**: Playwright requires Chromium browser installation via `playwright install chromium`. Users may not have this installed.

**Severity**: High

**Likelihood**: Medium

**Impact**: URL resolution will fail on first use. User experience degraded.

**Mitigation**:
- Add clear installation instructions to project README
- Detect missing Chromium and provide actionable error message with install command
- Add optional auto-install prompt in setup flow
- Document Playwright dependency in pyproject.toml (already present)

---

### 2. URL Resolution Timeout & Latency
**Risk**: Headless navigation to resolve URLs adds significant latency (2-5 seconds per resolution). Users may perceive system as slow.

**Severity**: Medium

**Likelihood**: High

**Impact**: Poor user experience for commands requiring URL resolution. Voice command responsiveness degraded.

**Mitigation**:
- Set reasonable default timeout (30 seconds) configurable via `playwright_navigation_timeout_ms`
- Cache resolved URLs for repeated queries (15-minute TTL like WebFetch)
- Provide immediate feedback to user that resolution is in progress
- Make URL resolution optional via `use_playwright_for_web` toggle

---

### 3. DOM Structure Variability Across Sites
**Risk**: Different websites have vastly different DOM structures. Heuristics that work on one site may fail on another.

**Severity**: High

**Likelihood**: High

**Impact**: URL resolution frequently fails, falling back to search engine. Feature provides less value than expected.

**Mitigation**:
- Implement site-specific adapters (like whatsapp.py) for high-value domains
- Make fallback chain robust and configurable
- Log failed resolutions at DEEP level to identify patterns
- Consider future enhancement: machine learning or vision-based link detection

---

### 4. Concurrent Browser Context Conflicts
**Risk**: Running headless resolver and headed web executor simultaneously may cause Playwright context conflicts or resource exhaustion.

**Severity**: Medium

**Likelihood**: Medium

**Impact**: Browser crashes, lock errors, or execution failures.

**Mitigation**:
- Use separate profile directories for resolver and web executor
- Implement context lifecycle management (close resolver context after resolution)
- Add error handling for context lock errors with retry logic
- Test concurrent usage scenarios in Milestone 10

---

### 5. Search Engine Fallback Rate Limiting
**Risk**: Using DuckDuckGo or other search engines as fallback may trigger rate limiting or CAPTCHA challenges.

**Severity**: Low

**Likelihood**: Medium

**Impact**: Fallback chain fails entirely. Command execution blocked.

**Mitigation**:
- Respect search engine rate limits (implement exponential backoff)
- Allow configurable search engine URL in config
- Provide option to disable search fallback entirely
- Log fallback failures for monitoring

---

### 6. Permission Hook Implementation Complexity
**Risk**: Requirement mentions "permission hooks" but scope is unclear. Implementation may be more complex than anticipated.

**Severity**: Low

**Likelihood**: Medium

**Impact**: Feature may be deferred or cut if too complex.

**Mitigation**:
- Clarify permission hook requirements with stakeholders
- Implement minimal stub in Milestone 6 (infrastructure only)
- Defer full implementation to future iteration
- Design intent schema to support future expansion

---

### 7. Form Fill Security & Privacy
**Risk**: Headless form filling (gated by `allow_headless_form_fill`) raises security concerns. Malicious commands could submit forms with unintended data.

**Severity**: High

**Likelihood**: Low

**Impact**: User data could be submitted without explicit consent. Privacy violation.

**Mitigation**:
- Default `allow_headless_form_fill` to `false`
- Require explicit user confirmation before form submission (use existing confirmation system)
- Add form fill intents to ALWAYS_CONFIRM_INTENTS in engine.py
- Log all form fill attempts at INFO level
- Consider adding form field preview before submission

---

### 8. Backward Compatibility Breakage
**Risk**: Despite assumptions, refactoring WebExecutor may inadvertently break existing web intent workflows.

**Severity**: Medium

**Likelihood**: Low

**Impact**: Existing commands (like WhatsApp send_message) stop working. Users frustrated.

**Mitigation**:
- Maintain existing _handle_* methods in WebExecutor
- Add comprehensive regression tests in Milestone 10
- Test existing web_adapters (whatsapp.py) still work
- Keep fallback to original behavior if new features disabled via config

---

### 9. LLM Prompt Complexity Explosion
**Risk**: Adding new intents and subject extraction may make LLM prompts overly complex, reducing reliability.

**Severity**: Medium

**Likelihood**: Medium

**Impact**: Command parsing accuracy degrades. More parse failures.

**Mitigation**:
- Keep intent schemas simple and orthogonal
- Document new intents clearly in LLM prompt
- Test LLM parsing with diverse command examples
- Provide fallback to simpler parsing if complex parse fails
- Consider prompt length limits and token budgets

---

### 10. Config Sprawl & Usability
**Risk**: Adding 7+ new config options makes settings overwhelming for users.

**Severity**: Low

**Likelihood**: High

**Impact**: Users don't understand settings. System misconfigured.

**Mitigation**:
- Provide sensible defaults that work for 80% of use cases
- Add clear comments to app_settings.json explaining each option
- Group related settings together
- Consider future UI for config management
- Document common configuration patterns in project docs

---

## Open Questions

### 1. URL Resolution Scope
**Question**: Should URL resolution handle only search queries, or also deep links like "Gmail inbox" → "https://mail.google.com/mail/u/0/#inbox"?

**Impact**: Determines complexity of DOM search heuristics and site-specific adapters.

**Recommendation**: Start with simple search query resolution. Add deep link resolution as future enhancement with site-specific adapters.

---

### 2. Permission Hook Use Cases
**Question**: What specific permissions need hooks? (e.g., location access, camera, notifications, etc.)

**Impact**: Determines implementation scope for Milestone 6.

**Recommendation**: Implement minimal infrastructure in Milestone 6. Defer specific permission handling until use cases clarify.

---

### 3. Subject Extraction Granularity
**Question**: How should subject extraction handle ambiguous commands like "search for cats and dogs"? Is this one subject or two?

**Impact**: Affects SubjectExtractor algorithm complexity and accuracy.

**Recommendation**: Treat as single subject (search query) unless clear separation exists (e.g., "open Gmail and search for cats" = two subjects).

---

### 4. Fallback Chain Order
**Question**: Should fallback chain be configurable? Some users may prefer homepage fallback over search.

**Impact**: Adds configuration complexity but improves flexibility.

**Recommendation**: Implement fixed order (resolution → search → homepage) in Milestone 4. Add configurable order as future enhancement if needed.

---

### 5. Resolved URL Caching Strategy
**Question**: Should resolved URLs be cached? For how long? What's the invalidation strategy?

**Impact**: Affects performance and freshness of resolution results.

**Recommendation**: Implement simple 15-minute TTL cache in Milestone 3 (like WebFetch). Add cache clear command for manual invalidation.

---

## Risk Summary

**High Severity Risks**: 3 (Playwright installation, DOM variability, Form fill security)

**Medium Severity Risks**: 5 (URL latency, Browser conflicts, Permission hooks, Backward compatibility, LLM prompt complexity)

**Low Severity Risks**: 2 (Search rate limiting, Config sprawl)

**Total Open Questions**: 5

**Overall Project Risk Level**: **Medium-High**

The project is ambitious with multiple moving parts. Success depends on careful milestone execution, robust testing, and pragmatic scope management (e.g., deferring subject extraction if time-constrained).
