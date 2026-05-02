import { Loader2, Mic, Square } from "lucide-react";
import { useRef, useState } from "react";

function preferredMimeType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/wav", "audio/mp4"];
  return candidates.find((type) => window.MediaRecorder?.isTypeSupported(type)) || "";
}

export default function VoiceRecorder({ onTranscript, loading }) {
  const [recording, setRecording] = useState(false);
  const [localError, setLocalError] = useState("");
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);

  async function startRecording() {
    setLocalError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setLocalError("Microphone access is not available in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const mimeType = preferredMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        if (blob.size > 0) {
          await onTranscript(blob);
        }
      };
      recorder.start();
      setRecording(true);
    } catch (error) {
      setLocalError(error.message || "Could not start recording.");
    }
  }

  function stopRecording() {
    recorderRef.current?.stop();
    setRecording(false);
  }

  return (
    <section className="panel voice-panel" aria-label="Voice input">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Voice</p>
          <h2>Speech Input</h2>
        </div>
      </div>

      <div className={`record-orb ${recording ? "active" : ""}`}>
        {loading ? <Loader2 className="spin" size={32} /> : <Mic size={32} />}
      </div>

      <button
        type="button"
        className={`icon-button ${recording ? "danger" : "primary"}`}
        onClick={recording ? stopRecording : startRecording}
        disabled={loading}
      >
        {recording ? <Square size={18} /> : <Mic size={18} />}
        <span>{recording ? "Stop" : "Record"}</span>
      </button>
      {localError && <p className="inline-error">{localError}</p>}
    </section>
  );
}
