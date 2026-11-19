import CafeShell from "../../components/CafeShell";
import ProfileForm from "./ProfileForm";
import styles from "./page.module.css";

export default function ProfilePage() {
  return (
    <CafeShell
      title="あなたの情報"
      description="オーナーとの会話履歴、情報提供書、持ち帰った作品を見返せます。"
    >
      <ProfileForm />

      <section className={styles.section}>
        <h3>会話履歴</h3>
        <button type="button" className={styles.secondaryButton}>
          チャット履歴をダウンロード
        </button>
      </section>
    </CafeShell>
  );
}
