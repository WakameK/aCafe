"use client";

import dynamic from "next/dynamic";

// Unity はブラウザ専用なので、サーバー側では描画しない
const SandplayEmbed = dynamic(() => import("@/components/SandplayEmbed"), {
  ssr: false,
});

export default function SandplayPage() {
  return (
    <main style={{ padding: 16 }}>
      <SandplayEmbed
        onSubmit={(payload) => console.log("作品を受け取りました", payload)}
      />
    </main>
  );
}