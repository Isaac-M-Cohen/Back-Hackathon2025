import React, { useCallback, useEffect, useRef, useState } from "react";
import { Plus, MoreVertical, Trash2, Play, Pause, Settings, Camera, Mic } from "lucide-react";
import { Api, initApiBase, waitForApiReady } from "./api";

function detectClientOs() {
  if (typeof navigator === "undefined") {
    return "Unknown";
  }
  const ua = navigator.userAgent || "";
  const platform = navigator.platform || "";
  const text = `${platform} ${ua}`.toLowerCase();
  if (text.includes("mac")) {
    return "Darwin";
  }
  if (text.includes("win")) {
    return "Windows";
  }
  if (text.includes("linux")) {
    return "Linux";
  }
  return "Unknown";
}

export default function GestureControlApp() {
  const [gestures, setGestures] = useState([]);
  const [allGestures, setAllGestures] = useState([]);
  const [presetGestures, setPresetGestures] = useState([]);
  const [isGestureRunning, setIsGestureRunning] = useState(false);
  const [isVoiceRunning, setIsVoiceRunning] = useState(false);
  const [showPresets, setShowPresets] = useState(false);
  const [hoveredId, setHoveredId] = useState(null);
  const [menuOpen, setMenuOpen] = useState(null);
  const [error, setError] = useState("");
  const [lastDetection, setLastDetection] = useState(null);
  const [voiceStatus, setVoiceStatus] = useState({
    running: false,
    live_transcript: "",
    final_transcript: "",
    subjects: [],
    audio_level: 0,
    error: "",
    phase: "idle",
  });
  const [pollIntervalMs, setPollIntervalMs] = useState(1000);
  const [pendingCommands, setPendingCommands] = useState([]);
  const [lastCommand, setLastCommand] = useState(null);
  const [isBooting, setIsBooting] = useState(true);
  const [bootMessage, setBootMessage] = useState("Starting...");
  const bootStartedRef = useRef(false);
  const [settings, setSettings] = useState({});
  const [settingsDraft, setSettingsDraft] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [themeMode, setThemeMode] = useState("light");
  const [audioDevices, setAudioDevices] = useState({ inputs: [], outputs: [] });
  const [commandModal, setCommandModal] = useState(null);
  const [isSavingCommand, setIsSavingCommand] = useState(false);
  const [commandModalError, setCommandModalError] = useState("");
  const defaultSettings = {
    theme: "light",
    ui_poll_interval_ms: 500,
    recognition_stable_frames: 5,
    recognition_emit_cooldown_ms: 200,
    recognition_confidence_threshold: 0.6,
    microphone_device_index: null,
    speaker_device_index: null,
  };

  useEffect(() => {
    if (bootStartedRef.current) {
      return;
    }
    bootStartedRef.current = true;
    initApiBase().then(async () => {
      try {
        await waitForApiReady();
        Api.setClientInfo({ os: detectClientOs() }).catch(() => {});
        let enableCommands = true;
        try {
          const settings = await Api.getSettings();
          const nextPoll = Number(settings.ui_poll_interval_ms);
          if (!Number.isNaN(nextPoll) && nextPoll > 0) {
            setPollIntervalMs(nextPoll);
          }
          setSettings(settings);
          if (settings.theme) {
            setThemeMode(settings.theme);
          }
          if (typeof settings.enable_commands === "boolean") {
            enableCommands = settings.enable_commands;
          }
        } catch {
          // Settings are optional.
        }
        const ready = await waitForDependencies({ requireOllama: enableCommands });
        if (!ready && enableCommands) {
          setError("Ollama is not running. Please install or start it.");
        }
        await refreshGestures();
        try {
          const { emit } = await import("@tauri-apps/api/event");
          await emit("easy://frontend-ready");
        } catch {
          // Tauri APIs not available (web dev mode).
        }
        setIsBooting(false);
      } catch (err) {
        setError(err.message);
        setIsBooting(false);
      }
    });
  }, []);

  async function waitForDependencies({
    timeoutMs = 30000,
    intervalMs = 500,
    requireOllama = true,
  } = {}) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      try {
        const health = await Api.health();
        if (health && (health.ok || !requireOllama)) {
          setBootMessage("Ready");
          return true;
        }
        setBootMessage(requireOllama ? "Waiting for Ollama..." : "Waiting for backend...");
      } catch {
        setBootMessage("Waiting for backend...");
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    return false;
  }

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) {
      return;
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const applyTheme = () => {
      const isDark = themeMode === "dark" || (themeMode === "system" && media.matches);
      document.documentElement.classList.toggle("dark", isDark);
    };
    applyTheme();
    if (media.addEventListener) {
      media.addEventListener("change", applyTheme);
      return () => media.removeEventListener("change", applyTheme);
    }
    media.addListener(applyTheme);
    return () => media.removeListener(applyTheme);
  }, [themeMode]);

  useEffect(() => {
    const handleVisibility = () => {
      if (!document.hidden) {
        refreshGestures().catch(() => {});
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  useEffect(() => {
    if (!isGestureRunning) {
      setLastDetection(null);
      return undefined;
    }
    const id = setInterval(async () => {
      try {
        const res = await Api.lastDetection();
        if (res && res.label) {
          setLastDetection(res);
        }
        const status = await Api.status();
        if (status && status.recognition_running === false) {
          setIsGestureRunning(false);
        }
      } catch (err) {
        console.error(err);
      }
    }, pollIntervalMs);
    return () => clearInterval(id);
  }, [isGestureRunning, pollIntervalMs]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await Api.voiceStatus();
        if (!cancelled && status) {
          setVoiceStatus(status);
          setIsVoiceRunning(Boolean(status.running));
        }
      } catch {
        // Voice endpoint optional.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const id = setInterval(async () => {
      if (!isVoiceRunning) {
        setVoiceStatus((prev) => ({
          ...prev,
          running: false,
          audio_level: 0,
          error: prev.error || "",
        }));
        return;
      }
      try {
        const status = await Api.voiceStatus();
        if (status) {
          setVoiceStatus(status);
          if (status.running === false) {
            setIsVoiceRunning(false);
          }
        }
      } catch (err) {
        console.error(err);
      }
    }, pollIntervalMs);
    return () => clearInterval(id);
  }, [isVoiceRunning, pollIntervalMs]);

  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const res = await Api.listPendingCommands();
        setPendingCommands(res.items || []);
        const last = await Api.lastCommand();
        if (last && Object.keys(last).length > 0) {
          setLastCommand(last);
        }
      } catch (err) {
        console.error(err);
      }
    }, 1200);
    return () => clearInterval(id);
  }, []);

  const lastCommandMeta = (() => {
    if (!lastCommand) {
      return null;
    }
    const status = lastCommand.status || "unknown";
    const results = Array.isArray(lastCommand.results) ? lastCommand.results : [];
    const stepCount = results.length;
    const timestamp = lastCommand.timestamp
      ? new Date(lastCommand.timestamp * 1000)
      : null;
    return { status, stepCount, timestamp, reason: lastCommand.reason || "" };
  })();

  async function refreshGestures() {
    try {
      const data = await Api.listGestures();
      const items =
        data.items?.map((item) => ({
          id: item.label,
          gesture: { id: item.label, name: item.label },
          hotkey: item.hotkey || "",
          command: item.command || "",
          enabled: item.enabled || false,
        })) || [];
      setAllGestures(items);
      setGestures(
        items.filter((item) => item.enabled && item.id !== "NONE")
      );
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshPresets() {
    try {
      const data = await Api.listPresetGestures();
      const items =
        data.items?.map((item) => ({
          id: item.label,
          name: item.label,
        })) || [];
      setPresetGestures(items);
    } catch (err) {
      setError(err.message);
    }
  }

  const handleAddGesture = () => {
    refreshPresets().finally(() => setShowPresets(true));
  };

  const openCommandModal = useCallback(
    (preset, mode) => {
      const existing = allGestures.find((item) => item.id === preset.id);
      const commandValue = existing?.command || "";
      setCommandModalError("");
      setCommandModal({
        mode,
        gesture: preset,
        value: commandValue,
        originalValue: commandValue,
      });
    },
    [allGestures]
  );

  const handlePresetSelect = (preset) => {
    setShowPresets(false);
    openCommandModal(preset, "add");
  };

  const handleDelete = async (id) => {
    setMenuOpen(null);
    try {
      await Api.enableGesture(id, false);
      await refreshGestures();
    } catch (err) {
      setError(err.message);
    }
  };
  const closeCommandModal = () => {
    setCommandModal(null);
    setIsSavingCommand(false);
    setCommandModalError("");
  };

  const handleCommandSubmit = async () => {
    if (!commandModal) {
      return;
    }
    const commandText = commandModal.value.trim();
    if (!commandText) {
      return;
    }
    setIsSavingCommand(true);
    setCommandModalError("");
    try {
      await Api.setGestureCommand(commandModal.gesture.id, commandText);
      if (commandModal.mode === "add") {
        await Api.enableGesture(commandModal.gesture.id, true);
      }
      await refreshGestures();
      closeCommandModal();
    } catch (err) {
      setCommandModalError(err.message || "Failed to save command.");
    } finally {
      setIsSavingCommand(false);
    }
  };

  const toggleGestureRecognition = async () => {
    try {
      if (isGestureRunning) {
        try {
          await Api.stopRecognition();
        } finally {
          setIsGestureRunning(false);
          setLastDetection(null);
          refreshGestures().catch(() => {});
          refreshPresets().catch(() => {});
        }
      } else {
        await Api.startRecognition({ show_window: false });
        setIsGestureRunning(true);
      }
    } catch (err) {
      setError(err.message || "Failed to start/stop recognition. Collect and train first?");
      if (isGestureRunning) {
        setIsGestureRunning(false);
        setLastDetection(null);
      }
    }
  };

  const toggleVoiceRecognition = async () => {
    try {
      if (isVoiceRunning) {
        await Api.stopVoice();
        setIsVoiceRunning(false);
      } else {
        await Api.startVoice();
        setIsVoiceRunning(true);
      }
    } catch (err) {
      setError(err.message || "Failed to start/stop voice recognition.");
      if (isVoiceRunning) {
        setIsVoiceRunning(false);
      }
    }
  };

  const openSettings = useCallback(async () => {
    try {
      const next = await Api.getSettings();
      setSettings(next);
      setSettingsDraft({
        theme: next.theme ?? defaultSettings.theme,
        ui_poll_interval_ms:
          next.ui_poll_interval_ms ?? defaultSettings.ui_poll_interval_ms,
        recognition_stable_frames:
          next.recognition_stable_frames ??
          defaultSettings.recognition_stable_frames,
        recognition_emit_cooldown_ms:
          next.recognition_emit_cooldown_ms ??
          defaultSettings.recognition_emit_cooldown_ms,
        recognition_confidence_threshold:
          next.recognition_confidence_threshold ??
          defaultSettings.recognition_confidence_threshold,
        microphone_device_index:
          next.microphone_device_index ?? defaultSettings.microphone_device_index,
        speaker_device_index:
          next.speaker_device_index ?? defaultSettings.speaker_device_index,
      });
    } catch (err) {
      setError(err.message);
      setSettingsDraft({ ...defaultSettings });
    }
    try {
      const devices = await Api.listAudioDevices();
      setAudioDevices({
        inputs: devices.inputs || [],
        outputs: devices.outputs || [],
      });
    } catch {
      setAudioDevices({ inputs: [], outputs: [] });
    }
    setShowSettings(true);
  }, []);

  const closeSettings = () => {
    setShowSettings(false);
    setSettingsDraft(null);
  };

  const saveSettings = async () => {
    if (!settingsDraft) {
      return;
    }
    try {
      const res = await Api.updateSettings(settingsDraft);
      if (res && res.settings) {
        setSettings(res.settings);
        const nextPoll = Number(res.settings.ui_poll_interval_ms);
        if (!Number.isNaN(nextPoll) && nextPoll > 0) {
          setPollIntervalMs(nextPoll);
        }
        if (res.settings.theme) {
          setThemeMode(res.settings.theme);
        }
      }
      closeSettings();
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    let unlisten;
    (async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event");
        unlisten = await listen("easy://open-settings", () => {
          openSettings();
        });
      } catch {
        // Tauri APIs not available (web dev mode).
      }
    })();
    return () => {
      if (unlisten) {
        unlisten();
      }
    };
  }, [openSettings]);

  if (isBooting) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white border border-gray-200 rounded-2xl shadow-sm px-8 py-6 text-center">
          <div className="text-lg font-medium text-gray-900 mb-2">Easy</div>
          <div className="text-sm text-gray-600">{bootMessage}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="w-full max-w-2xl">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-light text-gray-800">Gesture Control</h1>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-2 py-1 rounded-lg border border-gray-200 bg-white">
              <span
                className={`h-2 w-2 rounded-full ${
                  isGestureRunning ? "bg-green-500" : "bg-red-500"
                }`}
              />
              <Camera size={14} className="text-gray-600" />
              <span className="text-[11px] text-gray-600">Camera</span>
            </div>
            <div className="flex items-center gap-2 px-2 py-1 rounded-lg border border-gray-200 bg-white">
              <span
                className={`h-2 w-2 rounded-full ${
                  isVoiceRunning ? "bg-green-500" : "bg-red-500"
                }`}
              />
              <Mic size={14} className="text-gray-600" />
              <div className="w-10 h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className={`h-2 transition-all ${
                    isVoiceRunning ? "bg-green-500" : "bg-gray-400"
                  }`}
                  style={{
                    width: `${Math.min(100, Math.max(0, Math.sqrt(voiceStatus.audio_level || 0) * 150))}%`,
                  }}
                />
              </div>
            </div>
            <button
              onClick={openSettings}
              className="p-2 rounded-lg border border-gray-200 bg-white text-gray-600 hover:text-gray-900 hover:border-gray-300 hover:bg-gray-100"
              aria-label="Settings"
              title="Settings"
            >
              <Settings size={18} />
            </button>
            <button
              onClick={toggleGestureRecognition}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all hover:shadow-sm ${
                isGestureRunning
                  ? "bg-green-500 text-white hover:bg-green-600"
                  : "bg-gray-300 text-gray-700 hover:bg-gray-400"
              }`}
            >
              {isGestureRunning ? <Pause size={16} /> : <Play size={16} />}
              {isGestureRunning ? "Gesture On" : "Gesture Off"}
            </button>
            <button
              onClick={toggleVoiceRecognition}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all hover:shadow-sm ${
                isVoiceRunning
                  ? "bg-green-500 text-white hover:bg-green-600"
                  : "bg-gray-300 text-gray-700 hover:bg-gray-400"
              }`}
            >
              {isVoiceRunning ? <Pause size={16} /> : <Play size={16} />}
              {isVoiceRunning ? "Voice On" : "Voice Off"}
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 border border-red-200 text-red-700 px-4 py-2 text-sm">
            {error}
          </div>
        )}

        {isGestureRunning && lastDetection && (
          <div className="mb-4 rounded-lg bg-green-50 border border-green-200 text-green-800 px-4 py-2 text-sm flex items-center justify-between">
            <span>
              Detected: <strong>{lastDetection.label}</strong>{" "}
              {lastDetection.confidence !== undefined &&
                `(conf ${lastDetection.confidence.toFixed(2)})`}
            </span>
          </div>
        )}

        {isVoiceRunning && (
          <div className={`mb-4 rounded-lg px-4 py-2 text-sm border ${
            voiceStatus.phase === "recording"
              ? "bg-red-50 border-red-200 text-red-900"
              : voiceStatus.phase === "transcribing"
                ? "bg-blue-50 border-blue-200 text-blue-900"
                : "bg-amber-50 border-amber-200 text-amber-900"
          }`}>
            <div className="flex items-center justify-between">
              <span>
                {voiceStatus.phase === "recording" ? (
                  <>
                    <span className="inline-block w-2 h-2 bg-red-500 rounded-full animate-pulse mr-2" />
                    <strong>Recording...</strong>
                  </>
                ) : voiceStatus.phase === "transcribing" ? (
                  <>
                    <span className="inline-block w-2 h-2 bg-blue-500 rounded-full animate-pulse mr-2" />
                    <strong>Transcribing...</strong>
                  </>
                ) : voiceStatus.live_transcript ? (
                  <>
                    Transcribed: <strong>{voiceStatus.live_transcript}</strong>
                  </>
                ) : (
                  <>
                    <span className="inline-block w-2 h-2 bg-amber-500 rounded-full mr-2" />
                    <strong>Listening...</strong>
                  </>
                )}
              </span>
              <span className={`text-[11px] uppercase tracking-wide ${
                voiceStatus.phase === "recording"
                  ? "text-red-700"
                  : voiceStatus.phase === "transcribing"
                    ? "text-blue-700"
                    : "text-amber-700"
              }`}>
                {voiceStatus.phase || "listening"}
              </span>
            </div>
            {voiceStatus.error && (
              <div className="mt-2 text-xs text-red-600">
                Error: {voiceStatus.error}
              </div>
            )}
            {Array.isArray(voiceStatus.subjects) && voiceStatus.subjects.length > 0 && (
              <div className="mt-2 text-xs opacity-80">
                Subjects: {voiceStatus.subjects.join(", ")}
              </div>
            )}
          </div>
        )}

        {lastCommandMeta && (
          <div className="mb-4 rounded-lg bg-blue-50 border border-blue-200 text-blue-900 px-4 py-2 text-sm flex items-center justify-between">
            <span>
              Last command: <strong>{lastCommandMeta.status}</strong>{" "}
              {lastCommandMeta.stepCount > 0 && `(${lastCommandMeta.stepCount} steps)`}
              {lastCommandMeta.reason && ` — ${lastCommandMeta.reason}`}
            </span>
            {lastCommandMeta.timestamp && (
              <span className="text-xs text-blue-700">
                {lastCommandMeta.timestamp.toLocaleTimeString()}
              </span>
            )}
          </div>
        )}

        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
          {gestures.length === 0 ? (
            <div className="p-16 text-center">
              <div className="text-gray-400 mb-4">
                <svg
                  className="w-16 h-16 mx-auto"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1}
                    d="M7 11.5V14m0-2.5v-6a1.5 1.5 0 113 0m-3 6a1.5 1.5 0 00-3 0v2a7.5 7.5 0 0015 0v-5a1.5 1.5 0 00-3 0m-6-3V11m0-5.5v-1a1.5 1.5 0 013 0v1m0 0V11m0-5.5a1.5 1.5 0 013 0v3m0 0V11"
                  />
                </svg>
              </div>
              <p className="text-gray-500 text-sm font-light">No gestures tracked yet</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {gestures.map((item) => (
                <div
                  key={item.id}
                  className={`flex items-center px-6 py-4 transition-colors ${
                    hoveredId === item.id ? "bg-gray-100" : ""
                  }`}
                  onMouseEnter={() => setHoveredId(item.id)}
                  onMouseLeave={() => setHoveredId(null)}
                >
                  <div className="w-20 h-20 bg-gray-200 rounded-lg flex items-center justify-center mr-4 flex-shrink-0">
                    {hoveredId === item.id ? (
                      <div className="text-xs text-gray-500 animate-pulse">
                        {item.gesture.name}
                      </div>
                    ) : (
                      <div className="text-xs text-gray-400">
                        {item.gesture.name.split(" ")[0]}
                      </div>
                    )}
                  </div>

                  <div className="flex-1">
                    <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-gray-100 rounded-lg">
                      {(item.hotkey || "Unset")
                        .split("+")
                        .filter(Boolean)
                        .map((key, i) => (
                          <React.Fragment key={i}>
                            {i > 0 && <span className="text-gray-400 text-xs">+</span>}
                            <kbd className="text-sm font-medium text-gray-700">{key}</kbd>
                          </React.Fragment>
                        ))}
                    </div>
                    <div className="mt-3 text-xs text-gray-500">
                      <span className="uppercase tracking-wide text-[10px]">
                        Command
                      </span>
                      <div className="mt-1 text-sm text-gray-700">
                        {item.command || "No command set"}
                      </div>
                    </div>
                  </div>

                  <div className="relative">
                    <button
                      onClick={() => setMenuOpen(menuOpen === item.id ? null : item.id)}
                      className="p-2 hover:bg-gray-200 rounded-lg transition-colors"
                    >
                      <MoreVertical size={18} className="text-gray-500" />
                    </button>

                    {menuOpen === item.id && (
                      <div className="absolute right-0 mt-2 w-40 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-10">
                        <button
                          onClick={() => handleDelete(item.id)}
                          className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
                        >
                          <Trash2 size={14} />
                          Delete
                        </button>
                        <button
                          onClick={() => {
                            setMenuOpen(null);
                            openCommandModal(item.gesture, "edit");
                          }}
                          className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                        >
                          Edit
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <button
            onClick={handleAddGesture}
            className="w-full p-4 flex items-center justify-center gap-2 text-gray-500 hover:bg-gray-100 transition-colors border-t border-gray-100"
          >
            <Plus size={20} />
            <span className="text-sm font-medium">Add Gesture</span>
          </button>
        </div>
      </div>

      {showPresets && (
        <PresetModal
          presets={presetGestures.filter(
            (preset) =>
              !allGestures.some(
                (item) => item.id === preset.id && item.enabled
              )
          )}
          onSelect={handlePresetSelect}
          onClose={() => setShowPresets(false)}
        />
      )}

      {commandModal && (
        <CommandModal
          mode={commandModal.mode}
          gesture={commandModal.gesture}
          value={commandModal.value}
          originalValue={commandModal.originalValue}
          onChange={(next) =>
            setCommandModal((prev) =>
              prev ? { ...prev, value: next } : prev
            )
          }
          onCancel={closeCommandModal}
          onConfirm={handleCommandSubmit}
          isSaving={isSavingCommand}
          error={commandModalError}
        />
      )}

      {showSettings && settingsDraft && (
        <SettingsModal
          values={settingsDraft}
          onChange={setSettingsDraft}
          onSave={saveSettings}
          onClose={closeSettings}
          audioDevices={audioDevices}
          defaultValues={defaultSettings}
        />
      )}

      {pendingCommands.length > 0 && (
        <CommandConfirmModal
          item={pendingCommands[0]}
          onApprove={async () => {
            await Api.confirmCommand(pendingCommands[0].id);
            const res = await Api.listPendingCommands();
            setPendingCommands(res.items || []);
          }}
          onDeny={async () => {
            await Api.denyCommand(pendingCommands[0].id);
            const res = await Api.listPendingCommands();
            setPendingCommands(res.items || []);
          }}
        />
      )}
    </div>
  );
}

function PresetModal({ presets, onSelect, onClose }) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center p-8 z-50">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
        <h2 className="text-xl font-light mb-6">Choose a Gesture</h2>
        <div className="grid grid-cols-2 gap-3 max-h-96 overflow-y-auto">
          {presets.map((preset) => (
            <button
              key={preset.id}
              onClick={() => onSelect(preset)}
              className="p-4 border border-gray-200 rounded-lg hover:border-gray-400 hover:bg-gray-50 transition-all text-left"
            >
              <div className="w-full h-16 bg-gray-200 rounded mb-2 flex items-center justify-center">
                <span className="text-xs text-gray-500">
                  {preset.name.split(" ")[0]}
                </span>
              </div>
              <p className="text-sm text-gray-700">{preset.name}</p>
            </button>
          ))}
        </div>
        <button
          onClick={onClose}
          className="mt-6 w-full py-2 text-sm text-gray-600 hover:text-gray-800"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function CommandModal({
  mode,
  gesture,
  value,
  originalValue,
  onChange,
  onCancel,
  onConfirm,
  isSaving,
  error,
}) {
  const trimmed = value.trim();
  const isUnchanged =
    mode === "edit" && trimmed === originalValue.trim();
  const isDisabled = !trimmed || isUnchanged || isSaving;
  const title = mode === "edit" ? "Edit Command" : "Add Command";
  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center p-8 z-50">
      <div className="relative bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
        <h2 className="text-xl font-light mb-2">{title}</h2>
        {gesture && (
          <p className="text-sm text-gray-600 mb-4">
            {mode === "edit" ? "Update" : "Add"}{" "}
            <span className="font-medium">{gesture.name}</span> command
          </p>
        )}
        <label className="text-xs text-gray-500 block mb-2">
          Command
        </label>
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-200"
          placeholder="Describe the action to run"
          disabled={isSaving}
        />
        {error && (
          <div className="mt-3 text-sm text-red-600">
            {error}
          </div>
        )}
        <div className="mt-6 flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-2 px-4 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
            disabled={isSaving}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={`flex-1 py-2 px-4 rounded-lg transition-colors ${
              isDisabled
                ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                : "bg-blue-500 text-white hover:bg-blue-600"
            }`}
            disabled={isDisabled}
          >
            Add
          </button>
        </div>
        {isSaving && (
          <div className="absolute inset-0 bg-white/80 flex items-center justify-center rounded-2xl">
            <div className="text-sm text-gray-600">
              Interpreting command...
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SettingsModal({
  values,
  onChange,
  onSave,
  onClose,
  audioDevices,
  defaultValues,
}) {
  const isDark = values.theme === "dark";
  const micValue = values.microphone_device_index ?? "";
  const speakerValue = values.speaker_device_index ?? "";
  const inputDevices = audioDevices?.inputs || [];
  const outputDevices = audioDevices?.outputs || [];
  return (
    <div className="fixed inset-0 bg-black/20 flex items-center justify-center p-6 z-50">
      <div className="bg-surface-elevated rounded-2xl shadow-lg border border-line w-full max-w-md p-6">
        <h2 className="text-lg font-medium text-content-primary mb-4">Settings</h2>
        <div className="max-h-[70vh] overflow-y-auto pr-1 space-y-4">
          <div className="flex items-center justify-between text-sm text-content-secondary">
            <span>Dark mode</span>
            <button
              type="button"
              role="switch"
              aria-checked={isDark}
              onClick={() =>
                onChange({ ...values, theme: isDark ? "light" : "dark" })
              }
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                isDark ? "bg-toggle-on" : "bg-toggle-off"
              }`}
            >
              <span
                className={`inline-block h-5 w-5 transform rounded-full bg-toggle-knob transition-transform ${
                  isDark ? "translate-x-5" : "translate-x-1"
                }`}
              />
            </button>
          </div>
          <div className="rounded-xl border border-line bg-surface-inset p-3 space-y-4">
            <p className="text-xs font-medium text-content-tertiary uppercase tracking-wide">
              Audio I/O
            </p>
            <div className="space-y-3">
              <DeviceSelectSegmented
                label="Microphone input"
                value={micValue}
                devices={inputDevices}
                onChange={(value) =>
                  onChange({
                    ...values,
                    microphone_device_index: value,
                  })
                }
              />
              <DeviceSelectSegmented
                label="Speaker output"
                value={speakerValue}
                devices={outputDevices}
                onChange={(value) =>
                  onChange({
                    ...values,
                    speaker_device_index: value,
                  })
                }
              />
            </div>
          </div>
          <div className="rounded-xl border border-line bg-surface-inset p-3 space-y-4">
            <p className="text-xs font-medium text-content-tertiary uppercase tracking-wide">
              Value Settings
            </p>
            <ValueSettingsPresets values={values} onChange={onChange} />
          </div>
        </div>
        <div className="mt-6 flex items-center justify-end gap-3">
            <button
              onClick={() => onChange({ ...defaultValues })}
              className="px-4 py-2 text-sm rounded-lg bg-btn-tertiary text-btn-tertiary-text hover:bg-btn-tertiary-hover transition-colors"
            >
              Reset to defaults
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm rounded-lg bg-btn-secondary text-btn-secondary-text hover:bg-btn-secondary-hover transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={onSave}
              className="px-4 py-2 text-sm rounded-lg bg-accent text-content-onaccent hover:bg-accent-hover transition-colors"
            >
              Save
            </button>
        </div>
      </div>
    </div>
  );
}

