# AGENTS

Project quickstart and conventions for coding agents. This file is intended to
be the single source of context when resetting a session.

## Overview
- Hand + voice control system with gesture ML pipeline, voice STT, and Tauri + React desktop UI.
- Python entrypoint: `main.py` launches the Tauri desktop app and sets up env loading.
- FastAPI server for web UI: `api/server.py`.

## Project map (what lives where)
- `main.py`: entrypoint; loads env files, enforces Python 3.11, and launches the Tauri desktop app.
- `command_controller/`: command routing (`controller.py`), execution (`executor.py` placeholder), logging (`logger.py`).
- `gesture_module/`: realtime recognizer (`gesture_recognizer.py`), workflow wrapper (`workflow.py`), basic tracking (`hand_tracking.py`).
- `video_module/gesture_ml.py`: dataset, training (MLP), inference smoothing, and sample collection.
- `voice_module/`: mic listener (`voice_listener.py`), STT engine (`stt_engine.py`), whisper backends.
- `api/server.py`: FastAPI endpoints used by the React UI.
- `ui/`: legacy PySide6 desktop UI (no longer used).
- `webui/`: React + Vite UI (`webui/src/App.jsx`, `webui/src/api.js`).
- `config/`: JSON configs for gestures, voice, app settings, and command mapping.
- `user_data/<user_id>/`: persisted datasets, labels, hotkeys, and trained model.

## Requirements
- Python 3.11.x (MediaPipe compatibility).
- Optional deps:
  - `python-dotenv` for `env/.env`.
  - `pyaudio` for microphone capture.
  - `faster-whisper` for local Whisper STT.
  - `websockets` >= 12 for OpenAI Realtime STT.
- Node 18+ for the web UI (`webui`).

## Run
- Desktop app (Tauri):
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
- Gesture training (desktop or web UI): collect static/dynamic samples, save dataset, then train and save model.
- Gesture recognition (desktop or web UI): open camera, recognize labels, emit `CommandController.handle_event`.
- Voice recognition: mic audio is streamed to STT provider, transcript is forwarded to `CommandController.handle_event`.

## Gesture ML pipeline (details)
- Input features: 21 hand landmarks * 3 dims = 63 floats per frame.
- Dynamic gestures are flattened into windows: `window_size * 63`.
- `GestureCollector` captures frames, normalizes landmarks, and builds windows.
- `GestureTrainer` trains an `MLPClassifier` from scratch each time.
- `GestureRecognizer` applies confidence thresholding and stability (streak) logic.
- If no model is trained, `GestureDataset.build_none_only_artifacts` creates a fallback model that always returns `NONE`.

## API endpoints (FastAPI)
- `GET /gestures` → `{ items: [{ label, hotkey? }] }`
- `POST /gestures/static` → collect static samples and save hotkey
- `POST /gestures/dynamic` → collect dynamic samples and save hotkey
- `POST /gestures/delete` → delete a gesture and its samples
- `POST /train` → train model (requires samples)
- `POST /recognition/start` → starts realtime recognition
- `POST /recognition/stop` → stops realtime recognition
- `GET /recognition/last` → last detection info
- `GET /status` → recognition status + user id

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
- `scripts/import_preset_gestures.py` imports CSV presets into a user dataset and trains.
- Expects `data/presets/keypoint.csv` and `data/presets/keypoint_classifier_label.csv`.

## Notes for edits
- Keep code ASCII-only unless a file already uses Unicode.
- Avoid changing unrelated files or generated artifacts.
- If you touch training, keep input dimension logic aligned with `window_size * 63`.
- UI collects gesture samples, then calls training; API endpoints mirror these flows.

## Testing
- No formal test suite in repo. For manual checks, run the desktop app or API + web UI.

## Current working context (session-specific)
- OS/IDE: macOS (Apple Silicon), using PyCharm; run configs live in `.idea/workspace.xml`.
- Primary interpreter (working): `/Users/isaaccohen/.conda/envs/Back-Hackathon2025/bin/python`.
- Alternate interpreter used earlier: `/opt/homebrew/Caskroom/miniconda/base/envs/qt/bin/python` (Qt works there too).
- The `.idea` configs were patched to point to the Back-Hackathon2025 conda env:
  - `.idea/misc.xml` uses `Python 3.11 (Back-Hackathon2025)`
  - `.idea/workspace.xml` run configs `Backend` + `NativeWindow` set `SDK_HOME` to the conda env path.
- If PyCharm still runs the wrong env, restart PyCharm so it reloads `.idea` changes.

## Recent UI changes
- `ui/main_window.py` replaced with an "Enhanced" UI that matches the web UI styling.
- New elements: custom `GestureRow` widget, scroll area list, banners, larger spacing, updated styles.
- Uses `APP_NAME` from `config/app_settings.json`, falling back to "Gesture Control".
- Window icon path uses `ui/assets/icons/<app_name>.png` (lowercase, spaces -> underscores).

## Packaging (macOS .app)
- PyInstaller setup added:
  - Spec file: `pyinstaller_easy.spec` (builds `easy.app` and bundles `config/`, `data/presets/`, `ui/assets/`).
  - Build script: `scripts/build_macos_app.sh` (cds to repo root).
- Build output: `dist/easy.app`. Signing may warn about resource forks; use:
  - `xattr -cr dist/easy.app` or `xattr -cr <repo>` before rebuilding if needed.
- Optional icon for bundle: `ui/assets/icons/easy.icns` (if present).

## Dependency setup notes
- The Back-Hackathon2025 conda env was repaired:
  - Upgraded `pip`/`setuptools` to fix `_distutils_hack`.
  - Installed `joblib`.
  - Installed project deps via `pip install -e .` (pyproject.toml).

## Known run commands
- Run desktop app (conda env): `/Users/isaaccohen/.conda/envs/Back-Hackathon2025/bin/python main.py`
- Build macOS app bundle: `scripts/build_macos_app.sh`
