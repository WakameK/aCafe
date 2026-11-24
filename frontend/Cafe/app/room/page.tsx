"use client";

import dynamic from "next/dynamic";

// Unity はブラウザ専用なので、サーバー側では描画しない
const UnityRoom = dynamic(() => import("@/components/UnityRoom"), {
  ssr: false,
});

export default function RoomPage() {
  return (
    <main style={{ padding: 16, display: "flex", justifyContent: "center" }}>
      <UnityRoom />
    </main>
  );
}
