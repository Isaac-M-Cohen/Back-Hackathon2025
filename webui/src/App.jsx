import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus, MoreVertical, Trash2, Play, Pause, Settings, Camera, Mic } from "lucide-react";
import { Api, initApiBase, waitForApiReady } from "./api";
import SettingsModal from "./components/settings/SettingsModal";

const defaultSettings = {
  theme: "light",
  ui_poll_interval_ms: 500,
  recognition_stable_frames: 5,
  recognition_emit_cooldown_ms: 200,
  recognition_confidence_threshold: 0.6,
  microphone_device_index: null,
  speaker_device_index: null,
};

function buildSettingsDraft(next = {}) {
  return {
    theme: next.theme ?? defaultSettings.theme,
    ui_poll_interval_ms:
      next.ui_poll_interval_ms ?? defaultSettings.ui_poll_interval_ms,
    recognition_stable_frames:
      next.recognition_stable_frames ?? defaultSettings.recognition_stable_frames,
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
  };
}

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

export default function App() {
  const isSettingsWindow = useMemo(() => {
    if (typeof window === "undefined") {
      return false;
    }
    const params = new URLSearchParams(window.location.search);
    return params.get("window") === "settings";
  }, []);

  return isSettingsWindow ? <SettingsWindow /> : <GestureControlApp />;
}

