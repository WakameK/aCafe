"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

type Room = {
  slug: string;
  name: string;
  count: number;
};

// サーバーから部屋一覧を取ってくるだけの関数(stateは触らない)
async function fetchRooms(): Promise<Room[]> {
  const res = await fetch(`${API_BASE}/api/space/rooms/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data: { rooms: Room[] } = await res.json();
  return data.rooms;
}

export default function RoomLobbyPage() {
  const router = useRouter();
  const [rooms, setRooms] = useState<Room[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  // 人数を最新に保つため、5秒ごとに読み直す
  useEffect(() => {
    let cancelled = false;

    const load = () => {
      fetchRooms()
        .then((list) => {
          if (cancelled) return;
          setRooms(list);
          setError(null);
        })
        .catch(() => {
          if (!cancelled) setError("部屋の一覧を読み込めませんでした");
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    };

    load();
    const timer = setInterval(load, 5000);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const createRoom = async (e: FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name || creating) return;

    setCreating(true);
    try {
      const res = await fetch(`${API_BASE}/api/space/rooms/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? "部屋を作れませんでした");
        return;
      }
      // 作った部屋にそのまま入る
      router.push(`/room/${data.slug}`);
    } catch {
      setError("部屋を作れませんでした");
    } finally {
      setCreating(false);
    }
  };

  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: 24 }}>
      <h1 style={{ fontSize: 24, marginBottom: 16 }}>焚火の部屋</h1>

      {error && <p style={{ color: "#c0392b", marginBottom: 12 }}>{error}</p>}

      {loading ? (
        <p>読み込み中…</p>
      ) : rooms.length === 0 ? (
        <p>まだ部屋がありません。最初の焚火を作ってみませんか。</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: 12 }}>
          {rooms.map((room) => (
            <li key={room.slug}>
              <Link
                href={`/room/${room.slug}`}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "14px 18px",
                  borderRadius: 12,
                  border: "1px solid #d8c8b0",
                  background: "#fffaf2",
                  color: "#3b2f25",
                  textDecoration: "none",
                }}
              >
                <span style={{ fontWeight: 600 }}>{room.name}</span>
                <span>{room.count === 0 ? "まだ誰もいません" : `${room.count}人がいます`}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={createRoom} style={{ display: "flex", gap: 8, marginTop: 24 }}>
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          maxLength={30}
          placeholder="新しい部屋の名前"
          style={{ flex: 1, padding: "10px 12px", borderRadius: 8, border: "1px solid #ccc" }}
        />
        <button
          type="submit"
          disabled={creating || !newName.trim()}
          style={{ padding: "10px 18px", borderRadius: 8 }}
        >
          {creating ? "作成中…" : "部屋を作る"}
        </button>
      </form>
    </main>
  );
}