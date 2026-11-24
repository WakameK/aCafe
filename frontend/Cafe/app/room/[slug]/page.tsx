"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

// Unity はブラウザ専用なので、サーバー側では描画しない
const UnityRoom = dynamic(() => import("@/components/UnityRoom"), {
  ssr: false,
});

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

type Room = {
  slug: string;
  name: string;
  count: number;
};

export default function RoomPage() {
  const { slug } = useParams<{ slug: string }>();
  const [room, setRoom] = useState<Room | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_BASE}/api/space/rooms/${slug}/`, { cache: "no-store" })
      .then(async (res) => {
        if (res.status === 404) {
          if (!cancelled) setNotFound(true);
          return;
        }
        if (!res.ok) return;
        const data: Room = await res.json();
        if (!cancelled) setRoom(data);
      })
      .catch(() => {
        // 部屋名が取れなくてもUnityには入れるので、ここでは何もしない
      });

    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (notFound) {
    return (
      <main style={{ padding: 24, textAlign: "center" }}>
        <p>この部屋は見つかりませんでした。</p>
        <Link href="/room">ロビーへ戻る</Link>
      </main>
    );
  }

  return (
    <main style={{ padding: 16, display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
      <header style={{ width: "100%", maxWidth: 960, display: "flex", alignItems: "center", gap: 16 }}>
        <Link href="/room">← ロビーへ</Link>
        <h1 style={{ fontSize: 20, margin: 0 }}>{room?.name ?? "…"}</h1>
      </header>
      <UnityRoom roomSlug={slug} />
    </main>
  );
}