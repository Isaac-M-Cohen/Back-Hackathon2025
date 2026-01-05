"""FastAPI server exposing gesture workflow endpoints for the React UI."""

from __future__ import annotations

import os
from typing import Optional, Any
import csv
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from command_controller.controller import CommandController
from gesture_module.workflow import GestureWorkflow
from utils.file_utils import load_json

USER_ID = os.getenv("GESTURE_USER_ID", "default")

controller = CommandController()
workflow = GestureWorkflow(user_id=USER_ID)

app = FastAPI(title="Gesture Control API", version="0.1.0")

# Allow local dev origins (Vite, Tauri webview, etc.)
_origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StaticGestureRequest(BaseModel):
    label: str
    target_frames: int = Field(default=60, ge=5, le=500)
    hotkey: Optional[str] = None


class DynamicGestureRequest(BaseModel):
    label: str
    repetitions: int = Field(default=5, ge=1, le=20)
    sequence_length: int = Field(default=30, ge=5, le=200)
    hotkey: Optional[str] = None


class DeleteGestureRequest(BaseModel):
    label: str


class EnableGestureRequest(BaseModel):
    label: str
    enabled: bool = True


class StartRecognitionRequest(BaseModel):
    confidence_threshold: Optional[float] = Field(default=None, ge=0, le=1)
    stable_frames: Optional[int] = Field(default=None, ge=1, le=30)
    show_window: bool = False


@app.get("/gestures")
def list_gestures():
    workflow.ensure_presets_loaded()
    return {"items": workflow.dataset.list_gestures()}


@app.get("/gestures/presets")
def list_preset_gestures():
    labels_path = Path("data/presets/keypoint_classifier_label.csv")
    if not labels_path.exists():
        return {"items": []}
    labels: list[str] = []
    with labels_path.open() as fh:
        for row in csv.reader(fh):
            if not row:
                continue
            labels.append(row[0].lstrip("\ufeff").strip())
    return {"items": [{"label": lbl} for lbl in labels if lbl]}


@app.get("/settings")
def get_settings():
    return load_json("config/app_settings.json")


@app.post("/settings")
def update_settings(payload: dict[str, Any]):
    settings = load_json("config/app_settings.json")
    allowed = {
        "theme",
        "ui_poll_interval_ms",
        "recognition_stable_frames",
        "recognition_emit_cooldown_ms",
        "recognition_confidence_threshold",
        "microphone_device_index",
        "speaker_device_index",
    }
    updates = {key: value for key, value in payload.items() if key in allowed}
    if not updates:
        return {"status": "ok", "settings": settings}
    settings.update(updates)
    from utils.file_utils import save_json

    save_json("config/app_settings.json", settings)
    return {"status": "ok", "settings": settings}


@app.get("/audio/devices")
def list_audio_devices():
    try:
        import pyaudio
    except ImportError:
        return {"inputs": [], "outputs": []}

    pa = pyaudio.PyAudio()
    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    try:
        device_count = pa.get_device_count()
        for index in range(device_count):
            info = pa.get_device_info_by_index(index)
            item = {
                "index": index,
                "name": info.get("name"),
                "default_sample_rate": info.get("defaultSampleRate"),
                "max_input_channels": info.get("maxInputChannels", 0),
                "max_output_channels": info.get("maxOutputChannels", 0),
            }
            if item["max_input_channels"] > 0:
                inputs.append(item)
            if item["max_output_channels"] > 0:
                outputs.append(item)
    finally:
        pa.terminate()

    return {"inputs": inputs, "outputs": outputs}


@app.post("/gestures/static")
def add_static(req: StaticGestureRequest):
    workflow.collect_static(req.label, target_frames=req.target_frames, show_preview=False)
    workflow.dataset.set_hotkey(req.label, req.hotkey)
    workflow.dataset.save()
    return {"status": "ok"}


@app.post("/gestures/dynamic")
def add_dynamic(req: DynamicGestureRequest):
    workflow.collect_dynamic(
        req.label,
        repetitions=req.repetitions,
        sequence_length=req.sequence_length,
        show_preview=False,
    )
    workflow.dataset.set_hotkey(req.label, req.hotkey)
    workflow.dataset.save()
    return {"status": "ok"}


@app.post("/gestures/delete")
def delete_gesture(req: DeleteGestureRequest):
    workflow.dataset.remove_label(req.label)
    return {"status": "ok"}


@app.post("/gestures/enable")
def enable_gesture(req: EnableGestureRequest):
    workflow.ensure_presets_loaded()
    workflow.dataset.set_enabled(req.label, req.enabled)
    workflow.refresh_enabled_labels()
    return {"status": "ok"}


@app.post("/train")
def train():
    if workflow.dataset.X is None or workflow.dataset.y is None:
        raise HTTPException(status_code=400, detail="No samples to train on")
    workflow.train_and_save()
    return {"status": "ok"}


@app.post("/recognition/start")
def start_recognition(req: StartRecognitionRequest):
    try:
        settings = load_json("config/app_settings.json")
        stable_frames = req.stable_frames or int(settings.get("recognition_stable_frames", 5))
        emit_cooldown_ms = int(settings.get("recognition_emit_cooldown_ms", 500))
        emit_cooldown_secs = max(0.0, emit_cooldown_ms / 1000.0)
        confidence_threshold = (
            req.confidence_threshold
            if req.confidence_threshold is not None
            else float(settings.get("recognition_confidence_threshold", 0.6))
        )
        workflow.ensure_presets_loaded()
        workflow.start_recognition(
            controller,
            confidence_threshold=confidence_threshold,
            stable_frames=stable_frames,
            emit_cooldown_secs=emit_cooldown_secs,
            show_window=req.show_window,
        )
    except RuntimeError as exc:
        # Surface missing model / setup errors as 400 for the UI.
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@app.post("/recognition/stop")
def stop_recognition():
    try:
        workflow.stop_recognition()
    except Exception as exc:
        # Prevent a crash from propagating to the UI; log and return ok.
        print(f"[API] Failed to stop recognition: {exc}")
    return {"status": "ok"}


@app.get("/status")
def status():
    return {"recognition_running": workflow.is_recognizing(), "user_id": workflow.user_id}


@app.get("/", response_class=HTMLResponse)
def root():
    return "<html><body><h1>Gesture Control API</h1><p>Status: OK</p></body></html>"


@app.get("/recognition/last")
def last_detection():
    det = workflow.last_detection()
    return det or {}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
