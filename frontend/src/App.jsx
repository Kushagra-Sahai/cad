import { Activity, AlertCircle } from "lucide-react";
import { useEffect, useState } from "react";
import ChatBox from "./components/ChatBox.jsx";
import ImageUploader from "./components/ImageUploader.jsx";
import MedicineCard from "./components/MedicineCard.jsx";
import VoiceRecorder from "./components/VoiceRecorder.jsx";
import { analyzeImage, healthCheck, searchMedicine, speechToText, textToSpeech } from "./services/api.js";

function asList(...values) {
  return values
    .flatMap((value) => {
      if (!value) return [];
      if (Array.isArray(value)) return value;
      return [value];
    })
    .map((value) => String(value).trim())
    .filter(Boolean);
}

function resultMessage(medicine) {
  const name = medicine.brand_name || medicine.generic_name || "the medicine";
  const confidence = Math.round((medicine.confidence_score || 0) * 100);
  const indications = asList(
    medicine.why_used,
    medicine.indications,
    medicine.uses,
    medicine.use,
    medicine.indication,
    medicine.purpose,
  );
  const usedFor = indications.length ? ` Used for: ${indications.slice(0, 2).join("; ")}.` : "";
  return `Result for ${name}. Confidence ${confidence}%.${usedFor}`;
}

function speechSummary(medicine) {
  const indications = asList(
    medicine.why_used,
    medicine.indications,
    medicine.uses,
    medicine.use,
    medicine.indication,
    medicine.purpose,
  );
  return [
    medicine.brand_name && `Brand name: ${medicine.brand_name}.`,
    medicine.generic_name && `Generic name: ${medicine.generic_name}.`,
    medicine.drug_class && `Drug class: ${medicine.drug_class}.`,
    indications.length ? `Used for: ${indications.slice(0, 3).join("; ")}.` : "",
    medicine.usage_guidance,
    medicine.timing_guidance,
    medicine.warnings_precautions?.length ? `Warnings: ${medicine.warnings_precautions.slice(0, 2).join(" ")}` : "",
    medicine.disclaimer,
  ]
    .filter(Boolean)
    .join(" ");
}

export default function App() {
  const [messages, setMessages] = useState([
    { id: "welcome", role: "assistant", text: "Ready for a medicine name, label image, or voice input." },
  ]);
  const [medicine, setMedicine] = useState(null);
  const [loading, setLoading] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState("");
  const [health, setHealth] = useState(null);

  useEffect(() => {
    healthCheck()
      .then(setHealth)
      .catch(() => setHealth({ status: "offline", mongo: "unknown", llm_provider: "unknown" }));
  }, []);

  function appendMessage(role, text) {
    setMessages((items) => [...items, { id: crypto.randomUUID(), role, text }]);
  }

  async function runAnalysis(label, work) {
    setLoading(true);
    setError("");
    appendMessage("user", label);
    try {
      const result = await work();
      setMedicine(result);
      appendMessage("assistant", resultMessage(result));
    } catch (err) {
      const detail = err.message || "Analysis failed.";
      setError(detail);
      appendMessage("assistant", detail);
    } finally {
      setLoading(false);
    }
  }

  async function handleTextSubmit(query) {
    await runAnalysis(query, () => searchMedicine(query));
  }

  async function handleImageAnalyze(file) {
    await runAnalysis(`Image: ${file.name}`, () => analyzeImage(file));
  }

  async function handleTranscript(blob) {
    setLoading(true);
    setError("");
    try {
      const transcript = await speechToText(blob);
      if (!transcript.transcript) {
        throw new Error("No speech was recognized.");
      }
      appendMessage("user", transcript.transcript);
      const result = await searchMedicine(transcript.transcript);
      setMedicine(result);
      appendMessage("assistant", resultMessage(result));
    } catch (err) {
      const detail = err.message || "Speech analysis failed.";
      setError(detail);
      appendMessage("assistant", detail);
    } finally {
      setLoading(false);
    }
  }

  async function handleSpeak() {
    if (!medicine || speaking) return;
    setSpeaking(true);
    setError("");
    try {
      const audioBlob = await textToSpeech(speechSummary(medicine));
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        setSpeaking(false);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        setSpeaking(false);
      };
      await audio.play();
    } catch (err) {
      setSpeaking(false);
      setError(err.message || "Audio playback failed.");
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">
            <Activity size={24} />
          </div>
          <div>
            <h1>MediScan AI</h1>
            <p>Medicine analysis workspace</p>
          </div>
        </div>
        <div className={`status-pill ${health?.status === "ok" ? "online" : "offline"}`}>
          <span />
          {health?.status === "ok" ? "Online" : "Checking"}
        </div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      <div className="workspace">
        <div className="input-stack">
          <ChatBox messages={messages} onSubmit={handleTextSubmit} loading={loading} />
          <div className="tool-grid">
            <ImageUploader onAnalyze={handleImageAnalyze} loading={loading} />
            <VoiceRecorder onTranscript={handleTranscript} loading={loading} />
          </div>
        </div>
        <MedicineCard medicine={medicine} onSpeak={handleSpeak} speaking={speaking} />
      </div>
    </main>
  );
}
