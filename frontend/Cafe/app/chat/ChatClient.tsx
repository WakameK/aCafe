"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import styles from "./page.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const ANON_ID_KEY = "acafe_anon_id";

type Message = { id: number; role: "user" | "bot"; content: string };

type CrisisResource = {
  name: string;
  description?: string;
  tel?: string;
  url?: string;
};

type ChatResponse = {
  reply?: string;
  provider?: string;
  error?: string;
  crisis?: boolean;
  crisis_message?: string;
  resources?: CrisisResource[];
};

function getAnonId(): string {
  try {
    const saved = window.localStorage.getItem(ANON_ID_KEY);
    if (saved) return saved;
    const created = crypto.randomUUID();
    window.localStorage.setItem(ANON_ID_KEY, created);
    return created;
  } catch {
    return crypto.randomUUID();
  }
}

export default function ChatClient() {
  const [messages, setMessages] = useState<Message[]>([
    { id: 0, role: "bot", content: "……(マスターが黙々と作業している)" },
  ]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 一度表示した相談窓口は、そのセッション中は消さない
  const [crisis, setCrisis] = useState<{ message: string; resources: CrisisResource[] } | null>(null);

  const seq = useRef(1);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, sending]);

  const push = (role: Message["role"], content: string) =>
    setMessages((prev) => [...prev, { id: seq.current++, role, content }]);

  const send = async (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;

    push("user", text);
    setDraft("");
    setSending(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/sosuke/chat/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ anon_id: getAnonId(), message: text }),
      });
      const data: ChatResponse = await res.json().catch(() => ({}));

      if (data.crisis && data.resources?.length) {
        setCrisis({ message: data.crisis_message ?? "", resources: data.resources });
      }
      if (!res.ok || !data.reply) {
        setError(data.error ?? "マスターに声が届かなかったみたいです。少ししてからもう一度どうぞ。");
        return;
      }
      push("bot", data.reply);
    } catch {
      setError("サーバーにつながりませんでした。");
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <div className={styles.chatContainer}>
        <div className={styles.chatHeader}>
          <h3>☕ カフェのカウンター</h3>
          <p>マスターが黙々と作業している...</p>
        </div>

        <div className={styles.chatBox} aria-live="polite">
          {messages.map((m) => (
            <div key={m.id} className={`${styles.chatMessage} ${m.role === "user" ? styles.user : styles.bot}`}>
              <div className={m.role === "user" ? styles.userBubble : styles.botBubble}>{m.content}</div>
            </div>
          ))}
          {sending && (
            <div className={`${styles.chatMessage} ${styles.bot}`}>
              <div className={`${styles.botBubble} ${styles.typing}`}>……</div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <form className={styles.chatInputArea} onSubmit={send}>
          <input
            type="text"
            placeholder="マスターに話しかける..."
            value={draft}
            maxLength={2000}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button type="submit" disabled={sending || !draft.trim()}>
            送信
          </button>
        </form>
      </div>

      {crisis && (
        <aside className={styles.crisisPanel} aria-label="相談窓口のご案内">
          <h4>ひとりで抱えこまないでください</h4>
          {crisis.message && <p className={styles.crisisLead}>{crisis.message}</p>}
          <ul>
            {crisis.resources.map((r) => (
              <li key={r.name}>
                <div className={styles.crisisName}>
                  {r.url ? (
                    <a href={r.url} target="_blank" rel="noopener noreferrer">
                      {r.name}
                    </a>
                  ) : (
                    r.name
                  )}
                </div>
                {r.tel && (
                  <a className={styles.crisisTel} href={`tel:${r.tel.replace(/-/g, "")}`}>
                    📞 {r.tel}
                  </a>
                )}
                {r.description && <div className={styles.crisisDesc}>{r.description}</div>}
              </li>
            ))}
          </ul>
        </aside>
      )}
    </>
  );
}
