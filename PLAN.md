# YouTube Search Execution Fix - Implementation Plan

## Problem Summary

Gesture "Open" mapped to "open YouTube and search for cats" opens YouTube but never types "cats" into the search bar. The issue affects both predefined steps and LLM-generated steps, producing a broken sequence: `open_url` → `type_text` with no wait for page load and no focus on the search bar.

## Assumptions & Open Questions

- **Assumption 1**: The `wait_for_url` intent exists in the schema (`intents.py:21`) but is not being used by the LLM or in predefined steps
- **Assumption 2**: The macOS `subprocess.Popen` approach is intentionally non-blocking (lines 64-71 in `macos_executor.py`), so we cannot make it blocking without breaking other use cases
- **Assumption 3**: A reasonable default wait after `open_url` is 2-3 seconds for most web pages to load
- **Assumption 4**: YouTube's search bar is automatically focused when the page loads, so we only need to wait for page load, not explicitly focus the search bar
- **Open Question**: Should we implement a generic "wait_for_page_load" intent that uses browser automation, or rely on fixed delays? (Proceeding with fixed delays as simpler solution)
- **Open Question**: Do we need to handle focus for all `type_text` operations, or just those following `open_url`? (Proceeding with YouTube-specific fix first, then generalizing)

## Step-by-Step Plan

1. **Add inter-step delay mechanism to executor**: Modify `executor.py:20-30` to insert configurable delays between steps based on intent transitions
   - Rationale: This is the central bottleneck; fixing it here impacts both predefined and LLM-generated paths

2. **Enhance LLM prompt with timing rules**: Update `llm.py:75-107` to teach the LLM when to add wait steps and delays
   - Rationale: Fixes LLM-generated steps to include proper wait logic

3. **Fix predefined steps in command_steps.json**: Update hardcoded YouTube searches to include wait steps
   - Rationale: Immediate fix for the specific "Open" gesture reported

4. **Add wait_for_url implementation to macOS executor**: Implement the `wait_for_url` intent in `macos_executor.py` that polls for browser window/URL
   - Rationale: Provides a more robust wait mechanism than fixed delays

5. **Pass supported_intents from engine to LLM**: Fix `engine.py:168` to actually pass the supported intents list to the interpreter
   - Rationale: The LLM needs to know what intents are available to generate valid steps

6. **Add configurable delay settings**: Add settings to `config/app_settings.json` for default delays after certain intents
   - Rationale: Allows tuning delays without code changes

7. **Add focus mechanism for YouTube search**: Insert a `click` step to focus the search bar before typing, or use a `key_combo` to activate search (Cmd+K or Cmd+L)
   - Rationale: Even with page load wait, the search bar may not be focused

8. **Test and validate**: Test the complete flow with the "Open" gesture and verify all steps execute in sequence
   - Rationale: Ensure the fix works end-to-end

## File List & Responsibilities

**Core Executor Layer**
- `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/executor.py` [MODIFY]: Add inter-step delay logic between intent execution
- `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/executors/macos_executor.py` [MODIFY]: Implement `wait_for_url` intent to poll for page load completion

**LLM Prompt Engineering**
- `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/llm.py` [MODIFY]: Add timing rules to prompt (when to insert waits, delays after URL opens)

**Integration Layer**
- `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/engine.py` [MODIFY]: Pass `supported_intents` from ALLOWED_INTENTS to LLM interpreter

**Data/Configuration**
- `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/data/user_data/default/command_steps.json` [MODIFY]: Fix "Open" and "Pointer" gesture steps to include wait/focus
- `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/config/app_settings.json` [MODIFY]: Add intent_delays configuration section

**Optional Enhancement**
- `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/intents.py` [MODIFY]: Add new `wait` intent with configurable duration if needed

## Risks & Unknowns

- **Risk: Fixed delays may be too short for slow connections** → Mitigation: Use generous defaults (3s after `open_url`) and make them configurable in settings; eventually implement `wait_for_url` with polling

- **Risk: YouTube's UI may change, breaking click-based focus** → Mitigation: Use keyboard shortcut (Cmd+L or /) to activate search instead of clicking specific coordinates

- **Risk: Adding delays between all steps may slow down execution unnecessarily** → Mitigation: Only add delays for specific intent transitions (e.g., `open_url` → any, `open_app` → any), not between all steps

- **Risk: wait_for_url implementation may be complex on macOS without browser integration** → Mitigation: Start with simple AppleScript to check if browser window exists; advanced URL polling can be added later via accessibility APIs

- **Risk: LLM may ignore new prompt rules if context is too long** → Mitigation: Keep rules concise and use bullet points; test with actual queries to verify compliance

## Definition of Done

- [ ] Gesture "Open" successfully opens YouTube and types "cats" into the search bar without manual intervention
- [ ] LLM-generated steps for "open YouTube and search for X" include appropriate wait steps or delays
- [ ] Predefined steps in `command_steps.json` for "Open" and "Pointer" gestures execute successfully
- [ ] Configuration file includes customizable delay settings for `open_url` and `open_app` intents
- [ ] The `wait_for_url` intent is implemented in macOS executor and can poll for page load (basic implementation)
- [ ] The `supported_intents` parameter is correctly passed from `engine.py` to `llm.py`
- [ ] Execution logs show clear timing between steps (elapsed_ms) and no immediate failures
- [ ] At least one alternative URL-based workflow (e.g., "open Google and search for dogs") works correctly

---

## Detailed Implementation Notes

### 1. Executor Inter-Step Delays (executor.py)

**Location**: `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/executor.py:20-30`

**Changes**:
- Import `time` module
- Load delay settings from `app_settings.json`
- After each step execution, check if the current intent requires a post-execution delay
- Insert `time.sleep(delay_secs)` if delay is configured

