"""FastAPI server exposing gesture workflow endpoints for the React UI."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from command_controller.controller import CommandController
from gesture_module.workflow import GestureWorkflow

USER_ID = os.getenv("GESTURE_USER_ID", "default")

controller = CommandController()
workflow = GestureWorkflow(user_id=USER_ID)

app = FastAPI(title="Gesture Control API", version="0.1.0")

# Allow local dev origins (Vite, etc.)
_origins = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:1573",
    "http://127.0.0.1:1573",
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_origins),
    allow_credentials=True,
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


class StartRecognitionRequest(BaseModel):
    confidence_threshold: float = Field(default=0.6, ge=0, le=1)
    stable_frames: int = Field(default=5, ge=1, le=30)
    show_window: bool = False


@app.get("/gestures")
def list_gestures():
    return {"items": workflow.dataset.list_gestures()}


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


@app.post("/train")
def train():
    if workflow.dataset.X is None or workflow.dataset.y is None:
        raise HTTPException(status_code=400, detail="No samples to train on")
    workflow.train_and_save()
    return {"status": "ok"}


@app.post("/recognition/start")
def start_recognition(req: StartRecognitionRequest):
    try:
        workflow.start_recognition(
            controller,
            confidence_threshold=req.confidence_threshold,
            stable_frames=req.stable_frames,
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
        # Prevent a crash from propagating to the UI; log and return error.
        raise HTTPException(status_code=500, detail=str(exc))
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
