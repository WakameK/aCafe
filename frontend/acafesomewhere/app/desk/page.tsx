import CafeShell from "../../components/CafeShell";
import styles from "./page.module.css";

export default function DeskPage() {
  return (
    <CafeShell title="誰かと話す" description="席に座って誰かと会話できます。">
      <div className={styles.card}>
        <p>ここでは席に座って、他の参加者と会話できます。</p>
      </div>
    </CafeShell>
  );
}
