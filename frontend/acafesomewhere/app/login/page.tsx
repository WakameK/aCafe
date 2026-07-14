import CafeShell from "../../components/CafeShell";
import styles from "./page.module.css";

export default function LoginPage() {
  return (
    <CafeShell
      title="合言葉"
      description="登録とログインを行います。名前と合言葉を入力してください。"
    >
      <form className={styles.form}>
        <label className={styles.field}>
          <span>名前</span>
          <input type="text" name="name" placeholder="名前" required />
        </label>

        <label className={styles.field}>
          <span>合言葉</span>
          <input type="password" name="login_key" placeholder="合言葉" required />
        </label>

        <div className={styles.actions}>
          <button type="submit">ログイン</button>
          <button type="button" className={styles.secondaryButton}>
            登録/更新
          </button>
        </div>
      </form>
    </CafeShell>
  );
}
