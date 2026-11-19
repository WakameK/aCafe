"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { loadDisplayName } from "@/lib/displayName";
import styles from "./page.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");
const ANON_ID_KEY = "acafe_anon_id";
const LIST_POLL_MS = 10_000;
// 自動で再接続してはいけない close code(サーバーと同じ)
const NO_RETRY_CODES = new Set([4401, 4403, 4404, 4410]);
const CLOSE_FULL = 4403;
const CLOSE_OUT = 4410;

type FireStage = "high" | "mid" | "low" | "ember";
type FireState = { level: number; stage: FireStage; label: string };

type Fire = {
  id: number;
  name: string;
  topic: string;
  kind: "ambient" | "user" | "legacy";
  capacity: number;
  human_count: number;
  is_full: boolean;
  characters: string[];
  fire: FireState;
  welcome: string;
  public_note: string;
  is_mine: boolean;
};

type ServerMessage = {
  id: number;
  sender_type: "human" | "ai";
  sender_name: string;
  sender_user_id: number | null;
  message: string;
};

type Gift = { id: number; from: string; from_user_id: number | null; item: string; message: string };

type JoinResponse = {
  fire: Fire;
  user: { id: number; name: string };
  ws_path: string;
  history: ServerMessage[];
  gift_items: string[];
  note_draft: string;
};

type CrisisLine = { name: string; number: string; hours: string };
type Care = { kind: string; title: string; body: string; lines: CrisisLine[] };

type ChatLine =
  | { kind: "message"; key: string; mine: boolean; senderType: "human" | "ai"; senderName: string; text: string }
  | { kind: "notice"; key: string; text: string };

type ServerEvent =
  | ({ type: "chat.message"; message_id?: number | null } & Omit<ServerMessage, "id">)
  | { type: "chat.presence"; event: "join" | "leave" | "ai_join" | "ai_leave"; user: string; user_id: number | null; count?: number | null }
  | { type: "chat.gift"; gift: Gift }
  | { type: "chat.guide"; text: string }
  | { type: "chat.hold"; hold_id: string; message: string; softened: string }
  | { type: "chat.burned" }
  | { type: "chat.care"; care: Care }
  | { type: "chat.error"; message: string }
  | { type: "fire.level"; fire: FireState }
  | { type: "fire.closing" }
  | { type: "fire.out" }
  | { type: "fire.updated"; name: string; topic: string; capacity: number; public_note: string }
  | { type: "note.draft"; draft: string };

type Hold = { id: string; message: string; softened: string };

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

function fireEmoji(stage: FireStage): string {
  if (stage === "high" || stage === "mid") return "🔥";
  if (stage === "low") return "🕯️";
  return "✨";
}

async function readError(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.error === "string") return body.error;
  } catch {
    // JSONでなければ、既定の文言を使う
  }
  return fallback;
}

