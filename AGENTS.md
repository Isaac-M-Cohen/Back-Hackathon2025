# AGENTS

Project quickstart and conventions for coding agents. This file is intended to
be the single source of context when resetting a session.

## Overview
- Hand + voice control system with gesture ML pipeline, voice STT, and Tauri + React desktop UI.
- Python entrypoint: `main.py` launches the Tauri desktop app and sets up env loading.
- FastAPI server for web UI: `api/server.py`.
- Windows-first target; macOS support is for local development.
- Session notes: see `SESSION.md` for in-progress context.

## Project map (what lives where)
- `main.py`: entrypoint; loads env files, enforces Python 3.11, and launches the Tauri desktop app.
- `command_controller/`: command routing (`controller.py`), execution (`executor.py` placeholder), logging (`logger.py`).
- `gesture_module/`: realtime recognizer (`gesture_recognizer.py`), workflow wrapper (`workflow.py`), basic tracking (`hand_tracking.py`).
- `video_module/gesture_ml.py`: dataset + sample collection for TFLite keypoint/point-history classifiers.
- `voice_module/`: mic listener (`voice_listener.py`), STT engine (`stt_engine.py`), whisper backends.
- `api/server.py`: FastAPI endpoints used by the React UI.
- `ui/`: legacy PySide6 desktop UI (no longer used).
- `webui/`: React + Vite UI (`webui/src/App.jsx`, `webui/src/api.js`).
- `config/`: JSON configs for gestures, voice, app settings, and command mapping.
- `user_data/<user_id>/`: persisted datasets, labels, hotkeys, and trained model.

## Requirements
- Python 3.11.x (MediaPipe compatibility).
- Local LLM runtime for command interpretation: Ollama (local-only, no cloud).
- Optional deps:
  - `python-dotenv` for `env/.env`.
  - `pyaudio` for microphone capture.
  - `faster-whisper` for local Whisper STT.
  - `websockets` >= 12 for OpenAI Realtime STT.
- Node 18+ for the web UI (`webui`).

## Run
- Desktop app (Tauri, dev on macOS):
  - `python main.py` (runs `npm run tauri:dev` by default)
  - Or `cd webui && npm run tauri:dev`
- API server:
  - `python -m uvicorn api.server:app --reload --host 0.0.0.0 --port 8000`
- Web UI:
  - `cd webui && npm install && npm run dev`

## Environment variables
- `OPENAI_API_KEY` required for OpenAI Realtime STT.
- `STT_PROVIDER` can be `openai-realtime`, `whisperlive`, or `whisper-local`.
- `OPENAI_REALTIME_MODEL`, `OPENAI_REALTIME_URL`, `OPENAI_TRANSCRIPTION_MODEL`, `OPENAI_TRANSCRIPTION_LANGUAGE` for Realtime STT config.
- `WHISPERLIVE_URL`, `WHISPERLIVE_MODEL`, `WHISPERLIVE_LANGUAGE`, `WHISPERLIVE_CHUNK_MS` for WhisperLive.
- `LOCAL_WHISPER_MODEL_PATH`, `LOCAL_WHISPER_DEVICE`, `LOCAL_WHISPER_COMPUTE_TYPE`, `LOCAL_WHISPER_LANGUAGE` for local Whisper.
- `GESTURE_USER_ID` to select a user profile.
- `ENABLE_VOICE=0` to disable voice in the backend (API/sidecar).

## Core flows (high level)
- Gesture training (desktop or web UI): collect static/dynamic samples to CSVs, then train TFLite models via notebooks.
- Gesture recognition (desktop or web UI): open camera, recognize labels, emit `CommandController.handle_event`.
- Voice recognition: mic audio is streamed to STT provider, transcript is forwarded to `CommandController.handle_event`.

