"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./page.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");
const ANON_ID_KEY = "acafe_anon_id";
const TABLE_POLL_MS = 10_000;
const PING_MS = 15_000; // サーバーに在席を知らせる間隔(止まると一定時間後にテーブルから外れる)

type TableStatus = "vacant" | "occupied";

const TABLE_NAME_MAX = 30;

type Table = {
  id: number;
  name: string;
  is_permanent: boolean;
  status: TableStatus;
  human_count: number;
  characters: string[];
  atmosphere: string;
};

type SitResponse = {
  table: Table;
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

const STATUS_LABEL: Record<TableStatus, string> = {
  vacant: "誰もいません",
  occupied: "誰かいます",
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
  if (event === "leave") return `${user} がテーブルを離れました`;
  return `${user} がテーブルにつきました`;
}

export default function DeskClient() {
  const [tables, setTables] = useState<Table[]>([]);
  const [floorCount, setFloorCount] = useState(0);
  const [newTopic, setNewTopic] = useState("");
  const [tableError, setTableError] = useState<string | null>(null);
  const [sitting, setSitting] = useState<SitResponse | null>(null);
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [atmosphere, setAtmosphere] = useState("");
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const lineSeq = useRef(0);

  const loadTables = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/desk/tables/`);
      if (!res.ok) throw new Error(String(res.status));
      const data: { tables: Table[]; floor: { human_count: number } } = await res.json();
      setTables(data.tables);
      setFloorCount(data.floor.human_count);
      setTableError(null);
    } catch {
      setTableError("テーブルの様子を確認できませんでした。少し待ってからもう一度お試しください。");
    }
  }, []);

  // テーブルに座っていない間だけ、店内の様子を定期的に確認する
  useEffect(() => {
    if (sitting) return;
    const first = setTimeout(loadTables, 0);
    const timer = setInterval(loadTables, TABLE_POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [sitting, loadTables]);

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

      const pinger = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
      }, PING_MS);

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

      socket.onclose = () => {
        clearInterval(pinger);
        if (socketRef.current !== socket) return; // 自分でテーブルを離れた場合
        socketRef.current = null;
        setSitting(null);
        setNotice("接続が切れたので、テーブルから離れました。");
      };
    },
    [pushLine],
  );

  async function join(path: string, init: RequestInit) {
    setNotice(null);
    try {
      const res = await fetch(`${API_BASE}${path}`, init);
      if (res.status === 404) {
        setNotice("そのテーブルはもう片付けられてしまいました。");
        await loadTables();
        return;
      }
      if (res.status === 409) {
        setNotice("テーブルが多すぎて、新しく作れませんでした。");
        return;
      }
      if (!res.ok) throw new Error(String(res.status));
      const session: SitResponse = await res.json();
      setLines([]);
      setAtmosphere(tables.find((t) => t.id === session.table.id)?.atmosphere ?? "");
      setSitting(session);
      connect(session);
    } catch {
      setNotice("テーブルにつけませんでした。もう一度お試しください。");
    }
  }

  const postInit = (body: object): RequestInit => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ anon_id: getAnonId(), ...body }),
  });

  function sit(table: Table) {
    return join(`/api/desk/tables/${table.id}/sit/`, postInit({}));
  }

  function createTable(e: React.FormEvent) {
    e.preventDefault();
    const name = newTopic.trim();
    if (!name) return;
    setNewTopic("");
    return join("/api/desk/tables/", postInit({ name }));
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
            <h3>{sitting.table.name}</h3>
            {atmosphere ? <p className={styles.atmosphere}>{atmosphere}</p> : null}
          </div>
          <button type="button" className={styles.leaveButton} onClick={leave}>
            テーブルを離れる
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
    <div className={styles.tableList}>
      {notice ? <p className={styles.alert}>{notice}</p> : null}
      {tableError ? <p className={styles.alert}>{tableError}</p> : null}

      <p className={styles.floor}>店内に {floorCount} 人います。気になる話題のテーブルに座ってみてください。</p>

      <ul className={styles.tables}>
        {tables.map((table) => (
          <li key={table.id} className={`${styles.table} ${styles[table.status]}`}>
            <div className={styles.tableHead}>
              <strong>{table.name}</strong>
              <span className={styles.badge}>{STATUS_LABEL[table.status]}</span>
            </div>
            {table.human_count > 0 ? (
              <p className={styles.who}>
                {table.human_count}人
                {table.characters.length > 0 ? `・${table.characters.join("、")} が同席` : ""}
              </p>
            ) : null}
            {table.atmosphere ? <p className={styles.atmosphere}>{table.atmosphere}</p> : null}
            <button type="button" onClick={() => sit(table)}>
              {table.human_count > 0 ? "同じテーブルにつく" : "座る"}
            </button>
          </li>
        ))}
      </ul>

      <form className={styles.newTable} onSubmit={createTable}>
        <label htmlFor="new-table-topic">話したい話題で新しいテーブルを作る</label>
        <div className={styles.newTableRow}>
          <input
            id="new-table-topic"
            type="text"
            value={newTopic}
            onChange={(e) => setNewTopic(e.target.value)}
            placeholder="例: 最近読んだ本"
            maxLength={TABLE_NAME_MAX}
          />
          <button type="submit">作って座る</button>
        </div>
      </form>
    </div>
  );
}
