import { Loader2, Send } from "lucide-react";
import { useState } from "react";

export default function ChatBox({ messages, onSubmit, loading }) {
  const [value, setValue] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    const query = value.trim();
    if (!query || loading) return;
    onSubmit(query);
    setValue("");
  }

  return (
    <section className="panel chat-panel" aria-label="Medicine search">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Input</p>
          <h2>Medicine Search</h2>
        </div>
      </div>

      <div className="message-list" aria-live="polite">
        {messages.map((message) => (
          <div className={`message ${message.role}`} key={message.id}>
            <span>{message.text}</span>
          </div>
        ))}
      </div>

      <form className="chat-form" onSubmit={handleSubmit}>
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Type a brand or generic name"
          disabled={loading}
          maxLength={500}
        />
        <button type="submit" className="icon-button primary" disabled={loading || !value.trim()} title="Analyze">
          {loading ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
          <span>Analyze</span>
        </button>
      </form>
    </section>
  );
}
