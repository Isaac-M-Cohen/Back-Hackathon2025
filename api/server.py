"""FastAPI server exposing gesture workflow endpoints for the React UI."""

from __future__ import annotations

import os
import platform
import subprocess
import time
from urllib import request as urlrequest
from urllib.error import URLError
from typing import Optional, Any
import csv
import concurrent.futures
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from command_controller.controller import CommandController
from command_controller.intents import ALLOWED_INTENTS, normalize_steps, validate_steps
from command_controller.subject_extractor import SubjectExtractor
from gesture_module.workflow import GestureWorkflow
from utils.file_utils import load_json
from utils.log_utils import tprint
from utils.settings_store import refresh_settings, is_deep_logging, get_settings
from utils.runtime_state import get_client_os, set_client_os
from voice_module.voice_listener import VoiceListener

USER_ID = os.getenv("GESTURE_USER_ID", "default")
OLLAMA_URL = os.getenv("EASY_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_BIN = os.getenv("EASY_OLLAMA_BIN", "ollama")
OLLAMA_AUTOSTART = os.getenv("EASY_OLLAMA_AUTOSTART", "1") == "1"
GESTURES_ENABLED = os.getenv("ENABLE_GESTURES", "1") != "0"
_OLLAMA_CHECKED = False

controller = CommandController(user_id=USER_ID)
workflow = GestureWorkflow(user_id=USER_ID)
subject_extractor = SubjectExtractor(controller.engine.interpreter)
voice_listener: VoiceListener | None = None
voice_state: dict[str, Any] = {
    "running": False,
    "live_transcript": "",
    "final_transcript": "",
    "subjects": [],
    "audio_level": 0.0,
    "error": "",
    "phase": "idle",
    "updated_at": None,
}

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


@app.on_event("shutdown")
def _shutdown_cleanup() -> None:
    try:
        workflow.stop_recognition()
    except Exception as exc:
        tprint(f"[API] Shutdown cleanup failed: {exc}")
    try:
        if voice_listener is not None:
            voice_listener.stop()
    except Exception as exc:
        tprint(f"[API] Voice cleanup failed: {exc}")
    try:
        web_exec = getattr(controller.engine.executor, "_web_executor", None)
        if web_exec is not None:
            web_exec.shutdown()
            tprint("[API] WebExecutor shutdown complete")
    except Exception as exc:
        tprint(f"[API] WebExecutor cleanup failed: {exc}")


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


class SetGestureCommandRequest(BaseModel):
    label: str
    command: str = ""


class StartRecognitionRequest(BaseModel):
    confidence_threshold: Optional[float] = Field(default=None, ge=0, le=1)
    stable_frames: Optional[int] = Field(default=None, ge=1, le=30)
    show_window: bool = False


class ClientInfoRequest(BaseModel):
    os: Optional[str] = None


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
        "enable_commands",
        "recognition_max_fps",
        "recognition_watchdog_timeout_ms",
        "command_timeout_ms",
        "command_hotkey_interval_secs",
        "log_command_debug",
        "microphone_device_index",
        "speaker_device_index",
        # New WAV pipeline voice settings
        "voice_silence_threshold",
        "voice_silence_duration_secs",
        "voice_min_record_duration_secs",
        "voice_max_record_duration_secs",
        "voice_send_to_executor",
        "voice_min_voice_duration_secs",
        "voice_pre_roll_secs",
        "voice_min_gap_secs",
        "voice_use_legacy_pause_threshold",
        # Legacy voice settings (kept for backwards compatibility)
        "voice_pause_threshold_ms",
        "voice_live_transcribe_interval_ms",
        "voice_min_command_seconds",
        "voice_audio_level_threshold",
        "voice_partial_window_secs",
    }
    updates = {key: value for key, value in payload.items() if key in allowed}
    if not updates:
        return {"status": "ok", "settings": settings}
    settings.update(updates)
    from utils.file_utils import save_json

    save_json("config/app_settings.json", settings)
    refresh_settings()
    workflow.apply_runtime_settings(settings)
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


