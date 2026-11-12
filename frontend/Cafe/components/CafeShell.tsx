import type { ReactNode } from "react";
import Link from "next/link";
import styles from "./CafeShell.module.css";

type CafeShellProps = {
  title: string;
  description?: string;
  children: ReactNode;
};

export default function CafeShell({ title, description, children }: CafeShellProps) {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>
          <Link href="/">『くまの隠れ家』</Link>
        </h1>
        <nav aria-label="サイトナビゲーション">
          <ul>
            <li>
              <Link href="/login">合言葉(登録とログイン)</Link>
            </li>
            <li>
              <Link href="/profile">あなたの事</Link>
            </li>
            <li>
              <Link href="/chat">カフェのマスターと話す</Link>
            </li>
            <li>
              <Link href="/atelier">女性のアトリエ</Link>
            </li>
            <li>
              <Link href="/desk">誰かと話す</Link>
            </li>
          </ul>
        </nav>
      </header>

      <main className={styles.main}>
        <section className={styles.panel}>
          <h2>{title}</h2>
          {description ? <p className={styles.description}>{description}</p> : null}
          {children}
        </section>
      </main>

      <footer className={styles.footer}>
        <p>© {new Date().getFullYear()} くまの隠れ家</p>
      </footer>
    </div>
  );
}