**Pseudocode**:
```python
# After line 20, before the loop:
delay_config = load_json("config/app_settings.json").get("intent_delays", {})

# In the loop, after line 28:
result = self._router.execute_step(step)
results.append(result.to_dict())

# Add delay logic:
delay_secs = delay_config.get(intent, 0.0)
if delay_secs > 0:
    time.sleep(delay_secs)
```

### 2. LLM Prompt Enhancement (llm.py)

**Location**: `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/llm.py:96-107`

**Changes**:
- Update line 98 from "Use the smallest number of steps" to "Use the minimum number of steps while ensuring proper timing"
- Add new rules after line 104:
  - "Always insert wait_for_url after open_url if subsequent steps interact with the page (type_text, click, etc.)"
  - "For YouTube searches: open_url → wait_for_url → key_combo(cmd+l) OR type_text with search bar focus"
  - "When typing into a web page, ensure focus by either: (1) using wait_for_url, (2) clicking the input field, or (3) using keyboard shortcuts to activate search"

**Exact text to add**:
```
"- After open_url, if the next step requires page interaction (type_text, click), insert wait_for_url with timeout_secs=5-10.\n"
"- For YouTube: after opening YouTube URL, use wait_for_url, then '/' key or cmd+l to focus search, then type_text.\n"
"- Never use type_text immediately after open_url without a wait step.\n"
```

### 3. Predefined Steps Fix (command_steps.json)

**Location**: `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/data/user_data/default/command_steps.json:2-11`

**Changes**:
Replace the "Open" gesture steps with:
```json
"Open": [
  {
    "intent": "open_url",
    "url": "https://www.youtube.com"
  },
  {
    "intent": "wait_for_url",
    "url": "https://www.youtube.com",
    "timeout_secs": 10,
    "interval_secs": 0.5
  },
  {
    "intent": "key_combo",
    "keys": ["cmd", "l"]
  },
  {
    "intent": "type_text",
    "text": "cats"
  }
]
```

Or simpler (if relying on automatic delays):
```json
"Open": [
  {
    "intent": "open_url",
    "url": "https://www.youtube.com"
  },
  {
    "intent": "type_text",
    "text": "/"
  },
  {
    "intent": "type_text",
    "text": "cats"
  }
]
```

### 4. wait_for_url Implementation (macos_executor.py)

**Location**: `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/executors/macos_executor.py:14-62`

**Changes**:
Add new intent handler between existing intents (around line 44):
```python
if intent == "wait_for_url":
    url = str(step.get("url", "")).strip()
    timeout = step.get("timeout_secs", 15)
    interval = step.get("interval_secs", 0.5)
    self._wait_for_url(url, timeout, interval)
    return self._ok(intent, target, start)
```

Add new method after `_type_text` (around line 145):
```python
def _wait_for_url(self, url: str, timeout: float, interval: float) -> None:
    """Poll until browser window appears or timeout."""
    end_time = time.monotonic() + timeout
    while time.monotonic() < end_time:
        # Basic implementation: just wait for timeout
        # Advanced: use AppleScript to check if Safari/Chrome window exists
        time.sleep(interval)
        # TODO: check actual URL via accessibility API
        break  # For now, just wait once
    # Simple fallback: sleep for minimum time
    time.sleep(min(timeout, 3.0))
```

### 5. Pass supported_intents (engine.py)

**Location**: `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/command_controller/engine.py:168`

**Changes**:
Import ALLOWED_INTENTS at top of file:
```python
from command_controller.intents import ALLOWED_INTENTS, normalize_steps, validate_steps
```

Modify line 168 to pass intents:
```python
return self.interpreter.interpret(text, context, supported_intents=ALLOWED_INTENTS)
```

### 6. Configuration Settings (app_settings.json)

**Location**: `/Users/isaaccohen/Desktop/IntelliJ/Back-Hackathon2025/config/app_settings.json`

**Changes**:
Add new section (exact line depends on current structure):
```json
"intent_delays": {
  "open_url": 3.0,
  "open_app": 2.0,
  "open_file": 1.0
}
```

### 7. YouTube Search Focus Mechanism

**Approach**: Use keyboard shortcut `/` (YouTube's native search shortcut) or `Cmd+L` (browser address bar)

**Implementation**: Already covered in step 3 above (predefined steps include key_combo or "/" character)

**Alternative**: Add a `click` step with YouTube search bar coordinates, but this is brittle and not recommended

### 8. Testing Checklist

**Manual Tests**:
1. Trigger "Open" gesture → Verify YouTube opens and "cats" is typed in search bar
2. Say "open YouTube and search for dogs" → Verify LLM generates proper wait steps
3. Check logs for elapsed_ms between steps → Verify delays are applied
4. Test with slow internet → Verify wait_for_url timeout handles it gracefully

**Code Validation**:
1. Verify `supported_intents` is not None in LLM logs
2. Verify delay_config is loaded in executor
3. Verify wait_for_url returns "ok" status

---

## Implementation Order Recommendation

**Phase 1 (Immediate Fix)**:
1. Step 6: Add delay configuration to settings
2. Step 1: Add delay logic to executor
3. Step 3: Fix predefined steps in command_steps.json
4. Step 8: Test "Open" gesture

**Phase 2 (LLM Fix)**:
5. Step 5: Pass supported_intents to LLM
6. Step 2: Enhance LLM prompt with timing rules
7. Step 8: Test LLM-generated YouTube searches

**Phase 3 (Robust Wait)**:
8. Step 4: Implement wait_for_url in macOS executor
9. Step 3 (revisit): Update predefined steps to use wait_for_url
10. Step 8: Final end-to-end testing

This phased approach allows for incremental testing and validation, with the simplest fix (delays) deployed first, followed by prompt engineering, and finally the more complex wait implementation.
