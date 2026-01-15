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
## Recent Context (CodexCommandGesture)
- Integrated MediaPipe + TFLite pipeline into `gesture_module/` + `video_module/`, replacing scikit approach.
- Pipeline (mirrors other project):
  - OpenCV capture, flip horizontally, BGR -> RGB for MediaPipe.
  - MediaPipe Hands (max_num_hands=1) yields 21 landmarks.
  - Static features: wrist-relative 21 (x,y) -> 42 floats, normalized by max abs.
  - Motion features: 16-frame point history of index fingertip (8) -> 32 floats.
  - Two TFLite classifiers (static + point history), smoothing by recent predictions.
- Presets: static + motion label CSVs and models copied into `user_data/<user_id>/keypoint_classifier/` and `user_data/<user_id>/point_history_classifier/` from `data/presets/`. Ensure preset folder structure exists before writing.
- Default FPS cap: 10 (settings).
- Other project reference copied to repo root: `hand-gesture-recognition-mediapipe/` (app.py, models, utils, notebooks).
- TensorFlow/protobuf warnings in runtime; PyAutoGUI can hit failsafe (mouse to corner). XNNPACK delegate logs expected.
- UI polls `/commands/pending` frequently.
- Known behavior/issues:
  - Run/stop slow on first camera start; ok after toggling.
  - Settings edits while camera running do not apply immediately.
  - Occasional freeze showing `NONE|`.
  - CPU spikes reported earlier.
  - Gestures detected even when disabled.
  - macOS beep on open/close gesture command actions.
  - Commands sometimes not executing.
[Session Addendum — 2025-01-09]
Context saved for continuation.

Work completed (high level):
- Switched gesture pipeline to MediaPipe + TFLite classifiers (static + point-history), replacing scikit MLP runtime for inference.
- Added fps cap setting (default 10), plus per-command timeout and a watchdog.
- Presets bootstrap now copies TFLite models + label CSVs into user_data on first run.

Key files added/updated:
- video_module/tflite_pipeline.py
- video_module/tflite_classifiers.py
- video_module/gesture_ml.py (preset bootstrap, pipeline integration)
- gesture_module/workflow.py / gesture_module/gesture_detector.py / gesture_module/hand_tracking.py
- api/server.py, webui/src/App.jsx, webui/src/api.js
- config/app_settings.json (new settings)

Presets/paths:
- Presets live in data/presets/.
- On startup, user_data/<user_id>/point_history_classifier/ and keypoint_classifier/ are created + labels/models copied.

Known runtime issues (user reported):
- First recognition start is slow; toggling run/stop once makes it stable.
- Commands sometimes execute multiple times per gesture; Open/Close triggers often repeat.
- Occasional freeze with detected label stuck at "NONE|" after executing commands.
- PyAutoGUI fail-safe triggers if cursor hits corner; this breaks command execution.
- LLM latency spikes (1-13s) cause command delays; shortcut matches bypass LLM.
- Settings changes while camera is running do not apply immediately.
- App beeps on Close/Open (macOS rejects some key events).
- Detection was matching all gestures, not only enabled ones (needs filtering).

TensorFlow/protobuf notes:
- TensorFlow kept for notebooks only; runtime uses TFLite.
- Earlier error: protobuf runtime_version import missing; fixed via protobuf pin.
- Warnings still appear (tf.lite.Interpreter deprecation, protobuf SymbolDatabase).

Commands/polling:
- /commands/pending polling is used for pending confirmations in the UI.

Branch/PR notes:
- Conflicts reported in PR: AGENTS.md, command_controller/controller.py, command_controller/engine.py, command_controller/executor.py, command_controller/llm.py, video_module/gesture_ml.py, webui/src/App.jsx, webui/src/api.js.
- Branches in play: command-gestures / command_gestures, Hand-mouse-implementation.

Open questions/todos:
- Filter gesture detection to only enabled gestures.
- Apply settings changes during recognition (restart or hot-reload behavior).
- Address command execution beeps + fail-safe; consider safer key injection.
- Tighten debouncing to avoid duplicate triggers.
