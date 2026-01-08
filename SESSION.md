CodexCommandController
======================

Repo Defaults
- Remote: origin (https://github.com/Isaac-M-Cohen/Back-Hackathon2025.git)
- PR base: main
- PR head: current working branch

Context
- Branch: command-gestures (main merged in separate worktree and pushed to PR branch).
- Focus: command controller pipeline, local LLM (Ollama), gesture-triggered execution, and UI command mapping.

Key work done
- Local LLM interpreter (Ollama) + intent schema + safety confirmation queue.
- Per-gesture command storage in `user_data/<user_id>/commands.json` (via `/gestures/command`).
- UI command editor + confirmation modal; startup health screen; backend `/health` endpoint with Ollama auto-start.
- Gesture execution now intended to be edge-triggered (fire on NONE -> LABEL).
- Added context capture (mouse position, active window title, selection text length) to pass into LLM; clipboard read uses copy + restore.
- Logging: backend logs `/health` polls and LLM parse time.

Current issues
- Automation sometimes not executing: macOS Accessibility/Input Monitoring permissions required for Terminal/PyCharm/python/Easy.
- Gesture command "copy selection" inconsistent; intended to add shortcut mapping (cmd/ctrl+c) but shortcut stash could not be applied due to local uncommitted changes.
- LLM latency observed (3s–15s). User wants fully LLM-driven with context on gesture transitions only.

Pending items
- Resolve stash conflict: `git stash pop` fails because of local changes in `command_controller/engine.py`.
- Decide whether to commit current context/edge-trigger changes before applying the shortcut mapping stash.
- Implement execution throttling and confirm edge-trigger behavior in `gesture_module/gesture_recognizer.py`.
- Confirm clipboard read performance; selection read uses copy without paste.

User requests
- Unstash the shortcut mapping changes (copy/paste aliases).
- Keep session context in this file and update AGENTS.md.
