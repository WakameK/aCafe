import Image from "next/image";
import Header from "../components/Header/Header";
import Footer from "../components/Footer/Footer";
import styles from "./page.module.css";

export default function Home() {
  return (
    <div className={styles.page}>
      <Header />
      <main className={styles.main}>
        <section className={styles.intro}>
          <p className={styles.kicker}>WELCOME HOME</p>
          <h2>灯りの向こうに、<br />あなたの席があります。</h2>
          <p className={styles.description}>
            静かな音楽とコーヒーの香りが漂う、くまの隠れ家へようこそ。
            店内を眺めながら、気になる場所を選んでください。
          </p>
        </section>

        <section className={styles.cafeMap} aria-label="店内案内">
          <Image
            src="/images/Cafe.png"
            alt="暖かな灯りに包まれた、くまの隠れ家の店内"
            fill
            priority
            sizes="(max-width: 700px) calc(100vw - 32px), 1200px"
            className={styles.cafeImage}
          />

          <a href="/chat" className={`${styles.hotspot} ${styles.counter}`} aria-label="カウンターでマスターと話す">
            <span>マスターと話す</span>
          </a>

          <a href="/desk" className={`${styles.hotspot} ${styles.tableLeft}`} aria-label="窓辺の席で誰かと話す">
            <span>窓辺の席</span>
          </a>

          <a href="/desk" className={`${styles.hotspot} ${styles.tableCenter}`} aria-label="中央のテーブルで誰かと話す">
            <span>中央の席</span>
          </a>

          <a href="/profile" className={`${styles.hotspot} ${styles.tableRight}`} aria-label="奥の席で自分のことを整理する">
            <span>奥の席</span>
          </a>

          <a href="/about" className={`${styles.hotspot} ${styles.entranceBoard}`} aria-label="入口の黒板を見る">
            <span>この店について</span>
          </a>

          <a href="/atelier" className={`${styles.hotspot} ${styles.backDoor}`} aria-label="奥のアトリエへ行く">
            <span>アトリエ</span>
          </a>
        </section>
      </main>
      <Footer />
    </div>
  );
}
