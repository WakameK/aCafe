"use client";

// 配置先: components/entrance/EntranceAnimation.tsx
// 地下街の通路 → 店の前 → ドアが開く → 暖色の光 → オーバーレイごとフェードアウト
// 店内(CafeHome)は最初から下に敷いてあるので、最後は「光が引くと店内」になる

import { useEffect, useRef, useState, type CSSProperties } from "react";
import styles from "./EntranceAnimation.module.css";

// 紙芝居のコマ。ms = そのコマを見せる時間
const FLIP = [
  { src: "/images/entrance/00_corridor.jpg", ms: 500 },
  { src: "/images/entrance/01_approach.jpg", ms: 750 },
  { src: "/images/entrance/02_door.jpg", ms: 750 },
];

// コマの切り替え方
//   "fade"  … 前のコマに次のコマがふわっと重なる(歩いて近づく感じ)
//   "slide" … 紙芝居の紙を横に引き抜くように前のコマが抜ける
const MODE: "fade" | "slide" = "fade";

const CHANGE_MS = 380; // 1回の切り替えにかける時間
const FLASH_MS = 350;  // 暖色の光に包まれる時間
const OUT_MS = 550;    // 光ごとフェードアウトして店内が見える時間

const TOTAL_FLIP_MS = FLIP.reduce((sum, f) => sum + f.ms, 0);

export const ENTERED_KEY = "kuma_entered";

type Phase = "loading" | "idle" | "playing" | "flash" | "out";

type Props = {
  onFinish: () => void;
};

export default function EntranceAnimation({ onFinish }: Props) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [index, setIndex] = useState(0); // 今見せているコマ
  const timers = useRef<number[]>([]);

  // 全コマを先に読み込み＆デコードしておく(切り替え時のチラつき・ガタつき防止)
  useEffect(() => {
    let cancelled = false;
    Promise.all(
      FLIP.map((f) => {
        const img = new Image();
        img.src = f.src;
        return img.decode().catch(() => undefined);
      })
    ).then(() => {
      if (!cancelled) setPhase("idle");
    });

    return () => {
      cancelled = true;
      timers.current.forEach((id) => window.clearTimeout(id));
    };
  }, []);

  const at = (ms: number, fn: () => void) => {
    timers.current.push(window.setTimeout(fn, ms));
  };

  const finish = () => {
    try {
      sessionStorage.setItem(ENTERED_KEY, "1");
    } catch {
      // プライベートモード等で使えなくても動くように
    }
    onFinish();
  };

  const start = () => {
    if (phase !== "idle") return;

    // 「視差効果を減らす」設定の人は紙芝居を省略
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setPhase("flash");
      at(FLASH_MS, () => setPhase("out"));
      at(FLASH_MS + OUT_MS, finish);
      return;
    }

    setPhase("playing");
    let t = 0;
    FLIP.forEach((f, i) => {
      if (i > 0) at(t, () => setIndex(i));
      t += f.ms;
    });
    at(t, () => setPhase("flash"));
    t += FLASH_MS;
    at(t, () => setPhase("out"));
    t += OUT_MS;
    at(t, finish);
  };

  const moving = phase === "playing" || phase === "flash" || phase === "out";
  const lit = phase === "flash" || phase === "out";

  return (
    <div
      className={`${styles.stage} ${phase === "out" ? styles.stageOut : ""}`}
      style={{ "--out": `${OUT_MS}ms` } as CSSProperties}
    >
      <div className={styles.viewport}>
        {/* カメラ: 全コマまとめて一定速度でゆっくり寄る(コマごとにリセットしない) */}
        <div
          className={`${styles.camera} ${moving ? styles.push : ""}`}
          style={{ "--push": `${TOTAL_FLIP_MS + FLASH_MS}ms` } as CSSProperties}
        >
          {FLIP.map((f, i) => {
            const state =
              MODE === "fade"
                ? i <= index
                  ? styles.shown
                  : styles.hidden
                : i < index
                  ? styles.slidOut
                  : "";
            // fade: 後のコマほど上 / slide: 前のコマほど上(上から抜いていく)
            const z = MODE === "fade" ? i : FLIP.length - i;

            return (
              <img
                key={f.src}
                src={f.src}
                alt=""
                draggable={false}
                className={`${styles.frame} ${styles[MODE]} ${state}`}
                style={{ zIndex: z, "--change": `${CHANGE_MS}ms` } as CSSProperties}
              />
            );
          })}
        </div>

        {phase === "idle" && (
          <button
            type="button"
            className={styles.hotspot}
            onClick={start}
            aria-label="くまの隠れ家に入る"
          />
        )}
        {(phase === "idle" || phase === "loading") && (
          <p className={styles.hint}>
            {phase === "loading" ? "読み込み中…" : "灯りのともる店をクリック"}
          </p>
        )}

        <div
          className={`${styles.flash} ${lit ? styles.flashOn : ""}`}
          style={{ "--flash": `${FLASH_MS}ms` } as CSSProperties}
        />
      </div>
    </div>
  );
}
