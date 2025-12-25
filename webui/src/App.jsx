import React, { useEffect, useState } from "react";
import { Plus, MoreVertical, Trash2, Play, Pause } from "lucide-react";
import { Api, initApiBase } from "./api";

const PRESET_GESTURES = [
  { id: "thumbs_up", name: "Thumbs Up", duration: 1.2 },
  { id: "peace_sign", name: "Peace Sign", duration: 1.0 },
  { id: "wave", name: "Wave", duration: 1.5 },
  { id: "fist", name: "Closed Fist", duration: 1.0 },
  { id: "open_palm", name: "Open Palm", duration: 1.0 },
  { id: "point_up", name: "Point Up", duration: 1.0 },
  { id: "swipe_left", name: "Swipe Left", duration: 1.3 },
  { id: "swipe_right", name: "Swipe Right", duration: 1.3 },
];

export default function GestureControlApp() {
  const [gestures, setGestures] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [showPresets, setShowPresets] = useState(false);
  const [showHotkeyModal, setShowHotkeyModal] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState(null);
  const [hoveredId, setHoveredId] = useState(null);
  const [menuOpen, setMenuOpen] = useState(null);
  const [error, setError] = useState("");
  const [lastDetection, setLastDetection] = useState(null);

  useEffect(() => {
    initApiBase().then(() => {
      refreshGestures().catch((err) => setError(err.message));
    });
  }, []);

  useEffect(() => {
    if (!isRunning) {
      setLastDetection(null);
      return undefined;
    }
    const id = setInterval(async () => {
      try {
        const res = await Api.lastDetection();
        if (res && res.label) {
          setLastDetection(res);
        }
      } catch (err) {
        console.error(err);
      }
    }, 1000);
    return () => clearInterval(id);
  }, [isRunning]);

  async function refreshGestures() {
    try {
      const data = await Api.listGestures();
      setGestures(
        data.items?.map((item) => ({
          id: item.label,
          gesture: { id: item.label, name: item.label },
          hotkey: item.hotkey || "",
        })) || []
      );
    } catch (err) {
      setError(err.message);
    }
  }

  const handleAddGesture = () => {
    setShowPresets(true);
  };

  const handlePresetSelect = (preset) => {
    setSelectedPreset(preset);
    setShowPresets(false);
    setShowHotkeyModal(true);
  };

  const handleHotkeySubmit = async (hotkey, mode = "static") => {
    if (hotkey && selectedPreset) {
      try {
        if (mode === "static") {
          await Api.addStaticGesture(selectedPreset.id, 60, hotkey);
        } else {
          await Api.addDynamicGesture(selectedPreset.id, 6, 25, hotkey);
        }
        await Api.train();
        await refreshGestures();
      } catch (err) {
        setError(err.message);
      }
      setShowHotkeyModal(false);
      setSelectedPreset(null);
    }
  };

  const handleDelete = async (id) => {
    setMenuOpen(null);
    try {
      await Api.deleteGesture(id);
      await Api.train();
      await refreshGestures();
    } catch (err) {
      setError(err.message);
    }
  };

  const toggleRecognition = async () => {
    try {
      if (isRunning) {
        await Api.stopRecognition();
        setIsRunning(false);
      } else {
        await Api.startRecognition({
          confidence_threshold: 0.6,
          stable_frames: 5,
          show_window: false,
        });
        setIsRunning(true);
      }
    } catch (err) {
      setError(err.message || "Failed to start/stop recognition. Collect and train first?");
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="w-full max-w-2xl">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-light text-gray-800">Gesture Control</h1>
          <button
            onClick={toggleRecognition}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
              isRunning
                ? "bg-green-500 text-white hover:bg-green-600"
                : "bg-gray-300 text-gray-700 hover:bg-gray-400"
            }`}
          >
            {isRunning ? <Pause size={16} /> : <Play size={16} />}
            {isRunning ? "Running" : "Stopped"}
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 border border-red-200 text-red-700 px-4 py-2 text-sm">
            {error}
          </div>
        )}

        {lastDetection && (
          <div className="mb-4 rounded-lg bg-green-50 border border-green-200 text-green-800 px-4 py-2 text-sm flex items-center justify-between">
            <span>
              Detected: <strong>{lastDetection.label}</strong>{" "}
              {lastDetection.confidence !== undefined &&
                `(conf ${lastDetection.confidence.toFixed(2)})`}
            </span>
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
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <button
            onClick={handleAddGesture}
            className="w-full p-4 flex items-center justify-center gap-2 text-gray-500 hover:bg-gray-50 transition-colors border-t border-gray-100"
          >
            <Plus size={20} />
            <span className="text-sm font-medium">Add Gesture</span>
          </button>
        </div>
      </div>

      {showPresets && (
        <PresetModal onSelect={handlePresetSelect} onClose={() => setShowPresets(false)} />
      )}

      {showHotkeyModal && (
        <HotkeyModal
          preset={selectedPreset}
          onSubmit={handleHotkeySubmit}
          onCancel={() => {
            setShowHotkeyModal(false);
            setSelectedPreset(null);
          }}
        />
      )}
    </div>
  );
}

function PresetModal({ onSelect, onClose }) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center p-8 z-50">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
        <h2 className="text-xl font-light mb-6">Choose a Gesture</h2>
        <div className="grid grid-cols-2 gap-3 max-h-96 overflow-y-auto">
          {PRESET_GESTURES.map((preset) => (
            <button
              key={preset.id}
              onClick={() => onSelect(preset)}
              className="p-4 border border-gray-200 rounded-lg hover:border-gray-400 hover:bg-gray-50 transition-all text-left"
            >
              <div className="w-full h-16 bg-gray-200 rounded mb-2 flex items-center justify-center">
                <span className="text-xs text-gray-500">{preset.name.split(" ")[0]}</span>
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

function HotkeyModal({ onSubmit, onCancel, preset }) {
  const [hotkey, setHotkey] = useState("");
  const [mode, setMode] = useState("static");

  const handleKeyDown = (e) => {
    e.preventDefault();
    const keys = [];
    if (e.ctrlKey) keys.push("Ctrl");
    if (e.shiftKey) keys.push("Shift");
    if (e.altKey) keys.push("Alt");
    if (e.metaKey) keys.push("Cmd");

    const key = e.key.length === 1 ? e.key.toUpperCase() : e.key;
    if (!["Control", "Shift", "Alt", "Meta"].includes(key)) {
      keys.push(key);
    }

    if (keys.length > 0) {
      setHotkey(keys.join("+"));
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center p-8 z-50">
      <div className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-6">
        <h2 className="text-xl font-light mb-4">Assign Hotkey</h2>
        {preset && (
          <p className="text-sm text-gray-600 mb-2">
            Gesture: <span className="font-medium">{preset.name}</span>
          </p>
        )}
        <p className="text-sm text-gray-600 mb-4">Press the key combination you want to use</p>

        <div
          onKeyDown={handleKeyDown}
          tabIndex={0}
          className="w-full p-4 border-2 border-gray-300 rounded-lg mb-4 text-center focus:border-blue-500 focus:outline-none cursor-text"
        >
          {hotkey ? (
            <span className="text-lg font-medium text-gray-800">{hotkey}</span>
          ) : (
            <span className="text-gray-400">Press keys...</span>
          )}
        </div>

        <div className="flex gap-3 mb-4">
          <button
            onClick={() => setMode("static")}
            className={`flex-1 py-2 px-4 rounded-lg border ${
              mode === "static" ? "bg-blue-50 border-blue-400 text-blue-700" : "bg-gray-100"
            }`}
          >
            Static
          </button>
          <button
            onClick={() => setMode("dynamic")}
            className={`flex-1 py-2 px-4 rounded-lg border ${
              mode === "dynamic" ? "bg-blue-50 border-blue-400 text-blue-700" : "bg-gray-100"
            }`}
          >
            Dynamic
          </button>
        </div>

        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-2 px-4 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onSubmit(hotkey, mode)}
            disabled={!hotkey}
            className="flex-1 py-2 px-4 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
