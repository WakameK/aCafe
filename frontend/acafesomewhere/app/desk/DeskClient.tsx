"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./page.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");
const ANON_ID_KEY = "acafe_anon_id";
const SEAT_POLL_MS = 10_000;
const CLOSE_SEAT_FULL = 4403;

type SeatStatus = "vacant" | "occupied" | "full";

type Seat = {
  id: number;
  label: string;
  capacity: number;
  status: SeatStatus;
  human_count: number;
  characters: string[];
  atmosphere: string;
};

type SitResponse = {
  seat: Seat;
  room_id: number;
  ws_path: string;
  user: { id: number; name: string };
};

type ChatLine =
  | { kind: "message"; id: string; senderType: "human" | "ai"; senderName: string; text: string }
  | { kind: "notice"; id: string; text: string };

type NewChatLine = ChatLine extends infer L ? (L extends ChatLine ? Omit<L, "id"> : never) : never;

type ServerEvent =
  | { type: "chat.message"; sender_type: "human" | "ai"; sender_name: string; message: string; message_id?: number }
  | { type: "chat.presence"; event: "join" | "leave" | "ai_join"; user: string }
  | { type: "chat.atmosphere"; summary: string }
  | { type: "chat.gift" };

const STATUS_LABEL: Record<SeatStatus, string> = {
  vacant: "空席",
  occupied: "誰かいます",
  full: "満席",
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

function presenceText(event: "join" | "leave" | "ai_join", user: string): string {
  if (event === "leave") return `${user} が席を立ちました`;
  return `${user} が席につきました`;
}

export default function DeskClient() {
  const [seats, setSeats] = useState<Seat[]>([]);
  const [seatError, setSeatError] = useState<string | null>(null);
  const [sitting, setSitting] = useState<SitResponse | null>(null);
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [atmosphere, setAtmosphere] = useState("");
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const lineSeq = useRef(0);

  const loadSeats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/desk/seats/`);
      if (!res.ok) throw new Error(String(res.status));
      const data: { seats: Seat[] } = await res.json();
      setSeats(data.seats);
      setSeatError(null);
    } catch {
      setSeatError("座席の様子を確認できませんでした。少し待ってからもう一度お試しください。");
    }
  }, []);

  // 席に座っていない間だけ、座席の空き状況を定期的に確認する
  useEffect(() => {
    if (sitting) return;
    const first = setTimeout(loadSeats, 0);
    const timer = setInterval(loadSeats, SEAT_POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [sitting, loadSeats]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  useEffect(() => () => socketRef.current?.close(), []);

  const pushLine = useCallback((line: NewChatLine) => {
    lineSeq.current += 1;
    setLines((prev) => [...prev, { ...line, id: `l${lineSeq.current}` } as ChatLine]);
  }, []);

  const connect = useCallback(
    (session: SitResponse) => {
      const socket = new WebSocket(`${WS_BASE}${session.ws_path}`);
      socketRef.current = socket;

      socket.onmessage = (ev: MessageEvent<string>) => {
        const data: ServerEvent = JSON.parse(ev.data);
        if (data.type === "chat.message") {
          pushLine({
            kind: "message",
            senderType: data.sender_type,
            senderName: data.sender_name,
            text: data.message,
          });
        } else if (data.type === "chat.presence") {
          pushLine({ kind: "notice", text: presenceText(data.event, data.user) });
        } else if (data.type === "chat.atmosphere") {
          setAtmosphere(data.summary);
        }
      };

      socket.onclose = (ev) => {
        if (socketRef.current !== socket) return; // 自分で席を立った場合
        socketRef.current = null;
        setSitting(null);
        setNotice(
          ev.code === CLOSE_SEAT_FULL
            ? "その席は満席になってしまいました。"
            : "接続が切れたので、席から離れました。",
        );
      };
    },
    [pushLine],
  );

  async function sit(seat: Seat) {
    setNotice(null);
    try {
      const res = await fetch(`${API_BASE}/api/desk/seats/${seat.id}/sit/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ anon_id: getAnonId() }),
      });
      if (res.status === 409) {
        setNotice("その席は満席です。");
        await loadSeats();
        return;
      }
      if (!res.ok) throw new Error(String(res.status));
      const session: SitResponse = await res.json();
      setLines([]);
      setAtmosphere(seat.atmosphere);
      setSitting(session);
      connect(session);
    } catch {
      setNotice("席に座れませんでした。もう一度お試しください。");
    }
  }

  function leave() {
    const socket = socketRef.current;
    socketRef.current = null;
    socket?.close();
    setSitting(null);
  }

  function send(e: React.FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    const socket = socketRef.current;
    if (!text || !socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: "chat.message", message: text }));
    setDraft("");
  }

  if (sitting) {
    return (
      <div className={styles.room}>
        <div className={styles.roomHeader}>
          <div>
            <h3>{sitting.seat.label}</h3>
            {atmosphere ? <p className={styles.atmosphere}>{atmosphere}</p> : null}
          </div>
          <button type="button" className={styles.leaveButton} onClick={leave}>
            席を立つ
          </button>
        </div>

        <div className={styles.chatBox} aria-live="polite">
          {lines.map((line) =>
            line.kind === "notice" ? (
              <p key={line.id} className={styles.notice}>
                {line.text}
              </p>
            ) : (
              <div
                key={line.id}
                className={`${styles.message} ${line.senderName === sitting.user.name ? styles.mine : ""}`}
              >
                <span className={styles.sender}>
                  {line.senderType === "ai" ? "☕ " : ""}
                  {line.senderName}
                </span>
                <div className={line.senderType === "ai" ? styles.aiBubble : styles.bubble}>{line.text}</div>
              </div>
            ),
          )}
          <div ref={bottomRef} />
        </div>

        <form className={styles.inputArea} onSubmit={send}>
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="話しかける..."
            maxLength={500}
          />
          <button type="submit">送信</button>
        </form>
      </div>
    );
  }

  return (
    <div className={styles.seatList}>
      {notice ? <p className={styles.alert}>{notice}</p> : null}
      {seatError ? <p className={styles.alert}>{seatError}</p> : null}
      <ul className={styles.seats}>
        {seats.map((seat) => (
          <li key={seat.id} className={`${styles.seat} ${styles[seat.status]}`}>
            <div className={styles.seatHead}>
              <strong>{seat.label}</strong>
              <span className={styles.badge}>{STATUS_LABEL[seat.status]}</span>
            </div>
            {seat.status !== "vacant" ? (
              <p className={styles.who}>
                {seat.human_count}人 / {seat.capacity}人
                {seat.characters.length > 0 ? `・${seat.characters.join("、")} が同席` : ""}
              </p>
            ) : null}
            {seat.atmosphere ? <p className={styles.atmosphere}>{seat.atmosphere}</p> : null}
            <button type="button" disabled={seat.status === "full"} onClick={() => sit(seat)}>
              {seat.status === "occupied" ? "相席する" : "座る"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
