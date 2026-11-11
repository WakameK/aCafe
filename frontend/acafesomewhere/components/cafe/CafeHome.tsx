"use client";

// 配置先: components/cafe/CafeHome.tsx
// 店内のベース画面。各場所をクリックするとページへ遷移する
// href と位置(%)は仮。cafe_base.jpg(誰もいない店内)基準

import Link from "next/link";
import styles from "./CafeHome.module.css";

const CAFE_IMAGE = "/images/cafe/cafe_base.png"; // 誰もいない店内(4枚目の画像)

const SPOTS = [
  { label: "カウンター", href: "/counter", left: 60, top: 28, width: 38, height: 38 },
  { label: "テーブル", href: "/desk", left: 27, top: 60, width: 42, height: 20 },
  { label: "本棚", href: "/library", left: 49, top: 22, width: 11, height: 28 },
  { label: "奥の部屋", href: "/back-room", left: 36, top: 19, width: 12, height: 32 },
  { label: "看板", href: "/about", left: 0, top: 54, width: 18, height: 40 },
];

export default function CafeHome() {
  return (
    <div className={styles.stage}>
      <div className={styles.viewport}>
        <img src={CAFE_IMAGE} alt="くまの隠れ家店内" className={styles.bg} draggable={false} />

        {SPOTS.map((s) => (
          <Link
            key={s.href}
            href={s.href}
            className={styles.spot}
            style={{
              left: `${s.left}%`,
              top: `${s.top}%`,
              width: `${s.width}%`,
              height: `${s.height}%`,
            }}
            aria-label={s.label}
          >
            <span className={styles.label}>{s.label}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
