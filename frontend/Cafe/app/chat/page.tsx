import CafeShell from "../../components/CafeShell";
import ChatClient from "./ChatClient";

export default function ChatPage() {
  return (
    <CafeShell title="カフェのマスターと話す" description="マスターに話しかけてください。">
      <ChatClient />
    </CafeShell>
  );
}