@app.post("/gestures/command")
def set_gesture_command(req: SetGestureCommandRequest):
    workflow.ensure_presets_loaded()
    workflow.dataset.set_command(req.label, req.command)
    controller.dataset.set_command(req.label, req.command)
    if is_deep_logging():
        tprint(f"[DEEP][API] set_gesture_command label={req.label!r} command={req.command!r}")
    if req.command.strip():
        cached = workflow.dataset.get_command_metadata(req.label)
        steps = None
        cached_resolved = None
        if cached and cached.get("command") == req.command:
            cached_resolved = cached.get("resolved_url")
            if cached_resolved:
                steps = [
                    {
                        "intent": "open_url",
                        "target": "web",
                        "url": cached_resolved,
                        "resolved_url": cached_resolved,
                        "precomputed": True,
                    }
                ]
            elif cached.get("steps"):
                try:
                    steps = validate_steps(cached.get("steps", []))
                    if is_deep_logging():
                        tprint(f"[DEEP][API] reuse_cached_steps label={req.label!r}")
                except Exception:
                    steps = None
        if steps and cached_resolved:
            if is_deep_logging():
                tprint(f"[DEEP][API] reuse_cached_resolved label={req.label!r}")

        # Detect login intent for precompute
        is_login_intent = any(
            term in req.command.lower()
            for term in ("login", "log in", "sign in", "sign-in", "signin", "account")
        )
        if is_login_intent:
            tprint(f"[API] Login intent detected for command: {req.command}")

        if steps is None:
            try:
                settings = get_settings()
                timeout_secs = float(settings.get("command_parse_timeout_secs", 15))
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        controller.engine.interpreter.interpret,
                        req.command,
                        {},
                        ALLOWED_INTENTS,
                    )
                    payload = future.result(timeout=timeout_secs)
                steps = validate_steps(normalize_steps(payload))
                if not steps:
                    raise ValueError("No executable steps returned")
            except concurrent.futures.TimeoutError:
                raise HTTPException(status_code=504, detail="Command parsing timed out")
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Command parsing failed: {exc}")
        resolved = {}
        if not cached_resolved:
            # Extract base URL from steps for login precompute logging
            base_url = None
            raw_base_url = None
            for step in steps:
                if step.get("intent") == "open_url":
                    raw_base_url = step.get("url")
                    base_url = raw_base_url
                    break

            if is_login_intent and base_url:
                base_url = _normalize_login_base_url(base_url)
                tprint(f"[API] Precomputing login URL for base: {base_url}")
                # Use specialized login link search for login intents
                try:
                    subjects = _extract_subjects(req.command)
                    subject = None
                    if subjects:
                        candidate = subjects[0].strip().lower()
                        if not any(token in candidate for token in (":", "/", "http")):
                            subject = candidate
                    if subject is None and base_url:
                        subject = _subject_from_base_url(base_url)
                    login_query = req.command
                    if subject:
                        login_query = f"{subject} login"
                        tprint(f"[API] Login subject detected: {subject}")
                    settings = get_settings()
                    timeout_secs = float(settings.get("command_parse_timeout_secs", 15))
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(
                            _resolve_login_url_with_resolver, login_query
                        )
                        login_url = future.result(timeout=timeout_secs)
                    if login_url:
                        tprint(f"[API] Login URL resolved: {login_url}")
                        resolved = {
                            "resolved_url": login_url,
                            "base_url": base_url,
                            "query": login_query,
                        }
                    else:
                        tprint(f"[API] Login URL resolution returned no result, keeping original steps")
                        resolved = {}
                except concurrent.futures.TimeoutError:
                    tprint(f"[API] Login URL resolution timed out for {base_url}")
                    resolved = {}
                except Exception as exc:
                    tprint(f"[API] Login URL resolution failed for {base_url}: {exc}")
                    resolved = {}
            else:
                # Non-login intent: use standard resolution
                try:
                    settings = get_settings()
                    timeout_secs = float(settings.get("command_parse_timeout_secs", 15))
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(
                            controller.engine.executor.resolve_web_steps,
                            steps,
                        )
                        resolved = future.result(timeout=timeout_secs)
                except concurrent.futures.TimeoutError:
                    tprint(f"[API] Resolve steps timed out for {req.label!r}")
                    resolved = {}
                except Exception as exc:
                    tprint(f"[API] Resolve steps failed for {req.label!r}: {exc}")
                    resolved = {}

        if resolved.get("resolved_url"):
            if is_login_intent:
                tprint(f"[API] Login URL precomputed: {resolved['resolved_url']}")
            steps = [
                {
                    "intent": "open_url",
                    "target": "web",
                    "url": resolved["resolved_url"],
                    "resolved_url": resolved["resolved_url"],
                    "precomputed": True,
                }
            ]
        elif is_login_intent and raw_base_url:
            tprint(
                f"[API] Login URL precompute failed, using fallback: {raw_base_url}"
            )

        if is_deep_logging():
            tprint(f"[DEEP][API] parsed_steps label={req.label!r} steps={steps}")

        workflow.dataset.set_command_steps(req.label, steps)
        controller.dataset.set_command_steps(req.label, steps)
        urls = [
            str(step.get("url"))
            for step in steps
            if str(step.get("intent")) == "open_url" and step.get("url")
        ]
        workflow.dataset.set_command_metadata(
            req.label,
            {
                "command": req.command,
                "steps": steps,
                "urls": urls,
                "resolved_url": resolved.get("resolved_url"),
                "resolved_base_url": resolved.get("base_url"),
                "resolved_query": resolved.get("query"),
            },
        )
        # Avoid prewarming Playwright here to keep web automation thread-safe.
    else:
        workflow.dataset.set_command_steps(req.label, None)
        controller.dataset.set_command_steps(req.label, None)
    return {"status": "ok"}

