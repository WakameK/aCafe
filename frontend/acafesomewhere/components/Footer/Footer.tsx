import styles from "./Footer.module.css";

export default function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className={styles.footer}>
      <p>copyright &copy; {year} くまの隠れ家</p>
    </footer>
  );
}