export default function DeskClient() {
  const [anonId, setAnonId] = useState<string | null>(null);

  // 一覧
  const [fires, setFires] = useState<Fire[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newTopic, setNewTopic] = useState("");
  const [newCapacity, setNewCapacity] = useState(6);
  const [createError, setCreateError] = useState<string | null>(null);

  // 輪の中
  const [room, setRoom] = useState<JoinResponse | null>(null);
  const [fire, setFire] = useState<Fire | null>(null);
  const [fireState, setFireState] = useState<FireState | null>(null);
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [draft, setDraft] = useState("");
  const [connection, setConnection] = useState<"connecting" | "open" | "reconnecting">("connecting");
  const [hold, setHold] = useState<Hold | null>(null);
  const [care, setCare] = useState<Care | null>(null);
  const [guide, setGuide] = useState<string | null>(null);
  const [closing, setClosing] = useState(false);
  const [ended, setEnded] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [capacityInput, setCapacityInput] = useState(6);
  const [ownerMessage, setOwnerMessage] = useState<string | null>(null);
  const [confirmingOut, setConfirmingOut] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const seenIds = useRef<Set<number>>(new Set());
  const lastId = useRef(0);
  const noticeSeq = useRef(0);

  useEffect(() => {
    // localStorage はブラウザでしか読めないので、初回の描画のあとで取り出す
    const id = getAnonId();
    queueMicrotask(() => setAnonId(id));
  }, []);

  // ---------- 一覧 ----------

  const loadFires = useCallback(async () => {
    if (!anonId) return;
    try {
      const res = await fetch(`${API_BASE}/api/desk/fires/?anon_id=${encodeURIComponent(anonId)}`);
      if (!res.ok) throw new Error(String(res.status));
      const data = (await res.json()) as { fires: Fire[] };
      setFires(data.fires);
      setListError(null);
    } catch {
      setListError("焚火の一覧を読み込めませんでした。");
    }
  }, [anonId]);

  useEffect(() => {
    if (!anonId || room) return;
    const first = setTimeout(loadFires, 0);
    const timer = setInterval(loadFires, LIST_POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [anonId, room, loadFires]);

  // ---------- 輪の中: 表示を足す ----------

  const addNotice = useCallback((text: string) => {
    noticeSeq.current += 1;
    const key = `n${noticeSeq.current}`;
    setLines((prev) => [...prev, { kind: "notice", key, text }]);
  }, []);

  const addMessage = useCallback((m: ServerMessage, myId: number) => {
    // 同じ発言が2回届いても(再接続の取りこぼし回収など)、1回だけ出す
    if (seenIds.current.has(m.id)) return;
    seenIds.current.add(m.id);
    lastId.current = Math.max(lastId.current, m.id);
    setLines((prev) => [
      ...prev,
      {
        kind: "message",
        key: `m${m.id}`,
        mine: m.sender_type === "human" && m.sender_user_id === myId,
        senderType: m.sender_type,
        senderName: m.sender_name,
        text: m.message,
      },
    ]);
  }, []);

  // ---------- 入る・出る ----------

  const joinFire = useCallback(
    async (target: Fire) => {
      if (!anonId) return;
      setJoinError(null);
      try {
        const res = await fetch(`${API_BASE}/api/desk/fires/${target.id}/join/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ anon_id: anonId, display_name: loadDisplayName() }),
        });
        if (!res.ok) {
          setJoinError(await readError(res, "入れませんでした。"));
          loadFires();
          return;
        }
        const data = (await res.json()) as JoinResponse;
        seenIds.current = new Set();
        lastId.current = 0;
        noticeSeq.current = 0;
        setLines([]);
        setHold(null);
        setCare(null);
        setGuide(null);
        setClosing(false);
        setEnded(null);
        setConfirmingOut(false);
        setOwnerMessage(null);
        setConnection("connecting");
        setFire(data.fire);
        setFireState(data.fire.fire);
        setCapacityInput(data.fire.capacity);
        setNoteDraft(data.note_draft);
        setRoom(data);
        for (const m of data.history) {
          seenIds.current.add(m.id);
          lastId.current = Math.max(lastId.current, m.id);
        }
        setLines(
          data.history.map((m) => ({
            kind: "message" as const,
            key: `m${m.id}`,
            mine: m.sender_type === "human" && m.sender_user_id === data.user.id,
            senderType: m.sender_type,
            senderName: m.sender_name,
            text: m.message,
          })),
        );
      } catch {
        setJoinError("入れませんでした。通信を確かめてください。");
      }
    },
    [anonId, loadFires],
  );

  const leaveFire = useCallback(() => {
    const socket = socketRef.current;
    socketRef.current = null;
    socket?.close(1000);
    setRoom(null);
    setFire(null);
    setLines([]);
  }, []);

  // ---------- WebSocket(落ちたら、つなぎ直す) ----------

  const roomId = room?.fire.id ?? null;
  const wsPath = room?.ws_path ?? null;
  const myId = room?.user.id ?? null;

  useEffect(() => {
    if (roomId === null || wsPath === null || myId === null || !anonId) return;

    let cancelled = false;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    // つなぎ直したとき、切れていた間の発言を取りに行く
    const catchUp = async () => {
      try {
        const res = await fetch(
          `${API_BASE}/api/desk/fires/${roomId}/messages/?anon_id=${encodeURIComponent(anonId)}&after=${lastId.current}`,
        );
        if (!res.ok) return;
        const data = (await res.json()) as { messages: ServerMessage[] };
        if (!cancelled) data.messages.forEach((m) => addMessage(m, myId));
      } catch {
        // 取れなくても、次の発言からは届く
      }
    };

    const handle = (ev: ServerEvent) => {
      switch (ev.type) {
        case "chat.message": {
          if (typeof ev.message_id === "number") {
            addMessage(
              {
                id: ev.message_id,
                sender_type: ev.sender_type,
                sender_name: ev.sender_name,
                sender_user_id: ev.sender_user_id,
                message: ev.message,
              },
              myId,
            );
          }
          break;
        }
        case "chat.presence": {
          // 自分の入退室は出さない(再接続のたびに「席につきました」が出て鬱陶しいため)
          if (ev.user_id !== null && ev.user_id === myId) break;
          if (ev.event === "join") addNotice(`${ev.user} が輪に加わりました`);
          else if (ev.event === "leave") addNotice(`${ev.user} が火のそばを離れました`);
          else if (ev.event === "ai_join") addNotice(`${ev.user} が火にあたりに来ました`);
          else if (ev.event === "ai_leave") addNotice(`${ev.user} が帰っていきました`);
          if (typeof ev.count === "number") {
            const count = ev.count;
            setFire((prev) => (prev ? { ...prev, human_count: count } : prev));
          }
          break;
        }
        case "chat.gift":
          addNotice(`${ev.gift.from} が「${ev.gift.item}」を置いてくれました${ev.gift.message ? `:${ev.gift.message}` : ""}`);
          break;
        case "chat.guide":
          setGuide(ev.text);
          break;
        case "chat.hold":
          setHold({ id: ev.hold_id, message: ev.message, softened: ev.softened });
          break;
        case "chat.burned":
          setHold(null);
          addNotice("燃やしました。この言葉は、誰にも見えていません。");
          break;
        case "chat.care":
          setCare(ev.care);
          break;
        case "chat.error":
          addNotice(ev.message);
          break;
        case "fire.level":
          setFireState(ev.fire);
          break;
        case "fire.closing":
          setClosing(true);
          break;
        case "fire.out":
          setEnded("火が消えました。ここでの言葉は、火と一緒に消えました。また会えたらいいね。");
          break;
        case "fire.updated":
          setFire((prev) =>
            prev
              ? { ...prev, name: ev.name, topic: ev.topic, capacity: ev.capacity, public_note: ev.public_note }
              : prev,
          );
          break;
        case "note.draft":
          setNoteDraft(ev.draft);
          break;
      }
    };

    const openSocket = function openSocket(isRetry: boolean) {
      if (cancelled) return;
      const socket = new WebSocket(`${WS_BASE}${wsPath}`);
      socketRef.current = socket;

      socket.onopen = () => {
        retry = 0;
        setConnection("open");
        if (isRetry) void catchUp();
      };
      socket.onmessage = (e) => {
        try {
          handle(JSON.parse(e.data) as ServerEvent);
        } catch {
          // 読めないデータは無視する
        }
      };
      socket.onclose = (e) => {
        if (cancelled || socketRef.current !== socket) return;
        if (e.code === CLOSE_OUT) return; // fire.out で、すでに案内を出している
        if (NO_RETRY_CODES.has(e.code)) {
          setEnded(
            e.code === CLOSE_FULL
              ? "輪がいっぱいになっていました。"
              : "この焚火には入れませんでした。",
          );
          return;
        }
        setConnection("reconnecting");
        retry += 1;
        const wait = Math.min(1000 * 2 ** Math.min(retry, 4), 10_000);
        timer = setTimeout(() => openSocket(true), wait);
      };
    };

    openSocket(false);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      const socket = socketRef.current;
      socketRef.current = null;
      socket?.close(1000);
    };
  }, [roomId, wsPath, myId, anonId, addMessage, addNotice]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines, hold, care, guide]);

  // ---------- 送る ----------

  const send = useCallback((payload: Record<string, unknown>) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(payload));
    return true;
  }, []);

  const submitMessage = (e: React.FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || hold) return;
    if (send({ type: "chat.message", message: text })) setDraft("");
    else addNotice("つながっていません。つなぎ直しています…");
  };

  const resolveHold = (choice: "softened" | "burn" | "cancel") => {
    if (!hold) return;
    send({ type: "chat.resolve_hold", hold_id: hold.id, choice });
    // burn は、サーバーからの chat.burned で閉じる
    if (choice !== "burn") setHold(null);
  };

  const sendGift = async (item: string) => {
    if (!anonId || !roomId) return;
    try {
      const res = await fetch(`${API_BASE}/api/desk/fires/${roomId}/gifts/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ anon_id: anonId, item }),
      });
      if (res.status === 429) addNotice("少し待ってから、また置いてね。");
      else if (!res.ok) addNotice(await readError(res, "置けませんでした。"));
    } catch {
      addNotice("置けませんでした。");
    }
  };

  // ---------- 作る・持ち主の操作 ----------

  const createFire = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!anonId) return;
    setCreateError(null);
    try {
      const res = await fetch(`${API_BASE}/api/desk/fires/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ anon_id: anonId, name: newName, topic: newTopic, capacity: newCapacity }),
      });
      if (!res.ok) {
        setCreateError(await readError(res, "作れませんでした。"));
        return;
      }
      const created = (await res.json()) as Fire;
      setNewName("");
      setNewTopic("");
      setCreating(false);
      await joinFire(created);
    } catch {
      setCreateError("作れませんでした。通信を確かめてください。");
    }
  };

  const patchFire = async (body: Record<string, unknown>, okText: string) => {
    if (!anonId || !roomId) return;
    setOwnerMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/desk/fires/${roomId}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ anon_id: anonId, ...body }),
      });
      if (!res.ok) {
        setOwnerMessage(await readError(res, "変更できませんでした。"));
        return;
      }
      const updated = (await res.json()) as Fire;
      setFire((prev) => (prev ? { ...prev, ...updated } : prev));
      setOwnerMessage(okText);
    } catch {
      setOwnerMessage("変更できませんでした。");
    }
  };

  const approveNote = async () => {
    await patchFire({ public_note: noteDraft }, "外に見せるひとことを、これにしました。");
    setNoteDraft("");
  };

  const putOut = async () => {
    if (!anonId || !roomId) return;
    try {
      await fetch(`${API_BASE}/api/desk/fires/${roomId}/`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ anon_id: anonId }),
      });
    } catch {
      setOwnerMessage("消せませんでした。");
    }
  };

  // ====================================
  // 表示
  // ====================================

  if (!anonId) return <p className={styles.muted}>焚火を探しています…</p>;

  if (room && fire) {
    const state = fireState ?? fire.fire;
    const isOwner = fire.is_mine;
    const canType = connection === "open" && !ended;
    return (
      <div className={styles.room}>
        <header className={styles.roomHead}>
          <div>
            <h2 className={styles.roomTitle}>
              <span aria-hidden>{fireEmoji(state.stage)}</span> {fire.name}
            </h2>
            {fire.topic && <p className={styles.topic}>{fire.topic}</p>}
          </div>
          <button type="button" className={styles.ghostButton} onClick={leaveFire}>
            火のそばを離れる
          </button>
        </header>

        <div className={styles.fireBar} role="img" aria-label={`火の大きさ: ${state.label}`}>
          <div className={`${styles.fireFill} ${styles[`stage_${state.stage}`]}`} style={{ width: `${Math.max(4, state.level * 100)}%` }} />
          <span className={styles.fireLabel}>
            {state.label} ・ {fire.human_count}/{fire.capacity}人
          </span>
        </div>

        {connection === "reconnecting" && !ended && (
          <p className={styles.alert}>つなぎ直しています…(このまま待っていて大丈夫です)</p>
        )}
        {closing && !ended && <p className={styles.soft}>火が小さくなってきました。話すと、火は続きます。</p>}
        {ended && <p className={styles.alert}>{ended}</p>}

        <div className={styles.log} aria-live="polite">
          {lines.map((line) =>
            line.kind === "notice" ? (
              <p key={line.key} className={styles.notice}>
                {line.text}
              </p>
            ) : (
              <div
                key={line.key}
                className={`${styles.bubble} ${line.mine ? styles.mine : ""} ${line.senderType === "ai" ? styles.ai : ""}`}
              >
                <span className={styles.sender}>{line.senderName}</span>
                <p>{line.text}</p>
              </div>
            ),
          )}

          {guide && (
            <div className={styles.guide}>
              <p>{guide}</p>
              <button type="button" className={styles.linkButton} onClick={() => setGuide(null)}>
                閉じる
              </button>
            </div>
          )}

          {care && (
            <div className={styles.care}>
              <strong>{care.title}</strong>
              {care.body.split("\n").map((t, i) => (
                <p key={i}>{t}</p>
              ))}
              {care.lines.length > 0 && (
                <ul>
                  {care.lines.map((l) => (
                    <li key={l.number}>
                      {l.name}:<a href={`tel:${l.number.replace(/-/g, "")}`}>{l.number}</a>
                      <span className={styles.hours}>({l.hours})</span>
                    </li>
                  ))}
                </ul>
              )}
              <button type="button" className={styles.linkButton} onClick={() => setCare(null)}>
                閉じる
              </button>
            </div>
          )}

          {hold && (
            <div className={styles.hold}>
              <p>{hold.message}</p>
              <blockquote>{hold.softened}</blockquote>
              <div className={styles.holdButtons}>
                <button type="button" onClick={() => resolveHold("softened")}>
                  これで送る
                </button>
                <button type="button" onClick={() => resolveHold("burn")}>
                  こっそり燃やす
                </button>
                <button type="button" onClick={() => resolveHold("cancel")}>
                  書き直す
                </button>
              </div>
              <p className={styles.hours}>「こっそり燃やす」と、元の言葉は誰にも見えず、どこにも残りません。</p>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className={styles.gifts}>
          {room.gift_items.map((item) => (
            <button key={item} type="button" className={styles.giftButton} disabled={!!ended} onClick={() => sendGift(item)}>
              {item}を置く
            </button>
          ))}
        </div>

        <form onSubmit={submitMessage} className={styles.composer}>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={canType ? "ここに、思ったことを置いてみる" : "つながるのを待っています…"}
            maxLength={500}
            disabled={!canType || !!hold}
            aria-label="メッセージ"
          />
          <button type="submit" disabled={!canType || !!hold || !draft.trim()}>
            送る
          </button>
        </form>

        {isOwner && !ended && (
          <details className={styles.owner}>
            <summary>この焚火の持ち主の設定</summary>
            <label className={styles.field}>
              定員(2〜12人)
              <input
                type="number"
                min={2}
                max={12}
                value={capacityInput}
                onChange={(e) => setCapacityInput(Number(e.target.value))}
              />
            </label>
            <button type="button" onClick={() => patchFire({ capacity: capacityInput }, "定員を変えました。")}>
              定員を変える
            </button>

            <p className={styles.hours}>
              一覧に出る「外向けのひとこと」: {fire.public_note || "(まだありません)"}
            </p>
            {noteDraft && (
              <div className={styles.noteDraft}>
                <p>AIの下書き(あなたにだけ見えています):</p>
                <textarea value={noteDraft} onChange={(e) => setNoteDraft(e.target.value)} maxLength={120} rows={3} />
                <button type="button" onClick={approveNote}>
                  これを外に見せる
                </button>
              </div>
            )}

            {confirmingOut ? (
              <div className={styles.holdButtons}>
                <button type="button" onClick={putOut}>
                  本当に火を消す(言葉もすべて消えます)
                </button>
                <button type="button" onClick={() => setConfirmingOut(false)}>
                  やめる
                </button>
              </div>
            ) : (
              <button type="button" onClick={() => setConfirmingOut(true)}>
                火を消す
              </button>
            )}
            {ownerMessage && <p className={styles.soft}>{ownerMessage}</p>}
          </details>
        )}
      </div>
    );
  }

  return (
    <div className={styles.list}>
      <p className={styles.soft}>
        焚火にあたりに来ませんか。話した言葉が薪になって、火が続きます。話さなくなると火は小さくなり、消えたら、ここでの言葉も一緒に消えます。
      </p>

      {listError && <p className={styles.alert}>{listError}</p>}
      {joinError && <p className={styles.alert}>{joinError}</p>}

      <ul className={styles.fires}>
        {fires.map((f) => (
          <li key={f.id} className={`${styles.card} ${f.is_full ? styles.full : ""}`}>
            <div className={styles.cardHead}>
              <strong>
                <span aria-hidden>{fireEmoji(f.fire.stage)}</span> {f.name}
              </strong>
              <span className={styles.badge}>
                {f.human_count}/{f.capacity}人
              </span>
            </div>
            {f.topic && <p className={styles.topic}>{f.topic}</p>}
            <p className={styles.welcome}>{f.welcome}</p>
            {f.public_note && <p className={styles.note}>「{f.public_note}」</p>}
            <p className={styles.hours}>
              {f.fire.label}
              {f.characters.length > 0 && ` ・ ${f.characters.join("、")} がいます`}
            </p>
            <button type="button" disabled={f.is_full} onClick={() => joinFire(f)}>
              {f.is_full ? "いっぱいです" : f.is_mine ? "自分の焚火に戻る" : "あたりに行く"}
            </button>
          </li>
        ))}
      </ul>

      {creating ? (
        <form onSubmit={createFire} className={styles.createForm}>
          <label className={styles.field}>
            名前(30文字まで)
            <input value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={30} required />
          </label>
          <label className={styles.field}>
            どんな話をしたい?(任意)
            <input value={newTopic} onChange={(e) => setNewTopic(e.target.value)} maxLength={100} />
          </label>
          <label className={styles.field}>
            定員(2〜12人)
            <input
              type="number"
              min={2}
              max={12}
              value={newCapacity}
              onChange={(e) => setNewCapacity(Number(e.target.value))}
            />
          </label>
          {createError && <p className={styles.alert}>{createError}</p>}
          <div className={styles.holdButtons}>
            <button type="submit">火を起こす</button>
            <button type="button" onClick={() => setCreating(false)}>
              やめる
            </button>
          </div>
        </form>
      ) : (
        <button type="button" className={styles.primary} onClick={() => setCreating(true)}>
          自分の焚火を起こす
        </button>
      )}
    </div>
  );
}
