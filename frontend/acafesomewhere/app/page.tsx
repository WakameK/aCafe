"use client";

// 配置先: app/page.tsx(トップページ)
// 店内(CafeHome)を常に下に敷き、入場アニメーションはその上に被せるだけ
// 同じタブで2回目以降(sessionStorage にフラグあり)はアニメなし

import { useState, useSyncExternalStore } from "react";
import EntranceAnimation, { ENTERED_KEY } from "@/components/entrance/EntranceAnimation";
import CafeHome from "@/components/cafe/CafeHome";

// sessionStorage は変更通知がないので購読は何もしない
const subscribe = () => () => {};

// ブラウザ側: sessionStorage から入場済みかを読む
const getEnteredSnapshot = (): boolean | null => {
  try {
    return sessionStorage.getItem(ENTERED_KEY) === "1";
  } catch {
    return false; // 使えない環境では毎回アニメーション
  }
};

// サーバー側: まだ分からないので null
const getServerSnapshot = (): boolean | null => null;

export default function Home() {
  // effect 内で setState せずに sessionStorage を読める(ハイドレーションのズレも出ない)
  const storedEntered = useSyncExternalStore(subscribe, getEnteredSnapshot, getServerSnapshot);

  // 今回アニメを見終わったかどうか(クリックの流れで更新するだけなので effect 不要)
  const [justEntered, setJustEntered] = useState(false);

  if (storedEntered === null) {
    return <div style={{ position: "fixed", inset: 0, background: "#0b0806" }} />;
  }

  const entered = storedEntered || justEntered;

  return (
    <>
      <CafeHome />
      {!entered && <EntranceAnimation onFinish={() => setJustEntered(true)} />}
    </>
  );
}