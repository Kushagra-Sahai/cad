const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const API_PREFIX = `${API_BASE_URL.replace(/\/$/, "")}/api/v1`;

async function parseResponse(response) {
  if (response.ok) {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return response.json();
    }
    return response.blob();
  }

  let detail = `Request failed with status ${response.status}`;
  try {
    const payload = await response.json();
    detail = payload.detail || detail;
  } catch {
    detail = response.statusText || detail;
  }
  throw new Error(detail);
}

export async function searchMedicine(query) {
  const response = await fetch(`${API_PREFIX}/search-medicine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  return parseResponse(response);
}

export async function analyzeImage(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_PREFIX}/analyze-image`, {
    method: "POST",
    body: formData,
  });
  return parseResponse(response);
}

export async function speechToText(blob) {
  const formData = new FormData();
  const extension = blob.type.includes("wav") ? "wav" : "webm";
  formData.append("file", blob, `recording.${extension}`);
  const response = await fetch(`${API_PREFIX}/speech-to-text`, {
    method: "POST",
    body: formData,
  });
  return parseResponse(response);
}

export async function textToSpeech(text) {
  const params = new URLSearchParams({ text });
  const response = await fetch(`${API_PREFIX}/text-to-speech?${params.toString()}`);
  return parseResponse(response);
}

export async function healthCheck() {
  const response = await fetch(`${API_PREFIX}/health`);
  return parseResponse(response);
}
