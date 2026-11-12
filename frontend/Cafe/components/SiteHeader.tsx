"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navLinks } from "@/lib/navLinks";
import styles from "./SiteHeader.module.css";

export default function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className={styles.header}>
      <Link href="/" className={styles.logo}>
        くまの隠れ家
      </Link>

      <nav aria-label="メインメニュー">
        <ul className={styles.nav}>
          {navLinks.map(({ href, label }) => (
            <li key={href}>
              <Link
                href={href}
                className={styles.link}
                aria-current={pathname === href ? "page" : undefined}
              >
                {label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
