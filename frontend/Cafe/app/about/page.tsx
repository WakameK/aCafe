import CafeShell from "../../components/CafeShell";
import styles from "./page.module.css";

export default function AboutPage() {
  return (
    <CafeShell
      title="この店について"
      description="くまの隠れ家の世界観と、各スペースの役割をご紹介します。"
    >
      <div className={styles.card}>
        <p>ここは静かな喫茶店のような空間で、各種の会話や体験が楽しめます。</p>
        <p>ログイン、プロフィール、アトリエ、対話のスペースがそれぞれ役割を持っています。</p>
      </div>
    </CafeShell>
  );
}
