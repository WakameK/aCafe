"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { navLinks } from "@/lib/navLinks";
import styles from "./SiteHeader.module.css";

// ロゴとメニューの間のすき間(CSS の .header の gap と合わせる)
const GAP = 24;

export default function SiteHeader() {
  const pathname = usePathname();
  const headerRef = useRef<HTMLElement>(null);
  const logoRef = useRef<HTMLAnchorElement>(null);
  const measureRef = useRef<HTMLUListElement>(null);

  // メニューが横に収まらないときは true(ハンバーガー表示)
  const [collapsed, setCollapsed] = useState(false);
  // ハンバーガーメニューが開いているか
  const [open, setOpen] = useState(false);

  // 見えない計測用リストの幅で、ヘッダーに収まるかを判定する
  useLayoutEffect(() => {
    const header = headerRef.current;
    const logo = logoRef.current;
    const measure = measureRef.current;
    if (!header || !logo || !measure) return;

    const check = () => {
      const style = getComputedStyle(header);
      const inner =
        header.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      const needed = logo.offsetWidth + GAP + measure.scrollWidth;
      const next = needed > inner;
      setCollapsed(next);
      if (!next) setOpen(false);
    };

    check();
    const observer = new ResizeObserver(check);
    observer.observe(header);
    observer.observe(measure);
    return () => observer.disconnect();
  }, []);

  // Esc キーで閉じる
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const links = navLinks.map(({ href, label }) => (
    <li key={href}>
      <Link
        href={href}
        className={styles.link}
        aria-current={pathname === href ? "page" : undefined}
        onClick={() => setOpen(false)}
      >
        {label}
      </Link>
    </li>
  ));

  return (
    <header ref={headerRef} className={styles.header}>
      <Link ref={logoRef} href="/" className={styles.logo} onClick={() => setOpen(false)}>
        くまの隠れ家
      </Link>

      {/* 幅を測るためだけの見えないリスト */}
      <div className={styles.measureBox} aria-hidden="true">
        <ul ref={measureRef} className={`${styles.nav} ${styles.measure}`}>
          {navLinks.map(({ href, label }) => (
            <li key={href}>
              <span className={styles.link}>{label}</span>
            </li>
          ))}
        </ul>
      </div>

      {collapsed ? (
        <>
          <button
            type="button"
            className={styles.burger}
            aria-label={open ? "メニューを閉じる" : "メニューを開く"}
            aria-expanded={open}
            aria-controls="site-menu"
            onClick={() => setOpen((v) => !v)}
          >
            <span className={`${styles.bars} ${open ? styles.barsOpen : ""}`} />
          </button>

          {open ? (
            <>
              <div className={styles.backdrop} onClick={() => setOpen(false)} />
              <nav id="site-menu" aria-label="メインメニュー" className={styles.drawer}>
                <ul className={styles.drawerList}>{links}</ul>
              </nav>
            </>
          ) : null}
        </>
      ) : (
        <nav aria-label="メインメニュー">
          <ul className={styles.nav}>{links}</ul>
        </nav>
      )}
    </header>
  );
}
