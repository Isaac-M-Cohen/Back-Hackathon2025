# Login Pipeline Test Plan

This document provides a comprehensive manual test checklist for the login URL precompute pipeline feature.

## Prerequisites

### Environment Setup

1. **Install Playwright:**
   ```bash
   pip install playwright
   playwright install chromium
   ```

2. **Configuration Requirements:**
   - Ensure `config/app_settings.json` has the following settings:
     ```json
     {
       "use_playwright_for_web": true,
       "warmup_url_resolver": true,
       "command_parse_timeout_secs": 15,
       "log_command_debug": true
     }
     ```

3. **Environment Variables:**
   - `GESTURE_USER_ID` (optional, defaults to "default")
   - `EASY_OLLAMA_URL` (optional, defaults to "http://127.0.0.1:11434")
   - Ensure Ollama is running with the required model

4. **Start the API Server:**
   ```bash
   python -m api.server
   ```

5. **Check Logs:**
   - Monitor terminal output for `[API]`, `[WEB_EXEC]`, `[URL_RESOLVER]`, and `[INTENTS]` log prefixes
   - For verbose logging, enable deep logging in settings

---

## Test Cases

### Test 1: Amazon Login Precompute

**Objective:** Verify that Amazon login intent is detected and precomputed correctly.

**Steps:**
1. Create a new gesture via the API or UI
2. Set the gesture command to: `"go to Amazon login"`
3. Check the API logs immediately after setting the command

**Expected Results:**
- ✅ Log message: `[API] Login intent detected for command: go to Amazon login`
- ✅ Log message: `[API] Precomputing login URL for base: https://www.amazon.com` (or similar)
- ✅ Log message: `[API] Login URL precomputed: <resolved_login_url>` (e.g., `https://www.amazon.com/ap/signin`)
- ✅ The command metadata should contain `resolved_url` field
- ✅ The command steps should have `precomputed: true`

**Execute Gesture:**
1. Trigger the gesture
2. Check execution logs

**Expected Execution Logs:**
- ✅ Log message: `[WEB_EXEC] Using precomputed URL: <resolved_login_url>`
- ✅ Browser opens directly to the login page without Playwright automation at runtime
- ✅ Amazon login page loads successfully

**Pass/Fail:** ☐

**Notes:**
_Record any discrepancies, error messages, or unexpected behavior_

---

### Test 2: Google Login Precompute

**Objective:** Verify that Google sign-in intent is detected and precomputed.

**Steps:**
1. Create a new gesture
2. Set the gesture command to: `"go to Google sign in"`
3. Check the API logs

**Expected Results:**
- ✅ Log message: `[API] Login intent detected for command: go to Google sign in`
- ✅ Log message: `[API] Precomputing login URL for base: <google_base_url>`
- ✅ Log message: `[API] Login URL precomputed: <google_signin_url>`
- ✅ Precomputed URL should point to Google accounts sign-in page

**Execute Gesture:**
1. Trigger the gesture
2. Verify browser opens to Google sign-in page

**Expected Execution Logs:**
- ✅ Log message: `[WEB_EXEC] Using precomputed URL: <google_signin_url>`
- ✅ Google sign-in page loads correctly

**Pass/Fail:** ☐

**Notes:**
_Record any observations_

---

### Test 3: GitHub Login Precompute

**Objective:** Test login precompute with GitHub.

**Steps:**
1. Create a new gesture
2. Set the gesture command to: `"go to GitHub login"`
3. Monitor logs

**Expected Results:**
- ✅ Log message: `[API] Login intent detected for command: go to GitHub login`
- ✅ Log message: `[API] Precomputing login URL for base: https://github.com`
- ✅ Log message: `[API] Login URL precomputed: https://github.com/login` (or similar)

**Execute Gesture:**
1. Trigger the gesture
2. Verify execution

**Expected Execution Logs:**
- ✅ Log message: `[WEB_EXEC] Using precomputed URL: https://github.com/login`
- ✅ GitHub login page opens successfully

**Pass/Fail:** ☐

**Notes:**

---

### Test 4: Fallback for Unknown Site

**Objective:** Verify graceful fallback when login link cannot be found.

**Steps:**
1. Create a new gesture
2. Set the gesture command to: `"go to unknownsite123.com login"`
3. Monitor logs

**Expected Results:**
- ✅ Log message: `[API] Login intent detected for command: go to unknownsite123.com login`
- ✅ Log message: `[API] Precomputing login URL for base: <base_url>`
- ✅ Either:
  - Log message: `[API] Login URL precompute failed, using fallback: <base_url>`, OR
  - Resolution succeeds with homepage URL

**Execute Gesture:**
1. Trigger the gesture
2. Check execution behavior

**Expected Execution Logs:**
- ✅ If precompute failed: Opens base URL (homepage)
- ✅ No crash or unhandled exceptions
- ✅ User can manually navigate to login from the opened page

**Pass/Fail:** ☐

**Notes:**

---

### Test 5: Empty type_text Step Handling

**Objective:** Verify that type_text steps with empty text are dropped without breaking the command.

**Steps:**
1. Manually craft a command payload that would produce a `type_text` step with empty text
   - This may require direct API testing or modifying interpreter output
   - Alternatively, create a command that results in an ambiguous query: `"go to Amazon and type"`

2. Monitor logs during command parsing

**Expected Results:**
- ✅ Log message: `[INTENTS] Dropping type_text step with empty text`
- ✅ Command parsing completes successfully
- ✅ Other valid steps are preserved

**Execute Command:**
1. Trigger the command
2. Verify execution continues without the empty type_text step

