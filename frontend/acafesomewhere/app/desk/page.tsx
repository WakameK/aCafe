import CafeShell from "../../components/CafeShell";
import DeskClient from "./DeskClient";

export default function DeskPage() {
  return (
    <CafeShell title="誰かと話す" description="席に座って誰かと会話できます。">
      <DeskClient />
    </CafeShell>
  );
}
