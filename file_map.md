# Executor Rework: File Map

This document outlines which files need to be created, modified, or remain unchanged during the executor rework. Each entry includes the action type, milestone, and summary of changes.

---

## Legend

- **[CREATE]** - New file to be created
- **[MODIFY]** - Existing file to be modified
- **[UNCHANGED]** - Existing file, no changes needed
- **[DELETE]** - File to be removed (none in this project)

---

## Configuration Files

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/config/app_settings.json`
**Action:** [MODIFY]
**Milestone:** M1 (Configuration Infrastructure)
**Changes:**
- Add `use_playwright_for_web` (bool, default: true)
- Add `request_before_open_url` (bool, default: false)
- Add `enable_search_fallback` (bool, default: true)
- Add `enable_homepage_fallback` (bool, default: true)
- Add `allow_headless_form_fill` (bool, default: false)
- Add `search_engine_url` (string, default: "https://duckduckgo.com/?q={query}")
- Add `playwright_navigation_timeout_ms` (int, default: 30000)
- Add `playwright_resolver_profile` (string, default: "user_data/playwright_resolver")
- Add comments explaining each new config option

**Lines to modify:** Add new JSON fields after existing `playwright_headless` field (line 26)

---

## Core Executor Files

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/executors/base.py`
**Action:** [MODIFY]
**Milestone:** M2 (Enhanced ExecutionResult Structure)
**Changes:**
- Add optional fields to `ExecutionResult` dataclass:
  - `resolved_url: str | None = None`
  - `fallback_used: str | None = None`
  - `navigation_time_ms: int | None = None`
  - `dom_search_query: str | None = None`
- Update `to_dict()` method to include new fields only when not None

**Lines to modify:**
- Line 9-15: Add new dataclass fields
- Line 17-27: Update `to_dict()` method

**Backward Compatibility:** All new fields default to None, existing usage unaffected

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/executor.py`
**Action:** [MODIFY]
**Milestone:** M7 (Executor Integration)
**Changes:**
- Update `_execute_web_step()` method (lines 75-90):
  - Check for `_last_resolution` attribute on WebExecutor
  - Create enriched ExecutionResult with resolution metadata if present
  - Preserve existing error handling for WebExecutionError

**Lines to modify:** Lines 75-90 (replace `_execute_web_step` method)

**Backward Compatibility:** WebExecutor without `_last_resolution` returns basic result (no changes)

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/web_executor.py`
**Action:** [MODIFY]
**Milestone:** M6 (Web Executor Rework)
**Changes:**
- Add imports:
  - `from command_controller.fallback_chain import FallbackChain, FallbackResult`
  - `from command_controller.url_resolver import URLResolver`
  - `import subprocess`
- Add instance variables in `__init__`:
  - `self._url_resolver: URLResolver | None = None`
  - `self._fallback_chain: FallbackChain | None = None`
  - `self._last_resolution: FallbackResult | None = None`
- Add new methods:
  - `_get_url_resolver() -> URLResolver` (lazy init)
  - `_get_fallback_chain() -> FallbackChain` (lazy init)
  - `_handle_form_fill(step: dict) -> None` (new intent handler)
  - `_handle_request_permission(step: dict) -> None` (stub)
  - `_is_safe_url(url: str | None) -> bool` (static method)
- Modify existing methods:
  - `execute_step()`: Add routing for `web_fill_form` and `web_request_permission`
  - `_handle_open_url()`: Replace implementation with URL resolution + fallback logic
  - `shutdown()`: Add cleanup for `_url_resolver`

**Lines to modify:**
- Lines 1-12: Add imports
- Lines 17-21: Add new instance variables to `__init__`
- Lines 69-88: Update `execute_step()` to route new intents
- Lines 103-109: Replace `_handle_open_url()` implementation
- Lines 216-231: Update `shutdown()` to cleanup resolver

