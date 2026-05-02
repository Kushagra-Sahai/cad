import { AlertTriangle, BadgeCheck, Pill, Volume2 } from "lucide-react";

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

function ListSection({ title, values, empty = "No trusted details found." }) {
  return (
    <section className="result-section">
      <h3>{title}</h3>
      {values?.length ? (
        <ul>
          {values.map((value, index) => (
            <li key={`${title}-${index}`}>{value}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">{empty}</p>
      )}
    </section>
  );
}

export default function MedicineCard({ medicine, onSpeak, speaking }) {
  if (!medicine) {
    return (
      <section className="empty-state" aria-label="No result">
        <Pill size={38} />
        <h2>MediScan AI</h2>
        <p>Medicine analysis appears here.</p>
      </section>
    );
  }

  const title = medicine.brand_name || medicine.generic_name || "Unknown medicine";
  const confidencePercent = Math.round((medicine.confidence_score || 0) * 100);
  const indications = asList(
    medicine.why_used,
    medicine.indications,
    medicine.uses,
    medicine.use,
    medicine.indication,
    medicine.purpose,
  );

  return (
    <article className="medicine-card" aria-label="Medicine analysis result">
      <div className="result-header">
        <div>
          <p className="eyebrow">Analysis</p>
          <h2>{title}</h2>
          <p className="generic-name">{medicine.generic_name || "Generic name unavailable"}</p>
        </div>
        <button className="icon-button" type="button" onClick={onSpeak} disabled={speaking} title="Play audio">
          <Volume2 size={18} />
          <span>{speaking ? "Playing" : "Audio"}</span>
        </button>
      </div>

      <div className="identity-grid">
        <div>
          <span>Brand</span>
          <strong>{medicine.brand_name || "Unknown"}</strong>
        </div>
        <div>
          <span>Generic</span>
          <strong>{medicine.generic_name || "Unknown"}</strong>
        </div>
        <div>
          <span>Class</span>
          <strong>{medicine.drug_class || "Unknown"}</strong>
        </div>
      </div>

      <div className="confidence-row">
        <BadgeCheck size={18} />
        <span>Confidence</span>
        <div className="confidence-track">
          <div style={{ width: `${confidencePercent}%` }} />
        </div>
        <strong>{confidencePercent}%</strong>
      </div>

      <section className="used-for-box">
        <h3>Why Used</h3>
        {indications.length ? (
          <ul>
            {indications.slice(0, 4).map((value, index) => (
              <li key={`used-for-${index}`}>{value}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No trusted use information found.</p>
        )}
      </section>

      <div className="guidance-grid">
        <section className="guidance-box">
          <h3>Usage Guidance</h3>
          <p>{medicine.usage_guidance || "Usage guidance unavailable."}</p>
        </section>
        <section className="guidance-box">
          <h3>Timing Guidance</h3>
          <p>{medicine.timing_guidance || "Timing guidance unavailable."}</p>
        </section>
      </div>

      <div className="result-grid">
        <ListSection title="Indications / Why Used" values={indications} />
        <ListSection title="Side Effects" values={medicine.side_effects} />
        <ListSection title="Warnings" values={medicine.warnings_precautions} />
        <ListSection title="Interactions" values={medicine.interactions_basic} />
        <ListSection title="Generic Alternatives" values={medicine.alternatives_generic} empty="No generic alternative identified." />
      </div>

      <div className="disclaimer">
        <AlertTriangle size={18} />
        <span>{medicine.disclaimer}</span>
      </div>
    </article>
  );
}
