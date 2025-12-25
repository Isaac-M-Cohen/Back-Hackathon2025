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
  } catch {
    // Tauri APIs not available (web dev mode).
  }
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
  async lastDetection() {
    return request("/recognition/last");
  },
  async deleteGesture(label) {
    return request("/gestures/delete", {
      method: "POST",
      body: JSON.stringify({ label }),
    });
  },
};