**Backward Compatibility:** Check `use_playwright_for_web` config; if false, use legacy navigation

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/executors/macos_executor.py`
**Action:** [UNCHANGED]
**Milestone:** N/A
**Reason:** OS-native executor doesn't need web navigation changes

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/executors/router.py`
**Action:** [UNCHANGED]
**Milestone:** N/A
**Reason:** Routing logic unchanged, fallback pattern already present

---

## New Module Files

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/url_resolver.py`
**Action:** [CREATE]
**Milestone:** M3 (URL Resolution Engine)
**Contents:**
- `LinkCandidate` dataclass
- `URLResolutionResult` dataclass
- `URLResolver` class with methods:
  - `__init__(settings)`
  - `resolve(query) -> URLResolutionResult`
  - `_ensure_browser()`
  - `_search_dom_for_links(page, query) -> list[LinkCandidate]`
  - `_rank_candidates(candidates, query) -> LinkCandidate | None`
  - `_infer_initial_url(query) -> str`
  - `shutdown()`

**Dependencies:**
- `playwright.sync_api`
- `utils.log_utils`
- `utils.settings_store`
- `command_controller.url_resolution_cache`

**Estimated Lines:** ~300-400

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/url_resolution_cache.py`
**Action:** [CREATE]
**Milestone:** M3 (URL Resolution Engine)
**Contents:**
- `CacheEntry` dataclass
- `URLResolutionCache` class with methods:
  - `__init__(ttl_secs)`
  - `get(query) -> URLResolutionResult | None`
  - `put(query, result)`
  - `clear()`
  - `size() -> int`

**Dependencies:**
- `command_controller.url_resolver` (for URLResolutionResult type)
- `time` (standard library)

**Estimated Lines:** ~60-80

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/fallback_chain.py`
**Action:** [CREATE]
**Milestone:** M4 (Fallback Chain System)
**Contents:**
- `FallbackResult` dataclass
- `FallbackChain` class with methods:
  - `__init__(resolver, settings)`
  - `execute(query) -> FallbackResult`
  - `_try_direct_resolution(query) -> FallbackResult | None`
  - `_try_search_fallback(query) -> FallbackResult | None`
  - `_try_homepage_fallback(query) -> FallbackResult | None`

**Dependencies:**
- `command_controller.url_resolver`
- `utils.log_utils`
- `utils.settings_store`
- `urllib.parse` (standard library)

**Estimated Lines:** ~200-250

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/subject_extractor.py`
**Action:** [CREATE]
**Milestone:** M5 (Subject Extraction Module)
**Contents:**
- `SubjectGroup` dataclass
- `SubjectExtractor` class with methods:
  - `__init__(llm_interpreter)`
  - `extract(text, steps) -> list[SubjectGroup]`
  - `_identify_subjects(text, steps) -> list[str]`
  - `_assign_steps_to_subjects(subjects, steps) -> list[SubjectGroup]`
  - `_infer_subject_type(subject, step) -> str`

**Dependencies:**
- `command_controller.llm` (for LocalLLMInterpreter type)
- `utils.log_utils`

**Estimated Lines:** ~150-200

---

## Intent and Validation Files

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/intents.py`
**Action:** [MODIFY]
**Milestone:** M8 (Intent Schema Extensions)
**Changes:**
- Add new intents to `ALLOWED_INTENTS` set (line 19-33):
  - `"web_fill_form"`
  - `"web_request_permission"`
- Add validation logic in `validate_step()` function:
  - `web_fill_form` validation (after line 199)
  - `web_request_permission` validation (after `web_fill_form`)

**Lines to modify:**
- Line 19-33: Add new intents to set
- After line 199: Add new validation branches

**Estimated lines added:** ~40-50

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/engine.py`
**Action:** [MODIFY]
**Milestone:** M9 (Subject-Aware Execution) - OPTIONAL
**Changes:**
- Add import: `from command_controller.subject_extractor import SubjectExtractor`
- Add instance variable in `__init__`: `self._subject_extractor = SubjectExtractor(self.interpreter)`
- Add subject extraction logic in `run()` method (after line 53):
  ```python
  settings = get_settings()
  if settings.get("enable_subject_extraction", False):
      subject_groups = self._subject_extractor.extract(text, steps)
      deep_log(f"[DEEP][ENGINE] subject_groups={subject_groups}")
  ```

