import Link from "next/link";
import styles from "./Header.module.css";

export default function Footer() {
  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <p className={styles.eyebrow}>A QUIET PLACE TO REST</p>
        <h1 className={styles.title}>
          <Link href="/">くまの隠れ家</Link>
        </h1>
        <nav className={styles.nav} aria-label="サイトナビゲーション">
          <ul>
            <li><Link href="/">店内を見る</Link></li>
            <li><Link href="/about">この店について</Link></li>
            <li><Link href="/chat">マスターと話す</Link></li>
            <li><Link href="/atelier">アトリエ</Link></li>
            <li><Link href="/login">合言葉</Link></li>
          </ul>
        </nav>
      </div>
    </header>
  );
}