## Gesture ML pipeline (details)
- Input features: 21 hand landmarks (x,y) = 42 values for static sign classification.
- Motion gestures use point history: 16 frames of index fingertip (x,y) = 32 values.
- `GestureCollector` captures frames and writes rows to CSVs under `user_data/<user_id>/`.
- TFLite classifiers are loaded from:
  - `user_data/<user_id>/keypoint_classifier/keypoint_classifier.tflite`
  - `user_data/<user_id>/point_history_classifier/point_history_classifier.tflite`
- Labels are read from the corresponding `*_label.csv` files.

## API endpoints (FastAPI)
- `GET /gestures` → `{ items: [{ label, hotkey? }] }`
- `POST /gestures/command` → set command text for a gesture
- `POST /gestures/static` → collect static samples and save hotkey
- `POST /gestures/dynamic` → collect dynamic samples and save hotkey
- `POST /gestures/delete` → delete a gesture and its samples
- `POST /train` → returns an error; training is done via the notebooks
- `POST /recognition/start` → starts realtime recognition
- `POST /recognition/stop` → stops realtime recognition
- `GET /recognition/last` → last detection info
- `GET /status` → recognition status + user id
- `GET /health` → backend + local LLM readiness
- `GET /commands/pending` → list pending confirmations
- `POST /commands/confirm` → approve a pending command
- `POST /commands/deny` → deny a pending command

## Desktop UI (Tauri + React)
- `webui/` provides the desktop UI inside a Tauri shell.
- The UI calls the FastAPI backend endpoints for gesture workflows.

## Web UI (React)
- `webui/src/App.jsx` mirrors desktop functionality for:
  - List/add/delete gestures, hotkey entry, train, and recognition control.
  - Polls `/recognition/last` while running to show detections.
- `webui/src/api.js` centralizes API calls; `VITE_API_BASE` overrides default.

## Command mapping (future integration)
- `config/command_map.json` defines mappings for gestures and voice phrases.
- `command_controller/executor.py` is a placeholder for OS automation hooks.
- `voice_module/voice_utils.py` normalizes phrases for matching.

## Data + artifacts
- Per-user datasets and models stored in `user_data/<user_id>/`.
- Preset data files live in `data/presets/`.
- Configs are in `config/*.json`.

## Preset import script
- `scripts/import_preset_gestures.py` copies preset CSVs into `user_data/<user_id>/keypoint_classifier/`.
- Expects `data/presets/keypoint.csv` and `data/presets/keypoint_classifier_label.csv`.

## Notes for edits
- Keep code ASCII-only unless a file already uses Unicode.
- Avoid changing unrelated files or generated artifacts.
- If you touch training, keep input dimensions aligned with 42 (keypoint) and 32 (point history).
- UI collects gesture samples, then calls training; API endpoints mirror these flows.

## Testing
- No formal test suite in repo. For manual checks, run the desktop app or API + web UI.

## Current working context (session-specific)
- OS/IDE: macOS (Apple Silicon), using PyCharm; run configs live in `.idea/workspace.xml`.
- Ensure PyCharm points to the active Python 3.11 interpreter you want to use.

## Recent UI changes
- `ui/main_window.py` replaced with an "Enhanced" UI that matches the web UI styling.
- New elements: custom `GestureRow` widget, scroll area list, banners, larger spacing, updated styles.
- Uses `APP_NAME` from `config/app_settings.json`, falling back to "Gesture Control".
- Window icon path uses `ui/assets/icons/<app_name>.png` (lowercase, spaces -> underscores).

## Dependency setup notes
- Install project deps via `pip install -e .` (pyproject.toml).

## Known run commands
- Run desktop app: `python main.py`

## Branching policy
- Create all new features on a new branch.
- Create fixes and feature additions on new branches as well.
- Feature branches: `feature/<short-description>` or `feat/<ticket-id>-<summary>`.
- Bug fix branches: `fix/<ticket-id>-<summary>` or `bugfix/<short-description>`.
- Hotfix branches: `hotfix/<issue-id>-<summary>`.
- Experiments/spikes: `spike/<summary>` or `experiment/<summary>`.
- Refactoring branches: `refactor/<area>`.
- Release branches: `release/<version>`.