**Lines to modify:**
- Line 1-15: Add import
- Line 27-39: Add `_subject_extractor` initialization
- After line 53: Add subject extraction logic

**Note:** This is optional and can be deferred

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/llm.py`
**Action:** [MODIFY] - OPTIONAL
**Milestone:** M8 (Intent Schema Extensions)
**Changes:**
- Update LLM prompt to document new intents:
  - `web_fill_form` intent documentation
  - `web_request_permission` intent documentation

**Lines to modify:** Locate prompt template (likely around lines 75-107), add intent documentation

**Note:** Only needed if LLM should generate new intents

---

## Web Adapter Files

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/web_adapters/whatsapp.py`
**Action:** [UNCHANGED]
**Milestone:** N/A
**Reason:** Existing adapter remains functional, serves as pattern for future adapters

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/web_adapters/__init__.py`
**Action:** [UNCHANGED]
**Milestone:** N/A
**Reason:** No changes needed

---

## Utility and Support Files

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/utils/settings_store.py`
**Action:** [UNCHANGED]
**Milestone:** N/A
**Reason:** Existing `get_settings()` function sufficient for config access

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/utils/log_utils.py`
**Action:** [UNCHANGED]
**Milestone:** N/A
**Reason:** Existing logging utilities (`tprint`, `deep_log`) sufficient

---

## Testing Files (Milestone 10)

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/tests/test_url_resolver.py`
**Action:** [CREATE]
**Milestone:** M10 (Testing & Documentation)
**Contents:**
- Unit tests for URLResolver class
- Mock Playwright for DOM search tests
- Test cases:
  - `test_resolve_cached_query()`
  - `test_search_dom_for_links()`
  - `test_rank_candidates()`
  - `test_infer_initial_url()`
  - `test_timeout_handling()`

**Estimated Lines:** ~200-300

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/tests/test_fallback_chain.py`
**Action:** [CREATE]
**Milestone:** M10 (Testing & Documentation)
**Contents:**
- Unit tests for FallbackChain class
- Mock URLResolver for fallback logic tests
- Test cases:
  - `test_direct_resolution_success()`
  - `test_search_fallback_triggered()`
  - `test_homepage_fallback_triggered()`
  - `test_all_fallbacks_failed()`
  - `test_fallback_disabled_via_config()`

**Estimated Lines:** ~150-200

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/tests/test_subject_extractor.py`
**Action:** [CREATE]
**Milestone:** M10 (Testing & Documentation)
**Contents:**
- Unit tests for SubjectExtractor class
- Test cases:
  - `test_single_subject_extraction()`
  - `test_multi_subject_extraction()`
  - `test_ambiguous_subject_handling()`
  - `test_subject_type_inference()`

**Estimated Lines:** ~100-150

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/tests/test_execution_result.py`
**Action:** [CREATE]
**Milestone:** M10 (Testing & Documentation)
**Contents:**
- Unit tests for enhanced ExecutionResult
- Test cases:
  - `test_to_dict_basic_fields()`
  - `test_to_dict_with_web_metadata()`
  - `test_backward_compatibility()`

**Estimated Lines:** ~60-80

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/tests/test_web_executor_integration.py`
**Action:** [CREATE]
**Milestone:** M10 (Testing & Documentation)
**Contents:**
- Integration tests for WebExecutor with real Playwright
- Test cases:
  - `test_open_url_with_resolution()`
  - `test_open_url_with_search_fallback()`
  - `test_form_fill_disabled_by_default()`
  - `test_form_fill_with_config_enabled()`

