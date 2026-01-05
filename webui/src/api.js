let apiBase =
  import.meta.env.VITE_API_BASE ||
  (typeof window !== "undefined" && window.__EASY_API_BASE__) ||
  "http://127.0.0.1:8000";

export function setApiBase(nextBase) {
  if (nextBase) {
    apiBase = nextBase;
  }
}

export async function initApiBase() {
  try {
    const { listen } = await import("@tauri-apps/api/event");
    await listen("easy://api-base", (event) => {
      setApiBase(event.payload);
    });
    if (typeof window !== "undefined" && window.__EASY_API_BASE__) {
      setApiBase(window.__EASY_API_BASE__);
    }
  } catch {
    // Tauri APIs not available (web dev mode).
  }
}

export async function waitForApiReady({ timeoutMs = 8000, intervalMs = 200 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${apiBase}/status`);
      if (res.ok) {
        return true;
      }
    } catch {
      // Backend still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Backend is still starting. Please wait a moment and retry.");
}

async function request(path, options = {}) {
  const res = await fetch(`${apiBase}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export const Api = {
  async listGestures() {
    return request("/gestures");
  },
  async addStaticGesture(label, targetFrames = 60, hotkey = "") {
    return request("/gestures/static", {
      method: "POST",
      body: JSON.stringify({ label, target_frames: targetFrames, hotkey }),
    });
  },
  async addDynamicGesture(label, repetitions = 5, sequenceLength = 30, hotkey = "") {
    return request("/gestures/dynamic", {
      method: "POST",
      body: JSON.stringify({
        label,
        repetitions,
        sequence_length: sequenceLength,
        hotkey,
      }),
    });
  },
  async train() {
    return request("/train", { method: "POST" });
  },
  async startRecognition(params) {
    return request("/recognition/start", {
      method: "POST",
      body: JSON.stringify(params || {}),
    });
  },
  async stopRecognition() {
    return request("/recognition/stop", { method: "POST" });
  },
  async status() {
    return request("/status");
  },
  async lastDetection() {
    return request("/recognition/last");
  },
  async deleteGesture(label) {
    return request("/gestures/delete", {
      method: "POST",
      body: JSON.stringify({ label }),
    });
  },
  async enableGesture(label, enabled = true) {
    return request("/gestures/enable", {
      method: "POST",
      body: JSON.stringify({ label, enabled }),
    });
  },
  async listPresetGestures() {
    return request("/gestures/presets");
  },
  async getSettings() {
    return request("/settings");
  },
  async updateSettings(values) {
    return request("/settings", {
      method: "POST",
      body: JSON.stringify(values || {}),
    });
  },
  async listAudioDevices() {
    return request("/audio/devices");
  },
};
