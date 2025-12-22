const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
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
  async addStaticGesture(label, targetFrames = 60) {
    return request("/gestures/static", {
      method: "POST",
      body: JSON.stringify({ label, target_frames: targetFrames }),
    });
  },
  async addDynamicGesture(label, repetitions = 5, sequenceLength = 30) {
    return request("/gestures/dynamic", {
      method: "POST",
      body: JSON.stringify({
        label,
        repetitions,
        sequence_length: sequenceLength,
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
  async deleteGesture(label) {
    return request("/gestures/delete", {
      method: "POST",
      body: JSON.stringify({ label }),
    });
  },
};
