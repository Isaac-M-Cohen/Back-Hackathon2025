# Gesture Control Web UI

React + Vite frontend for managing gestures and starting/stopping recognition. The backend API is expected to run at `http://localhost:8000` (override with `VITE_API_BASE`).

## Commands
```bash
cd webui
npm install
npm run dev     # start dev server
npm run build   # production build
```

## Expected backend endpoints
- `GET /gestures` → `{ items: [{ label, hotkey? }] }`
- `POST /gestures/static` → `{ label, target_frames }` (opens camera to collect static samples)
- `POST /gestures/dynamic` → `{ label, repetitions, sequence_length }`
- `POST /gestures/delete` → `{ label }`
- `POST /train` → retrains model
- `POST /recognition/start` → `{ confidence_threshold, stable_frames, show_window }`
- `POST /recognition/stop`

Wire these to the Python `GestureWorkflow` methods in `gesture_module/workflow.py`.
