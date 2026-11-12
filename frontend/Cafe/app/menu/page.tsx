import CafeShell from "../../components/CafeShell";
import styles from "./page.module.css";

export default function MenuPage() {
  return (
    <CafeShell title="メニュー" description="店内のおすすめメニューを紹介します。">
      <div className={styles.card}>
        <p>本日のおすすめコーヒー、焼き菓子、和の茶席を用意しています。</p>
        <p>静かな空間でゆっくりと過ごせるよう、程よい選択肢を用意しました。</p>
      </div>
    </CafeShell>
  );
}
