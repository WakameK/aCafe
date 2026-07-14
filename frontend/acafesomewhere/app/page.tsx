import styles from './page.module.css';

export default function Home() {
  return (
    <main className={styles.container}>
      <h1 className={styles.title}>喫茶くまの隠れ家へようこそ</h1>

      <div className={styles.card}>
        <p>本日のおすすめコーヒーをご紹介します。</p>
      </div>
    </main>
  );
}
