"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { navLinks } from "@/lib/navLinks";
import styles from "./CafeScene.module.css";

export default function CafeScene() {
  const [hovered, setHovered] = useState<string | null>(null);
  const spots = navLinks.filter((l) => l.spot);

  return (
    <div className={styles.scene}>
      <Image
        src="/images/cafe.png"
        alt="喫茶店の店内"
        fill
        priority
        sizes="(max-width: 1280px) 100vw, 1280px"
        className={styles.bg}
      />

      {/* ビネット：全体を暗くして、中央とクリック対象だけ穴を開けて明るく見せる */}
      <svg
        className={styles.vignette}
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          {/* マスク内では 黒 = 暗幕が消える = 明るく見える */}
          <radialGradient id="cafe-light">
            <stop offset="0%" stopColor="#000" stopOpacity="1" />
            <stop offset="55%" stopColor="#000" stopOpacity="0.75" />
            <stop offset="100%" stopColor="#000" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="cafe-light-soft">
            <stop offset="0%" stopColor="#000" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#000" stopOpacity="0" />
          </radialGradient>

          <mask id="cafe-mask" maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100">
            <rect x="0" y="0" width="100" height="100" fill="#fff" />
            {/* 部屋の中央にうっすら灯り */}
            <ellipse cx="50" cy="50" rx="34" ry="40" fill="url(#cafe-light-soft)" />
            {/* クリックできる場所の灯り */}
            {spots.map(({ href, spot }) => (
              <ellipse
                key={href}
                cx={spot!.x + spot!.w / 2}
                cy={spot!.y + spot!.h / 2}
                rx={spot!.w * 0.85}
                ry={spot!.h * 0.85}
                fill="url(#cafe-light)"
                className={`${styles.light} ${hovered === href ? styles.lightActive : ""}`}
              />
            ))}
          </mask>
        </defs>

        {/* 暗幕本体。濃さは fillOpacity で調整 */}
        <rect
          x="0"
          y="0"
          width="100"
          height="100"
          fill="#0c0704"
          mask="url(#cafe-mask)"
          className={styles.curtain}
        />
      </svg>

      {/* クリック範囲（見た目は透明、ホバーで名前だけ出す） */}
      {spots.map(({ href, label, spot }) => (
        <Link
          key={href}
          href={href}
          aria-label={label}
          className={styles.spot}
          style={{
            left: `${spot!.x}%`,
            top: `${spot!.y}%`,
            width: `${spot!.w}%`,
            height: `${spot!.h}%`,
          }}
          onMouseEnter={() => setHovered(href)}
          onMouseLeave={() => setHovered(null)}
          onFocus={() => setHovered(href)}
          onBlur={() => setHovered(null)}
        >
          <span className={styles.label}>{label}</span>
        </Link>
      ))}
    </div>
  );
}
