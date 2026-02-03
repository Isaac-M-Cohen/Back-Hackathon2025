# Executor Rework: Milestones

## Overview
This document outlines the phased implementation of the headless Playwright-based web navigation system with modular fallbacks, subject extraction, and structured execution results.

---

## Milestone 1: Configuration Infrastructure
**Goal**: Add all configuration toggles to app_settings.json and create a settings accessor for web executor features.

**Scope**:
- Add new config fields to app_settings.json:
  - `use_playwright_for_web` (bool, default: true)
  - `request_before_open_url` (bool, default: false)
  - `enable_search_fallback` (bool, default: true)
  - `enable_homepage_fallback` (bool, default: true)
  - `allow_headless_form_fill` (bool, default: false)
  - `search_engine_url` (string, default: "https://duckduckgo.com/?q={query}")
  - `playwright_navigation_timeout_ms` (int, default: 30000)
- Update existing `playwright_headless` setting documentation to clarify headless mode usage
- No code changes yet, just configuration foundation

**Deliverables**:
- Updated config/app_settings.json with new fields
- Config schema validation ready for implementation

**Dependencies**: None

**Estimated Complexity**: Low

---

## Milestone 2: Enhanced ExecutionResult Structure
**Goal**: Extend ExecutionResult to support rich metadata for web navigation and fallback tracking.

**Scope**:
- Update ExecutionResult dataclass in command_controller/executors/base.py to add optional fields:
  - `resolved_url` (str | None): Final URL after navigation/resolution
  - `fallback_used` (str | None): Which fallback was triggered (e.g., "search", "homepage", "none")
  - `navigation_time_ms` (int | None): Time spent navigating
  - `dom_search_query` (str | None): What was searched in DOM if applicable
- Ensure backward compatibility with existing ExecutionResult usage
- Update to_dict() method to include new fields when present

**Deliverables**:
- Extended ExecutionResult class
- All existing executors continue to work without modification

**Dependencies**: Milestone 1

**Estimated Complexity**: Low

---

## Milestone 3: URL Resolution Engine
**Goal**: Build a headless Playwright-based URL resolver that searches DOM for deep links and returns final URLs.

**Scope**:
- Create new module: command_controller/url_resolver.py
- Implement URLResolver class with methods:
  - `resolve_url(query: str) -> URLResolutionResult`: Takes a search query or partial URL, navigates headless, searches DOM for relevant links, returns final URL
  - `_search_dom_for_links(page, query) -> list[str]`: Extract candidate URLs from DOM based on text matching
  - `_rank_candidates(candidates, query) -> str`: Simple ranking to pick best match
- Use Playwright in headless mode regardless of global headless setting
- Implement timeout handling based on playwright_navigation_timeout_ms config
- Return structured URLResolutionResult with status, resolved_url, search_query, candidates_found, selected_reason

**Deliverables**:
- command_controller/url_resolver.py with URLResolver class
- Unit-testable URL resolution logic
- Does NOT integrate with executor yet

**Dependencies**: Milestone 2

**Estimated Complexity**: High

---

## Milestone 4: Fallback Chain System
**Goal**: Create a modular fallback system that tries URL resolution, then search engine, then homepage.

**Scope**:
- Create new module: command_controller/fallback_chain.py
- Implement FallbackChain class with methods:
  - `execute(query: str, config: dict) -> FallbackResult`: Orchestrates fallback attempts
  - `_try_direct_resolution(query) -> FallbackResult | None`: Try URLResolver first
  - `_try_search_fallback(query) -> FallbackResult | None`: Fallback to search engine with query
  - `_try_homepage_fallback(query) -> FallbackResult | None`: Fallback to domain homepage
- Check config toggles before each fallback attempt
- Return FallbackResult with final_url, fallback_used, attempts_made
- Each fallback attempt should be logged at DEEP level

**Deliverables**:
- command_controller/fallback_chain.py with FallbackChain class
- Toggle-aware fallback orchestration
- Does NOT integrate with executor yet

**Dependencies**: Milestone 3

**Estimated Complexity**: Medium

---

## Milestone 5: Subject Extraction Module
**Goal**: Extract distinct subjects and child actions from complex commands.

**Scope**:
- Create new module: command_controller/subject_extractor.py
- Implement SubjectExtractor class with methods:
  - `extract(text: str, steps: list[dict]) -> list[SubjectGroup]`: Group steps by subject
  - `_identify_subjects(text, steps) -> list[str]`: Identify distinct entities/apps/urls in command
  - `_assign_steps_to_subjects(subjects, steps) -> list[SubjectGroup]`: Associate steps with subjects
- SubjectGroup dataclass contains: subject_name, subject_type (url/app/file), steps
- Handle cases where no clear subject exists (return single group with all steps)
- Integrate with LLM context to improve subject identification

