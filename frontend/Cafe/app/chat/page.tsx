import CafeShell from "../../components/CafeShell";
import styles from "./page.module.css";

const initialMessages = [
  { role: "bot", content: "マスターが黙々と作業している…」" },
];

export default function ChatPage() {
  return (
    <CafeShell title="カフェのマスターと話す" description="マスターに話しかけてください。">
      <div className={styles.chatContainer}>
        <div className={styles.chatHeader}>
          <h3>☕ カフェのカウンター</h3>
          <p>マスターが黙々と作業している...</p>
        </div>

        <div className={styles.chatBox}>
          {initialMessages.map((message, index) => (
            <div
              key={`${message.role}-${index}`}
              className={`${styles.chatMessage} ${message.role === "user" ? styles.user : styles.bot}`}
            >
              <div className={message.role === "user" ? styles.userBubble : styles.botBubble}>
                {message.content}
              </div>
            </div>
          ))}
        </div>

        <div className={styles.chatInputArea}>
          <input type="text" placeholder="マスターに話しかける..." />
          <button type="button">送信</button>
        </div>
      </div>
    </CafeShell>
  );
}
