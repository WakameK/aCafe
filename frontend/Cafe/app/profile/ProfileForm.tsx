"use client";

import { useEffect, useState } from "react";
import { MAX_DISPLAY_NAME, loadDisplayName, saveDisplayName } from "@/lib/displayName";
import styles from "./page.module.css";

export default function ProfileForm() {
  const [name, setName] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    // localStorage はブラウザでしか読めないので、描画のあとで取り出す
    const saved = loadDisplayName();
    queueMicrotask(() => setName(saved || "くま"));
  }, []);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const ok = name.trim() !== "" && saveDisplayName(name);
    setMessage(ok ? "名前を更新しました。焚火に入るときから、この名前で表示されます。" : "名前を保存できませんでした。");
  };

  return (
    <form className={styles.form} onSubmit={submit}>
      <label className={styles.field}>
        <span>あなたの名前</span>
        <input
          type="text"
          value={name}
          maxLength={MAX_DISPLAY_NAME}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <button type="submit">更新</button>
      {message && <p role="status">{message}</p>}
    </form>
  );
}
