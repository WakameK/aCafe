import Link from "next/link";
import { navLinks } from "@/lib/navLinks";
import styles from "./SiteFooter.module.css";

export default function SiteFooter() {
  return (
    <footer className={styles.footer}>
      <nav aria-label="フッターメニュー">
        <ul className={styles.links}>
          {navLinks.map(({ href, label }) => (
            <li key={href}>
              <Link href={href}>{label}</Link>
            </li>
          ))}
        </ul>
      </nav>

      <p className={styles.note}>
        つらさが強いときは、ひとりで抱えずに専門の窓口も頼ってください。
        <a
          href="https://www.mhlw.go.jp/mamorouyokokoro/"
          target="_blank"
          rel="noopener noreferrer"
        >
          相談窓口の一覧（厚生労働省）
        </a>
      </p>

      <p className={styles.copy}>© {new Date().getFullYear()} くまの隠れ家</p>
    </footer>
  );
}