def _resolve_login_url_with_resolver(query: str) -> str | None:
    """Use URLResolver to find login page from a query string."""
    try:
        from command_controller.url_resolver import URLResolver

        resolver = URLResolver()
        result = resolver.resolve(query)
        resolver.shutdown()
        if result and result.resolved_url:
            return result.resolved_url
        return None

    except Exception as exc:
        tprint(f"[API] Login URL resolution with URLResolver failed: {exc}")
        return None


@app.post("/train")
def train():
    raise HTTPException(
        status_code=400,
        detail="Training is handled via the TFLite notebooks. Run them to update models.",
    )


@app.post("/recognition/start")
def start_recognition(req: StartRecognitionRequest):
    if not GESTURES_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="Gesture recognition disabled (set ENABLE_GESTURES=1 to enable).",
        )
    try:
        settings = load_json("config/app_settings.json")
        stable_frames = req.stable_frames or int(settings.get("recognition_stable_frames", 5))
        emit_cooldown_ms = int(settings.get("recognition_emit_cooldown_ms", 500))
        emit_cooldown_secs = max(0.0, emit_cooldown_ms / 1000.0)
        emit_actions = bool(settings.get("enable_commands", True))
        max_fps_value = settings.get("recognition_max_fps", 0)
        max_fps = float(max_fps_value) if max_fps_value is not None else 0.0
        if max_fps < 0:
            max_fps = 0.0
        watchdog_ms = settings.get("recognition_watchdog_timeout_ms", 0)
        watchdog_secs = float(watchdog_ms) / 1000.0 if watchdog_ms else 0.0
        if watchdog_secs < 0:
            watchdog_secs = 0.0
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
            emit_actions=emit_actions,
            max_fps=max_fps,
            watchdog_timeout_secs=watchdog_secs,
        )
    except RuntimeError as exc:
        # Surface missing model / setup errors as 400 for the UI.
        tprint(f"[API] Start recognition failed: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@app.post("/recognition/stop")
def stop_recognition():
    try:
        workflow.stop_recognition()
    except Exception as exc:
        # Prevent a crash from propagating to the UI; log and return ok.
        tprint(f"[API] Failed to stop recognition: {exc}")
    return {"status": "ok"}


def _extract_subjects(text: str) -> list[str]:
    if not text.strip():
        return []
    try:
        payload = controller.engine.interpreter.interpret(text, {}, ALLOWED_INTENTS)
        steps = validate_steps(normalize_steps(payload))
    except Exception as exc:
        tprint(f"[API] Subject extraction failed: {exc}")
        return []
    groups = subject_extractor.extract(text, steps)
    ordered = sorted(groups, key=lambda group: group.start_index)
    return [group.subject_name for group in ordered if group.subject_name]


def _subject_from_base_url(base_url: str) -> str | None:
    try:
        from urllib.parse import urlparse

        host = urlparse(base_url).hostname or ""
        host = host.lower()
        if host.startswith("www."):
            host = host[4:]
        parts = [part for part in host.split(".") if part]
        if len(parts) >= 2:
            return parts[-2]
        return parts[0] if parts else None
    except Exception:
        return None


def _normalize_login_base_url(base_url: str) -> str:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        path_lower = (parsed.path or "").lower()
        if any(term in path_lower for term in ("login", "signin", "sign-in", "auth")):
            return f"{parsed.scheme}://{parsed.netloc}/"
    except Exception:
        return base_url
    return base_url


def _update_voice_state(**updates: Any) -> None:
    voice_state.update(updates)
    voice_state["updated_at"] = time.time()


@app.post("/voice/start")
def start_voice():
    global voice_listener
    if voice_listener and voice_listener.is_running():
        return {"status": "ok", "running": True}

    settings = load_json("config/app_settings.json")
    # New WAV pipeline settings
    silence_threshold = float(settings.get("voice_silence_threshold", 0.02))
    silence_duration_secs = float(settings.get("voice_silence_duration_secs", 1.1))
    min_record_duration_secs = float(settings.get("voice_min_record_duration_secs", 0.7))
    max_record_duration_secs = float(settings.get("voice_max_record_duration_secs", 8.0))
    min_voice_duration_secs = float(settings.get("voice_min_voice_duration_secs", 0.12))
    pre_roll_secs = float(settings.get("voice_pre_roll_secs", 0.25))
    min_gap_secs = float(settings.get("voice_min_gap_secs", 0.25))
    send_to_executor = bool(settings.get("voice_send_to_executor", False))
    # Legacy settings (only used if explicitly enabled)
    use_legacy_pause = bool(settings.get("voice_use_legacy_pause_threshold", False))
    audio_level_threshold = float(settings.get("voice_audio_level_threshold", silence_threshold))
    pause_threshold_ms = settings.get("voice_pause_threshold_ms") if use_legacy_pause else None
    pause_threshold_secs = float(pause_threshold_ms) / 1000.0 if pause_threshold_ms else None
    min_command_seconds = float(settings.get("voice_min_command_seconds", min_record_duration_secs))

    def _handle_partial(text: str) -> None:
        _update_voice_state(live_transcript=text, error="")

    def _handle_final(text: str) -> None:
        subjects = _extract_subjects(text) if send_to_executor else []
        _update_voice_state(
            final_transcript=text,
            live_transcript=text,
            subjects=subjects,
            error="",
        )

    def _handle_level(level: float) -> None:
        _update_voice_state(audio_level=level)

    def _handle_error(message: str) -> None:
        _update_voice_state(error=message, phase="error")

    def _handle_state(state: str) -> None:
        _update_voice_state(phase=state)

    voice_listener = VoiceListener(
        controller,
        listen_seconds=None,
        chunk_size=4096,
        single_batch=False,
        log_token_usage=False,
        on_partial_transcript=_handle_partial,
        on_final_transcript=_handle_final,
        on_audio_level=_handle_level,
        on_error=_handle_error,
        on_state=_handle_state,
        send_to_executor=send_to_executor,
        # New WAV pipeline parameters
        silence_threshold=silence_threshold,
        silence_duration_secs=silence_duration_secs,
        min_record_duration_secs=min_record_duration_secs,
        max_record_duration_secs=max_record_duration_secs,
        min_voice_duration_secs=min_voice_duration_secs,
        pre_roll_secs=pre_roll_secs,
        min_gap_secs=min_gap_secs,
        # Legacy parameters (VoiceListener maps these internally)
        pause_threshold_secs=pause_threshold_secs,
        min_command_seconds=min_command_seconds,
        audio_level_threshold=audio_level_threshold,
    )
    voice_listener.start()
    _update_voice_state(running=True, error="", phase="listening")
    return {"status": "ok", "running": True}


@app.post("/voice/stop")
def stop_voice():
    global voice_listener
    if voice_listener:
        voice_listener.stop()
    _update_voice_state(running=False, audio_level=0.0, phase="idle")
    return {"status": "ok", "running": False}


@app.get("/voice/status")
def voice_status():
    running = bool(voice_listener and voice_listener.is_running())
    voice_state["running"] = running
    return voice_state


@app.get("/status")
def status():
    return {
        "recognition_running": workflow.is_recognizing(),
        "user_id": workflow.user_id,
        "client_os": get_client_os(),
        "gestures_enabled": GESTURES_ENABLED,
    }


@app.post("/client/info")
def set_client_info(payload: ClientInfoRequest):
    set_client_os(payload.os)
    return {"status": "ok", "client_os": get_client_os()}


@app.get("/", response_class=HTMLResponse)
def root():
    return "<html><body><h1>Gesture Control API</h1><p>Status: OK</p></body></html>"


@app.get("/recognition/last")
def last_detection():
    det = workflow.last_detection()
    return det or {}


def _ollama_ready(timeout_secs: float = 2.0) -> tuple[bool, str | None]:
    try:
        with urlrequest.urlopen(f"{OLLAMA_URL.rstrip('/')}/api/tags", timeout=timeout_secs) as resp:
            if resp.status == 200:
                return True, None
    except URLError as exc:
        return False, str(exc)
    return False, "Unexpected response"


def _try_start_ollama() -> bool:
    if not OLLAMA_AUTOSTART:
        return False
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", "-a", "Ollama"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "Windows":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen(
                [OLLAMA_BIN, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        else:
            subprocess.Popen([OLLAMA_BIN, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False
    for _ in range(12):
        ready, _ = _ollama_ready(timeout_secs=1.0)
        if ready:
            return True
        time.sleep(0.5)
    return False


@app.get("/health")
def health():
    global _OLLAMA_CHECKED
    tprint("[HEALTH] /health check requested")
    ready, err = _ollama_ready()
    if not ready and not _OLLAMA_CHECKED:
        _OLLAMA_CHECKED = True
        _try_start_ollama()
        ready, err = _ollama_ready()
    return {
        "ok": ready,
        "ollama": {
            "running": ready,
            "url": OLLAMA_URL,
            "error": err,
        },
        "recognition_running": workflow.is_recognizing(),
    }


@app.get("/commands/pending")
def list_pending_commands():
    return {"items": controller.list_pending()}


@app.get("/commands/last")
def last_command():
    return controller.last_result() or {}


class CommandConfirmationRequest(BaseModel):
    id: str


@app.post("/commands/confirm")
def confirm_command(req: CommandConfirmationRequest):
    return controller.approve(req.id)


@app.post("/commands/deny")
def deny_command(req: CommandConfirmationRequest):
    return controller.deny(req.id)


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    access_log = bool(settings.get("http_access_log", False))
    log_level = str(settings.get("log_level", "INFO")).upper()
    if log_level == "DEEP":
        log_level = "DEBUG"
    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=log_level.lower(),
        access_log=access_log,
    )