function CommandConfirmModal({ item, onApprove, onDeny }) {
  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center p-6 z-50">
      <div className="bg-white rounded-2xl shadow-lg border border-gray-200 w-full max-w-md p-6">
        <h2 className="text-lg font-medium text-gray-900 mb-2">
          Confirm Command
        </h2>
        <p className="text-sm text-gray-600 mb-4">
          {item.reason || "This command needs confirmation before running."}
        </p>
        <div className="bg-gray-100 rounded-lg p-3 text-sm text-gray-700 mb-4">
          <div className="text-xs text-gray-500 mb-1">
            Source: {item.source}
          </div>
          <div className="font-medium">{item.text}</div>
        </div>
        <div className="flex gap-3">
          <button
            onClick={onDeny}
            className="flex-1 py-2 px-4 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
          >
            Deny
          </button>
          <button
            onClick={onApprove}
            className="flex-1 py-2 px-4 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}

function DeviceSelectSegmented({ label, value, devices, onChange }) {
  const [showPicker, setShowPicker] = useState(false);
  const [mode, setMode] = useState(
    value === "" || value === null ? "default" : "pick"
  );
  const isDefault = value === "" || value === null;
  const selected = devices.find((device) => device.index === value);
  useEffect(() => {
    setMode(isDefault ? "default" : "pick");
    if (isDefault) {
      setShowPicker(false);
    }
  }, [isDefault]);
  return (
    <div>
      <label className="block text-sm text-gray-700">{label}</label>
      <div className="mt-1 rounded-lg border border-gray-300 bg-gray-100 p-2 text-sm">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setMode("default");
              setShowPicker(false);
              onChange(null);
            }}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              mode === "default"
                ? "bg-gray-800 text-white"
                : "bg-gray-300 text-gray-800 hover:bg-gray-400"
            }`}
          >
            Default
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("pick");
              setShowPicker(true);
            }}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              mode === "pick"
                ? "bg-gray-800 text-white"
                : "bg-gray-300 text-gray-800 hover:bg-gray-400"
            }`}
          >
            Pick device
          </button>
          <span className="text-xs text-gray-500">
            {selected ? selected.name : "System default"}
          </span>
        </div>
        {(showPicker || mode === "pick") && (
          <div className="mt-2 max-h-28 overflow-y-auto grid grid-cols-1 gap-1">
            {devices.map((device) => (
              <button
                key={device.index}
                type="button"
                onClick={() => {
                  onChange(Number(device.index));
                  setShowPicker(false);
                  setMode("pick");
                }}
                className={`w-full text-left px-2 py-1 rounded-md text-xs transition-colors ${
                  device.index === value
                    ? "bg-gray-300 text-gray-800"
                    : "bg-gray-100 hover:bg-gray-200 text-gray-700"
                }`}
              >
                {device.name}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ValueSettingsPresets({ values, onChange }) {
  const presets = [
    {
      key: "ui_poll_interval_ms",
      label: "UI poll interval",
      unit: "ms",
      min: 100,
      max: 2000,
      step: 50,
      values: [
        { label: "Fast", value: 250 },
        { label: "Normal", value: 500 },
        { label: "Relaxed", value: 1000 },
      ],
    },
    {
      key: "recognition_stable_frames",
      label: "Stable frames",
      unit: "frames",
      min: 1,
      max: 30,
      step: 1,
      values: [
        { label: "Low", value: 3 },
        { label: "Normal", value: 5 },
        { label: "High", value: 8 },
      ],
    },
    {
      key: "recognition_emit_cooldown_ms",
      label: "Emit cooldown",
      unit: "ms",
      min: 0,
      max: 2000,
      step: 50,
      values: [
        { label: "Short", value: 100 },
        { label: "Normal", value: 200 },
        { label: "Long", value: 500 },
      ],
    },
    {
      key: "recognition_confidence_threshold",
      label: "Confidence threshold",
      unit: "",
      min: 0,
      max: 1,
      step: 0.05,
      values: [
        { label: "Loose", value: 0.4 },
        { label: "Normal", value: 0.6 },
        { label: "Strict", value: 0.8 },
      ],
    },
  ];
  return (
    <div>
      <div className="space-y-3">
        {presets.map((preset) => (
          <div key={preset.key} className="rounded-lg border border-gray-300 bg-gray-50 p-2">
            <div className="flex items-center justify-between text-xs text-gray-700">
              <span>{preset.label}</span>
              <span>
                {values[preset.key]} {preset.unit}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {preset.values.map((option) => (
                <button
                  key={option.label}
                  type="button"
                  onClick={() =>
                    onChange({ ...values, [preset.key]: option.value })
                  }
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    values[preset.key] === option.value
                      ? "bg-gray-800 text-white"
                      : "bg-gray-300 text-gray-800 hover:bg-gray-400"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-2">
              <div className="ml-auto flex items-center gap-2 rounded-full border border-gray-300 bg-gray-100 px-2 py-1">
                <button
                  type="button"
                  onClick={() =>
                    onChange({
                      ...values,
                      [preset.key]: stepValue(preset, values[preset.key], -1),
                    })
                  }
                  className="h-6 w-6 rounded-full bg-gray-300 text-gray-800 text-xs hover:bg-gray-400 transition-colors"
                >
                  -
                </button>
                <span className="min-w-[52px] text-center text-xs text-gray-700">
                  {values[preset.key]} {preset.unit}
                </span>
                <button
                  type="button"
                  onClick={() =>
                    onChange({
                      ...values,
                      [preset.key]: stepValue(preset, values[preset.key], 1),
                    })
                  }
                  className="h-6 w-6 rounded-full bg-gray-300 text-gray-800 text-xs hover:bg-gray-400 transition-colors"
                >
                  +
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function stepValue(preset, current, direction) {
  const min = preset.min ?? 0;
  const max = preset.max ?? 1;
  const step = preset.step ?? 1;
  const next = Math.min(max, Math.max(min, Number(current) + direction * step));
  return Number(next.toFixed(2));
}
