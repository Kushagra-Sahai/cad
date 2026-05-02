import { Camera, FileImage, ScanSearch, X } from "lucide-react";
import { useRef, useState } from "react";

export default function ImageUploader({ onAnalyze, loading }) {
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");

  function selectFile(file) {
    if (!file) return;
    setSelectedFile(file);
    setPreviewUrl(URL.createObjectURL(file));
  }

  function clearSelection() {
    setSelectedFile(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl("");
  }

  async function handleAnalyze() {
    if (!selectedFile || loading) return;
    await onAnalyze(selectedFile);
    clearSelection();
  }

  return (
    <section className="panel media-panel" aria-label="Image analysis">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">OCR</p>
          <h2>Image Scan</h2>
        </div>
        {selectedFile && (
          <button className="icon-only" onClick={clearSelection} type="button" title="Clear image">
            <X size={18} />
          </button>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(event) => selectFile(event.target.files?.[0])}
      />
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={(event) => selectFile(event.target.files?.[0])}
      />

      <div className="image-preview">
        {previewUrl ? <img src={previewUrl} alt="Selected medicine label" /> : <FileImage size={42} />}
      </div>

      <div className="button-row">
        <button type="button" className="icon-button" onClick={() => fileInputRef.current?.click()} disabled={loading}>
          <FileImage size={18} />
          <span>File</span>
        </button>
        <button type="button" className="icon-button" onClick={() => cameraInputRef.current?.click()} disabled={loading}>
          <Camera size={18} />
          <span>Camera</span>
        </button>
        <button
          type="button"
          className="icon-button accent"
          onClick={handleAnalyze}
          disabled={loading || !selectedFile}
        >
          <ScanSearch size={18} />
          <span>Scan</span>
        </button>
      </div>
    </section>
  );
}