**Expected Behavior:**
- ✅ No errors or exceptions
- ✅ Command executes remaining valid steps

**Pass/Fail:** ☐

**Notes:**

---

### Test 6: Non-Login Command (Control Test)

**Objective:** Verify that non-login commands do NOT trigger login precompute logic.

**Steps:**
1. Create a new gesture
2. Set the gesture command to: `"go to Amazon"`
3. Monitor logs

**Expected Results:**
- ❌ NO log message: `[API] Login intent detected`
- ❌ NO log message: `[API] Precomputing login URL`
- ✅ Command parses normally
- ✅ Steps generated for standard navigation (not login-specific)

**Execute Gesture:**
1. Trigger the gesture
2. Verify behavior

**Expected Execution Logs:**
- ✅ Standard execution flow
- ❌ NO `[WEB_EXEC] Using precomputed URL` message
- ✅ Opens Amazon homepage

**Pass/Fail:** ☐

**Notes:**

---

### Test 7: Login Intent Variations

**Objective:** Test different phrasings of login intent.

**Commands to Test:**
- `"sign in to Netflix"`
- `"log in to Twitter"`
- `"signin to LinkedIn"`
- `"go to Facebook account login"`

**For Each Command:**
1. Set gesture command
2. Verify login intent detection in logs: `[API] Login intent detected`
3. Verify precompute attempt
4. Execute gesture and verify behavior

**Expected Results:**
- ✅ All variations trigger login intent detection
- ✅ Precompute attempts for each
- ✅ Successful execution or graceful fallback

**Pass/Fail:** ☐

**Notes:**

---

### Test 8: Cached Login URL Reuse

**Objective:** Verify that cached login URLs are reused on subsequent command sets.

**Steps:**
1. Set a gesture command to: `"go to Amazon login"`
2. Wait for precompute to complete (check logs)
3. Delete the gesture
4. Create a new gesture with the SAME command: `"go to Amazon login"`
5. Monitor logs

**Expected Results:**
- ✅ First time: Full precompute with `[API] Login URL precomputed` message
- ✅ Second time: Log message `[DEEP][API] reuse_cached_resolved` (if deep logging enabled)
- ✅ No redundant Playwright navigation on second attempt
- ✅ Both gestures execute correctly

**Pass/Fail:** ☐

**Notes:**

---

### Test 9: Precompute Timeout Handling

**Objective:** Test behavior when precompute times out.

**Steps:**
1. Temporarily reduce `command_parse_timeout_secs` in `config/app_settings.json` to a very low value (e.g., `1`)
2. Set a gesture command to: `"go to Amazon login"`
3. Monitor logs

**Expected Results:**
- ✅ Log message: `[API] Resolve steps timed out for <label>`
- ✅ Command still saves with unparsed steps
- ✅ No crash or unhandled exception

**Execute Gesture:**
1. Trigger the gesture
2. Verify fallback behavior

**Expected Behavior:**
- ✅ Falls back to dynamic resolution at runtime OR opens base URL
- ✅ No catastrophic failure

**Cleanup:**
- Restore original `command_parse_timeout_secs` value

**Pass/Fail:** ☐

**Notes:**

---

### Test 10: Playwright Not Installed Scenario

**Objective:** Test graceful degradation when Playwright is not available.

**Steps:**
1. Temporarily uninstall Playwright: `pip uninstall playwright -y`
2. Restart the API server
3. Set a gesture command to: `"go to Amazon login"`
4. Monitor logs

**Expected Results:**
- ✅ Log message indicating Playwright unavailable
- ✅ Command parsing may fail or fall back to basic URL handling
- ✅ Clear error message to user (not a cryptic stack trace)

**Execute Gesture:**
1. Trigger the gesture
2. Verify behavior

**Expected Behavior:**
- ✅ Opens URL in default browser using fallback mechanism
- ✅ No Playwright automation attempted

**Cleanup:**
- Reinstall Playwright: `pip install playwright && playwright install chromium`

**Pass/Fail:** ☐

**Notes:**

---

## Summary

**Total Tests:** 10

**Passed:** ☐

**Failed:** ☐

**Blocked:** ☐

---

## Additional Notes

### Debugging Tips

1. **Enable Deep Logging:**
   - Set `"log_level": "DEEP"` in `config/app_settings.json`
   - Restart the server
   - Check for `[DEEP][API]`, `[DEEP][WEB_EXEC]`, and `[DEEP][URL_RESOLVER]` messages

2. **Check Error Screenshots:**
   - If web execution fails, screenshots are saved to `user_data/error_screenshots/`
   - Review these for debugging

3. **Inspect Command Metadata:**
   - Query the gesture dataset to inspect stored `command_metadata`
   - Verify `resolved_url`, `steps`, and `precomputed` fields

4. **URL Resolution Cache:**
   - The URL resolver caches results for 15 minutes (TTL: 900 seconds)
   - If testing repeatedly, you may see cached results
   - Restart the server to clear the cache

### Known Limitations

- Precompute only works for login intents (sign in, log in, signin)
- Resolution uses Playwright headless browser (requires Chromium)
- Network latency may affect precompute timing
- Some sites may block automated browsing or have dynamic login pages

---

## Sign-Off

**Tester Name:** ___________________________

**Date:** ___________________________

**Environment:** ___________________________

**Overall Assessment:**
- ☐ All tests passed
- ☐ Minor issues found (document in notes)
- ☐ Major issues found (requires investigation)

**Recommendation:**
- ☐ Ready for production
- ☐ Needs additional fixes
- ☐ Blocked by external dependencies
