import type { ReactNode } from "react";
import styles from "./CafeShell.module.css";

type CafeShellProps = {
  title: string;
  description?: string;
  children: ReactNode;
};

export default function CafeShell({ title, description, children }: CafeShellProps) {
  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <section className={styles.panel}>
          <h2>{title}</h2>
          {description ? <p className={styles.description}>{description}</p> : null}
          {children}
        </section>
      </main>
    </div>
  );
}