function GestureControlApp() {
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
  const [showExitConfirm, setShowExitConfirm] = useState(false);
  const settingsOpenRef = useRef(false);
  const lastSettingsOpenAtRef = useRef(0);

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
            try {
              window.localStorage.setItem("easy-theme", settings.theme);
            } catch {
              // Ignore storage failures.
            }
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
    let unlisten;
    (async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event");
        unlisten = await listen("easy://theme-changed", (event) => {
          const next = event?.payload?.theme;
          if (typeof next === "string") {
            setThemeMode(next);
            try {
              window.localStorage.setItem("easy-theme", next);
            } catch {
              // Ignore storage failures.
            }
          }
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
  }, []);

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
    const handleKeyDown = (event) => {
      if (event.isComposing) {
        return;
      }
      if (event.key !== "Escape") {
        return;
      }
      if (
        showPresets ||
        commandModal ||
        showSettings ||
        pendingCommands.length > 0 ||
        showExitConfirm
      ) {
        return;
      }
      event.preventDefault();
      setShowExitConfirm(true);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    commandModal,
    pendingCommands.length,
    showExitConfirm,
    showPresets,
    showSettings,
  ]);

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

  const openSettings = useCallback(async (source = "unknown") => {
    const now = Date.now();
    if (now - lastSettingsOpenAtRef.current < 1000) {
      console.log("[Settings] open throttled", {
        source,
        sinceMs: now - lastSettingsOpenAtRef.current,
      });
      return;
    }
    if (showSettings || settingsOpenRef.current) {
      console.log("[Settings] open ignored", {
        source,
        showSettings,
        inFlight: settingsOpenRef.current,
      });
      return;
    }
    lastSettingsOpenAtRef.current = now;
    settingsOpenRef.current = true;
    console.log("[Settings] open requested", { source });
    console.trace("[Settings] open stack");
    try {
      const { emit } = await import("@tauri-apps/api/event");
      await emit("easy://open-settings-window");
      settingsOpenRef.current = false;
      return;
    } catch {
      // Tauri APIs not available (web dev mode).
    }
    try {
      const next = await Api.getSettings();
      setSettings(next);
      setSettingsDraft(buildSettingsDraft(next));
    } catch (err) {
      setError(err.message);
      setSettingsDraft(buildSettingsDraft());
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
    setTimeout(() => {
      setShowSettings(true);
    }, 200);
    settingsOpenRef.current = false;
  }, [showSettings]);

  const closeSettings = () => {
    console.log("[Settings] close requested");
    console.trace("[Settings] close stack");
    setShowSettings(false);
    setSettingsDraft(null);
  };

  const saveSettings = async () => {
    console.log("[Settings] save requested");
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
          try {
            const { emit } = await import("@tauri-apps/api/event");
            await emit("easy://theme-changed", { theme: res.settings.theme });
          } catch {
            // Tauri APIs not available (web dev mode).
          }
          try {
            window.localStorage.setItem("easy-theme", res.settings.theme);
          } catch {
            // Ignore storage failures.
          }
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
          console.log("[Settings] menu event received");
          openSettings("menu");
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

  useEffect(() => {
    console.log("[Settings] state", {
      showSettings,
      hasDraft: Boolean(settingsDraft),
    });
  }, [showSettings, settingsDraft]);

  if (isBooting) {
    return (
      <div className="min-h-screen bg-surface-base flex flex-col">
        <div className="h-7 w-full flex-shrink-0" data-tauri-drag-region />
        <div className="flex-1 flex items-center justify-center">
          <div className="bg-surface-elevated border border-line rounded-2xl shadow-sm px-8 py-6 text-center">
            <div className="text-sm text-content-secondary">{bootMessage}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface-base flex flex-col">
      <div className="h-7 w-full flex-shrink-0" data-tauri-drag-region />
      <div className="flex-1 flex items-center justify-center p-8">
      <div className="w-full max-w-2xl">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-light text-content-primary">Gesture Control</h1>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-2 py-1 rounded-lg border border-line bg-surface-elevated">
              <span
                className={`h-2 w-2 rounded-full ${
                  isGestureRunning ? "bg-status-active" : "bg-status-inactive"
                }`}
              />
              <Camera size={14} className="text-content-secondary" />
              <span className="text-[11px] text-content-secondary">Camera</span>
            </div>
            <div className="flex items-center gap-2 px-2 py-1 rounded-lg border border-line bg-surface-elevated">
              <span
                className={`h-2 w-2 rounded-full ${
                  isVoiceRunning ? "bg-status-active" : "bg-status-inactive"
                }`}
              />
              <Mic size={14} className="text-content-secondary" />
              <div className="w-10 h-2 bg-surface-inset rounded-full overflow-hidden">
                <div
                  className={`h-2 transition-all ${
                    isVoiceRunning ? "bg-status-active" : "bg-content-tertiary"
                  }`}
                  style={{
                    width: `${Math.min(100, Math.max(0, (voiceStatus.audio_level || 0) * 100))}%`,
                  }}
                />
              </div>
            </div>
            <button
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                openSettings("button");
              }}
              className="p-2 rounded-lg border border-line bg-surface-elevated text-content-secondary hover:text-content-primary hover:border-line hover:bg-surface-elevated-hover"
              aria-label="Settings"
              title="Settings"
            >
              <Settings size={18} />
            </button>
            <button
              onClick={toggleGestureRecognition}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all hover:shadow-sm ${
                isGestureRunning
                  ? "bg-status-active text-white hover:bg-status-active-hover"
                  : "bg-btn-secondary text-btn-secondary-text hover:bg-btn-secondary-hover"
              }`}
            >
              {isGestureRunning ? <Pause size={16} /> : <Play size={16} />}
              {isGestureRunning ? "Gesture On" : "Gesture Off"}
            </button>
            <button
              onClick={toggleVoiceRecognition}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all hover:shadow-sm ${
                isVoiceRunning
                  ? "bg-status-active text-white hover:bg-status-active-hover"
                  : "bg-btn-secondary text-btn-secondary-text hover:bg-btn-secondary-hover"
              }`}
            >
              {isVoiceRunning ? <Pause size={16} /> : <Play size={16} />}
              {isVoiceRunning ? "Voice On" : "Voice Off"}
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg bg-status-error-bg border border-status-error-border text-status-error-text px-4 py-2 text-sm">
            {error}
          </div>
        )}

        {isGestureRunning && lastDetection && (
          <div className="mb-4 rounded-lg bg-status-success-bg border border-status-success-border text-status-success-text px-4 py-2 text-sm flex items-center justify-between">
            <span>
              Detected: <strong>{lastDetection.label}</strong>{" "}
              {lastDetection.confidence !== undefined &&
                `(conf ${lastDetection.confidence.toFixed(2)})`}
            </span>
          </div>
        )}

        {isVoiceRunning && (
          <div className="mb-4 rounded-lg bg-status-info-bg border border-status-info-border text-status-info-text px-4 py-2 text-sm">
            <div className="flex items-center justify-between">
              <span>
                Transcribed:{" "}
                <strong>
                  {voiceStatus.live_transcript
                    ? voiceStatus.live_transcript
                    : "Listening..."}
                </strong>
              </span>
            </div>
            {Array.isArray(voiceStatus.subjects) && voiceStatus.subjects.length > 0 && (
              <div className="mt-2 text-xs opacity-80">
                Subjects: {voiceStatus.subjects.join(", ")}
              </div>
            )}
          </div>
        )}

        {lastCommandMeta && (
          <div className="mb-4 rounded-lg bg-surface-inset border border-accent text-content-primary px-4 py-2 text-sm flex items-center justify-between">
            <span>
              Last command: <strong>{lastCommandMeta.status}</strong>{" "}
              {lastCommandMeta.stepCount > 0 && `(${lastCommandMeta.stepCount} steps)`}
              {lastCommandMeta.reason && ` — ${lastCommandMeta.reason}`}
            </span>
            {lastCommandMeta.timestamp && (
              <span className="text-xs text-content-secondary">
                {lastCommandMeta.timestamp.toLocaleTimeString()}
              </span>
            )}
          </div>
        )}

        <div className="bg-surface-elevated rounded-2xl shadow-sm border border-line overflow-hidden">
          {gestures.length === 0 ? (
            <div className="p-16 text-center">
              <div className="text-content-tertiary mb-4">
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
              <p className="text-content-secondary text-sm font-light">No gestures tracked yet</p>
            </div>
          ) : (
            <div className="divide-y divide-line-divider">
              {gestures.map((item) => (
                <div
                  key={item.id}
                  className={`flex items-center px-6 py-4 transition-colors ${
                    hoveredId === item.id ? "bg-surface-inset" : ""
                  }`}
                  onMouseEnter={() => setHoveredId(item.id)}
                  onMouseLeave={() => setHoveredId(null)}
                >
                  <div className="w-20 h-20 bg-surface-input rounded-lg flex items-center justify-center mr-4 flex-shrink-0">
                    {hoveredId === item.id ? (
                      <div className="text-xs text-content-secondary animate-pulse">
                        {item.gesture.name}
                      </div>
                    ) : (
                      <div className="text-xs text-content-tertiary">
                        {item.gesture.name.split(" ")[0]}
                      </div>
                    )}
                  </div>

                  <div className="flex-1">
                    <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-surface-inset rounded-lg">
                      {(item.hotkey || "Unset")
                        .split("+")
                        .filter(Boolean)
                        .map((key, i) => (
                          <React.Fragment key={i}>
                            {i > 0 && <span className="text-content-tertiary text-xs">+</span>}
                            <kbd className="text-sm font-medium text-content-primary">{key}</kbd>
                          </React.Fragment>
                        ))}
                    </div>
                    <div className="mt-3 text-xs text-content-secondary">
                      <span className="uppercase tracking-wide text-[10px]">
                        Command
                      </span>
                      <div className="mt-1 text-sm text-content-primary">
                        {item.command || "No command set"}
                      </div>
                    </div>
                  </div>

                  <div className="relative">
                    <button
                      onClick={() => setMenuOpen(menuOpen === item.id ? null : item.id)}
                      className="p-2 hover:bg-surface-input rounded-lg transition-colors"
                    >
                      <MoreVertical size={18} className="text-content-secondary" />
                    </button>

                    {menuOpen === item.id && (
                      <div className="absolute right-0 mt-2 w-40 bg-surface-elevated rounded-lg shadow-lg border border-line py-1 z-10">
                        <button
                          onClick={() => handleDelete(item.id)}
                          className="w-full px-4 py-2 text-left text-sm text-status-error-text hover:bg-status-error-bg flex items-center gap-2"
                        >
                          <Trash2 size={14} />
                          Delete
                        </button>
                        <button
                          onClick={() => {
                            setMenuOpen(null);
                            openCommandModal(item.gesture, "edit");
                          }}
                          className="w-full px-4 py-2 text-left text-sm text-content-primary hover:bg-surface-inset-hover flex items-center gap-2"
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
            className="w-full p-4 flex items-center justify-center gap-2 text-content-secondary hover:bg-surface-inset transition-colors border-t border-line-divider"
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
          isOpen={showSettings}
          values={settingsDraft}
          onChange={setSettingsDraft}
          onSave={saveSettings}
          onClose={closeSettings}
          onReset={() => setSettingsDraft({ ...defaultSettings })}
          audioDevices={audioDevices}
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
      {showExitConfirm && (
        <ExitConfirmModal
          onCancel={() => setShowExitConfirm(false)}
          onConfirm={async () => {
            setShowExitConfirm(false);
            try {
              const { getCurrentWebviewWindow } = await import(
                "@tauri-apps/api/webviewWindow"
              );
              const win = getCurrentWebviewWindow();
              await win.close();
            } catch {
              if (typeof window !== "undefined") {
                window.close();
              }
            }
          }}
        />
      )}
      </div>
    </div>
  );
}

function SettingsWindow() {
  const [settingsDraft, setSettingsDraft] = useState(null);
  const [audioDevices, setAudioDevices] = useState({ inputs: [], outputs: [] });
  const [error, setError] = useState("");
  const [themeMode, setThemeMode] = useState(defaultSettings.theme);

  useEffect(() => {
    let cancelled = false;
    initApiBase().then(async () => {
      try {
        const next = await Api.getSettings();
        if (cancelled) {
          return;
        }
        setSettingsDraft(buildSettingsDraft(next));
        if (next.theme) {
          setThemeMode(next.theme);
          try {
            window.localStorage.setItem("easy-theme", next.theme);
          } catch {
            // Ignore storage failures.
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || "Failed to load settings.");
          setSettingsDraft(buildSettingsDraft());
        }
      }
      try {
        const devices = await Api.listAudioDevices();
        if (!cancelled) {
          setAudioDevices({
            inputs: devices.inputs || [],
            outputs: devices.outputs || [],
          });
        }
      } catch {
        if (!cancelled) {
          setAudioDevices({ inputs: [], outputs: [] });
        }
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

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
    let unlisten;
    (async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event");
        unlisten = await listen("easy://theme-changed", (event) => {
          const next = event?.payload?.theme;
          if (typeof next === "string") {
            setThemeMode(next);
            try {
              window.localStorage.setItem("easy-theme", next);
            } catch {
              // Ignore storage failures.
            }
          }
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
  }, []);

  const closeSettings = useCallback(async () => {
    try {
      const { getCurrentWebviewWindow } = await import(
        "@tauri-apps/api/webviewWindow"
      );
      const win = getCurrentWebviewWindow();
      await win.close();
    } catch {
      if (typeof window !== "undefined") {
        window.close();
      }
    }
  }, []);

  const saveSettings = async () => {
    if (!settingsDraft) {
      return;
    }
    try {
      const res = await Api.updateSettings(settingsDraft);
      if (res && res.settings) {
        setSettingsDraft(buildSettingsDraft(res.settings));
        if (res.settings.theme) {
          setThemeMode(res.settings.theme);
          try {
            const { emit } = await import("@tauri-apps/api/event");
            await emit("easy://theme-changed", { theme: res.settings.theme });
          } catch {
            // Tauri APIs not available (web dev mode).
          }
          try {
            window.localStorage.setItem("easy-theme", res.settings.theme);
          } catch {
            // Ignore storage failures.
          }
        }
      }
      closeSettings();
    } catch (err) {
      setError(err.message || "Failed to save settings.");
    }
  };

  if (!settingsDraft) {
    return (
      <div className="h-screen bg-surface-elevated p-6 text-content-secondary overflow-hidden">
        <div className="h-7 w-full" data-tauri-drag-region />
        Loading settings...
      </div>
    );
  }

  return (
    <div className="h-screen bg-surface-elevated flex flex-col overflow-hidden">
      <div className="h-7 w-full flex-shrink-0" data-tauri-drag-region />
      {error && (
        <div className="px-6 pt-4 text-sm text-status-error-text">
          {error}
        </div>
      )}
      <div className="flex-1 overflow-hidden">
        <SettingsModal
          variant="window"
          isOpen
          values={settingsDraft}
          onChange={setSettingsDraft}
          onSave={saveSettings}
          onClose={closeSettings}
          onReset={() => setSettingsDraft(buildSettingsDraft())}
          audioDevices={audioDevices}
        />
      </div>
    </div>
  );
}

function PresetModal({ presets, onSelect, onClose }) {
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.isComposing) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center p-8 z-50">
      <div className="bg-surface-elevated rounded-2xl shadow-xl max-w-md w-full p-6">
        <h2 className="text-xl font-light mb-6 text-content-primary">Choose a Gesture</h2>
        <div className="grid grid-cols-2 gap-3 max-h-96 overflow-y-auto">
          {presets.map((preset) => (
            <button
              key={preset.id}
              onClick={() => onSelect(preset)}
              className="p-4 border border-line rounded-lg hover:border-line-strong hover:bg-surface-inset-hover transition-all text-left"
            >
              <div className="w-full h-16 bg-surface-input rounded mb-2 flex items-center justify-center">
                <span className="text-xs text-content-secondary">
                  {preset.name.split(" ")[0]}
                </span>
              </div>
              <p className="text-sm text-content-primary">{preset.name}</p>
            </button>
          ))}
        </div>
        <button
          onClick={onClose}
          className="mt-6 w-full py-2 text-sm text-content-secondary hover:text-content-primary"
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
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.isComposing) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key === "Enter") {
        if (isDisabled) {
          return;
        }
        event.preventDefault();
        onConfirm();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isDisabled, onCancel, onConfirm]);

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center p-8 z-50">
      <div className="relative bg-surface-elevated rounded-2xl shadow-xl max-w-md w-full p-6">
        <h2 className="text-xl font-light mb-2 text-content-primary">{title}</h2>
        {gesture && (
          <p className="text-sm text-content-secondary mb-4">
            {mode === "edit" ? "Update" : "Add"}{" "}
            <span className="font-medium">{gesture.name}</span> command
          </p>
        )}
        <label className="text-xs text-content-secondary block mb-2">
          Command
        </label>
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full border border-line rounded-lg px-3 py-2 text-sm text-content-primary bg-surface-input focus:outline-none focus:ring-2 focus:ring-accent"
          placeholder="Describe the action to run"
          disabled={isSaving}
          autoFocus
        />
        {error && (
          <div className="mt-3 text-sm text-status-error-text">
            {error}
          </div>
        )}
        <div className="mt-6 flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-2 px-4 bg-btn-secondary text-btn-secondary-text rounded-lg hover:bg-btn-secondary-hover transition-colors"
            disabled={isSaving}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={`flex-1 py-2 px-4 rounded-lg transition-colors ${
              isDisabled
                ? "bg-btn-secondary text-content-tertiary cursor-not-allowed"
                : "bg-accent text-content-onaccent hover:bg-accent-hover"
            }`}
            disabled={isDisabled}
          >
            Add
          </button>
        </div>
        {isSaving && (
          <div className="absolute inset-0 bg-white/90 dark:bg-black/60 backdrop-blur-sm flex items-center justify-center rounded-2xl">
            <div className="text-sm text-content-secondary">
              Interpreting command...
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function CommandConfirmModal({ item, onApprove, onDeny }) {
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.isComposing) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        onDeny();
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        onApprove();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onApprove, onDeny]);

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center p-6 z-50">
      <div className="bg-surface-elevated rounded-2xl shadow-lg border border-line w-full max-w-md p-6">
        <h2 className="text-lg font-medium text-content-primary mb-2">
          Confirm Command
        </h2>
        <p className="text-sm text-content-secondary mb-4">
          {item.reason || "This command needs confirmation before running."}
        </p>
        <div className="bg-surface-inset rounded-lg p-3 text-sm text-content-primary mb-4">
          <div className="text-xs text-content-secondary mb-1">
            Source: {item.source}
          </div>
          <div className="font-medium">{item.text}</div>
        </div>
        <div className="flex gap-3">
          <button
            onClick={onDeny}
            className="flex-1 py-2 px-4 bg-btn-secondary text-btn-secondary-text rounded-lg hover:bg-btn-secondary-hover transition-colors"
          >
            Deny
          </button>
          <button
            onClick={onApprove}
            className="flex-1 py-2 px-4 bg-accent text-content-onaccent rounded-lg hover:bg-accent-hover transition-colors"
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}

function ExitConfirmModal({ onCancel, onConfirm }) {
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.isComposing) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        onConfirm();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onCancel, onConfirm]);

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center p-6 z-50">
      <div className="bg-surface-elevated rounded-2xl shadow-lg border border-line w-full max-w-md p-6">
        <h2 className="text-lg font-medium text-content-primary mb-2">
          Close App?
        </h2>
        <p className="text-sm text-content-secondary mb-4">
          Are you sure you want to close the main window?
        </p>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-2 px-4 bg-btn-secondary text-btn-secondary-text rounded-lg hover:bg-btn-secondary-hover transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 py-2 px-4 bg-accent text-content-onaccent rounded-lg hover:bg-accent-hover transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