**Estimated Lines:** ~200-250

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/tests/test_whatsapp_regression.py`
**Action:** [CREATE]
**Milestone:** M10 (Testing & Documentation)
**Contents:**
- Regression test for WhatsApp adapter
- Verifies existing workflow still works after executor rework
- Test case: `test_whatsapp_send_message()`

**Estimated Lines:** ~50-80

---

## Documentation Files

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/architecture.md`
**Action:** [CREATE]
**Milestone:** Architect Phase
**Status:** ✅ Created in this session

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/interface_spec.md`
**Action:** [CREATE]
**Milestone:** Architect Phase
**Status:** ✅ Created in this session

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/file_map.md`
**Action:** [CREATE]
**Milestone:** Architect Phase
**Status:** ✅ This file

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/milestones.md`
**Action:** [UNCHANGED]
**Milestone:** Planner Phase
**Status:** ✅ Created by planner, used as reference

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/risks.md`
**Action:** [UNCHANGED]
**Milestone:** Planner Phase
**Status:** ✅ Created by planner, used as reference

---

### `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/HANDOFF.md`
**Action:** [MODIFY]
**Milestone:** Architect Phase
**Status:** To be updated with architect → implementer handoff

---

## Summary Statistics

### Files by Action Type
- **[CREATE]**: 10 files (3 new modules + 6 test files + 1 doc file completed)
- **[MODIFY]**: 6 files (config, base executor, executor, web executor, intents, engine)
- **[UNCHANGED]**: 9 files (macos executor, router, whatsapp, utils, existing docs)
- **[DELETE]**: 0 files

### Files by Milestone
- **M1 (Configuration)**: 1 file (app_settings.json)
- **M2 (ExecutionResult)**: 1 file (base.py)
- **M3 (URL Resolver)**: 2 files (url_resolver.py, url_resolution_cache.py)
- **M4 (Fallback Chain)**: 1 file (fallback_chain.py)
- **M5 (Subject Extraction)**: 1 file (subject_extractor.py)
- **M6 (Web Executor Rework)**: 1 file (web_executor.py)
- **M7 (Executor Integration)**: 1 file (executor.py)
- **M8 (Intent Extensions)**: 2 files (intents.py, llm.py optional)
- **M9 (Subject-Aware Execution)**: 1 file (engine.py) - OPTIONAL
- **M10 (Testing)**: 6 test files
- **Architect Phase**: 3 docs (architecture.md, interface_spec.md, file_map.md)

### Total Lines of Code (Estimated)
- **New modules**: ~900-1100 lines
- **Modified files**: ~200-300 lines changed
- **Test files**: ~800-1000 lines
- **Documentation**: ~2000 lines (architecture + interface specs)

**Total Estimated LOC**: ~3900-4400 lines

---

## Implementation Order (Recommended)

### Phase 1: Foundation (Milestones 1-2)
1. `config/app_settings.json` - Add config fields (5 minutes)
2. `command_controller/executors/base.py` - Extend ExecutionResult (15 minutes)

**Checkpoint:** Run existing tests to verify no breakage

---

### Phase 2: Core Resolution (Milestones 3-4)
3. `command_controller/url_resolution_cache.py` - Create cache (30 minutes)
4. `command_controller/url_resolver.py` - Create resolver (2-3 hours)
5. `command_controller/fallback_chain.py` - Create fallback orchestrator (1-2 hours)

**Checkpoint:** Unit test URLResolver and FallbackChain in isolation

---

### Phase 3: Optional Subject Extraction (Milestone 5)
6. `command_controller/subject_extractor.py` - Create extractor (1-2 hours)

**Checkpoint:** Unit test SubjectExtractor

**Note:** Can be deferred to later phase or v2

---

### Phase 4: Integration (Milestones 6-7)
7. `command_controller/web_executor.py` - Refactor with resolution (2-3 hours)
8. `command_controller/executor.py` - Enrich results (30 minutes)

**Checkpoint:** Integration test open_url flow end-to-end

---

### Phase 5: Intent Extensions (Milestone 8)
9. `command_controller/intents.py` - Add new intents (1 hour)
10. `command_controller/llm.py` - Update prompt (30 minutes, optional)

**Checkpoint:** Validate new intents parse correctly

---

### Phase 6: Subject-Aware Execution (Milestone 9) - OPTIONAL
11. `command_controller/engine.py` - Add subject extraction (1 hour)