**Deliverables**:
- command_controller/subject_extractor.py with SubjectExtractor class
- Subject grouping logic that preserves step execution order
- Does NOT integrate with executor yet

**Dependencies**: Milestone 2

**Estimated Complexity**: Medium

---

## Milestone 6: Web Executor Rework
**Goal**: Refactor WebExecutor to use URL resolution, fallback chain, and return enhanced ExecutionResults.

**Scope**:
- Update command_controller/web_executor.py:
  - Integrate URLResolver for open_url intents
  - Integrate FallbackChain for failed URL resolutions
  - Update _handle_open_url to:
    1. Check use_playwright_for_web config
    2. Try URL resolution first (if deep link/query)
    3. Apply fallback chain if resolution fails
    4. Check request_before_open_url config before opening in user's browser
    5. Open resolved URL in user's default browser (using macOS `open` command or OS equivalent)
    6. Return enriched ExecutionResult with resolved_url, fallback_used
  - Add _handle_form_fill method for web form interactions (gated by allow_headless_form_fill)
  - Add permission hook infrastructure for future extensions
- Maintain backward compatibility with existing web intents
- Ensure headless profile is separate from headed profile to avoid lock conflicts

**Deliverables**:
- Refactored command_controller/web_executor.py with URL resolution
- Enhanced open_url handling with fallback support
- Form fill infrastructure ready for future use

**Dependencies**: Milestones 3, 4

**Estimated Complexity**: High

---

## Milestone 7: Executor Integration
**Goal**: Update main Executor class to use enhanced WebExecutor and pass config through.

**Scope**:
- Update command_controller/executor.py:
  - Pass settings to WebExecutor on initialization
  - Update _execute_web_step to handle new ExecutionResult fields
  - Ensure resolved_url and fallback_used are propagated to engine results
  - Maintain existing web chain inference logic
- Update command_controller/engine.py:
  - Log enhanced execution results at appropriate levels
  - Include resolved_url in result payloads returned to API clients
- No changes to intent validation or step normalization needed

**Deliverables**:
- Updated executor.py with enhanced result handling
- Updated engine.py with enhanced logging
- End-to-end flow from command to enhanced result

**Dependencies**: Milestone 6

**Estimated Complexity**: Medium

---

## Milestone 8: Intent Schema Extensions
**Goal**: Add new intents for web actions (form fills, clicks, permission hooks).

**Scope**:
- Update command_controller/intents.py:
  - Add `web_fill_form` intent with fields: form_fields (dict), submit (bool)
  - Add `web_request_permission` intent for future permission dialogs
  - Update ALLOWED_INTENTS set
  - Add validation for new intents in validate_step
- Update LLM prompt in command_controller/llm.py to include new intent documentation
- Document new intents in intent schema comments

**Deliverables**:
- Extended intent schema with web action support
- LLM aware of new intents
- Validation for new intent structures

**Dependencies**: Milestone 7

**Estimated Complexity**: Low

---

## Milestone 9: Subject-Aware Execution (Optional Enhancement)
**Goal**: Use subject extraction to optimize command execution and provide better context.

**Scope**:
- Update command_controller/engine.py:
  - Integrate SubjectExtractor after step normalization
  - Log subject groupings at DEBUG/DEEP level
  - Optionally execute subject groups in parallel (if no dependencies)
  - Include subject metadata in execution results for debugging
- This is an optional enhancement and can be deferred
- Focus on correctness first, performance optimization second

**Deliverables**:
- Subject-aware execution in engine.py
- Enhanced logging with subject context
- Foundation for parallel execution (not implemented yet)

**Dependencies**: Milestones 5, 7

**Estimated Complexity**: Medium

---

## Milestone 10: Testing & Documentation
**Goal**: Validate all features work end-to-end and document the new capabilities.

**Scope**:
- Create test commands covering:
  - Direct URL navigation
  - URL resolution with DOM search
  - Search engine fallback
  - Homepage fallback
  - Form fill interactions (if implemented)
  - Subject extraction with multi-subject commands
- Document new config options in app_settings.json comments
- Document new intent schemas in intents.py docstrings
- Create examples of common use cases in project docs
- Test all config toggle combinations
- Verify backward compatibility with existing commands

**Deliverables**:
- Comprehensive test coverage
- Updated documentation
- Example commands demonstrating new features
- Regression test confirmation

**Dependencies**: Milestones 1-9

**Estimated Complexity**: Medium

---

## Summary

**Total Milestones**: 10 (with Milestone 9 optional)

**Critical Path**:
M1 → M2 → M3 → M4 → M6 → M7 → M8 → M10

**Parallel Opportunities**:
- M3 and M5 can be developed in parallel after M2
- M4 depends on M3 but not M5
- M8 can start after M7 completes

**Estimated Total Complexity**: High