**Checkpoint:** Log subject groups for sample commands

---

### Phase 7: Testing & Documentation (Milestone 10)
12. Create all test files (3-4 hours)
13. Run regression tests on existing workflows (1 hour)
14. Update documentation with examples (1 hour)

**Checkpoint:** All tests pass, documentation complete

---

## Critical Path Files

These files are on the critical path and must be completed in order:

1. `config/app_settings.json` (M1)
2. `command_controller/executors/base.py` (M2)
3. `command_controller/url_resolver.py` (M3)
4. `command_controller/fallback_chain.py` (M4)
5. `command_controller/web_executor.py` (M6)
6. `command_controller/executor.py` (M7)
7. `command_controller/intents.py` (M8)

**Estimated Critical Path Time**: 8-12 hours of focused development

---

## Parallel Development Opportunities

These files can be developed in parallel after dependencies are met:

**After M2 (ExecutionResult complete):**
- `command_controller/url_resolver.py` (M3)
- `command_controller/subject_extractor.py` (M5)

**After M3 (URLResolver complete):**
- `command_controller/fallback_chain.py` (M4)
- `tests/test_url_resolver.py` (M10)

**After M7 (Integration complete):**
- `command_controller/intents.py` (M8)
- `command_controller/engine.py` (M9, optional)
- All test files (M10)

---

## Backward Compatibility Checklist

Files that MUST maintain backward compatibility:

- ✅ `command_controller/executors/base.py` - New fields are optional
- ✅ `command_controller/executor.py` - Falls back to basic result if no metadata
- ✅ `command_controller/web_executor.py` - Legacy path if `use_playwright_for_web=false`
- ✅ `command_controller/intents.py` - New intents don't break existing validation

Files that can break compatibility (new files):
- N/A - All new files, no existing consumers

---

## File Dependencies Diagram

```
config/app_settings.json
    ↓
[All modules use get_settings()]
    ↓
url_resolution_cache.py
    ↓
url_resolver.py
    ↓
fallback_chain.py
    ↓
web_executor.py ←── subject_extractor.py (optional)
    ↓
executor.py
    ↓
engine.py
```

**Dependency Notes:**
- URLResolver depends on URLResolutionCache
- FallbackChain depends on URLResolver
- WebExecutor depends on FallbackChain
- Executor depends on WebExecutor
- Engine depends on Executor
- SubjectExtractor is standalone (only used by Engine if enabled)

---

## File Size Estimates (for Planning)

| File | Category | Estimated Lines | Complexity |
|------|----------|----------------|------------|
| url_resolver.py | New | 300-400 | High |
| fallback_chain.py | New | 200-250 | Medium |
| subject_extractor.py | New | 150-200 | Medium |
| url_resolution_cache.py | New | 60-80 | Low |
| web_executor.py | Modified | +150-200 | High |
| executor.py | Modified | +20-30 | Low |
| base.py | Modified | +10-15 | Low |
| intents.py | Modified | +40-50 | Medium |
| engine.py | Modified (opt) | +15-20 | Low |
| Test files (6 total) | New | 800-1000 | Medium |

**Total Implementation Effort**: ~1700-2200 new/modified lines (excluding docs)

---

## Risk Mitigation per File

**High-Risk Files** (refactoring existing critical paths):
- `web_executor.py` - Mitigation: Preserve legacy path, feature toggle
- `executor.py` - Mitigation: Check attribute existence before access

**Medium-Risk Files** (new complex logic):
- `url_resolver.py` - Mitigation: Extensive unit tests, timeout handling
- `fallback_chain.py` - Mitigation: Config toggles for each fallback

**Low-Risk Files** (additive changes):
- `base.py` - Mitigation: Optional fields, backward-compatible serialization
- `intents.py` - Mitigation: New intents don't affect existing validation

---

This file map provides a complete inventory of all files involved in the executor rework, organized by action type, milestone, and implementation priority. Use this as a checklist during development to ensure no files are missed.
